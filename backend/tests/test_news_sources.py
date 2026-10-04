"""news_sources (pure rules) + the GNews ingest path in server.py against a
fake GNews and an in-memory Mongo.

    fetch_from_gnews ─▶ budget ─▶ since-window ─▶ page 2 only when full ─▶ admit ─▶ build
    ingest cycle ─▶ upsert (labels NOT overwritten) ─▶ tagger marks Developing
    switch-over ─▶ NewsAPI items re-dated once; no age-based Breaking
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

import news_sources as N

NOW = datetime.now(timezone.utc)
KW = ["india", "modi", "delhi", "rbi"]


# ── pure rules ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url,cat,title,ok,why", [
    ("https://timesofindia.indiatimes.com/x", "general", "Anything at all", True, "trusted_indian"),
    ("https://www.thehindu.com/a", "world", "Gaza ceasefire talks", True, "trusted_indian"),
    ("https://www.bbc.com/news/x", "world", "Gaza ceasefire talks", True, "trusted_international"),
    ("https://www.bbc.com/sport/x", "sports", "Arsenal beat Spurs", False, "off_topic"),
    ("https://www.bbc.com/news/x", "sports", "India beat Pakistan", True, "india_relevant"),
    ("https://finance.biggo.com/x", "general", "India deals today", False, "blocked"),
    ("https://en.softonic.com/x", "technology", "Download Modi app", False, "blocked"),
    ("https://randomblog.example/x", "general", "Weather in Paris", False, "off_topic"),
    ("https://randomblog.example/x", "general", "RBI holds rates", True, "india_relevant"),
    ("not a url", "general", "India", False, "blocked"),
])
def test_admit(url, cat, title, ok, why):
    assert N.admit(url, title, "", cat, KW) == (ok, why)


def test_india_relevance_is_word_boundary():
    # The old substring check matched "ed" in "updated", "ott" in "Scott"...
    assert not N.india_relevant("Scott updated the report", ["ed", "ott"])
    assert N.india_relevant("Modi's speech", ["modi"])


def test_subdomains_count_as_their_publisher():
    assert N.admit("https://sportstar.thehindu.com/x", "sports", "Arsenal", "", KW)[0]


def test_provider_delay():
    assert N.provider_delay_h("gnews", True, 24) == 0
    assert N.provider_delay_h("newsapi", False, 24) == 24   # only source: rank by arrival
    assert N.provider_delay_h("newsapi", True, 24) == 0     # GNews live: real age


def test_since_window():
    assert N.gnews_since(None, NOW) == NOW - timedelta(hours=24)
    last = NOW - timedelta(minutes=20)
    assert N.gnews_since(last, NOW) == last - timedelta(minutes=5)
    assert N.gnews_since(NOW - timedelta(days=3), NOW) == NOW - timedelta(hours=24)


def test_summarize_quota_keeps_hourly_spend():
    assert N.summarize_quota(30, 20) == 10 and N.summarize_quota(30, 60) == 30


def test_build_article_has_no_age_labels():
    a = N.build_article(url="https://www.thehindu.com/x", title="T", description="D", raw_content="C c c",
                        source_name="The Hindu", published_at=NOW.isoformat(), image_url=None, author=None,
                        provider="gnews", rank_at=NOW.isoformat(),
                        detect_category=lambda t, b: ("Politics", None), default_image="https://img/default")
    assert a["is_breaking"] is False and a["is_developing"] is False
    assert a["provider"] == "gnews" and a["image_url"] == "https://img/default"
    assert a["article_id"] == N.article_id_for("https://www.thehindu.com/x")


# ── server integration ──────────────────────────────────────────────────────

mongomock_motor = pytest.importorskip("mongomock_motor")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "t")
os.environ.setdefault("JWT_SECRET", "t")
server = pytest.importorskip("server")


def g(url, title, minutes_ago=10, source="The Hindu", image="https://img/x.jpg"):
    return {"title": title, "description": f"{title} description", "content": f"{title} body " * 40,
            "url": url, "image": image, "publishedAt": (NOW - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": {"name": source, "url": "https://" + url.split("/")[2]}}


class Resp:
    def __init__(self, status, data=None, text=""):
        self.status_code, self._data, self.text = status, data, text

    def json(self):
        return self._data


class FakeGNews:
    """Returns a scripted response per (endpoint, category/q, page)."""

    def __init__(self, script=None, default=None):
        self.script = script or {}
        self.default = default if default is not None else []
        self.calls = []

    async def get(self, url, params=None):
        ep = url.rsplit("/", 1)[1]
        key = (ep, params.get("category") or params.get("q"), params.get("page"))
        self.calls.append((key, dict(params)))
        r = self.script.get(key)
        if isinstance(r, Resp):
            return r
        return Resp(200, {"totalArticles": 0, "articles": r if r is not None else self.default})

    async def aclose(self):
        pass


@pytest.fixture
def db(monkeypatch):
    d = mongomock_motor.AsyncMongoMockClient()["t"]
    monkeypatch.setattr(server, "db", d)
    monkeypatch.setattr(server, "GNEWS_KEY", "test-key")
    monkeypatch.setattr(server, "GNEWS_DAILY_CAP", 900)
    return d


async def test_fetch_maps_filters_and_dedupes(db):
    fake = FakeGNews({
        ("top-headlines", "nation", 1): [g("https://www.thehindu.com/a", "Parliament session opens"),
                                         g("https://finance.biggo.com/b", "India deals today")],
        ("top-headlines", "world", 1): [g("https://www.bbc.com/news/c", "Gaza ceasefire", source="BBC"),
                                        g("https://www.thehindu.com/a", "Parliament session opens")],
        ("top-headlines", "sports", 1): [g("https://www.bbc.com/sport/d", "Arsenal beat Spurs", source="BBC")],
    })
    arts = await server.fetch_from_gnews(client=fake)
    urls = {a["url"] for a in arts}
    assert urls == {"https://www.thehindu.com/a", "https://www.bbc.com/news/c"}
    a = next(x for x in arts if x["url"].endswith("/a"))
    assert a["provider"] == "gnews" and a["is_breaking"] is False
    assert a["rank_at"].startswith(a["published_at"][:16]) or a["rank_at"] == a["published_at"]
    # first run: 6 searches + the 9 headline categories (due), one page each
    assert len(fake.calls) == 15
    assert [c[0][0] for c in fake.calls[:6]] == ["search"] * 6
    assert all(c[1]["country"] == "in" and c[1]["lang"] == "en" and c[1]["max"] == 25 for c in fake.calls)
    assert all("apikey" in c[1] for c in fake.calls)


async def test_second_page_only_when_first_is_full(db):
    full = [g(f"https://www.thehindu.com/p{i}", f"Story {i}") for i in range(25)]
    fake = FakeGNews({("top-headlines", "general", 1): full,
                      ("top-headlines", "general", 2): [g("https://www.thehindu.com/extra", "Extra")]})
    arts = await server.fetch_from_gnews(client=fake)
    pages = [k for k, _ in fake.calls if k[1] == "general"]
    assert pages == [("top-headlines", "general", 1), ("top-headlines", "general", 2)]
    assert len(arts) == 26


async def test_since_window_advances_after_success(db):
    fake = FakeGNews(default=[])
    await server.fetch_from_gnews(client=fake)
    first_from = fake.calls[0][1]["from"]
    state = await db.app_meta.find_one({"_id": "gnews_state"})
    assert state and state["last_success"]
    fake2 = FakeGNews(default=[])
    await server.fetch_from_gnews(client=fake2)
    assert fake2.calls[0][1]["from"] > first_from


async def test_daily_budget_stops_requests(db, monkeypatch):
    monkeypatch.setattr(server, "GNEWS_DAILY_CAP", 3)
    fake = FakeGNews(default=[])
    await server.fetch_from_gnews(client=fake)
    assert len(fake.calls) == 3
    fake2 = FakeGNews(default=[])
    await server.fetch_from_gnews(client=fake2)
    assert fake2.calls == []


async def test_rejected_key_stops_the_run_and_keeps_last_success(db):
    fake = FakeGNews({("search", "India", 1): Resp(401, None, "invalid key")})
    assert await server.fetch_from_gnews(client=fake) == []
    assert len(fake.calls) == 1
    state = await db.app_meta.find_one({"_id": "gnews_state"})
    assert not state.get("last_success") and state["last_error"].startswith("401")
    assert "test-key" not in state["last_error"]


async def test_no_key_no_requests(db, monkeypatch):
    monkeypatch.setattr(server, "GNEWS_KEY", "")
    fake = FakeGNews(default=[g("https://www.thehindu.com/a", "x")])
    assert await server.fetch_from_gnews(client=fake) == [] and fake.calls == []


async def test_cycle_upsert_keeps_labels_and_tagger_marks_developing(db, monkeypatch):
    art = g("https://www.thehindu.com/a", "Monsoon session of Parliament opens in Delhi")
    fake = FakeGNews({("top-headlines", "nation", 1): [art]})

    real_fetch = server.fetch_from_gnews

    async def fetch():
        return await real_fetch(client=fake)
    monkeypatch.setattr(server, "fetch_from_gnews", fetch)
    monkeypatch.setattr(server, "ANTHROPIC_API_KEY", "")

    async def yes_judge(system="", user_content="", **k):       # story_members confirms the candidate
        n = sum(1 for line in user_content.splitlines() if line[:1].isdigit() and ": " in line)
        return '{"same": %s}' % list(range(n))
    monkeypatch.setattr(server, "_llm", yes_judge)

    async def nothing(*a, **k):
        return None
    for fn in ("_sync_scheduled_events", "_sync_wave_topics", "_sync_calendar_events",
               "_detect_developing_stories", "_expire_scout_stories", "_close_quiet_desk_stories"):
        if hasattr(server, fn):
            monkeypatch.setattr(server, fn, nothing)
    await db.developing_stories.insert_one({"story_id": "parl", "is_active": True, "kind": "scheduled",
                                            "keywords": ["parliament"], "article_ids": []})
    await server._run_ingest_cycle_body(run_newsapi=False, summarize_limit=10)
    aid = N.article_id_for("https://www.thehindu.com/a")
    stored = await db.articles.find_one({"article_id": aid})
    assert stored["provider"] == "gnews" and stored["is_developing"] is True and stored["is_breaking"] is False
    # a refetch must not reset the tagger's label while the story is live
    await server._run_ingest_cycle_body(run_newsapi=False, summarize_limit=10)
    assert (await db.articles.find_one({"article_id": aid}))["is_developing"] is True
    # ...and the label goes when the story closes
    await db.developing_stories.update_one({"story_id": "parl"}, {"$set": {"is_active": False}})
    await server._run_ingest_cycle_body(run_newsapi=False, summarize_limit=10)
    assert (await db.articles.find_one({"article_id": aid}))["is_developing"] is False
    assert (await db.app_meta.find_one({"_id": "ingest_state"}))["last_run"]


async def test_switch_over_redates_newsapi_once(db):
    pub = (NOW - timedelta(hours=20)).isoformat()
    await db.articles.insert_many([
        {"article_id": "old1", "published_at": pub, "rank_at": (NOW + timedelta(hours=4)).isoformat(),
         "is_breaking": True},
        {"article_id": "desk1", "origin": "desk", "published_at": pub, "rank_at": pub, "is_breaking": True},
    ])
    await server._redate_newsapi_for_gnews()
    old = await db.articles.find_one({"article_id": "old1"})
    assert old["rank_at"] == pub and old["is_breaking"] is False
    assert (await db.articles.find_one({"article_id": "desk1"}))["is_breaking"] is True   # Desk untouched
    await db.articles.update_one({"article_id": "old1"}, {"$set": {"rank_at": "x"}})
    await server._redate_newsapi_for_gnews()                                               # runs once only
    assert (await db.articles.find_one({"article_id": "old1"}))["rank_at"] == "x"


async def test_restart_spacing(db):
    assert await server._ran_recently(15) is False
    await db.app_meta.insert_one({"_id": "ingest_state", "last_run": NOW.isoformat()})
    assert await server._ran_recently(15) is True
    await db.app_meta.update_one({"_id": "ingest_state"},
                                 {"$set": {"last_run": (NOW - timedelta(minutes=30)).isoformat()}})
    assert await server._ran_recently(15) is False


def test_query_key_is_mongo_safe():
    assert N.query_key("top-headlines", {"category": "nation"}) == "top-headlines~nation"
    assert N.query_key("search", {"q": "Tamil Nadu OR Kerala"}) == "search~Tamil_Nadu_OR_Kerala"
    assert "." not in N.query_key("search", {"q": "a.b$c"})


async def test_yield_counts_new_admitted_per_query(db):
    await db.articles.insert_one({"article_id": N.article_id_for("https://www.thehindu.com/old"), "url": "x"})
    fake = FakeGNews({
        ("top-headlines", "nation", 1): [g("https://www.thehindu.com/old", "Parliament old story"),
                                         g("https://www.thehindu.com/new", "Parliament new story")],
        ("top-headlines", "world", 1): [g("https://www.thehindu.com/new", "Parliament new story")],
    })
    await server.fetch_from_gnews(client=fake)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    y = (await db.app_meta.find_one({"_id": f"gnews_yield:{day}"}))["q"]
    assert y["top-headlines~nation"] == {"requests": 1, "returned": 2, "new": 1}
    assert y["top-headlines~world"] == {"requests": 1, "returned": 1, "new": 0}   # first query gets the credit


async def test_headlines_only_every_few_hours_searches_every_run(db):
    await server.fetch_from_gnews(client=FakeGNews(default=[]))      # first run: headlines due
    fake2 = FakeGNews(default=[])
    await server.fetch_from_gnews(client=fake2)                       # 20 min later: searches only
    assert {c[0][0] for c in fake2.calls} == {"search"}
    assert len(fake2.calls) == len(N.GNEWS_SEARCHES)


def test_gnews_plan_windows():
    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
    since = now - timedelta(minutes=20)
    plan, due = N.gnews_plan(now, since, now - timedelta(minutes=30))
    assert not due and all(e == "search" and x["from"] == N.iso_z(since) for e, x, _ in plan)
    plan, due = N.gnews_plan(now, since, now - timedelta(hours=4))
    hl = [x for e, x, _ in plan if e == "top-headlines"]
    assert due and len(hl) == 9 and hl[0]["from"] == N.iso_z(now - timedelta(hours=6))
    cats = {q: c for q, c in N.GNEWS_SEARCHES}
    assert cats["India"] is None and set(cats.values()) - {None} <= set(N.GNEWS_CATEGORIES)

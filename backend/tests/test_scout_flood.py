"""The 2026-10-03 Developing flood: scout stories keyed on every title word
("india", "live"...), one hit tagged an article and renewed the story, so 254 of
275 fresh stories wore the Developing label and 114 stories stayed open.

    scout keywords ─▶ distinctive words only (no india / live / vs / wins)
    tagging        ─▶ 2 hits for scout, like auto/wave/desk
    re-flag        ─▶ joins the open story for the same event
    cleanup (once) ─▶ retire stale scouts, re-key, merge duplicates, spare boosts
    labels         ─▶ is_developing == member of a live story
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "t")
os.environ.setdefault("JWT_SECRET", "t")
server = pytest.importorskip("server")
import story_members  # noqa: E402

NOW = datetime.now(timezone.utc)


def ago(h):
    return (NOW - timedelta(hours=h)).isoformat()


@pytest.fixture
def db(monkeypatch):
    d = mongomock_motor.AsyncMongoMockClient()["t"]
    monkeypatch.setattr(server, "db", d)
    return d


# ── pure rules ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("title,expected", [
    ("India vs Zimbabwe 3rd T20I live", ["zimbabwe"]),     # one word: can't tag on its own
    ("Education Minister Pradhan Resigns After Exam Scandal", ["education", "pradhan", "resigns", "exam", "scandal"]),
    ("India wins first CWG bronze medal", ["bronze", "medal"]),
    ("Air India flight returns mid-air", ["flight", "returns", "mid-air"]),
])
def test_scout_keywords_drop_generic_words(title, expected):
    assert server._scout_keywords(title) == expected


def test_india_is_never_a_scout_keyword():
    assert "india" not in server._scout_keywords("India India India crushes Pakistan in Asia Cup")


def test_same_event_needs_two_shared_words():
    a = server._scout_keywords("Education Minister Pradhan Resigns After Exam Scandal")
    assert server._same_scout_story(a, server._scout_keywords("Dharmendra Pradhan resigns from position"))
    assert not server._same_scout_story(a, server._scout_keywords("Pradhan visits Odisha"))


# ── tagging ─────────────────────────────────────────────────────────────────

async def yes_judge(system="", user_content="", **k):
    """story_members' check, answering "same story" for every report shown."""
    n = sum(1 for line in user_content.splitlines() if line[:1].isdigit() and ": " in line)
    return '{"same": %s}' % list(range(n))


async def _tag(db, monkeypatch, articles):
    """Run only the tagging + label steps of an ingest cycle over `articles`."""
    async def nothing(*a, **k):
        return None
    for fn in ("_sync_scheduled_events", "_sync_wave_topics", "_sync_calendar_events",
               "_detect_developing_stories", "_expire_scout_stories", "_close_quiet_desk_stories",
               "_scout_developing_candidates"):
        monkeypatch.setattr(server, fn, nothing)

    async def fetch():
        return articles
    monkeypatch.setattr(server, "fetch_from_gnews", fetch)
    monkeypatch.setattr(server, "GNEWS_KEY", "test-key")
    monkeypatch.setattr(server, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(server, "_llm", yes_judge)        # the member check confirms every candidate
    await db.app_meta.insert_one({"_id": "scout_cleanup_v2", "at": NOW.isoformat()})
    await server._run_ingest_cycle_body(run_newsapi=False, summarize_limit=0)


def art(aid, title):
    return {"article_id": aid, "url": f"https://www.thehindu.com/{aid}", "title": title,
            "description": "", "content": title, "published_at": NOW.isoformat(), "rank_at": NOW.isoformat(),
            "category": "Politics", "source": "The Hindu", "is_developing": False, "is_breaking": False}


async def test_one_shared_word_no_longer_tags(db, monkeypatch):
    await db.developing_stories.insert_one({
        "story_id": "scout-pradhan", "kind": "scout", "is_active": True, "detected_at": ago(1),
        "title": "Pradhan resigns after exam scandal",
        "keywords": server._scout_keywords("Pradhan resigns after exam scandal"), "article_ids": []})
    await _tag(db, monkeypatch, [art("a1", "India beat Pakistan in exam-week thriller"),
                                 art("a2", "Pradhan resigns as exam row deepens")])
    s = await db.developing_stories.find_one({"story_id": "scout-pradhan"})
    assert s["article_ids"] == ["a2"]
    assert (await db.articles.find_one({"article_id": "a1"}))["is_developing"] is False
    assert (await db.articles.find_one({"article_id": "a2"}))["is_developing"] is True


async def test_scout_with_one_keyword_never_tags(db, monkeypatch):
    await db.developing_stories.insert_one({
        "story_id": "scout-x", "kind": "scout", "is_active": True, "detected_at": ago(1),
        "title": "India vs Pakistan live", "keywords": ["pakistan"], "article_ids": []})
    await _tag(db, monkeypatch, [art("a1", "Pakistan PM speaks at UN")])
    assert (await db.developing_stories.find_one({"story_id": "scout-x"}))["article_ids"] == []


# ── re-flag joins the open story ────────────────────────────────────────────

async def test_scout_reflag_joins_the_open_story(db, monkeypatch):
    await db.developing_stories.insert_one({
        "story_id": "scout-education-minister-pradhan-resigns", "kind": "scout", "is_active": True,
        "detected_at": ago(1), "title": "Education Minister Pradhan Resigns",
        "keywords": server._scout_keywords("Education Minister Pradhan Resigns"), "article_ids": ["a0"]})
    monkeypatch.setattr(server, "ANTHROPIC_API_KEY", "k")

    async def fake_llm(**k):
        return '{"flagged": [{"index": 0, "title": "Dharmendra Pradhan resigns from position", "theme": "politics"}]}'
    monkeypatch.setattr(server, "_llm", fake_llm)
    await server._scout_developing_candidates([art("a9", "Pradhan quits")])
    stories = await db.developing_stories.find({"kind": "scout"}).to_list(10)
    # It joins the open story as a candidate; the member check then confirms it.
    assert len(stories) == 1 and stories[0]["pending_ids"] == ["a9"] and stories[0]["article_ids"] == ["a0"]
    await db.articles.insert_many([art("a0", "Education Minister Pradhan Resigns"), art("a9", "Pradhan quits")])
    await story_members.verify_members(db, yes_judge, NOW)
    s = await db.developing_stories.find_one({"kind": "scout"})
    assert set(s["article_ids"]) == {"a0", "a9"} and s["pending_ids"] == []


# ── one-time cleanup ────────────────────────────────────────────────────────

async def test_cleanup_retires_stale_rekeys_merges_and_spares_boosts(db):
    await db.articles.insert_many([
        art("p1", "Pradhan resigns after exam scandal"),
        art("p2", "India beat Zimbabwe"),                      # tagged by the old 'india' rule
        art("p3", "Dharmendra Pradhan resigns, exam row"),
    ])
    await db.developing_stories.insert_many([
        {"story_id": "scout-old", "kind": "scout", "is_active": True, "detected_at": ago(30),
         "title": "India wins first CWG medal", "keywords": ["india", "wins", "first", "medal"], "article_ids": ["p2"]},
        {"story_id": "scout-a", "kind": "scout", "is_active": True, "detected_at": ago(5),
         "title": "Education Minister Pradhan Resigns After Exam Scandal",
         "keywords": ["india", "education", "minister", "pradhan"], "article_ids": ["p1", "p2"]},
        {"story_id": "scout-b", "kind": "scout", "is_active": True, "detected_at": ago(3),
         "title": "Dharmendra Pradhan resigns from position", "keywords": ["dharmendra"], "article_ids": ["p3"]},
        {"story_id": "scout-boost", "kind": "scout", "is_active": True, "detected_at": ago(40),
         "title": "CJP protest at Jantar Mantar today", "keywords": ["jantar"], "article_ids": [],
         "desk_boosted_at": ago(2)},
    ])
    await server._cleanup_scout_stories_v2()
    s = {d["story_id"]: d async for d in db.developing_stories.find({})}
    assert s["scout-old"]["is_active"] is False
    assert s["scout-a"]["is_active"] is True and "india" not in s["scout-a"]["keywords"]
    assert set(s["scout-a"]["article_ids"]) == {"p1", "p3"}                # p2 dropped, p3 merged in
    assert s["scout-b"]["is_active"] is False and s["scout-b"]["merged_into"] == "scout-a"
    assert s["scout-boost"]["is_active"] is True                           # owner's boost untouched
    # runs once
    await db.developing_stories.update_one({"story_id": "scout-old"}, {"$set": {"is_active": True}})
    await server._cleanup_scout_stories_v2()
    assert (await db.developing_stories.find_one({"story_id": "scout-old"}))["is_active"] is True


async def test_labels_follow_live_story_membership(db):
    await db.articles.insert_many([
        {**art("live", "x"), "is_developing": True},
        {**art("stray", "y"), "is_developing": True},
        {**art("desk", "z"), "is_developing": True, "origin": "desk"},
        {**art("boost", "w"), "is_developing": True, "boosted": True},
    ])
    await db.developing_stories.insert_many([
        {"story_id": "s1", "is_active": True, "article_ids": ["live"]},
        {"story_id": "s2", "is_active": False, "article_ids": ["stray"]},
    ])
    await server._reconcile_developing_labels()
    got = {a["article_id"]: a["is_developing"] async for a in db.articles.find({})}
    assert got == {"live": True, "stray": False, "desk": True, "boost": True}

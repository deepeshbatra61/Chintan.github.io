"""events_service against an in-memory Mongo.

    shadow  ─ assigns, writes events + article fields, never event_hidden/categories
    live    ─ non-leads hidden, lead carries outlets/mix, category vote written through
    wires   ─ syndicated copy recorded, counts as one voice
    status  ─ developing after a 2nd outlet ≥2h later; closes after 36h
    cache   ─ rebuilt-from-DB DocFreq equals the incremental one
    alarm   ─ metrics + alarm stored in app_meta
    server  ─ an events failure never breaks the ingest cycle
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "t")
os.environ.setdefault("JWT_SECRET", "t")

import events as E  # noqa: E402
import events_service as S  # noqa: E402

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)


def iso(h):
    return (NOW + timedelta(hours=h)).isoformat()


def art(aid, title, h, url, source="", desc="", content="", category="Politics", sub=None):
    return {"article_id": aid, "title": title, "description": desc or title, "content": content,
            "published_at": iso(h), "rank_at": iso(h), "url": url, "source": source,
            "category": category, "subcategory": sub, "is_developing": False}


@pytest.fixture
async def db():
    S.reset_cache()
    d = mongomock_motor.AsyncMongoMockClient()["t"]
    # background corpus so IDF behaves like production (many unrelated stories)
    filler = [art(f"f{i}", t, -10 - i, f"https://example{i}.com/x") for i, t in enumerate([
        "RBI holds repo rate steady amid inflation worries", "Sensex closes higher on IT gains",
        "Monsoon rains lash Kerala coast", "Virat Kohli scores century in ODI",
        "ISRO schedules Gaganyaan test flight", "Apple launches new iPhone in India",
        "Farmers protest in Punjab over paddy procurement", "Delhi air quality worsens",
        "Tata Motors unveils electric SUV", "Supreme Court hears electoral bonds case",
    ])]
    await d.articles.insert_many(filler)
    await S.run_cycle(d, now=NOW - timedelta(hours=9), mode="shadow")
    return d


PRADHAN = [
    ("p1", "Dharmendra Pradhan resigns as education minister over exam paper leak", 0, "https://www.thehindu.com/a"),
    ("p2", "Education minister Pradhan resigns amid exam leak protests", 0.5, "https://indianexpress.com/b"),
    ("p3", "Pradhan resigns over exam paper leak, students continue protest", 3, "https://www.tribuneindia.com/c"),
]


async def add(db, rows):
    await db.articles.insert_many([art(aid, t, h, u) for aid, t, h, u in rows])


async def test_shadow_groups_without_touching_the_feed(db):
    await add(db, PRADHAN)
    await S.run_cycle(db, now=NOW + timedelta(hours=3.5), mode="shadow")
    docs = {a["article_id"]: a async for a in db.articles.find({"article_id": {"$in": ["p1", "p2", "p3"]}})}
    assert len({d["event_id"] for d in docs.values()}) == 1
    assert docs["p1"]["publisher"] == "thehindu.com" and docs["p3"]["publisher_group"] == "regional"
    assert all("event_hidden" not in d for d in docs.values())
    ev = await db.events.find_one({"event_id": docs["p1"]["event_id"]})
    assert ev["outlets_count"] == 3 and ev["coverage_mix"] == {"national": 2, "regional": 1}
    assert ev["lead_article_id"] == "p1" and ev["status"] == "developing"
    state = await db.app_meta.find_one({"_id": "events_state"})
    assert state["mode"] == "shadow" and state["developing_open"] == 1 and "alarm" in state


async def test_live_hides_non_leads_and_writes_category(db):
    await db.articles.insert_many([
        art("p1", PRADHAN[0][1], 0, PRADHAN[0][3], category="Politics"),
        art("p2", PRADHAN[1][1], 0.5, PRADHAN[1][3], category="Science"),
        art("p3", PRADHAN[2][1], 3, PRADHAN[2][3], category="Politics"),
    ])
    await S.run_cycle(db, now=NOW + timedelta(hours=3.5), mode="live")
    docs = {a["article_id"]: a async for a in db.articles.find({"article_id": {"$in": ["p1", "p2", "p3"]}})}
    assert docs["p1"]["event_hidden"] is False and docs["p1"]["outlets_count"] == 3
    assert docs["p2"]["event_hidden"] is True and docs["p3"]["event_hidden"] is True
    assert {d["category"] for d in docs.values()} == {"Politics"}       # vote written through


async def test_wire_copy_is_one_voice(db):
    await add(db, [
        ("w1", "RBI awaits Tata Sons formal response on upper layer NBFC compliance", 0, "https://aninews.in/x"),
        ("w2", "RBI awaits Tata Sons’ formal response on Upper Layer NBFC compliance", 0.2, "https://www.devdiscourse.com/y"),
    ])
    await S.run_cycle(db, now=NOW + timedelta(hours=1), mode="shadow")
    w2 = await db.articles.find_one({"article_id": "w2"})
    assert w2["syndicated_of"] == "w1" and w2["syndicated_publisher"] == "aninews.in"
    ev = await db.events.find_one({"event_id": w2["event_id"]})
    assert ev["outlets_count"] == 1 and ev["status"] == "forming"


async def test_unrelated_stories_stay_apart(db):
    await add(db, [PRADHAN[0], ("k1", "Kerala teachers strike over pay commission delay", 0.5, "https://www.onmanorama.com/z")])
    await S.run_cycle(db, now=NOW + timedelta(hours=1), mode="shadow")
    a = await db.articles.find_one({"article_id": "p1"})
    b = await db.articles.find_one({"article_id": "k1"})
    assert a["event_id"] != b["event_id"]


async def test_developing_settles_then_closes(db):
    await add(db, PRADHAN)
    await S.run_cycle(db, now=NOW + timedelta(hours=3.5), mode="shadow")
    eid = (await db.articles.find_one({"article_id": "p1"}))["event_id"]
    await S.run_cycle(db, now=NOW + timedelta(hours=12), mode="shadow")
    assert (await db.events.find_one({"event_id": eid}))["status"] == "settled"
    await S.run_cycle(db, now=NOW + timedelta(hours=40), mode="shadow")
    assert (await db.events.find_one({"event_id": eid}))["status"] == "closed"


async def test_rerun_is_idempotent(db):
    await add(db, PRADHAN)
    await S.run_cycle(db, now=NOW + timedelta(hours=3.5), mode="shadow")
    n_events = await db.events.count_documents({})
    await S.run_cycle(db, now=NOW + timedelta(hours=3.6), mode="shadow")
    assert await db.events.count_documents({}) == n_events


async def test_cache_rebuild_matches_incremental(db):
    await add(db, PRADHAN)
    await S.run_cycle(db, now=NOW + timedelta(hours=3.5), mode="shadow")
    inc = S._cache["df"]
    snapshot = (inc.n, dict(inc.df))
    S.reset_cache()
    rebuilt = await S._ensure_cache(db, NOW + timedelta(hours=3.5))
    assert (rebuilt.n, dict(rebuilt.df)) == snapshot


async def test_off_mode_does_nothing(db):
    await add(db, PRADHAN)
    assert (await S.run_cycle(db, now=NOW + timedelta(hours=1), mode="off")) == {"mode": "off"}
    assert "event_id" not in await db.articles.find_one({"article_id": "p1"})


async def test_desk_block_is_respected(db):
    await add(db, PRADHAN[:1])
    await S.run_cycle(db, now=NOW + timedelta(hours=0.2), mode="shadow")
    eid = (await db.articles.find_one({"article_id": "p1"}))["event_id"]
    await db.events.update_one({"event_id": eid}, {"$set": {"desk": {"blocked_members": ["p2"]}}})
    await add(db, PRADHAN[1:2])
    await S.run_cycle(db, now=NOW + timedelta(hours=1), mode="shadow")
    assert (await db.articles.find_one({"article_id": "p2"}))["event_id"] != eid


def test_mode_env(monkeypatch):
    monkeypatch.setenv("EVENTS_MODE", "LIVE")
    assert S.current_mode() == "live"
    monkeypatch.setenv("EVENTS_MODE", "nonsense")
    assert S.current_mode() == "shadow"
    monkeypatch.delenv("EVENTS_MODE")
    assert S.current_mode() == "shadow"


async def test_ingest_cycle_survives_events_failure(monkeypatch):
    server = pytest.importorskip("server")
    d = mongomock_motor.AsyncMongoMockClient()["t2"]
    monkeypatch.setattr(server, "db", d)
    monkeypatch.setattr(server, "GNEWS_KEY", "")
    monkeypatch.setattr(server, "NEWSAPI_ENABLED", False, raising=False)

    async def nothing(*a, **k):
        return None
    for fn in ("_sync_scheduled_events", "_sync_wave_topics", "_sync_calendar_events",
               "_detect_developing_stories", "_expire_scout_stories", "_close_quiet_desk_stories",
               "_scout_developing_candidates", "_cleanup_scout_stories_v2"):
        monkeypatch.setattr(server, fn, nothing)

    async def boom(*a, **k):
        raise RuntimeError("events exploded")
    monkeypatch.setattr(server.events_service, "run_cycle", boom)
    await server._run_ingest_cycle_body(run_newsapi=False, summarize_limit=0)   # must not raise
    assert await d.app_meta.find_one({"_id": "ingest_state"})

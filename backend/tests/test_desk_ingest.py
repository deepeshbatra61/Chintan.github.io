"""Desk changes to EXISTING behaviour: feed ranking, ingest, lifecycle.

Imports the real server.py (needs the full requirements in the test
environment) with an in-memory database swapped in.

The REGRESSION test is the important one: moving ranking from published_at
to rank_at must leave an API-only feed in exactly the order it had before.
"""

import os
import random
from datetime import datetime, timedelta, timezone

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "t")
os.environ.setdefault("JWT_SECRET", "t")
server = pytest.importorskip("server")

import desk  # noqa: E402
import feed  # noqa: E402

NOW = datetime.now(timezone.utc)
CATS = ["Politics", "Business", "Sports", "World", "Science"]


def api_article(i, hours_ago, cat):
    pub = (NOW - timedelta(hours=hours_ago)).isoformat()
    return {"article_id": f"api{i}", "title": f"t{i}", "description": "", "category": cat,
            "published_at": pub, "source": "TOI"}


@pytest.fixture
def db(monkeypatch):
    d = mongomock_motor.AsyncMongoMockClient()["t"]
    monkeypatch.setattr(server, "db", d)
    return d


async def _seed_api(db, n=40, seed=7):
    rng = random.Random(seed)
    docs = [api_article(i, 24 + rng.uniform(0, 100), rng.choice(CATS)) for i in range(n)]
    await db.articles.insert_many([dict(d) for d in docs])
    return docs


async def guest_feed(page=1, limit=20):
    return [a["article_id"] for a in await server.get_articles(limit=limit, page=page, request=None)]


# ─────────────────────── regression ───────────────────────

async def test_REGRESSION_api_only_guest_feed_order_unchanged(db):
    docs = await _seed_api(db)
    # The pre-Desk algorithm: newest published_at first, rank-as-score, diversify.
    by_pub = sorted(docs, key=lambda a: a["published_at"], reverse=True)[:60]
    ranked = [(float(len(by_pub) - i), a) for i, a in enumerate(by_pub)]
    expected = [a["article_id"] for a in feed.diversify(ranked, needed=20, penalty=6.0)][:20]

    await server._backfill_rank_at()
    assert await guest_feed() == expected


async def test_backfill_is_idempotent_and_shifts_by_delay(db):
    docs = await _seed_api(db, n=5)
    await server._backfill_rank_at()
    await server._backfill_rank_at()
    for d in docs:
        stored = await db.articles.find_one({"article_id": d["article_id"]})
        assert stored["rank_at"] == desk.rank_at(d["published_at"], server.NEWSAPI_DELAY_H)


def test_freshness_signal_now_fires_for_just_arrived_api_articles(monkeypatch):
    """Before rank_at every API article was >24h old on arrival, so the
    freshness points (+10 within 6h) never applied. Now they do, on arrival."""
    monkeypatch.setattr(server.random, "random", lambda: 1.0)   # no discovery wildcard
    a = {"category": "Politics", "published_at": (NOW - timedelta(hours=25)).isoformat(),
         "rank_at": (NOW - timedelta(hours=1)).isoformat()}
    old_way = {k: v for k, v in a.items() if k != "rank_at"}
    assert server._score_article(a, [], {}, {}, NOW) - server._score_article(old_way, [], {}, {}, NOW) == 10.0


# ─────────────────────── placement ───────────────────────

def desk_article(aid, heat, minutes_ago=5, cat="Politics", **extra):
    t = (NOW - timedelta(minutes=minutes_ago)).isoformat()
    return {"article_id": aid, "title": aid, "description": "", "category": cat, "published_at": t,
            "rank_at": t, "origin": "desk", "heat": heat, "heat_from": t, "source": "Chintan Desk", **extra}


async def test_breaking_is_first_on_page_one_only(db):
    await _seed_api(db)
    await server._backfill_rank_at()
    await db.articles.insert_one(desk_article("brk", desk.HEAT_BREAKING, minutes_ago=90))
    p1 = await guest_feed(page=1, limit=10)
    p2 = await guest_feed(page=2, limit=10)
    assert p1[0] == "brk" and "brk" not in p2


async def test_normal_desk_item_competes_on_the_same_clock(db):
    """A Normal desk story from 3h ago must NOT outrank an API story that
    arrived (rank_at) 1h ago: the 24h publish lag no longer hands the Desk
    a free lead."""
    await db.articles.insert_one({**api_article(1, 25, "Business"), "rank_at": (NOW - timedelta(hours=1)).isoformat()})
    await db.articles.insert_one(desk_article("dsk", desk.HEAT_NORMAL, minutes_ago=180))
    assert await guest_feed() == ["api1", "dsk"]


async def test_big_desk_item_is_lifted_above_newer_api_items(db):
    for i in range(6):
        await db.articles.insert_one({**api_article(i, 25, CATS[i % 5]),
                                      "rank_at": (NOW - timedelta(minutes=10 * i)).isoformat()})
    await db.articles.insert_one(desk_article("big", desk.HEAT_BIG, minutes_ago=120, cat="World"))
    order = await guest_feed()
    assert order.index("big") <= 1


async def test_absorbed_and_unpublished_items_are_hidden(db):
    await db.articles.insert_one({**api_article(1, 25, "Politics"), "rank_at": NOW.isoformat(), "merged_into": "desk_x"})
    await db.articles.insert_one(desk_article("gone", desk.HEAT_BIG, desk_hidden=True))
    await db.articles.insert_one({**api_article(2, 25, "Sports"), "rank_at": NOW.isoformat()})
    assert await guest_feed() == ["api2"]


# ─────────────────────── ingest hooks ───────────────────────

async def test_absorb_folds_matching_new_api_articles(db):
    host = desk_article("dsk", desk.HEAT_NOTABLE, keywords=["electoral bonds", "sbi", "supreme court"],
                        absorb_until=(NOW + timedelta(hours=10)).isoformat())
    await db.articles.insert_one(host)
    new = [
        {"article_id": "m1", "title": "Supreme Court orders SBI on electoral bonds", "description": ""},
        {"article_id": "m2", "title": "SBI quarterly profit rises", "description": ""},
        {"article_id": "m3", "title": "SBI must disclose electoral bonds data", "description": "", },
    ]
    await db.articles.insert_many([dict(a) for a in new])
    await db.articles.update_one({"article_id": "m3"}, {"$set": {"absorb_exempt": True}})
    await server._absorb_into_desk(new)
    assert (await db.articles.find_one({"article_id": "m1"})).get("merged_into") == "dsk"
    assert "merged_into" not in await db.articles.find_one({"article_id": "m2"})
    assert "merged_into" not in await db.articles.find_one({"article_id": "m3"})   # undo respected


async def test_absorb_window_expires(db):
    await db.articles.insert_one(desk_article("dsk", 2, keywords=["electoral bonds", "sbi"],
                                              absorb_until=(NOW - timedelta(minutes=1)).isoformat()))
    new = [{"article_id": "m1", "title": "SBI electoral bonds", "description": ""}]
    await db.articles.insert_many([dict(a) for a in new])
    await server._absorb_into_desk(new)
    assert "merged_into" not in await db.articles.find_one({"article_id": "m1"})


async def test_quiet_desk_story_is_closed_busy_one_stays(db):
    created = NOW - timedelta(hours=40)
    quiet = {"story_id": "q", "kind": "desk", "is_active": True, **desk.lifecycle_fields(3, created)}
    quiet["last_updated"] = (NOW - timedelta(hours=37)).isoformat()
    busy = {"story_id": "b", "kind": "desk", "is_active": True, **desk.lifecycle_fields(3, created)}
    busy["last_updated"] = (NOW - timedelta(hours=2)).isoformat()
    other = {"story_id": "w", "kind": "wave", "is_active": True, "last_updated": "2020-01-01T00:00:00+00:00"}
    await db.developing_stories.insert_many([quiet, busy, other])
    await server._close_quiet_desk_stories()
    assert (await db.developing_stories.find_one({"story_id": "q"}))["ended_reason"] == "quiet"
    assert (await db.developing_stories.find_one({"story_id": "b"}))["is_active"]
    assert (await db.developing_stories.find_one({"story_id": "w"}))["is_active"]   # other kinds untouched


async def test_desk_story_listed_and_big_leads_the_strip(db):
    await db.articles.insert_many([
        {"article_id": "a1", "title": "x", "published_at": NOW.isoformat()},
        {"article_id": "a2", "title": "y", "published_at": (NOW - timedelta(hours=1)).isoformat()},
    ])
    await db.developing_stories.insert_many([
        {"story_id": "sched", "title": "S", "theme": "sports", "kind": "scheduled", "is_active": True,
         "article_ids": ["a1"], "last_updated": NOW.isoformat()},
        {"story_id": "desk-big", "title": "D", "theme": "politics", "kind": "desk", "is_active": True,
         "article_ids": ["a2"], "heat": 3, "last_updated": NOW.isoformat()},
    ])
    out = await server.get_developing_stories_list()
    assert [s["story_id"] for s in out] == ["desk-big", "sched"]

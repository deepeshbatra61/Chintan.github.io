"""Owner rules for the feed (2026-10-04). These must never regress.

    reshuffle ─ a new `seed` (sent by every pull-to-refresh) gives a different
                order, for guests AND signed-in readers
    paging    ─ one seed = one order: page 1 + page 2 = the first 40 of that
                order, no repeats, nothing skipped
    interests ─ a reader whose picks are v2-only (Health, a state) stays on the
                personalised path instead of falling into the fixed guest order
    follows   ─ a followed Developing story (container) that gains a report with
                a new headline sends ONE follow ping; the first look only records
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "t")
os.environ.setdefault("JWT_SECRET", "t")
server = pytest.importorskip("server")
import events_service  # noqa: E402

CATS = ["Politics", "Business", "Technology", "Sports", "Entertainment", "Science", "World"]


class Req:
    headers = {"X-Chintan-Client": "1.14.0"}
    cookies = {}


@pytest.fixture
async def db(monkeypatch):
    d = mongomock_motor.AsyncMongoMockClient()["t"]
    monkeypatch.setattr(server, "db", d)
    now = datetime.now(timezone.utc)
    await d.articles.insert_many([
        {"article_id": f"a{i:02d}", "title": f"Story {i}", "category": CATS[i % len(CATS)],
         "published_at": (now - timedelta(minutes=10 * i)).isoformat(),
         "rank_at": (now - timedelta(minutes=10 * i)).isoformat()}
        for i in range(60)
    ])
    return d


def as_user(monkeypatch, user):
    async def fake(request):
        return user
    monkeypatch.setattr(server, "get_current_user", fake)


async def ids(**kw):
    return [a["article_id"] for a in await server.get_articles(request=Req(), **kw)]


@pytest.mark.parametrize("who", ["guest", "reader"])
async def test_refresh_reshuffles_and_pages_stay_whole(db, monkeypatch, who):
    as_user(monkeypatch, None if who == "guest" else
            {"user_id": "u1", "interests": ["Politics", "Sports"], "interests_v2": ["Politics", "Cricket"]})
    first = await ids(seed=1, limit=20)
    assert await ids(seed=1, limit=20) == first                       # same seed, same feed
    assert await ids(seed=2, limit=20) != first                       # refresh = new order
    full = await ids(seed=1, limit=40)
    page2 = await ids(seed=1, limit=20, page=2)
    assert first + page2 == full and len(set(full)) == 40             # paging stays whole


async def test_v2_only_reader_is_personalised(db, monkeypatch):
    as_user(monkeypatch, {"user_id": "u2", "interests": [], "interests_v2": ["Health", "Kerala"]})
    guest_like = await ids(seed=None, limit=20)
    called = {}
    real = server._score_article

    def spy(*a, **k):
        called["yes"] = True
        return real(*a, **k)
    monkeypatch.setattr(server, "_score_article", spy)
    await ids(seed=None, limit=20)
    assert called.get("yes") and guest_like


async def test_container_follow_pings(db):
    now = datetime.now(timezone.utc)
    await db.developing_stories.insert_one({"story_id": "dev-strike", "title": "Rail strike in Kerala",
                                            "is_active": True, "article_ids": ["a01", "a02"]})
    await db.follows.insert_one({"user_id": "u1", "story_id": "dev-strike"})
    await db.follows.insert_one({"user_id": "u1", "story_id": "ev-123"})          # events ping elsewhere
    sent = []

    async def notify(**kw):
        sent.append(kw)

    assert await events_service.notify_container_follows(db, notify, now) == 0    # first look records
    await db.articles.insert_many([
        {"article_id": "n1", "title": "Story 1", "source": "NDTV",                   # a copy: no ping for it
         "published_at": (now + timedelta(minutes=5)).isoformat()},
        {"article_id": "n2", "title": "Unions call off Kerala rail strike after talks", "source": "The Hindu",
         "published_at": now.isoformat()},
    ])
    await db.developing_stories.update_one({"story_id": "dev-strike"},
                                           {"$set": {"article_ids": ["a01", "a02", "n1", "n2"]}})
    assert await events_service.notify_container_follows(db, notify, now) == 1
    assert sent == [{"story_id": "dev-strike", "story_title": "Rail strike in Kerala",
                     "headline": "Unions call off Kerala rail strike after talks", "outlet": "The Hindu"}]
    assert await events_service.notify_container_follows(db, notify, now) == 0    # nothing new
    await db.developing_stories.update_one({"story_id": "dev-strike"},
                                           {"$push": {"article_ids": "a03"}, "$set": {"is_active": False}})
    assert await events_service.notify_container_follows(db, notify, now) == 0    # settled stories stay quiet

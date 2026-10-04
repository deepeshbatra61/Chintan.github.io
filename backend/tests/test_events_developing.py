"""/developing-stories with events (eng review 1B: read-time projection).

    shadow ─ list unchanged (scout/auto shown, no events)
    live   ─ scout/auto dropped, developing events added, capped at 15,
             every item carries the fields the 1.12 app reads (contract)
    detail ─ "ev-…" ids resolve in the same response shape; hidden → 404
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "t")
os.environ.setdefault("JWT_SECRET", "t")
server = pytest.importorskip("server")
from fastapi import HTTPException  # noqa: E402

NOW = datetime.now(timezone.utc)

# Fields FeedPage.js / DevelopingPage.js (1.12) read on a default-kind item.
APP_112_KEYS = {"story_id", "title", "theme", "kind", "article_count", "last_updated", "latest_article"}


def iso(h):
    return (NOW - timedelta(hours=h)).isoformat()


@pytest.fixture
async def db(monkeypatch):
    d = mongomock_motor.AsyncMongoMockClient()["t"]
    monkeypatch.setattr(server, "db", d)
    monkeypatch.setattr(server, "ANTHROPIC_API_KEY", "")
    await d.developing_stories.insert_many([
        {"story_id": "scout-x", "kind": "scout", "is_active": True, "title": "Scout", "theme": "news",
         "article_ids": ["s1"], "last_updated": iso(1)},
        {"story_id": "asian-games-2026", "kind": "scheduled", "is_active": True, "title": "Asian Games",
         "theme": "sports", "article_ids": ["s1"], "last_updated": iso(1)},
    ])
    await d.articles.insert_one({"article_id": "s1", "title": "Scout article", "published_at": iso(1), "source": "X"})
    return d


async def add_event(d, eid, n_members=3, status="developing", hidden=False):
    ids = [f"{eid}-a{i}" for i in range(n_members)]
    await d.articles.insert_many([
        {"article_id": a, "title": f"{eid} headline {i}", "published_at": iso(3 - i), "source": f"Outlet {i}",
         "publisher": f"outlet{i}.com", "event_id": eid, "image_url": "https://img/x.jpg"}
        for i, a in enumerate(ids)])
    await d.events.insert_one({"event_id": eid, "status": status, "article_ids": ids, "size": n_members,
                               "lead_article_id": ids[0], "outlets_count": n_members, "category": "Politics",
                               "coverage_mix": {"national": n_members}, "last_member_at": iso(1),
                               **({"desk": {"hidden": True}} if hidden else {})})


async def test_shadow_list_is_unchanged(db, monkeypatch):
    monkeypatch.setenv("EVENTS_MODE", "shadow")
    await add_event(db, "ev-1")
    kinds = {s["kind"] for s in await server.get_developing_stories_list()}
    assert "scout" in kinds and "event" not in kinds


async def test_live_list_swaps_scout_for_events_and_keeps_the_112_contract(db, monkeypatch):
    monkeypatch.setenv("EVENTS_MODE", "live")
    await add_event(db, "ev-1")
    await add_event(db, "ev-hidden", hidden=True)
    await add_event(db, "ev-settled", status="settled")
    items = await server.get_developing_stories_list()
    kinds = [s["kind"] for s in items]
    assert "scout" not in kinds and "scheduled" in kinds
    ev = [s for s in items if s["kind"] == "event"]
    assert [s["story_id"] for s in ev] == ["ev-1"]
    assert APP_112_KEYS <= set(ev[0]) and ev[0]["article_count"] == 3 and ev[0]["outlets_count"] == 3
    assert ev[0]["title"] == "ev-1 headline 0"          # the lead's headline


async def test_live_list_is_capped(db, monkeypatch):
    monkeypatch.setenv("EVENTS_MODE", "live")
    for i in range(18):
        await add_event(db, f"ev-{i}", n_members=2)
    ev = [s for s in await server.get_developing_stories_list() if s["kind"] == "event"]
    assert len(ev) == 15


async def test_detail_resolves_event_ids_in_the_same_shape(db, monkeypatch):
    monkeypatch.setenv("EVENTS_MODE", "shadow")
    await add_event(db, "ev-1")
    d = await server.get_developing_story_detail("ev-1")
    # The fixture's three headlines carry the same facts, so they read as ONE
    # update with two more outlets (story_members.group_updates).
    assert d["kind"] == "event" and d["article_count"] == 1 and len(d["articles"]) == 1
    assert d["articles"][0]["also_count"] == 2
    assert d["outlets_count"] == 3 and "momentum" in d and d["title"] == "ev-1 headline 0"
    await add_event(db, "ev-hidden", hidden=True)
    with pytest.raises(HTTPException):
        await server.get_developing_story_detail("ev-hidden")
    with pytest.raises(HTTPException):
        await server.get_developing_story_detail("ev-missing")

"""Follow + "since you last looked" endpoints (events_routes.py), over HTTP.

    auth      ─ every route 401s without a session; identity never from the body
    follow    ─ only live stories; idempotent; capped at 50; sets seen
    list      ─ new_count since seen; settled stories drop out (D8)
    seen      ─ returns the previous time for the divider; unknown story 404
    purge     ─ account deletion erases follows + story_seen
"""

import os
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI

mongomock_motor = pytest.importorskip("mongomock_motor")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "t")
os.environ.setdefault("JWT_SECRET", "t")

import events_routes as R  # noqa: E402

NOW = datetime.now(timezone.utc)


def iso(h):
    return (NOW + timedelta(hours=h)).isoformat()


@pytest.fixture
async def h():
    db = mongomock_motor.AsyncMongoMockClient()["t"]
    users = {"tok-a": {"user_id": "a"}, "tok-b": {"user_id": "b"}}

    async def get_user(request):
        return users.get(request.headers.get("Authorization", "").removeprefix("Bearer "))

    app = FastAPI()
    app.include_router(R.build_events_router(db_getter=lambda: db, get_user=get_user))
    await db.articles.insert_many([
        {"article_id": "x1", "title": "Pradhan resigns", "published_at": iso(-3)},
        {"article_id": "x2", "title": "Congress demands probe", "published_at": iso(-1)},
    ])
    await db.events.insert_many([
        {"event_id": "ev-live", "status": "developing", "lead_article_id": "x1", "article_ids": ["x1", "x2"],
         "last_member_at": iso(-1)},
        {"event_id": "ev-done", "status": "settled", "lead_article_id": "x1", "article_ids": ["x1"],
         "last_member_at": iso(-20)},
        {"event_id": "ev-hidden", "status": "developing", "lead_article_id": "x1", "article_ids": ["x1"],
         "desk": {"hidden": True}},
    ])
    await db.developing_stories.insert_one({"story_id": "asian-games-2026", "kind": "scheduled",
                                            "is_active": True, "title": "Asian Games", "article_ids": ["x1"]})

    class H:
        pass
    x = H()
    x.db = db
    x.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    x.auth = lambda tok="tok-a": {"Authorization": f"Bearer {tok}"}
    yield x
    await x.client.aclose()


async def test_every_route_needs_a_session(h):
    for method, path, body in [("post", "/follows", {"story_id": "ev-live"}), ("delete", "/follows/ev-live", None),
                               ("get", "/follows", None), ("post", "/stories/ev-live/seen", None)]:
        r = await getattr(h.client, method)(path, **({"json": body} if body else {}))
        assert r.status_code == 401, path


async def test_follow_live_stories_only(h):
    assert (await h.client.post("/follows", json={"story_id": "ev-live"}, headers=h.auth())).status_code == 200
    assert (await h.client.post("/follows", json={"story_id": "asian-games-2026"}, headers=h.auth())).status_code == 200
    for bad in ("ev-done", "ev-hidden", "ev-nope", "x" * 200):
        r = await h.client.post("/follows", json={"story_id": bad}, headers=h.auth())
        assert r.status_code in (404, 422), bad
    # idempotent
    await h.client.post("/follows", json={"story_id": "ev-live"}, headers=h.auth())
    assert await h.db.follows.count_documents({"user_id": "a"}) == 2


async def test_follow_cap(h, monkeypatch):
    monkeypatch.setattr(R, "MAX_FOLLOWS", 1)
    await h.client.post("/follows", json={"story_id": "ev-live"}, headers=h.auth())
    r = await h.client.post("/follows", json={"story_id": "asian-games-2026"}, headers=h.auth())
    assert r.status_code == 409


async def test_list_counts_new_since_seen_and_drops_settled(h):
    await h.client.post("/follows", json={"story_id": "ev-live"}, headers=h.auth())
    await h.db.story_seen.update_one({"user_id": "a", "story_id": "ev-live"}, {"$set": {"seen_at": iso(-2)}})
    await h.db.follows.insert_one({"user_id": "a", "story_id": "ev-done", "created_at": iso(-30), "pushes": []})
    body = (await h.client.get("/follows", headers=h.auth())).json()
    assert [f["story_id"] for f in body["follows"]] == ["ev-live"]
    assert body["follows"][0]["new_count"] == 1 and body["new_total"] == 1
    assert await h.db.follows.count_documents({"story_id": "ev-done"}) == 0     # cleaned up
    # another reader sees nothing of a's
    assert (await h.client.get("/follows", headers=h.auth("tok-b"))).json()["follows"] == []


async def test_seen_returns_previous_time(h):
    first = (await h.client.post("/stories/ev-live/seen", headers=h.auth())).json()
    assert first["previous_seen_at"] is None
    second = (await h.client.post("/stories/ev-live/seen", headers=h.auth())).json()
    assert second["previous_seen_at"] == first["seen_at"]
    assert (await h.client.post("/stories/ev-nope/seen", headers=h.auth())).status_code == 404


async def test_unfollow(h):
    await h.client.post("/follows", json={"story_id": "ev-live"}, headers=h.auth())
    assert (await h.client.delete("/follows/ev-live", headers=h.auth())).json()["following"] is False
    assert await h.db.follows.count_documents({}) == 0


async def test_account_purge_erases_follows_and_seen(monkeypatch):
    server = pytest.importorskip("server")
    db = mongomock_motor.AsyncMongoMockClient()["p"]
    monkeypatch.setattr(server, "db", db)
    await db.follows.insert_one({"user_id": "u", "story_id": "ev-1"})
    await db.story_seen.insert_one({"user_id": "u", "story_id": "ev-1", "seen_at": iso(0)})
    await db.follows.insert_one({"user_id": "other", "story_id": "ev-1"})
    await server._purge_user("u")
    assert await db.follows.count_documents({"user_id": "u"}) == 0
    assert await db.story_seen.count_documents({}) == 0
    assert await db.follows.count_documents({"user_id": "other"}) == 1

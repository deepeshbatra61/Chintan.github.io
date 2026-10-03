"""Desk Newsroom routes (design 7B) over HTTP, behind the real Desk gates.

    gates   ─ no session → 401; non-event ids → 404
    list    ─ building / developing / settling + mode, alarm, cap
    actions ─ promote, hide, merge (follows move), split (blocked from origin),
              remove member; every one audited and recomputed
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "t")
os.environ.setdefault("JWT_SECRET", "t")

import events_service as S  # noqa: E402
from test_desk_routes import Harness  # noqa: E402

NOW = datetime.now(timezone.utc)


def iso(h):
    return (NOW - timedelta(hours=h)).isoformat()


def a(aid, eid, h, pub):
    return {"article_id": aid, "event_id": eid, "title": f"{aid} title", "published_at": iso(h), "rank_at": iso(h),
            "publisher": pub, "publisher_group": "national", "publisher_name": pub, "category": "Politics",
            "ev_terms": {"pradhan": 2.0, aid: 1.0}}


@pytest.fixture
async def h(monkeypatch):
    monkeypatch.setenv("EVENTS_MODE", "shadow")
    S.reset_cache()
    x = Harness(events=S)
    await x.seed_admin()
    await x.db.articles.insert_many([a("p1", "ev-p", 4, "thehindu.com"), a("p2", "ev-p", 1, "ndtv.com"),
                                     a("p3", "ev-p", 0.5, "tribuneindia.com"),
                                     a("q1", "ev-q", 3, "livemint.com"), a("q2", "ev-q", 0.2, "moneycontrol.com")])
    for eid, ids, status in (("ev-p", ["p1", "p2", "p3"], "developing"), ("ev-q", ["q1", "q2"], "forming")):
        await x.db.events.insert_one({"event_id": eid, "status": status, "size": len(ids), "article_ids": ids,
                                      "lead_article_id": ids[0], "first_member_at": iso(4), "last_member_at": iso(0.2),
                                      "centroid": {"pradhan": 1.0}, "founding": [{"pradhan": 1.0}], "members": []})
    yield x
    await x.client.aclose()


async def test_needs_a_desk_session(h):
    assert (await h.client.get("/api/desk/newsroom", headers=h.headers())).status_code == 401


async def test_newsroom_sections(h):
    await h.login()
    body = (await h.client.get("/api/desk/newsroom", headers=h.headers())).json()
    assert body["mode"] == "shadow" and body["developing_cap"] == 15 and body["alarm"] is False
    assert [e["event_id"] for e in body["developing"]] == ["ev-p"]
    assert [e["event_id"] for e in body["building"]] == ["ev-q"]
    detail = (await h.client.get("/api/desk/events/ev-p", headers=h.headers())).json()
    assert [m["article_id"] for m in detail["members"]] == ["p3", "p2", "p1"] and "centroid" not in detail
    assert (await h.client.get("/api/desk/events/nope", headers=h.headers())).status_code == 404


async def test_promote_and_hide(h):
    await h.login()
    r = await h.client.post("/api/desk/events/ev-q/promote", headers=h.headers(), json={"on": True})
    assert r.status_code == 200
    assert (await h.db.events.find_one({"event_id": "ev-q"}))["status"] == "developing"
    await h.client.post("/api/desk/events/ev-q/hide", headers=h.headers(), json={"on": True})
    assert (await h.db.events.find_one({"event_id": "ev-q"}))["desk"]["hidden"] is True
    actions = [d["action"] async for d in h.db.desk_audit.find({})]
    assert "event_promote" in actions and "event_hide" in actions


async def test_merge_moves_members_and_follows(h):
    await h.login()
    await h.db.follows.insert_many([{"user_id": "u1", "story_id": "ev-q"}, {"user_id": "u2", "story_id": "ev-q"},
                                    {"user_id": "u2", "story_id": "ev-p"}])
    r = await h.client.post("/api/desk/events/ev-q/merge", headers=h.headers(), json={"into": "ev-p"})
    assert r.status_code == 200
    assert await h.db.articles.count_documents({"event_id": "ev-p"}) == 5
    src = await h.db.events.find_one({"event_id": "ev-q"})
    assert src["status"] == "closed" and src["desk"]["merged_into"] == "ev-p"
    assert {(f["user_id"], f["story_id"]) async for f in h.db.follows.find({})} == {("u1", "ev-p"), ("u2", "ev-p")}
    bad = await h.client.post("/api/desk/events/ev-p/merge", headers=h.headers(), json={"into": "ev-p"})
    assert bad.status_code == 409


async def test_split_breaks_out_and_blocks(h):
    await h.login()
    r = await h.client.post("/api/desk/events/ev-p/split", headers=h.headers(), json={"article_ids": ["p3"]})
    assert r.status_code == 200
    new_id = r.json()["event_id"]
    assert (await h.db.articles.find_one({"article_id": "p3"}))["event_id"] == new_id
    old = await h.db.events.find_one({"event_id": "ev-p"})
    assert "p3" in old["desk"]["blocked_members"] and old["article_ids"] == ["p1", "p2"]
    everything = await h.client.post("/api/desk/events/ev-p/split", headers=h.headers(),
                                      json={"article_ids": ["p1", "p2"]})
    assert everything.status_code == 409


async def test_remove_member(h):
    await h.login()
    r = await h.client.post("/api/desk/events/ev-p/remove/p2", headers=h.headers())
    assert r.status_code == 200
    assert "event_id" not in await h.db.articles.find_one({"article_id": "p2"})
    assert "p2" in (await h.db.events.find_one({"event_id": "ev-p"}))["desk"]["blocked_members"]
    assert (await h.client.post("/api/desk/events/ev-p/remove/zzz", headers=h.headers())).status_code == 404

"""Desk stories on events (eng review 1A) and the EVENTS_MODE switch (OV4).

    live      ─ coverage joining a Desk article's event is folded into it
                (merged_into, merged_by=events), Desk leads, rank bumps,
                developing Desk story gets the timeline
    undo      ─ block_member: leaves the event for good, never re-joins
    unpublish ─ Desk article drops out, an API article leads again
    switch    ─ shadow→live runs go_live once; live→shadow runs go_back
                (clears live fields + event folds, re-runs the legacy fold)
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "t")
os.environ.setdefault("JWT_SECRET", "t")

import events_flip as F  # noqa: E402
import events_service as S  # noqa: E402

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)


def iso(h):
    return (NOW + timedelta(hours=h)).isoformat()


def art(aid, title, h, url, **kw):
    return {"article_id": aid, "title": title, "description": title, "content": "", "published_at": iso(h),
            "rank_at": iso(h), "url": url, "source": "", "category": "Politics", **kw}


DESK = art("d1", "Dharmendra Pradhan resigns as education minister over exam paper leak", 0, "https://chintan.news/d1",
           origin="desk", desk_story_id="desk-pradhan")
API = [art("a1", "Education minister Pradhan resigns amid exam leak protests", 0.5, "https://indianexpress.com/a"),
       art("a2", "Pradhan resigns over exam paper leak, students continue protest", 3, "https://www.tribuneindia.com/b")]


@pytest.fixture
async def db():
    S.reset_cache()
    d = mongomock_motor.AsyncMongoMockClient()["t"]
    filler = [art(f"f{i}", t, -10 - i, f"https://example{i}.com/x") for i, t in enumerate([
        "RBI holds repo rate steady amid inflation worries", "Sensex closes higher on IT gains",
        "Monsoon rains lash Kerala coast", "Virat Kohli scores century in ODI",
        "ISRO schedules Gaganyaan test flight", "Apple launches new iPhone in India",
        "Farmers protest in Punjab over paddy procurement", "Delhi air quality worsens"])]
    await d.articles.insert_many(filler + [DESK] + API)
    await d.developing_stories.insert_one({"story_id": "desk-pradhan", "kind": "desk", "is_active": True,
                                           "article_ids": ["d1"], "title": "Pradhan resigns"})
    return d


async def test_live_folds_coverage_into_the_desk_story(db):
    await S.run_cycle(db, now=NOW + timedelta(hours=3.5), mode="live")
    docs = {a["article_id"]: a async for a in db.articles.find({"article_id": {"$in": ["d1", "a1", "a2"]}})}
    assert len({d["event_id"] for d in docs.values()}) == 1
    ev = await db.events.find_one({"event_id": docs["d1"]["event_id"]})
    assert ev["lead_article_id"] == "d1"
    for aid in ("a1", "a2"):
        assert docs[aid]["merged_into"] == "d1" and docs[aid]["merged_by"] == "events"
    assert docs["d1"]["rank_at"] == iso(3)                       # host moved up with the newest member
    story = await db.developing_stories.find_one({"story_id": "desk-pradhan"})
    assert set(story["article_ids"]) == {"d1", "a1", "a2"}


async def test_shadow_never_folds(db):
    await S.run_cycle(db, now=NOW + timedelta(hours=3.5), mode="shadow")
    assert await db.articles.count_documents({"merged_by": "events"}) == 0


async def test_undo_blocks_for_good(db):
    await S.run_cycle(db, now=NOW + timedelta(hours=3.5), mode="live")
    eid = (await db.articles.find_one({"article_id": "a1"}))["event_id"]
    # the Desk route unsets merged_into, then calls block_member
    await db.articles.update_one({"article_id": "a1"}, {"$unset": {"merged_into": ""}, "$set": {"absorb_exempt": True}})
    left = await S.block_member(db, "a1", NOW + timedelta(hours=4), mode="live")
    assert left == eid
    await S.run_cycle(db, now=NOW + timedelta(hours=4.5), mode="live")
    a1 = await db.articles.find_one({"article_id": "a1"})
    assert a1["event_id"] != eid and "merged_into" not in a1
    ev = await db.events.find_one({"event_id": eid})
    assert "a1" in ev["desk"]["blocked_members"] and "a1" not in ev["article_ids"]


async def test_unpublish_hands_the_lead_back(db):
    await S.run_cycle(db, now=NOW + timedelta(hours=3.5), mode="live")
    eid = (await db.articles.find_one({"article_id": "d1"}))["event_id"]
    await db.articles.update_one({"article_id": "d1"}, {"$set": {"desk_hidden": True}})
    await db.articles.update_many({"merged_into": "d1"}, {"$unset": {"merged_into": "", "merged_by": ""}})
    await S.recompute_event(db, eid, NOW + timedelta(hours=4), mode="live")
    ev = await db.events.find_one({"event_id": eid})
    assert ev["lead_article_id"] == "a1" and "d1" not in ev["article_ids"]
    a1 = await db.articles.find_one({"article_id": "a1"})
    assert a1["event_hidden"] is False and "merged_into" not in a1


async def test_mode_switch_round_trip(db):
    calls = []

    async def legacy_fold():
        calls.append(1)
        return 0
    await S.run_cycle(db, now=NOW + timedelta(hours=3.5), mode="shadow")
    assert await F.sync_mode(db, now=NOW + timedelta(hours=3.6), mode="shadow") is None
    assert await db.articles.count_documents({"event_hidden": {"$exists": True}}) == 0

    assert await F.sync_mode(db, now=NOW + timedelta(hours=3.6), mode="live") == "go_live"
    assert await db.articles.count_documents({"event_hidden": True}) >= 1
    assert await db.articles.count_documents({"merged_by": "events"}) == 2
    assert await F.sync_mode(db, now=NOW + timedelta(hours=3.7), mode="live") is None      # already applied

    assert await F.sync_mode(db, now=NOW + timedelta(hours=3.8), mode="shadow", legacy_fold=legacy_fold) == "go_back"
    assert await db.articles.count_documents({"event_hidden": {"$exists": True}}) == 0
    assert await db.articles.count_documents({"outlets_count": {"$exists": True}}) == 0
    assert await db.articles.count_documents({"merged_by": "events"}) == 0
    assert calls == [1]
    assert (await db.app_meta.find_one({"_id": "events_applied"}))["mode"] == "shadow"


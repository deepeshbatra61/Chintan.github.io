"""Developing stories: who belongs, how the timeline reads, what the summary may
say. Built from the owner's report of 2026-10-05 (the CJP / Jantar Mantar story
holding an Apple story and a Delhi hit-and-run; "Chief Justice of Pakistan").

    members   ─ word-matched candidates join only when the check says "same event";
                live members are checked once too; rejected are never re-asked;
                model down = nothing joins, nobody is dropped
    timeline  ─ reports with the same facts are one update (+N outlets)
    summary   ─ a name the reports don't carry (an expanded acronym, a country)
                rejects the summary
"""

import json
import os
from datetime import datetime, timezone

import pytest

import story_members as SM

mongomock_motor = pytest.importorskip("mongomock_motor")
NOW = datetime(2026, 10, 5, 6, 0, tzinfo=timezone.utc)

CJP = [
    ("c1", "CJP leader demands FIR against Delhi ACP over alleged sexual assault of journalist"),
    ("c2", "Jantar Mantar 2.0 is on: activists, opposition leaders rally over vote theft"),
    ("x1", "Delhi hit-and-run: elderly couple flung into air after car hits them"),
    ("x2", "Apple removes messaging platform that works without internet from India App Store"),
]


def judge_by(words):
    """A stand-in for the model: 'same story' when a headline has one of `words`."""
    calls = []

    async def llm(system="", user_content="", **k):
        calls.append(user_content)
        same = [int(line.split(":", 1)[0]) for line in user_content.splitlines()
                if line[:1].isdigit() and any(w in line.lower() for w in words)]
        return json.dumps({"same": same})
    llm.calls = calls
    return llm


@pytest.fixture
async def db():
    d = mongomock_motor.AsyncMongoMockClient()["t"]
    await d.articles.insert_many([{"article_id": i, "title": t, "description": ""} for i, t in CJP])
    await d.developing_stories.insert_one({
        "story_id": "auto-cjp", "kind": "auto", "is_active": True,
        "title": "CJP criticizes Delhi Police Jantar Mantar crackdown",
        "article_ids": ["c1", "x1"], "pending_ids": ["c2", "x2"]})
    return d


async def test_only_the_same_event_stays(db):
    llm = judge_by(["cjp", "jantar"])
    out = await SM.verify_members(db, llm, NOW)
    s = await db.developing_stories.find_one({"story_id": "auto-cjp"})
    assert s["article_ids"] == ["c1", "c2"]                       # live member x1 removed, x2 never joins
    assert set(s["rejected_ids"]) == {"x1", "x2"} and s["pending_ids"] == []
    assert out["kept"] == 2 and out["rejected"] == 2
    # Nothing new: no second call. A rejected report coming back is not re-asked.
    await db.developing_stories.update_one({"story_id": "auto-cjp"}, {"$push": {"pending_ids": "x1"}})
    await SM.verify_members(db, llm, NOW)
    assert len(llm.calls) == 1
    assert (await db.developing_stories.find_one({"story_id": "auto-cjp"}))["article_ids"] == ["c1", "c2"]


async def test_model_down_changes_nothing(db):
    async def down(**k):
        raise RuntimeError("overloaded")
    await SM.verify_members(db, down, NOW)
    s = await db.developing_stories.find_one({"story_id": "auto-cjp"})
    assert s["article_ids"] == ["c1", "x1"] and s["pending_ids"] == ["c2", "x2"]


async def test_story_with_no_members_left_closes(db):
    await SM.verify_members(db, judge_by(["nothing matches"]), NOW)
    assert (await db.developing_stories.find_one({"story_id": "auto-cjp"}))["is_active"] is False


async def test_waves_are_judged_as_storylines(db):
    await db.developing_stories.update_one({"story_id": "auto-cjp"}, {"$set": {"kind": "wave"}})
    llm = judge_by(["cjp"])
    await SM.verify_members(db, llm, NOW)
    assert "long-running story" in llm.calls[0]


def test_same_facts_fold_into_one_update():
    reps = [
        {"article_id": "a", "title": "Drishyam 3 crosses Rs 150 crore at box office", "source": "NDTV",
         "published_at": "2026-10-05T05:00:00Z"},
        {"article_id": "b", "title": "Drishyam 3 box office: crosses Rs 150 crore", "source": "Times Now",
         "published_at": "2026-10-05T06:00:00Z"},
        {"article_id": "c", "title": "Drishyam 3 OTT platform revealed ahead of release", "source": "News18",
         "published_at": "2026-10-05T07:00:00Z"},
    ]
    groups = SM.group_updates(reps)
    assert [g["lead"]["article_id"] for g in groups] == ["c", "a"]
    assert [x["article_id"] for x in groups[1]["also"]] == ["b"]


def test_summary_may_not_name_what_the_reports_do_not():
    os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
    os.environ.setdefault("DB_NAME", "t")
    os.environ.setdefault("JWT_SECRET", "t")
    server = pytest.importorskip("server")
    src = ("CJP criticizes Delhi Police Jantar Mantar crackdown\n- CJP leader demands FIR against Delhi ACP "
           "over alleged sexual assault of journalist")
    bad = "Delhi Police face criticism from the Chief Justice of Pakistan after a Jantar Mantar crackdown."
    good = "Delhi Police face criticism from the CJP over the Jantar Mantar crackdown on protesters."
    assert not server._summary_grounded(bad, src)
    assert server._summary_grounded(good, src)


def test_one_entry_per_event_in_the_list():
    odi = [f"o{i}" for i in range(20)]
    items = [
        {"story_id": "scout-ind-wi-3rd-odi", "kind": "scout", "article_count": 18, "_ids": odi[:18]},
        {"story_id": "auto-west", "kind": "auto", "article_count": 12, "_ids": odi[5:17]},
        {"story_id": "auto-shai", "kind": "auto", "article_count": 6, "_ids": odi[14:20]},
        {"story_id": "scout-flydubai", "kind": "scout", "article_count": 4, "_ids": ["f1", "f2", "f3", "f4"]},
        {"story_id": "asian-games", "kind": "scheduled", "article_count": 90, "_ids": odi + ["g1"]},
        {"story_id": "world-animal-day", "kind": "calendar", "article_count": 0},
    ]
    out = SM.fold_duplicates(items)
    assert [i["story_id"] for i in out] == ["scout-ind-wi-3rd-odi", "scout-flydubai", "asian-games", "world-animal-day"]
    assert all("_ids" not in i for i in out)

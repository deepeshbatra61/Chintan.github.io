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
        {"story_id": "auto-games", "kind": "auto", "article_count": 30, "_ids": ["g1"] + odi[:10]},
    ]
    out = SM.fold_duplicates(items)
    assert [i["story_id"] for i in out] == ["scout-ind-wi-3rd-odi", "scout-flydubai", "asian-games", "world-animal-day"]
    assert all("_ids" not in i for i in out)


# ── 2026-10-09: developments vs reactions/explainers (Nana Patekar: 242 "updates") ──

NANA = [
    ("n1", "Nana Patekar dies at 75 in Goa after cardiac arrest", "development"),
    ("n2", "Amitabh Bachchan pays emotional tribute to Nana Patekar", "reaction"),
    ("n3", "When Nana Patekar helped Shah Rukh Khan get out of jail", "reaction"),
    ("n4", "Goa Police register unnatural death case in Nana Patekar's death", "development"),
    ("n5", "Nana Patekar's death puts sudden cardiac arrest in focus: why CPR matters", "explainer"),
    ("n6", "Panaji police file case after Nana Patekar's death, enquiry on", "repeat"),
]


def labeller(table):
    """Stand-in model: labels each shown headline from `table` (title -> label)."""
    async def llm(system="", user_content="", **k):
        labels = {}
        for line in user_content.splitlines():
            if line[:1].isdigit() and ": " in line:
                i, title = line.split(": ", 1)
                labels[i] = table.get(title.split(" | ")[0], "no")
        return json.dumps({"labels": labels})
    return llm


async def test_check_labels_what_each_report_adds():
    d = mongomock_motor.AsyncMongoMockClient()["t"]
    await d.articles.insert_many([{"article_id": i, "title": t, "description": ""} for i, t, _ in NANA]
                                 + [{"article_id": "x", "title": "Sensex falls 500 points", "description": ""}])
    await d.developing_stories.insert_one({"story_id": "scout-nana", "kind": "scout", "is_active": True,
                                           "title": "Nana Patekar death report",
                                           "article_ids": ["n1", "n2", "n3"],               # live before labels
                                           "pending_ids": ["n4", "n5", "n6", "x"]})
    table = {t: k for _, t, k in NANA}
    await SM.verify_members(d, labeller(table), NOW)
    s = await d.developing_stories.find_one({"story_id": "scout-nana"})
    assert s["member_kinds"] == {i: k for i, _, k in NANA}
    assert "x" in s["rejected_ids"] and "x" not in s["article_ids"]


def test_timeline_is_developments_with_bundles_and_at_most_8_sources():
    reps = [{"article_id": i, "title": t, "source": f"Outlet {i}", "published_at": f"2026-10-08T0{n}:00:00Z"}
            for n, (i, t, _) in enumerate(NANA)]
    # the police case was also reported by 15 more outlets
    reps += [{"article_id": f"p{j}", "title": "Goa Police register unnatural death case in Nana Patekar's death",
              "source": f"Paper {j}", "published_at": "2026-10-08T09:00:00Z"} for j in range(15)]
    kinds = {i: k for i, _, k in NANA} | {f"p{j}": "repeat" for j in range(15)}
    updates, bundles, n = SM.build_timeline(reps, kinds)
    assert n == 2 and [u["article_id"] for u in updates] == ["n4", "n1"]
    police = updates[0]
    assert police["also_count"] == len(police["also_sources"]) == SM.MAX_SOURCES - 1     # never "+16 outlets"
    assert {b["kind"]: b["count"] for b in bundles} == {"reaction": 2, "explainer": 1}
    assert bundles[0]["label"] == "Reactions & tributes"


def test_unlabelled_members_still_show_as_before():
    reps = [{"article_id": "a", "title": "Old member", "source": "X", "published_at": "2026-10-08T01:00:00Z"}]
    updates, bundles, n = SM.build_timeline(reps, {})
    assert n == 1 and updates[0]["article_id"] == "a" and bundles == []


def test_old_style_answer_still_parses():
    assert SM._parse_labels('{"same": [0, 2]}', 3) == {0: "development", 1: "no", 2: "development"}
    assert SM._parse_labels('{"labels": {"0": "reaction", "1": "banana", "7": "development"}}', 2) == {0: "reaction"}


async def test_tributes_never_ping_followers():
    import events_service
    d = mongomock_motor.AsyncMongoMockClient()["t"]
    await d.developing_stories.insert_one({"story_id": "scout-nana", "title": "Nana Patekar death report",
                                           "is_active": True, "article_ids": ["n1"]})
    await d.follows.insert_one({"user_id": "u1", "story_id": "scout-nana"})
    sent = []

    async def notify(**kw):
        sent.append(kw)
    await events_service.notify_container_follows(d, notify, NOW)            # first look records
    await d.articles.insert_one({"article_id": "n2", "title": "Amitabh Bachchan pays emotional tribute to Nana",
                                 "source": "NDTV", "published_at": NOW.isoformat()})
    await d.developing_stories.update_one({"story_id": "scout-nana"}, {"$set": {
        "article_ids": ["n1", "n2"], "member_kinds": {"n1": "development", "n2": "reaction"}}})
    assert await events_service.notify_container_follows(d, notify, NOW) == 0 and sent == []

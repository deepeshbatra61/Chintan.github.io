"""brief_service: the brief page's behaviour (regression, moved out of server.py)
plus push pinning.

    read_brief ─▶ pin (tap id, or latest before next slot) ─▶ cache (<1h) ─▶ build + cache
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")

import brief_service as S  # noqa: E402

NOW = datetime(2026, 9, 30, 2, 0, tzinfo=timezone.utc)
USER = {"user_id": "u1", "name": "Deepesh Batra", "interests": ["Economy", "Sports"]}


def run(coro):
    return asyncio.run(coro)


def article(i, cat, hours_ago=2):
    return {
        "article_id": f"a{i}", "title": f"Story {i} in {cat}", "source": "The Hindu",
        "category": cat, "subcategory": "", "summary": f"Summary {i}.",
        "description": f"Description {i}.",
        "published_at": (NOW - timedelta(hours=hours_ago)).isoformat(),
    }


class LLM:
    def __init__(self, text="1. Take one.\n2. Take two.\n3. Take three.", fail=False):
        self.text, self.fail, self.calls = text, fail, 0

    async def __call__(self, prompt):
        self.calls += 1
        if self.fail:
            raise RuntimeError("down")
        return self.text


def fresh_db(articles=None):
    db = mongomock_motor.AsyncMongoMockClient()["t"]
    arts = articles if articles is not None else [
        article(1, "Economy"), article(2, "Sports"), article(3, "Politics"), article(4, "Economy", 5),
    ]
    if arts:
        run(db.articles.insert_many([dict(a) for a in arts]))
    return db


SHAPE = {"greeting", "subtitle", "summary", "categories", "referenced_stories", "read_time"}


# ── regression: the brief page behaves as before ────────────────────────────

def test_build_shape_and_first_name_greeting():
    db, llm = fresh_db(), LLM()
    doc = run(S.build_brief(db, USER, "morning", llm, NOW))
    assert set(doc) == SHAPE
    assert doc["greeting"] == "Good morning"
    assert len(doc["referenced_stories"]) == len(doc["categories"]) >= 1
    for story in doc["referenced_stories"]:
        assert story["article_id"] and story["take"]
    assert "saved_for_you" not in doc


def test_interests_lead_the_categories():
    doc = run(S.build_brief(fresh_db(), USER, "night", LLM(), NOW))
    assert doc["categories"][:2] == ["Economy", "Sports"]


def test_llm_failure_still_returns_takes():
    llm = LLM(fail=True)
    doc = run(S.build_brief(fresh_db(), USER, "midday", llm, NOW))
    assert llm.calls == 1
    assert all(s["take"] for s in doc["referenced_stories"])


def test_empty_db_same_shape():
    doc = run(S.build_brief(fresh_db([]), None, "morning", LLM(), NOW))
    assert set(doc) == SHAPE
    assert doc["referenced_stories"] == [] and doc["categories"] == []


def test_invalid_type_rejected():
    with pytest.raises(ValueError):
        run(S.build_brief(fresh_db(), USER, "brunch", LLM(), NOW))


def test_cache_hit_within_hour_then_rebuild():
    db, llm = fresh_db(), LLM()
    first = run(S.read_brief(db, USER, "morning", llm, NOW))
    again = run(S.read_brief(db, USER, "morning", llm, NOW + timedelta(minutes=59)))
    assert llm.calls == 1 and again == first
    run(S.read_brief(db, USER, "morning", llm, NOW + timedelta(minutes=61)))
    assert llm.calls == 2


def test_cache_is_per_user_and_anon():
    db, llm = fresh_db(), LLM()
    run(S.read_brief(db, USER, "morning", llm, NOW))
    run(S.read_brief(db, None, "morning", llm, NOW))
    run(S.read_brief(db, {"user_id": "u2"}, "morning", llm, NOW))
    assert llm.calls == 3
    keys = {d["_id"] for d in run(db.brief_cache.find({}).to_list(10))}
    assert keys == {"v2:morning:u1", "v2:morning:anon", "v2:morning:u2"}


# ── pins ────────────────────────────────────────────────────────────────────

def pin(db, user_id="u1", brief_type="morning", valid_h=6, label="07:30 Sunrise", created=NOW):
    doc = {**{k: "" for k in SHAPE}, "summary": f"PINNED for {user_id}", "referenced_stories": [], "categories": []}
    return run(S.create_pin(db, user_id, brief_type, doc, created, created + timedelta(hours=valid_h), label))


def test_pin_wins_over_cache_and_build():
    db, llm = fresh_db(), LLM()
    run(S.read_brief(db, USER, "morning", llm, NOW))          # warm cache
    pin(db)
    doc = run(S.read_brief(db, USER, "morning", llm, NOW + timedelta(minutes=5)))
    assert doc["summary"] == "PINNED for u1"
    assert doc["pinned_from"] == "07:30 Sunrise"
    assert llm.calls == 1


def test_pin_expires_at_next_slot_without_id():
    db, llm = fresh_db(), LLM()
    pin(db, valid_h=6)
    doc = run(S.read_brief(db, USER, "morning", llm, NOW + timedelta(hours=7)))
    assert doc["summary"] != "PINNED for u1"
    assert "pinned_from" not in doc


def test_tap_with_pin_id_works_until_24h():
    db, llm = fresh_db(), LLM()
    pid = pin(db, valid_h=6)
    doc = run(S.read_brief(db, USER, "morning", llm, NOW + timedelta(hours=20), pin_id=pid))
    assert doc["summary"] == "PINNED for u1"
    doc = run(S.read_brief(db, USER, "morning", llm, NOW + timedelta(hours=25), pin_id=pid))
    assert doc["summary"] != "PINNED for u1"


def test_someone_elses_pin_is_ignored():
    db, llm = fresh_db(), LLM()
    pid = pin(db, user_id="u2")
    doc = run(S.read_brief(db, USER, "morning", llm, NOW, pin_id=pid))
    assert doc["summary"] != "PINNED for u2"


def test_pin_for_other_type_is_ignored():
    db, llm = fresh_db(), LLM()
    pin(db, brief_type="night")
    doc = run(S.read_brief(db, USER, "morning", llm, NOW))
    assert "pinned_from" not in doc


def test_guest_never_sees_pins():
    db, llm = fresh_db(), LLM()
    pid = pin(db)
    doc = run(S.read_brief(db, None, "morning", llm, NOW, pin_id=pid))
    assert "pinned_from" not in doc


def test_latest_pin_wins():
    db, llm = fresh_db(), LLM()
    pin(db, created=NOW - timedelta(hours=1), label="old")
    pin(db, created=NOW, label="new")
    doc = run(S.read_brief(db, USER, "morning", llm, NOW + timedelta(minutes=1)))
    assert doc["pinned_from"] == "new"

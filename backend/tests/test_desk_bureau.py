"""The Bureau's Desk quality check (CEO T1) over HTTP, behind the real Desk gates.

    gates    ─ no session → 401
    queue    ─ unchecked hidden items only, important first, filtered never shown,
               at most half from one source
    labels   ─ facts right? easy to read? → running score; gate needs 30 checks,
               95% facts, 85% readable; unknown / filtered ids → 404; audited
    override ─ importance level set by the owner, validated
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "t")
os.environ.setdefault("JWT_SECRET", "t")

import official_service as OS  # noqa: E402
from test_desk_routes import Harness  # noqa: E402

NOW = datetime.now(timezone.utc)


class FakeBureau:
    async def health(self):
        return {"mode": "shadow", "sources": {"pib": {"silent": False, "broken": False}}, "alarm": False}


def item(oid, source="pib", importance="normal", status="shadow", h=1):
    return {"official_id": oid, "source": source, "status": status, "importance": importance,
            "title": f"{oid} title", "what_changed": f"{oid} line", "fetched_at": (NOW - timedelta(hours=h)).isoformat(),
            "source_text": "Source text with ₹12,000 crore.", "facts": [], "issuer": source.upper()}


@pytest.fixture
async def h():
    x = Harness(bureau=FakeBureau())
    await x.seed_admin()
    await x.db.official_items.insert_many([
        item("o-low", importance="low", h=1), item("o-high", importance="high", h=5),
        item("o-norm", h=2), item("o-filtered", status="filtered", h=0.5),
        item("o-rbi1", source="rbi_press", h=3), item("o-rbi2", source="rbi_press", h=3.5),
    ])
    yield x
    await x.client.aclose()


async def test_needs_a_desk_session(h):
    assert (await h.client.get("/api/desk/bureau/review", headers=h.headers())).status_code == 401


async def test_queue_order_and_contents(h):
    await h.login()
    body = (await h.client.get("/api/desk/bureau/review", headers=h.headers())).json()
    ids = [i["official_id"] for i in body["items"]]
    assert "o-filtered" not in ids
    assert ids[0] == "o-high" and ids.index("o-norm") < ids.index("o-low")
    assert body["items"][0]["source_text"].startswith("Source text")
    assert body["summary"]["checked"] == 0 and body["summary"]["passed"] is False
    assert body["health"]["mode"] == "shadow"


async def test_queue_caps_one_source_at_half():
    db = mongomock_motor.AsyncMongoMockClient()["t"]
    await db.official_items.insert_many([item(f"p{i}", h=i) for i in range(10)] + [item("r1", source="rbi_press", h=20)])
    q = await OS.review_queue(db, limit=4)
    assert [d["source"] for d in q].count("pib") == 2 and "r1" in [d["official_id"] for d in q]


async def test_labels_score_and_leave_the_queue(h):
    await h.login()
    r = await h.client.post("/api/desk/bureau/labels", headers=h.headers(),
                            json={"official_id": "o-high", "facts_ok": True, "readable": False, "note": "too long"})
    s = r.json()
    assert r.status_code == 200 and s["checked"] == 1 and s["facts_ok"] == 1.0 and s["readable"] == 0.0
    assert s["by_source"]["pib"]["checked"] == 1 and s["notes"][0]["note"] == "too long"
    body = (await h.client.get("/api/desk/bureau/review", headers=h.headers())).json()
    assert "o-high" not in [i["official_id"] for i in body["items"]]
    for bad in ("nope", "o-filtered"):
        r = await h.client.post("/api/desk/bureau/labels", headers=h.headers(),
                                json={"official_id": bad, "facts_ok": True, "readable": True})
        assert r.status_code == 404
    assert "bureau_label" in [d["action"] async for d in h.db.desk_audit.find({})]


async def test_gate_needs_thirty_and_both_rates():
    db = mongomock_motor.AsyncMongoMockClient()["t"]
    await db.official_items.insert_many([item(f"g{i}") for i in range(40)])
    for i in range(29):
        await OS.record_label(db, f"g{i}", True, True, "", "o@x", NOW)
    assert (await OS.review_summary(db))["passed"] is False            # only 29 checked
    await OS.record_label(db, "g29", True, True, "", "o@x", NOW)
    assert (await OS.review_summary(db))["passed"] is True
    for i in range(30, 35):
        await OS.record_label(db, f"g{i}", True, False, "", "o@x", NOW)  # readable 30/35 = 0.857
    assert (await OS.review_summary(db))["passed"] is True
    await OS.record_label(db, "g35", True, False, "", "o@x", NOW)       # 30/36 = 0.833 < 0.85
    assert (await OS.review_summary(db))["passed"] is False


async def test_importance_override(h):
    await h.login()
    r = await h.client.post("/api/desk/bureau/items/o-low/importance", headers=h.headers(), json={"level": "high"})
    assert r.status_code == 200
    assert (await h.db.official_items.find_one({"official_id": "o-low"}))["importance_override"] == "high"
    bad = await h.client.post("/api/desk/bureau/items/o-low/importance", headers=h.headers(), json={"level": "urgent"})
    assert bad.status_code == 400
    missing = await h.client.post("/api/desk/bureau/items/nope/importance", headers=h.headers(), json={"level": "low"})
    assert missing.status_code == 404
    body = (await h.client.get("/api/desk/bureau/review", headers=h.headers())).json()
    assert body["items"][0]["official_id"] in ("o-high", "o-low")       # override now ranks it high

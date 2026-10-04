"""The Bureau for readers (app 1.14): who can see it, what they see.

    access   ─ live: everyone, admins too, as readers (no Preview line); shadow:
               admins only, as a preview; off: nobody
    hiding   ─ public never sees filtered, needs_desk, "never", or facts marked wrong
               (not even by id); preview sees all but filtered, with needs_desk shown
    feed     ─ lens = issuer, newest first, paging by `before`, today counted in IST
               for the whole lens, delayed sources named
    item     ─ owner's importance override wins; "Earlier on this" = items sharing a ref
    http     ─ /bureau/status, /bureau, /bureau/items/{id} behind the same rules
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import official_routes
import official_service as OS

mongomock_motor = pytest.importorskip("mongomock_motor")

NOW = datetime(2026, 10, 6, 9, 0, tzinfo=timezone.utc)          # Tuesday 14:30 IST


def item(oid, issuer_key="rbi", h=1, **kw):
    d = {"official_id": oid, "source": "rbi_press", "source_name": "RBI", "issuer": issuer_key.upper(),
         "issuer_key": issuer_key, "kind": "policy", "title": f"{oid} title", "what_changed": f"{oid} line",
         "published_at": (NOW - timedelta(hours=h)).isoformat(), "fetched_at": NOW.isoformat(),
         "importance": "normal", "status": "shadow", "facts": [], "refs": [], "source_text": "secret source text",
         "verified_dropped": []}
    d.update(kw)
    return d


@pytest.fixture
async def db():
    d = mongomock_motor.AsyncMongoMockClient()["t"]
    await d.official_items.insert_many([
        item("a", h=1, refs=["BILL 1/2026"]),
        item("b", issuer_key="sebi", h=2),
        item("c", h=30, refs=["BILL 1/2026"]),                 # yesterday in IST
        item("needs", h=3, needs_desk=True),
        item("never", h=4, importance="never"),
        item("overridden", h=5, importance_override="never"),
        item("wrong", h=6),
        item("cer", h=7, status="filtered", kind="ceremonial"),
        item("pib", issuer_key="pib", h=8, importance="low", importance_override="high"),
    ])
    await d.official_labels.insert_one({"official_id": "wrong", "facts_ok": False, "readable": True})
    return d


def ids(feed):
    return [i["official_id"] for i in feed["items"]]


def test_access_rules():
    assert OS.reader_access("live", False) == "public"
    assert OS.reader_access("live", True) == "public"
    assert OS.reader_access("shadow", True) == "preview"
    assert OS.reader_access("shadow", False) is None
    assert OS.reader_access("off", True) is None


async def test_public_sees_only_cleared_items(db):
    feed = await OS.reader_feed(db, access="public", lens=None, before=None, limit=20, now=NOW)
    assert ids(feed) == ["a", "b", "pib", "c"]
    assert all("source_text" not in i and "verified_dropped" not in i and "needs_desk" not in i
               for i in feed["items"])
    assert feed["preview"] is False
    for oid in ("needs", "never", "overridden", "wrong", "cer"):
        assert await OS.reader_item(db, oid, access="public") is None


async def test_preview_sees_everything_but_filtered(db):
    feed = await OS.reader_feed(db, access="preview", lens=None, before=None, limit=20, now=NOW)
    assert "cer" not in ids(feed) and {"needs", "never", "wrong"} <= set(ids(feed))
    assert next(i for i in feed["items"] if i["official_id"] == "needs")["needs_desk"] is True
    assert feed["preview"] is True


async def test_lens_paging_and_today(db):
    feed = await OS.reader_feed(db, access="public", lens="rbi", before=None, limit=1, now=NOW)
    assert ids(feed) == ["a"] and feed["has_more"] and feed["today_count"] == 1
    nxt = await OS.reader_feed(db, access="public", lens="rbi", before=feed["items"][-1]["published_at"],
                               limit=5, now=NOW)
    assert ids(nxt) == ["c"] and not nxt["has_more"]
    assert ids(await OS.reader_feed(db, access="public", lens="ministries", before=None, limit=5, now=NOW)) == ["pib"]
    everything = await OS.reader_feed(db, access="public", lens="nonsense", before=None, limit=99, now=NOW)
    assert len(everything["items"]) == 4 and everything["today_count"] == 3


async def test_delayed_sources_named(db):
    health = {"sources": {"rbi_press": {"broken": True}, "rbi_notif": {"broken": True},
                          "sebi": {"broken": False}, "gone": {"broken": True}}}
    feed = await OS.reader_feed(db, access="public", lens=None, before=None, limit=5, now=NOW, health=health)
    assert feed["delayed"] == ["RBI"]


async def test_item_override_and_thread(db):
    it = await OS.reader_item(db, "pib", access="public")
    assert it["importance"] == "high" and "importance_override" not in it
    a = await OS.reader_item(db, "a", access="public")
    assert [e["official_id"] for e in a["earlier"]] == ["c"]
    assert (await OS.reader_item(db, "b", access="public"))["earlier"] == []


# ── http ─────────────────────────────────────────────────────────────────────

class Svc:
    def __init__(self, db, mode):
        self.db, self._mode = db, mode

    def mode(self):
        return self._mode

    def now(self):
        return NOW

    async def health(self):
        return {"sources": {}}


def client(db, mode, email=None):
    async def get_user(request):
        return {"email": email} if email else None

    async def require_admin():
        return {}

    app = FastAPI()
    app.include_router(official_routes.build_official_router(
        service=Svc(db, mode), require_admin=require_admin, get_user=get_user,
        admin_emails=lambda: {"owner@chintan.news"}), prefix="/api")
    return TestClient(app)


async def test_http_shadow_is_admin_only(db):
    reader = client(db, "shadow", "reader@example.com")
    assert reader.get("/api/bureau/status").json() == {"enabled": False, "preview": False}
    assert reader.get("/api/bureau").status_code == 404
    assert reader.get("/api/bureau/items/a").status_code == 404
    owner = client(db, "shadow", "Owner@Chintan.news")
    assert owner.get("/api/bureau/status").json() == {"enabled": True, "preview": True}
    assert "needs" in [i["official_id"] for i in owner.get("/api/bureau").json()["items"]]
    assert owner.get("/api/bureau/items/a").json()["earlier"][0]["official_id"] == "c"


async def test_http_live_and_off(db):
    guest = client(db, "live")
    assert guest.get("/api/bureau/status").json() == {"enabled": True, "preview": False}
    assert [i["official_id"] for i in guest.get("/api/bureau?lens=sebi").json()["items"]] == ["b"]
    assert guest.get("/api/bureau/items/wrong").status_code == 404
    owner = client(db, "live", "owner@chintan.news")
    assert owner.get("/api/bureau/status").json() == {"enabled": True, "preview": False}
    assert owner.get("/api/bureau").json()["preview"] is False
    assert client(db, "off", "owner@chintan.news").get("/api/bureau/status").json()["enabled"] is False

"""Desk push endpoints through the real Desk gates (proxy secret, session, CSRF):
panel, go-live confirm, test push, Breaking preview/send with SEND confirm and
one-send-per-story."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("mongomock_motor")
import httpx  # noqa: E402
from fastapi import FastAPI  # noqa: E402

import desk_routes  # noqa: E402
import research  # noqa: E402
from test_desk_routes import EMAIL, PROXY, Harness  # noqa: E402


class FakePush:
    def __init__(self):
        self.enabled, self.calls, self.fail_send = False, [], False

    async def stats(self):
        return {"state": {"enabled": self.enabled, "env_enabled": True}, "rows": {}, "errors": [],
                "devices": 2, "readers": 1}

    async def next_slot_preview(self):
        return {"slot": "Dusk", "local_time": "19:30", "tz": "Asia/Kolkata", "readers": 1}

    async def set_enabled(self, enabled, by):
        self.enabled = enabled
        self.calls.append(("set_enabled", enabled, by))
        return {"enabled": enabled}

    async def test_push(self, email):
        self.calls.append(("test", email))
        return {"ok": True, "devices": [{"result": "delivered"}]}

    async def reach(self, story_id, category, national):
        self.calls.append(("reach", story_id, category, national))
        return {"readers": 3, "devices": 4, "held": {}, "live": True}

    async def send_breaking(self, *, story_id, text, category, national):
        self.calls.append(("send", story_id, text, category, national))
        if self.fail_send:
            return {"ok": False, "error": "Push is switched off."}
        return {"ok": True, "sent": 3, "failed": 0, "held": {"quiet": 1}, "title": "Breaking", "body": text}


@pytest.fixture
async def h():
    harness = Harness()
    harness.push = FakePush()
    app = FastAPI()
    app.include_router(desk_routes.build_desk_router(
        db=harness.db, auth=harness.auth, proxy_secret=lambda: PROXY, admin_emails=lambda: {EMAIL},
        research=harness._research, fetch_meta=harness._fetch, send_email=harness._email,
        registrable_domain=research._registrable_domain, suggest_category=lambda t: "Politics",
        default_image="x", logger=__import__("logging").getLogger("t"),
        push=harness.push, push_test_email=lambda: "owner@x.in"), prefix="/api")
    harness.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    await harness.seed_admin()
    await harness.db.articles.insert_one({"article_id": "desk_1", "title": "Quake hits Uttarakhand!",
                                          "category": "India", "desk_national": True})
    await harness.login()
    yield harness
    await harness.client.aclose()


PUSH_ROUTES = [
    ("get", "/api/desk/push", None),
    ("post", "/api/desk/push/enabled", {"enabled": False}),
    ("post", "/api/desk/push/test", None),
    ("post", "/api/desk/push/breaking/preview", {"article_id": "desk_1"}),
    ("post", "/api/desk/push/breaking/send", {"article_id": "desk_1", "confirm": "SEND"}),
]


async def _call(h, method, path, body, headers):
    kw = {"headers": headers}
    if body is not None:
        kw["json"] = body
    return await getattr(h.client, method)(path, **kw)


@pytest.mark.parametrize("method,path,body", PUSH_ROUTES)
async def test_gates(h, method, path, body):
    assert (await _call(h, method, path, body, h.headers(proxy="wrong"))).status_code == 404
    assert (await _call(h, method, path, body, h.headers(session=False))).status_code == 401
    if method != "get":
        assert (await _call(h, method, path, body, h.headers(csrf=False))).status_code == 403
    assert h.push.calls == []


async def test_panel(h):
    r = await h.client.get("/api/desk/push", headers=h.headers())
    assert r.status_code == 200
    assert r.json()["next_slot"]["slot"] == "Dusk" and r.json()["test_email_set"] is True


async def test_turning_on_needs_confirm_off_is_instant(h):
    r = await h.client.post("/api/desk/push/enabled", headers=h.headers(), json={"enabled": True})
    assert r.status_code == 409 and h.push.enabled is False
    r = await h.client.post("/api/desk/push/enabled", headers=h.headers(), json={"enabled": True, "confirm": True})
    assert r.status_code == 200 and h.push.enabled is True
    r = await h.client.post("/api/desk/push/enabled", headers=h.headers(), json={"enabled": False})
    assert r.status_code == 200 and h.push.enabled is False
    actions = [a["action"] for a in await h.db.desk_audit.find({}).to_list(50)]
    assert "push_on" in actions and "push_off" in actions


async def test_test_push_uses_configured_email(h):
    r = await h.client.post("/api/desk/push/test", headers=h.headers())
    assert r.json()["ok"] and ("test", "owner@x.in") in h.push.calls


async def test_breaking_preview_is_sober_and_counts(h):
    r = await h.client.post("/api/desk/push/breaking/preview", headers=h.headers(), json={"article_id": "desk_1"})
    body = r.json()
    assert body["title"] == "Breaking" and "!" not in body["body"]
    assert body["national"] is True and body["reach"]["readers"] == 3 and body["already_sent"] is False
    missing = await h.client.post("/api/desk/push/breaking/preview", headers=h.headers(), json={"article_id": "nope"})
    assert missing.status_code == 404


async def test_breaking_send_needs_SEND_and_goes_once(h):
    r = await h.client.post("/api/desk/push/breaking/send", headers=h.headers(),
                            json={"article_id": "desk_1", "confirm": "SEN"})
    assert r.status_code == 422
    r = await h.client.post("/api/desk/push/breaking/send", headers=h.headers(),
                            json={"article_id": "desk_1", "confirm": "SEND", "text": "Quake of 6.1 strikes Uttarakhand"})
    assert r.status_code == 200 and r.json()["sent"] == 3
    assert ("send", "desk_1", "Quake of 6.1 strikes Uttarakhand", "India", True) in h.push.calls
    again = await h.client.post("/api/desk/push/breaking/send", headers=h.headers(),
                                json={"article_id": "desk_1", "confirm": "SEND"})
    assert again.status_code == 409
    audit = await h.db.desk_audit.find_one({"action": "push_breaking"})
    assert audit and audit["detail"]["sent"] == 3


async def test_failed_breaking_send_can_be_retried(h):
    h.push.fail_send = True
    r = await h.client.post("/api/desk/push/breaking/send", headers=h.headers(),
                            json={"article_id": "desk_1", "confirm": "SEND"})
    assert r.status_code == 409
    h.push.fail_send = False
    r = await h.client.post("/api/desk/push/breaking/send", headers=h.headers(),
                            json={"article_id": "desk_1", "confirm": "SEND"})
    assert r.status_code == 200


async def test_router_without_push_has_no_push_routes():
    harness = Harness()
    await harness.seed_admin()
    await harness.login()
    r = await harness.client.get("/api/desk/push", headers=harness.headers())
    assert r.status_code == 404
    await harness.client.aclose()

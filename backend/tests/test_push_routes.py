"""HTTP tests for the app-facing push endpoints: identity only from the session,
token/platform/tz validation, per-IP rate limit, opened, prefs."""

import asyncio
from datetime import date, timedelta

import pytest

pytest.importorskip("fastapi")
mongomock_motor = pytest.importorskip("mongomock_motor")
import httpx  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402

import push as P  # noqa: E402
import push_routes  # noqa: E402
import push_service as PS  # noqa: E402

IST = "Asia/Kolkata"
TOKEN = "f" * 40
SESSIONS = {"Bearer good": {"user_id": "u1", "name": "Asha"}}


class Harness:
    def __init__(self, now):
        self.db = mongomock_motor.AsyncMongoMockClient()["t"]
        self.t = now
        self.mono = 0.0

        async def none(*a, **k):
            return None

        async def top(user):
            return []

        self.svc = PS.PushService(db=self.db, sender=None, llm=none, send_email=none, alert_to=lambda: [],
                                  top_categories=top, env_enabled=lambda: True, now=lambda: self.t)

        async def get_user(request: Request):
            return SESSIONS.get(request.headers.get("authorization", ""))

        app = FastAPI()
        app.include_router(push_routes.build_push_router(
            service=self.svc, get_user=get_user, client_ip=lambda r: r.headers.get("x-ip", "1.1.1.1"),
            clock=lambda: self.mono), prefix="/api")
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")

    def call(self, method, path, auth=None, ip=None, **kw):
        headers = {}
        if auth:
            headers["authorization"] = auth
        if ip:
            headers["x-ip"] = ip

        async def go():
            return await self.client.request(method, "/api" + path, headers=headers, **kw)
        return asyncio.run(go())


def dev(token=TOKEN, platform="android", tz=IST):
    return {"token": token, "platform": platform, "tz": tz, "app_version": "1.12.0"}


def h(now=None):
    return Harness(now or P.slot_instant("dusk", date(2026, 10, 1), IST) - timedelta(minutes=90))


def test_register_signed_in_gets_first_brief():
    x = h()          # 18:00 IST → Dusk still preparable
    r = x.call("POST", "/push/devices", auth="Bearer good", json=dev())
    assert r.status_code == 200
    assert r.json()["first_brief"] == {"slot": "Dusk", "local_time": "19:30", "day": "today"}
    d = asyncio.run(x.db.push_devices.find_one({}))
    assert d["user_id"] == "u1" and d["tz"] == IST


def test_register_late_evening_says_tomorrow():
    x = h(P.slot_instant("dusk", date(2026, 10, 1), IST) - timedelta(minutes=30))
    r = x.call("POST", "/push/devices", auth="Bearer good", json=dev())
    assert r.json()["first_brief"] == {"slot": "Sunrise", "local_time": "07:30", "day": "tomorrow"}


def test_guest_register_has_no_user_and_no_brief():
    x = h()
    r = x.call("POST", "/push/devices", json={**dev(), "user_id": "u1"})     # body can't name an account
    assert r.status_code == 200 and "first_brief" not in r.json()
    assert asyncio.run(x.db.push_devices.find_one({}))["user_id"] is None


@pytest.mark.parametrize("body,code", [
    (dev(token="short"), 400), (dev(token="bad token with spaces" * 3), 400),
    (dev(platform="windows"), 400),
])
def test_register_validation(body, code):
    assert h().call("POST", "/push/devices", json=body).status_code == code


def test_bad_tz_falls_back_to_ist():
    x = h()
    x.call("POST", "/push/devices", json=dev(tz="../../etc"))
    assert asyncio.run(x.db.push_devices.find_one({}))["tz"] == IST


def test_rate_limit_per_ip_per_hour():
    x = h()
    for i in range(20):
        assert x.call("POST", "/push/devices", ip="9.9.9.9", json=dev(token=f"{i:02d}" + "a" * 30)).status_code == 200
    assert x.call("POST", "/push/devices", ip="9.9.9.9", json=dev()).status_code == 429
    assert x.call("POST", "/push/devices", ip="8.8.8.8", json=dev()).status_code == 200
    x.mono += 3601
    assert x.call("POST", "/push/devices", ip="9.9.9.9", json=dev()).status_code == 200


def test_delete_device():
    x = h()
    x.call("POST", "/push/devices", json=dev())
    assert x.call("DELETE", "/push/devices", json={"token": TOKEN}).status_code == 200
    assert asyncio.run(x.db.push_devices.count_documents({})) == 0


def test_opened_never_reveals():
    x = h()
    assert x.call("POST", "/push/opened", json={"push_id": "unknown"}).json() == {"ok": True}
    assert x.call("POST", "/push/opened", json={"push_id": "x" * 65}).status_code == 422


def test_prefs_user_guest_and_anonymous():
    x = h()
    assert x.call("GET", "/push/prefs", auth="Bearer good").json()["prefs"] == P.DEFAULT_PREFS
    r = x.call("PUT", "/push/prefs", auth="Bearer good", json={"prefs": {"noon": True}})
    assert r.json()["prefs"]["noon"] is True
    x.call("POST", "/push/devices", json=dev())
    r = x.call("PUT", "/push/prefs", json={"prefs": {"breaking": False, "sunrise": True}, "token": TOKEN})
    assert r.json() == {"prefs": {"breaking": False}, "guest": True}
    assert x.call("GET", f"/push/prefs?token={TOKEN}").json()["prefs"] == {"breaking": False}
    assert x.call("PUT", "/push/prefs", json={"prefs": {"breaking": False}}).status_code == 401

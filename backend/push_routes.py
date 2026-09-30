"""App-facing push endpoints (eng review 3A).

    POST   /push/devices  register/refresh this device (called on every app resume)
    DELETE /push/devices  forget this device (logout)
    POST   /push/opened   a push was tapped (push_id from the payload)
    GET    /push/prefs    this reader's toggles (guests: Breaking only, by token)
    PUT    /push/prefs    change toggles

Identity comes ONLY from the session (get_user); a request body can never name
an account. A guest device is identified by its own FCM token, which only that
device holds.
"""

import re
import time
from collections import defaultdict, deque
from typing import Awaitable, Callable, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

import push as P

TOKEN_RE = re.compile(r"^[A-Za-z0-9:_\-.]{20,4096}$")
REGISTER_PER_HOUR = 20


class DeviceIn(BaseModel):
    token: str = Field(max_length=4096)
    platform: str = Field(max_length=10)
    tz: str = Field(default="", max_length=64)
    app_version: str = Field(default="", max_length=20)


class TokenIn(BaseModel):
    token: str = Field(max_length=4096)


class OpenedIn(BaseModel):
    push_id: str = Field(max_length=64)


class PrefsIn(BaseModel):
    prefs: dict
    token: Optional[str] = Field(default=None, max_length=4096)


def _valid_token(token: str) -> bool:
    return bool(TOKEN_RE.match(token or ""))


def build_push_router(*, service, get_user: Callable[[Request], Awaitable[Optional[dict]]],
                      client_ip: Callable[[Request], str],
                      clock: Callable[[], float] = time.monotonic) -> APIRouter:
    router = APIRouter(prefix="/push")
    hits = defaultdict(deque)   # ip -> monotonic timestamps (single Railway instance)

    def _rate_ok(ip: str) -> bool:
        now = clock()
        q = hits[ip]
        while q and now - q[0] > 3600:
            q.popleft()
        if len(q) >= REGISTER_PER_HOUR:
            return False
        q.append(now)
        return True

    @router.post("/devices")
    async def register(body: DeviceIn, request: Request):
        if not _rate_ok(client_ip(request)):
            raise HTTPException(status_code=429, detail="Too many requests. Try again later.")
        if not _valid_token(body.token):
            raise HTTPException(status_code=400, detail="Invalid device token.")
        if body.platform not in ("android", "ios"):
            raise HTTPException(status_code=400, detail="Invalid platform.")
        tz = body.tz if P.valid_tz(body.tz) else P.DEFAULT_TZ
        user = await get_user(request)
        user_id = user.get("user_id") if user else None
        out = await service.register(token=body.token, platform=body.platform, tz=tz,
                                     user_id=user_id, app_version=body.app_version)
        if user_id:
            prefs = await service.get_prefs(user_id)
            first = P.first_brief_slot(service.now(), tz, prefs)
            if first:
                key, day, at = first
                local = P.local_now(at, tz)
                today = P.local_now(service.now(), tz).date()
                when = "today" if day == today else "tomorrow" if (day - today).days == 1 else day.isoformat()
                out["first_brief"] = {"slot": P.SLOTS[key].label, "local_time": local.strftime("%H:%M"),
                                      "day": when}
        return out

    @router.delete("/devices")
    async def unregister(body: TokenIn):
        # Holding the token is the proof: it is secret to the device.
        if not _valid_token(body.token):
            raise HTTPException(status_code=400, detail="Invalid device token.")
        await service.unregister(body.token)
        return {"ok": True}

    @router.post("/opened")
    async def opened(body: OpenedIn):
        # Unknown or repeated ids are ignored; the response never says which.
        await service.opened(body.push_id)
        return {"ok": True}

    @router.get("/prefs")
    async def get_prefs(request: Request, token: Optional[str] = None):
        user = await get_user(request)
        if user:
            return {"prefs": await service.get_prefs(user["user_id"]), "guest": False}
        if not token or not _valid_token(token):
            return {"prefs": {"breaking": True}, "guest": True}
        return {"prefs": await service.get_prefs(None, token), "guest": True}

    @router.put("/prefs")
    async def put_prefs(body: PrefsIn, request: Request):
        user = await get_user(request)
        if user:
            return {"prefs": await service.set_prefs(user["user_id"], body.prefs), "guest": False}
        if not body.token or not _valid_token(body.token):
            raise HTTPException(status_code=401, detail="Sign in to change these.")
        return {"prefs": await service.set_prefs(None, body.prefs, token=body.token), "guest": True}

    return router

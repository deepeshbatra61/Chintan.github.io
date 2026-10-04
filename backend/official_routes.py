"""The Bureau endpoints.

    GET /health/official          public: mode, per-source last run, counts,
                                  silence / broken alarms (no secrets, no items)
    GET /official/shadow?limit=   admin only: newest reader-facing items while
                                  OFFICIAL_MODE=shadow, for checking quality

Reader endpoints (app 1.14). Who sees what: official_service.reader_access
(live: everyone; shadow: Desk admins only, as a preview; off: nobody).

    GET /bureau/status                         {enabled, preview}: the app shows
                                               the chip only when enabled
    GET /bureau?lens=&before=&limit=           the chip feed, newest first
    GET /bureau/items/{official_id}            one item + "Earlier on this"
"""

from __future__ import annotations

from typing import Awaitable, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

import official_service as OS


def build_official_router(*, service, require_admin: Callable[..., Awaitable[dict]],
                          get_user: Callable[..., Awaitable[Optional[dict]]] = None,
                          admin_emails: Callable[[], set] = lambda: set()) -> APIRouter:
    router = APIRouter()

    @router.get("/health/official")
    async def health_official():
        return await service.health()

    @router.get("/official/shadow")
    async def shadow_items(limit: int = 40, include_filtered: bool = False,
                           _admin: dict = Depends(require_admin)):
        q = {} if include_filtered else {"status": {"$ne": "filtered"}}
        items = await service.db.official_items.find(q, {"_id": 0}).sort(
            "fetched_at", -1).limit(max(1, min(limit, 200))).to_list(200)
        return {"items": items, "mode": service.mode()}

    async def access(request: Request) -> Optional[str]:
        user = await get_user(request) if get_user else None
        is_admin = bool(user) and str(user.get("email", "")).lower() in admin_emails()
        return OS.reader_access(service.mode(), is_admin)

    @router.get("/bureau/status")
    async def bureau_status(request: Request):
        a = await access(request)
        return {"enabled": a is not None, "preview": a == "preview"}

    @router.get("/bureau")
    async def bureau_feed(request: Request, lens: Optional[str] = None, before: Optional[str] = None,
                          limit: int = 20):
        a = await access(request)
        if a is None:
            raise HTTPException(status_code=404, detail="Not available")
        return await OS.reader_feed(service.db, access=a, lens=lens, before=before, limit=limit,
                                    now=service.now(), health=await service.health())

    @router.get("/bureau/items/{official_id}")
    async def bureau_item(official_id: str, request: Request):
        a = await access(request)
        if a is None:
            raise HTTPException(status_code=404, detail="Not available")
        item = await OS.reader_item(service.db, official_id, access=a)
        if not item:
            raise HTTPException(status_code=404, detail="Not found")
        return item

    return router

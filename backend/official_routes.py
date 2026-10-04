"""The Bureau endpoints (lane L1: health + an admin peek at shadow items).

    GET /health/official          public: mode, per-source last run, counts,
                                  silence / broken alarms (no secrets, no items)
    GET /official/shadow?limit=   admin only: newest reader-facing items while
                                  OFFICIAL_MODE=shadow, for checking quality

Reader endpoints (the chip feed, item page, follows) arrive with app 1.14.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from fastapi import APIRouter, Depends


def build_official_router(*, service, require_admin: Callable[..., Awaitable[dict]]) -> APIRouter:
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

    return router

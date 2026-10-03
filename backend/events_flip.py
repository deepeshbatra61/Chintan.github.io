"""Switching News v2 events on and off (eng review OV4).

The switch is the EVENTS_MODE env var on Railway. sync_mode() runs at the start
of every events cycle and compares it with the mode last APPLIED (app_meta
events_applied); a change triggers exactly one of:

    shadow/off ─▶ live : go_live  — recompute every event in the 72h window in
                         live mode (writes event_hidden, leads, Desk folds)
    live ─▶ shadow/off : go_back  — clear everything live mode wrote on
                         articles, release event-made Desk folds, then rerun
                         the legacy keyword fold so Desk stories keep their
                         absorbed coverage

Both are idempotent and safe to re-run; a crash halfway leaves the applied
mode unchanged, so the next cycle simply tries again. Rollback = set
EVENTS_MODE=shadow on Railway; nothing else.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional

import events_service as S

logger = logging.getLogger(__name__)
LIVE_FIELDS = ("event_hidden", "outlets_count", "coverage_mix", "event_status")


async def applied_mode(db) -> str:
    doc = await db.app_meta.find_one({"_id": "events_applied"}) or {}
    return doc.get("mode") or "shadow"


async def go_live(db, now: datetime) -> int:
    since = (now - timedelta(hours=S.WINDOW_H)).isoformat()
    n = 0
    async for ev in db.events.find({"last_member_at": {"$gte": since}}, {"_id": 0, "event_id": 1}):
        await S.recompute_event(db, ev["event_id"], now, mode="live")
        n += 1
    return n


async def go_back(db, legacy_fold: Optional[Callable[[], Awaitable[int]]] = None) -> int:
    res = await db.articles.update_many({"event_hidden": {"$exists": True}},
                                        {"$unset": {f: "" for f in LIVE_FIELDS}})
    await db.articles.update_many({"merged_by": "events"}, {"$unset": {"merged_into": "", "merged_by": ""}})
    if legacy_fold:
        await legacy_fold()
    return res.modified_count


async def sync_mode(db, now: Optional[datetime] = None, mode: Optional[str] = None,
                    legacy_fold: Optional[Callable[[], Awaitable[int]]] = None) -> Optional[str]:
    """Apply a pending mode change; returns "go_live"/"go_back" when one ran."""
    now = now or datetime.now(timezone.utc)
    want = mode or S.current_mode()
    have = await applied_mode(db)
    action = None
    if want == "live" and have != "live":
        n = await go_live(db, now)
        action = "go_live"
        logger.warning(f"Events: switched ON ({n} events recomputed live)")
    elif want != "live" and have == "live":
        n = await go_back(db, legacy_fold)
        action = "go_back"
        logger.warning(f"Events: switched OFF ({n} articles restored)")
    if want != have:
        await db.app_meta.update_one({"_id": "events_applied"},
                                     {"$set": {"mode": want, "at": now.isoformat(), "action": action}},
                                     upsert=True)
    return action

"""Reader endpoints for News v2 stories (app 1.13).

    POST   /follows                 follow a developing story  {story_id}
    DELETE /follows/{story_id}      unfollow
    GET    /follows                 the sidebar's Following list (newest activity first)
    POST   /stories/{story_id}/seen record "looked at it now"; returns the previous
                                    seen_at so the app can draw "SINCE YOU LOOKED"

Identity comes ONLY from the session (get_user), as in push_routes: a request
body can never name an account. Story ids are either an event ("ev-…") or a
developing_stories container id; anything else is a 404, never stored.
"""

from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

MAX_FOLLOWS = 50
STORY_ID_MAX = 120
LIVE_STATUSES = ("developing", "early_report")


class FollowIn(BaseModel):
    story_id: str = Field(max_length=STORY_ID_MAX)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def story_summary(db, story_id: str) -> Optional[dict]:
    """Title / last activity / liveness for an event or a container, or None."""
    if not story_id or len(story_id) > STORY_ID_MAX:
        return None
    if story_id.startswith("ev-"):
        ev = await db.events.find_one({"event_id": story_id}, {"_id": 0})
        if not ev or (ev.get("desk") or {}).get("hidden"):
            return None
        lead = await db.articles.find_one({"article_id": ev.get("lead_article_id")}, {"_id": 0, "title": 1}) or {}
        return {"story_id": story_id, "title": lead.get("title") or "Developing story",
                "last_updated": ev.get("last_member_at"), "live": ev.get("status") in LIVE_STATUSES,
                "article_ids": ev.get("article_ids") or []}
    st = await db.developing_stories.find_one({"story_id": story_id}, {"_id": 0})
    if not st:
        return None
    return {"story_id": story_id, "title": st.get("title", ""), "last_updated": st.get("last_updated"),
            "live": bool(st.get("is_active")), "article_ids": st.get("article_ids") or []}


def build_events_router(*, db_getter: Callable[[], object],
                        get_user: Callable[[Request], Awaitable[Optional[dict]]]) -> APIRouter:
    router = APIRouter()

    async def _user(request: Request) -> dict:
        user = await get_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Sign in to follow stories")
        return user

    @router.post("/follows")
    async def follow(body: FollowIn, request: Request):
        user = await _user(request)
        db = db_getter()
        story = await story_summary(db, body.story_id)
        if not story or not story["live"]:
            raise HTTPException(status_code=404, detail="That story isn't developing any more")
        existing = await db.follows.find_one({"user_id": user["user_id"], "story_id": body.story_id})
        if not existing:
            if await db.follows.count_documents({"user_id": user["user_id"]}) >= MAX_FOLLOWS:
                raise HTTPException(status_code=409, detail=f"You can follow up to {MAX_FOLLOWS} stories")
            await db.follows.insert_one({"user_id": user["user_id"], "story_id": body.story_id,
                                         "created_at": _now().isoformat(), "pushes": []})
            # Following counts as looking at it now.
            await db.story_seen.update_one({"user_id": user["user_id"], "story_id": body.story_id},
                                           {"$set": {"seen_at": _now().isoformat()}}, upsert=True)
        return {"following": True, "story_id": body.story_id}

    @router.delete("/follows/{story_id}")
    async def unfollow(story_id: str, request: Request):
        user = await _user(request)
        await db_getter().follows.delete_one({"user_id": user["user_id"], "story_id": story_id[:STORY_ID_MAX]})
        return {"following": False, "story_id": story_id}

    @router.get("/follows")
    async def list_follows(request: Request):
        user = await _user(request)
        db = db_getter()
        out = []
        async for f in db.follows.find({"user_id": user["user_id"]}, {"_id": 0}):
            story = await story_summary(db, f["story_id"])
            if not story or not story["live"]:
                # D8: a follow ends when its story settles or disappears.
                await db.follows.delete_one({"user_id": user["user_id"], "story_id": f["story_id"]})
                continue
            seen = await db.story_seen.find_one({"user_id": user["user_id"], "story_id": f["story_id"]}) or {}
            new = 0
            if story["article_ids"]:
                q = {"article_id": {"$in": story["article_ids"]}}
                if seen.get("seen_at"):
                    q["published_at"] = {"$gt": seen["seen_at"]}
                new = await db.articles.count_documents(q) if seen.get("seen_at") else 0
            out.append({"story_id": f["story_id"], "title": story["title"],
                        "last_updated": story["last_updated"], "new_count": new})
        out.sort(key=lambda x: x.get("last_updated") or "", reverse=True)
        return {"follows": out, "new_total": sum(x["new_count"] for x in out)}

    @router.post("/stories/{story_id}/seen")
    async def mark_seen(story_id: str, request: Request):
        user = await _user(request)
        db = db_getter()
        if not await story_summary(db, story_id):
            raise HTTPException(status_code=404, detail="Story not found")
        prev = await db.story_seen.find_one({"user_id": user["user_id"], "story_id": story_id}) or {}
        now = _now().isoformat()
        await db.story_seen.update_one({"user_id": user["user_id"], "story_id": story_id},
                                       {"$set": {"seen_at": now}}, upsert=True)
        return {"story_id": story_id, "previous_seen_at": prev.get("seen_at"), "seen_at": now}

    return router

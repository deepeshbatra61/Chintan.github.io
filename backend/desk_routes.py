"""Chintan Desk HTTP API, mounted at /api/desk. Built by a factory that is
handed its dependencies (database, auth, research, email) so it never
imports server.py: that keeps it testable with an in-memory database and
keeps the security code out of the 6k-line server module (D4).

Every route runs two gates before any work:
    _gate      proxy secret wrong/missing → 404, as if the route didn't exist
    _session   no live session, or the email left ADMIN_EMAILS → 401;
               state-changing requests also need the session's CSRF token → 403
Login is the only route behind _gate alone.

    POST /desk/login            email + password + code, all at once
    POST /desk/logout           this session
    POST /desk/logout-all       every session for this admin
    GET  /desk/me               who am I + csrf + alert banner flag
    POST /desk/check            existing coverage of a topic (no spend)
    POST /desk/drafts           create (or reuse) a draft, research in background
    GET  /desk/drafts/{id}      poll a draft
    PATCH /desk/drafts/{id}     edit before publishing
    POST /desk/drafts/{id}/publish | /discard
    POST /desk/boost            give an existing article/story a heat level
    GET  /desk/items            drafts + published items with live status
    POST /desk/stories/{id}/end | /extend
    POST /desk/articles/{id}/unpublish
    POST /desk/articles/{id}/restore/{absorbed_id}   undo one absorbed article
"""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import timedelta
from typing import Awaitable, Callable, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

import desk
import desk_auth as A
from pagemeta import looks_like_url
from push import breaking_copy as push_copy

try:  # real driver in production; mongomock raises the same class
    from pymongo.errors import DuplicateKeyError
except ImportError:  # pragma: no cover
    class DuplicateKeyError(Exception):
        pass


class LoginBody(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)
    code: str = Field(max_length=12)


class TopicBody(BaseModel):
    topic: str = Field(max_length=desk.TOPIC_MAX)
    category: str = Field(max_length=40)
    news_type: str = Field(max_length=20)
    heat: int
    force: bool = False           # "Create anyway" past a dedup match


class DraftEdit(BaseModel):
    headline: Optional[str] = Field(default=None, max_length=desk.HEADLINE_MAX)
    summary: Optional[str] = Field(default=None, max_length=desk.SUMMARY_MAX)
    points: Optional[List[str]] = None
    category: Optional[str] = Field(default=None, max_length=40)
    heat: Optional[int] = None
    news_type: Optional[str] = Field(default=None, max_length=20)
    image_url: Optional[str] = Field(default=None, max_length=desk.IMAGE_URL_MAX)
    keywords: Optional[List[str]] = None
    single_source_reason: Optional[str] = Field(default=None, max_length=500)
    long_running: Optional[bool] = None
    national: Optional[bool] = None      # push: Breaking goes to every reader
    sensitive: Optional[bool] = None     # push: sober copy, no photo, no wit


class BoostBody(BaseModel):
    type: str = Field(max_length=10)        # "article" | "story"
    id: str = Field(max_length=120)
    heat: int


class PushSwitchBody(BaseModel):
    enabled: bool
    confirm: bool = False


class BreakingBody(BaseModel):
    article_id: str = Field(max_length=120)
    text: Optional[str] = Field(default=None, max_length=300)
    confirm: Optional[str] = Field(default=None, max_length=10)


_EDITABLE = set(DraftEdit.model_fields)
_PUBLIC_DRAFT_FIELDS = (
    "draft_id", "topic", "category", "news_type", "heat", "status", "fail_reason",
    "headline", "summary", "points", "keywords", "citations", "domain_count",
    "image_url", "single_source_reason", "long_running", "national", "sensitive", "created_at", "updated_at",
    "published_ref", "attribution", "source_url", "note",
)
FAIL_MESSAGES = {
    "cap": "Today's research limit is used up. It resets at midnight UTC.",
    "timeout": "Research took too long. Try again in a minute.",
    "error": "Research failed on our side. Try again in a minute.",
    "tool_error": "Web search was unavailable. Try again shortly.",
    "unparseable": "Research came back in an unusable shape. Try again or rephrase the topic.",
    "no_sources": "No source could be found for this. Too early, or worth rephrasing.",
    "stale": "Research was interrupted (server restart). Try again.",
    "link_unreadable": "That link couldn't be opened (it may block previews or need a login). Paste the headline instead.",
}


def build_desk_router(
    *,
    db,
    auth: A.DeskAuth,
    proxy_secret: Callable[[], Optional[str]],
    admin_emails: Callable[[], set],
    research: Callable[[str, Optional[dict]], Awaitable[dict]],
    fetch_meta: Callable[[str], Awaitable[Optional[dict]]],
    send_email: Callable[[str, str, str], Awaitable[bool]],
    registrable_domain: Callable[[str], str],
    suggest_category: Callable[[str], str],
    default_image: str,
    logger,
    push=None,                                   # push_service.PushService (optional)
    push_test_email: Callable[[], str] = lambda: "",
) -> APIRouter:
    router = APIRouter(prefix="/desk")
    background: set = set()          # strong refs so tasks can't be GC'd mid-flight

    # ── gates ────────────────────────────────────────────────────────────────
    async def _gate(request: Request) -> dict:
        if not A.proxy_ok(request.headers.get("x-desk-proxy"), proxy_secret()):
            raise HTTPException(status_code=404, detail="Not Found")
        return {"ip": A.clean_ip(request.headers.get("x-desk-client-ip")),
                "ua": (request.headers.get("user-agent") or "")[:300]}

    async def _session(request: Request, ctx: dict = Depends(_gate)) -> dict:
        session = await auth.session_for(request.headers.get("x-desk-session"))
        if not session or session.get("email", "").lower() not in admin_emails():
            raise HTTPException(status_code=401, detail="Sign in again.")
        if request.method not in ("GET", "HEAD") and not A.constant_time_equals(
                request.headers.get("x-desk-csrf"), session.get("csrf")):
            raise HTTPException(status_code=403, detail="Refresh the page and try again.")
        return {**ctx, "session": session, "email": session["email"]}

    async def _audit(ctx: dict, action: str, **detail):
        await auth.audit(action, email=ctx.get("email", ""), ip=ctx.get("ip", ""),
                         ua=ctx.get("ua", ""), detail=detail)

    def _spawn(coro):
        task = asyncio.create_task(coro)
        background.add(task)
        task.add_done_callback(background.discard)

    # ── auth ─────────────────────────────────────────────────────────────────
    @router.post("/login")
    async def login(body: LoginBody, ctx: dict = Depends(_gate)):
        email = body.email.strip().lower()
        keys = [f"acct:{email}", f"ip:{ctx['ip']}"]
        until = await auth.locked_until(keys)
        if until:
            await auth.audit("login_blocked", email=email, ip=ctx["ip"], ua=ctx["ua"])
            raise HTTPException(status_code=429, detail="Too many attempts. Try again in 15 minutes.")

        admin = None
        if email in admin_emails():
            admin = await auth.authenticate(email, body.password, body.code)
        if not admin:
            newly_locked = await auth.record_failure(keys)
            await auth.audit("login_fail", email=email, ip=ctx["ip"], ua=ctx["ua"])
            if newly_locked and email in admin_emails():
                await send_email(email, "Chintan Desk locked after failed sign-ins",
                                 f"5 failed sign-ins to the Chintan Desk from {ctx['ip']}.\n"
                                 f"Sign-in is locked for 15 minutes. If this wasn't you, "
                                 f"run: python scripts/desk_admin.py reset-password {email}")
            raise HTTPException(status_code=401, detail=A.GENERIC_LOGIN_ERROR)

        await auth.clear_failures(keys)
        token, csrf = await auth.create_session(admin, ctx["ip"], ctx["ua"])
        alert_ok = await send_email(email, "New Chintan Desk sign-in",
                                    f"Signed in to the Chintan Desk from {ctx['ip']}.\n"
                                    f"Device: {ctx['ua'][:120]}\n\nIf this wasn't you, run:\n"
                                    f"python scripts/desk_admin.py reset-password {email}")
        if not alert_ok:
            await db.desk_sessions.update_one({"token_hash": A.hash_token(token)},
                                              {"$set": {"alert_failed": True}})
        await auth.audit("login_ok", email=email, ip=ctx["ip"], ua=ctx["ua"],
                         detail={"alert_sent": bool(alert_ok)})
        return {"token": token, "csrf": csrf, "email": email, "alert_failed": not alert_ok,
                "idle_minutes": int(A.SESSION_IDLE.total_seconds() // 60)}

    @router.post("/logout")
    async def logout(request: Request, ctx: dict = Depends(_session)):
        await auth.revoke(request.headers.get("x-desk-session"))
        await _audit(ctx, "logout")
        return {"ok": True}

    @router.post("/logout-all")
    async def logout_all(ctx: dict = Depends(_session)):
        n = await auth.revoke_all(ctx["session"]["admin_id"])
        await _audit(ctx, "logout_all", sessions=n)
        return {"ok": True, "sessions": n}

    @router.get("/me")
    async def me(ctx: dict = Depends(_session)):
        s = ctx["session"]
        return {"email": s["email"], "csrf": s["csrf"], "alert_failed": bool(s.get("alert_failed"))}

    # ── dedup ────────────────────────────────────────────────────────────────
    async def _candidates(topic: str) -> list:
        exact = []
        if looks_like_url(topic):
            # The ingest keys every API article on its URL, so a link we
            # already carry is an exact duplicate, found without any fetch.
            hit = await db.articles.find_one(
                {"url": topic.strip(), "merged_into": {"$exists": False}},
                {"_id": 0, "article_id": 1, "title": 1, "category": 1, "source": 1})
            if hit:
                exact = [{"type": "article", "id": hit["article_id"], "title": hit.get("title", ""),
                          "score": 1.0, "detail": f"Same link · {hit.get('source', '')}".strip(" ·")}]
        since = (desk.utcnow() - timedelta(days=7)).isoformat()
        articles = await db.articles.find(
            {"published_at": {"$gte": since}, "merged_into": {"$exists": False}},
            {"_id": 0, "article_id": 1, "title": 1, "description": 1, "category": 1, "source": 1},
        ).to_list(3000)
        stories = await db.developing_stories.find(
            {"is_active": True}, {"_id": 0, "story_id": 1, "title": 1, "keywords": 1, "kind": 1, "article_ids": 1},
        ).to_list(200)
        fuzzy = [m for m in desk.dedup_candidates(topic, articles, stories)
                 if not exact or m["id"] != exact[0]["id"]]
        return (exact + fuzzy)[:5]

    @router.post("/check")
    async def check(body: TopicBody, ctx: dict = Depends(_session)):
        errors = desk.validate_submit(body.topic, body.category, body.news_type, body.heat)
        return {"errors": errors, "matches": await _candidates(body.topic),
                "suggested_category": suggest_category(body.topic)}

    # ── drafts ───────────────────────────────────────────────────────────────
    def _public(d: dict) -> dict:
        out = {k: d.get(k) for k in _PUBLIC_DRAFT_FIELDS}
        out["fail_message"] = FAIL_MESSAGES.get(d.get("fail_reason") or "", None)
        out["errors"] = desk.validate_draft(d) if d.get("status") == "ready" else []
        return out

    async def _sweep_stale(d: dict) -> dict:
        """D11e: a job whose process died never finishes; call it."""
        if d.get("status") == "researching":
            started = desk.parse_dt(d.get("created_at"))
            if started and desk.utcnow() - started > timedelta(minutes=desk.RESEARCHING_STALE_MIN):
                await db.desk_drafts.update_one({"draft_id": d["draft_id"], "status": "researching"},
                                                {"$set": {"status": "failed", "fail_reason": "stale"}})
                d = {**d, "status": "failed", "fail_reason": "stale"}
        return d

    async def _first_image(urls: list) -> str:
        for u in urls[:3]:
            meta = await fetch_meta(u)
            if meta and meta.get("image"):
                return meta["image"]
        return ""

    async def _run_research(draft_id: str, topic: str):
        """Link or headline in; a reviewable draft out.

            link ─▶ read its headline/image/description (pagemeta, SSRF-safe)
                 ─▶ research anchored on that article
            text ─▶ research on the words
            then: the pasted link leads the sources; image = the link's, or
            the first source page that has one.
        If research finds nothing but the link itself was readable, the draft
        is built from that one article and marked single-source, which needs
        the owner's stated reason before it can publish (D9)."""
        source = None
        try:
            if looks_like_url(topic):
                source = await fetch_meta(topic.strip())
                if source:
                    source["url"] = topic.strip()
            query = (source or {}).get("title") or desk.topic_text(topic) or topic
            result = await research(query, source)
        except Exception as e:  # research is already defensive; belt and braces
            logger.error(f"desk research crashed for {draft_id}: {e}")
            result = {"ok": False, "reason": "error"}

        now = desk.utcnow().isoformat()
        note = None
        if not result.get("ok") and source and source.get("title") and source.get("description"):
            result = {"ok": True, "headline": source["title"], "summary": source["description"],
                      "points": [], "keywords": [], "citations": [], "domain_count": 0}
            note = "Web research found nothing beyond your link yet, so this draft is built from that article alone."

        if not result.get("ok"):
            update = {"status": "failed", "fail_reason": result.get("reason", "error"), "updated_at": now}
            if looks_like_url(topic) and not source:
                update["fail_reason"] = "link_unreadable"
        else:
            citations = list(result["citations"])
            if source:
                citations = [{"url": source["url"], "title": source.get("title", "")}] +                     [c for c in citations if c.get("url") != source["url"]]
            domains = len({registrable_domain(c["url"]) for c in citations if c.get("url")})
            image = (source or {}).get("image") or await _first_image([c["url"] for c in citations])
            update = {
                "status": "ready", "fail_reason": None, "updated_at": now, "note": note,
                "headline": result["headline"], "summary": result["summary"],
                "points": result["points"], "keywords": result["keywords"],
                "citations": citations, "domain_count": domains, "image_url": image,
                "source_url": (source or {}).get("url"),
                "attribution": desk.attribution(citations, registrable_domain),
            }
        # Only a still-researching draft is updated: a discard mid-research wins.
        await db.desk_drafts.update_one({"draft_id": draft_id, "status": "researching"}, {"$set": update})

    @router.post("/drafts")
    async def create_draft(body: TopicBody, ctx: dict = Depends(_session)):
        errors = desk.validate_submit(body.topic, body.category, body.news_type, body.heat)
        if looks_like_url(body.topic) and not body.topic.strip().lower().startswith("https://"):
            errors.append("Paste the https:// version of the link.")
        if errors:
            raise HTTPException(status_code=422, detail=" ".join(errors))
        if not body.force:
            matches = await _candidates(body.topic)
            if matches:
                return {"matches": matches, "draft": None}

        key = desk.normalize_topic(body.topic)
        now = desk.utcnow()
        # D3: the same topic within DRAFT_REUSE_MIN returns the same draft, so a
        # double-tap or a retry after a dropped connection never pays twice.
        # The lock row's unique _id makes this safe under simultaneous requests.
        try:
            await db.desk_draft_locks.insert_one({"_id": key, "created_at": now.isoformat(), "draft_id": None})
        except DuplicateKeyError:
            lock = await db.desk_draft_locks.find_one({"_id": key})
            fresh = lock and desk.parse_dt(lock.get("created_at")) and \
                now - desk.parse_dt(lock["created_at"]) < timedelta(minutes=desk.DRAFT_REUSE_MIN)
            existing = lock and lock.get("draft_id") and await db.desk_drafts.find_one(
                {"draft_id": lock["draft_id"], "status": {"$in": ["researching", "ready"]}}, {"_id": 0})
            if fresh and existing:
                return {"matches": [], "draft": _public(await _sweep_stale(existing)), "reused": True}
            if fresh and not lock.get("draft_id"):
                raise HTTPException(status_code=409, detail="Already starting this topic, one moment.")
            await db.desk_draft_locks.update_one({"_id": key}, {"$set": {"created_at": now.isoformat(), "draft_id": None}})

        draft = {
            "draft_id": "dft_" + uuid.uuid4().hex[:16], "topic": body.topic.strip(), "topic_key": key,
            "category": body.category, "news_type": body.news_type, "heat": body.heat,
            "status": "researching", "fail_reason": None, "headline": "", "summary": "",
            "points": [], "keywords": [], "citations": [], "domain_count": 0,
            "image_url": "", "single_source_reason": "", "long_running": False,
            "source_url": None, "note": None,
            "created_at": now.isoformat(), "updated_at": now.isoformat(),
            "created_by": ctx["email"], "published_ref": None,
        }
        await db.desk_drafts.insert_one(dict(draft))
        await db.desk_draft_locks.update_one({"_id": key}, {"$set": {"draft_id": draft["draft_id"]}})
        await _audit(ctx, "draft_create", draft_id=draft["draft_id"], topic=draft["topic"], forced=body.force)
        _spawn(_run_research(draft["draft_id"], draft["topic"]))
        return {"matches": [], "draft": _public(draft)}

    async def _get_draft(draft_id: str) -> dict:
        d = await db.desk_drafts.find_one({"draft_id": draft_id}, {"_id": 0})
        if not d:
            raise HTTPException(status_code=404, detail="Draft not found.")
        return await _sweep_stale(d)

    @router.get("/drafts/{draft_id}")
    async def get_draft(draft_id: str, ctx: dict = Depends(_session)):
        return _public(await _get_draft(draft_id))

    @router.patch("/drafts/{draft_id}")
    async def edit_draft(draft_id: str, body: DraftEdit, ctx: dict = Depends(_session)):
        d = await _get_draft(draft_id)
        if d["status"] != "ready":
            raise HTTPException(status_code=409, detail="Only a ready draft can be edited.")
        changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if k in _EDITABLE}
        for text_field in ("headline", "summary", "image_url", "single_source_reason"):
            if text_field in changes and changes[text_field] is not None:
                changes[text_field] = changes[text_field].strip()
        if "points" in changes and changes["points"] is not None:
            changes["points"] = [p.strip() for p in changes["points"] if p and p.strip()][:desk.POINTS_MAX]
        if "keywords" in changes and changes["keywords"] is not None:
            changes["keywords"] = [k.strip().lower()[:40] for k in changes["keywords"] if k and k.strip()][:desk.KEYWORDS_MIN_DEVELOPING + 2]
        changes["updated_at"] = desk.utcnow().isoformat()
        await db.desk_drafts.update_one({"draft_id": draft_id, "status": "ready"}, {"$set": changes})
        await _audit(ctx, "draft_edit", draft_id=draft_id, fields=sorted(k for k in changes if k != "updated_at"))
        return _public({**d, **changes})

    @router.post("/drafts/{draft_id}/discard")
    async def discard_draft(draft_id: str, ctx: dict = Depends(_session)):
        d = await _get_draft(draft_id)
        if d["status"] == "published":
            raise HTTPException(status_code=409, detail="Already published; unpublish it instead.")
        await db.desk_drafts.update_one({"draft_id": draft_id}, {"$set": {"status": "discarded"}})
        await db.desk_draft_locks.delete_one({"_id": d.get("topic_key"), "draft_id": draft_id})
        await _audit(ctx, "draft_discard", draft_id=draft_id)
        return {"ok": True}

    @router.post("/drafts/{draft_id}/publish")
    async def publish(draft_id: str, ctx: dict = Depends(_session)):
        d = await _get_draft(draft_id)
        if d["status"] != "ready":
            raise HTTPException(status_code=409, detail="This draft isn't ready to publish.")
        errors = desk.validate_draft(d)
        if errors:
            raise HTTPException(status_code=422, detail=" ".join(errors))
        # Claim it first, so a double-tap can't publish twice.
        claim = await db.desk_drafts.update_one({"draft_id": draft_id, "status": "ready"},
                                                {"$set": {"status": "publishing"}})
        if getattr(claim, "modified_count", 1) == 0:
            raise HTTPException(status_code=409, detail="Already publishing.")

        now = desk.utcnow()
        now_iso = now.isoformat()
        article_id = "desk_" + uuid.uuid4().hex[:12]
        single = (d.get("domain_count") or 0) == 1
        source = desk.attribution(d["citations"], registrable_domain)
        if single:
            source = source.replace("Chintan Desk · via", "Chintan Desk · single source:", 1)
        body_text = d["summary"] + ("\n\n" + "\n".join(f"• {p}" for p in d["points"]) if d["points"] else "")
        article = {
            "article_id": article_id, "title": d["headline"],
            "description": d["summary"][:300], "content": body_text, "summary": d["summary"],
            "what": d["summary"], "why": "", "context": "", "impact": "",
            "beats": [{"hook": p, "body": ""} for p in d["points"]],
            "category": d["category"], "subcategory": None,
            "source": source, "author": None,
            "published_at": now_iso, "rank_at": now_iso,          # D8: the Desk has no delay
            "image_url": d.get("image_url") or default_image,
            "is_developing": d["news_type"] == "developing", "is_breaking": d["heat"] == desk.HEAT_BREAKING,
            "likes": 0, "dislikes": 0, "view_count": 0,
            "reading_time_sec": max(30, len(body_text.split()) * 60 // 200),
            "url": d["citations"][0]["url"],
            "origin": "desk", "heat": d["heat"], "heat_from": now_iso,
            "citations": d["citations"], "keywords": d.get("keywords") or [],
            "single_source": single, "single_source_reason": d.get("single_source_reason") if single else None,
            "desk_draft_id": draft_id,
            "desk_national": bool(d.get("national")), "desk_sensitive": bool(d.get("sensitive")),
            # D11f: approved text is final. These keep the hourly summariser
            # and the (currently off) LLM categoriser from rewriting it.
            "claude_summarized": True, "claude_categorized": True, "claude_skip": True,
        }
        if d["news_type"] == "normal":
            article["absorb_until"] = (now + timedelta(hours=desk.ABSORB_WINDOW_H)).isoformat()
        await db.articles.insert_one(dict(article))

        ref = {"type": "article", "id": article_id}
        if d["news_type"] == "developing":
            slug = re.sub(r"[^a-z0-9]+", "-", d["headline"].lower()).strip("-")[:40]
            story_id = f"desk-{slug}-{uuid.uuid4().hex[:4]}"
            await db.developing_stories.insert_one({
                "story_id": story_id, "title": d["headline"], "theme": d["category"].lower(),
                "category": d["category"], "keywords": d["keywords"], "source": "desk", "kind": "desk",
                "is_active": True, "state_summary": d["summary"], "citations": d["citations"],
                "article_ids": [article_id], "detected_at": now_iso,
                **desk.lifecycle_fields(d["heat"], now, bool(d.get("long_running"))),
                "extra_h": 0, "desk_draft_id": draft_id,
            })
            await db.articles.update_one({"article_id": article_id}, {"$set": {"desk_story_id": story_id}})
            ref = {"type": "story", "id": story_id, "article_id": article_id}

        await db.desk_drafts.update_one({"draft_id": draft_id}, {"$set": {
            "status": "published", "published_ref": ref, "published_at": now_iso}})
        await db.desk_draft_locks.delete_one({"_id": d.get("topic_key")})
        await _audit(ctx, "publish", draft_id=draft_id, ref=ref, heat=d["heat"],
                     single_source=single, reason=d.get("single_source_reason") if single else None)
        return {"ok": True, "ref": ref}

    # ── boost existing ───────────────────────────────────────────────────────
    @router.post("/boost")
    async def boost(body: BoostBody, ctx: dict = Depends(_session)):
        if body.heat not in desk.HEAT_LABELS or body.type not in ("article", "story"):
            raise HTTPException(status_code=422, detail="Pick a heat level.")
        now_iso = desk.utcnow().isoformat()
        if body.type == "article":
            res = await db.articles.update_one({"article_id": body.id},
                                               {"$set": {"heat": body.heat, "heat_from": now_iso, "boosted": True}})
        else:
            res = await db.developing_stories.update_one({"story_id": body.id, "is_active": True},
                                                         {"$set": {"heat": body.heat, "heat_from": now_iso}})
        if getattr(res, "matched_count", 1) == 0:
            raise HTTPException(status_code=404, detail="That item no longer exists.")
        await _audit(ctx, "boost", type=body.type, id=body.id, heat=body.heat)
        return {"ok": True}

    # ── manage published ─────────────────────────────────────────────────────
    @router.get("/items")
    async def items(ctx: dict = Depends(_session)):
        drafts = await db.desk_drafts.find(
            {"status": {"$in": ["researching", "ready", "failed", "publishing"]}}, {"_id": 0},
        ).sort("created_at", -1).to_list(50)
        drafts = [_public(await _sweep_stale(d)) for d in drafts]

        now = desk.utcnow()
        since = (now - timedelta(days=7)).isoformat()
        arts = await db.articles.find(
            {"origin": "desk", "published_at": {"$gte": since}}, {"_id": 0},
        ).sort("published_at", -1).to_list(100)
        published = []
        for a in arts:
            absorbed = await db.articles.find(
                {"merged_into": a["article_id"]},
                {"_id": 0, "article_id": 1, "title": 1, "source": 1}).to_list(50)
            item = {"type": "article", "id": a["article_id"], "title": a["title"], "category": a["category"],
                    "heat": a.get("heat"), "published_at": a["published_at"], "hidden": bool(a.get("desk_hidden")),
                    "single_source": bool(a.get("single_source")), "absorbed": absorbed,
                    "pinned": desk.article_is_pinned(a, now), "story": None}
            sid = a.get("desk_story_id")
            if sid:
                s = await db.developing_stories.find_one({"story_id": sid}, {"_id": 0})
                if s:
                    decision, reason, closes_at = desk.lifecycle_decision(s, now)
                    since_24 = (now - timedelta(hours=24)).isoformat()
                    item["story"] = {
                        "id": sid, "active": bool(s.get("is_active")), "ended_reason": s.get("ended_reason"),
                        "updates": len(s.get("article_ids") or []),
                        "updates_24h": await db.articles.count_documents(
                            {"article_id": {"$in": s.get("article_ids") or []}, "rank_at": {"$gte": since_24}}),
                        "closes_at": closes_at if s.get("is_active") else None,
                        "long_running": bool(s.get("long_running")),
                    }
            published.append(item)
        return {"drafts": drafts, "published": published}

    async def _story(story_id: str) -> dict:
        s = await db.developing_stories.find_one({"story_id": story_id, "kind": "desk"}, {"_id": 0})
        if not s:
            raise HTTPException(status_code=404, detail="Story not found.")
        return s

    @router.post("/stories/{story_id}/end")
    async def end_story(story_id: str, ctx: dict = Depends(_session)):
        await _story(story_id)
        await db.developing_stories.update_one({"story_id": story_id}, {"$set": {
            "is_active": False, "ended_reason": "manual", "ended_at": desk.utcnow().isoformat()}})
        await _audit(ctx, "story_end", story_id=story_id)
        return {"ok": True}

    @router.post("/stories/{story_id}/extend")
    async def extend_story(story_id: str, ctx: dict = Depends(_session)):
        s = await _story(story_id)
        fields = desk.extended_fields(s, desk.utcnow())
        fields.update({"is_active": True, "ended_reason": None})
        await db.developing_stories.update_one({"story_id": story_id}, {"$set": fields})
        await _audit(ctx, "story_extend", story_id=story_id, fields=fields)
        return {"ok": True, **fields}

    @router.post("/articles/{article_id}/unpublish")
    async def unpublish(article_id: str, ctx: dict = Depends(_session)):
        a = await db.articles.find_one({"article_id": article_id, "origin": "desk"}, {"_id": 0})
        if not a:
            raise HTTPException(status_code=404, detail="Article not found.")
        await db.articles.update_one({"article_id": article_id}, {"$set": {"desk_hidden": True}})
        # Anything it absorbed goes back to the feed: it was only hidden because this was there.
        await db.articles.update_many({"merged_into": article_id}, {"$unset": {"merged_into": ""}})
        if a.get("desk_story_id"):
            await db.developing_stories.update_one({"story_id": a["desk_story_id"]}, {"$set": {
                "is_active": False, "ended_reason": "unpublished"}})
        await _audit(ctx, "unpublish", article_id=article_id)
        return {"ok": True}

    @router.post("/articles/{article_id}/restore/{absorbed_id}")
    async def restore_absorbed(article_id: str, absorbed_id: str, ctx: dict = Depends(_session)):
        res = await db.articles.update_one({"article_id": absorbed_id, "merged_into": article_id},
                                           {"$unset": {"merged_into": ""}, "$set": {"absorb_exempt": True}})
        if getattr(res, "matched_count", 1) == 0:
            raise HTTPException(status_code=404, detail="Nothing to restore.")
        await _audit(ctx, "absorb_undo", article_id=article_id, absorbed_id=absorbed_id)
        return {"ok": True}

    # ── push (Desk Push panel, go-live switch, test push, Breaking) ──────────
    if push is not None:
        @router.get("/push")
        async def push_panel(ctx: dict = Depends(_session)):
            return {**(await push.stats()), "next_slot": await push.next_slot_preview(),
                    "test_email_set": bool(push_test_email())}

        @router.post("/push/enabled")
        async def push_switch(body: PushSwitchBody, ctx: dict = Depends(_session)):
            # Going live is deliberate (confirm); stopping is instant (DR-16A).
            if body.enabled and not body.confirm:
                raise HTTPException(status_code=409, detail="Confirm to turn push on.")
            state = await push.set_enabled(body.enabled, ctx["email"])
            await _audit(ctx, "push_on" if body.enabled else "push_off")
            return state

        @router.post("/push/test")
        async def push_test(ctx: dict = Depends(_session)):
            res = await push.test_push(push_test_email())
            await _audit(ctx, "push_test", ok=res.get("ok"))
            return res

        async def _breaking_article(article_id: str) -> dict:
            a = await db.articles.find_one({"article_id": article_id}, {"_id": 0})
            if not a:
                raise HTTPException(status_code=404, detail="That story no longer exists.")
            return a

        @router.post("/push/breaking/preview")
        async def breaking_preview(body: BreakingBody, ctx: dict = Depends(_session)):
            a = await _breaking_article(body.article_id)
            national = bool(a.get("desk_national"))
            title, text = push_copy(body.text or a.get("title", ""))
            already = await db.push_breaking.find_one({"_id": body.article_id})
            return {"title": title, "body": text, "category": a.get("category"), "national": national,
                    "already_sent": bool(already),
                    "reach": await push.reach(body.article_id, a.get("category") or "", national)}

        @router.post("/push/breaking/send")
        async def breaking_send(body: BreakingBody, ctx: dict = Depends(_session)):
            if (body.confirm or "") != "SEND":
                raise HTTPException(status_code=422, detail="Type SEND to confirm.")
            a = await _breaking_article(body.article_id)
            text = (body.text or a.get("title", "")).strip()
            if not text:
                raise HTTPException(status_code=422, detail="The notification needs some text.")
            # One Breaking push per story, ever: a double-click or a second tab
            # loses here instead of interrupting everyone twice.
            try:
                await db.push_breaking.insert_one({"_id": body.article_id, "by": ctx["email"],
                                                   "at": desk.utcnow(), "text": text})
            except DuplicateKeyError:
                raise HTTPException(status_code=409, detail="This story was already sent as Breaking.")
            res = await push.send_breaking(story_id=body.article_id, text=text,
                                           category=a.get("category") or "", national=bool(a.get("desk_national")))
            if not res.get("ok"):
                await db.push_breaking.delete_one({"_id": body.article_id})
                raise HTTPException(status_code=409, detail=res.get("error") or "Push is switched off.")
            await _audit(ctx, "push_breaking", article_id=body.article_id, sent=res["sent"],
                         failed=res["failed"], held=res["held"])
            return res

    return router

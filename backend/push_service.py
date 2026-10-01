"""Push with I/O: Firebase sender, device registry, the slot scheduler, Breaking
sends, open tracking, Desk stats and owner alerts. Rules live in push.py.

Scheduler tick (every 60s, started in server lifespan):

    env PUSH_ENABLED=false or Desk switch off ─▶ sweep stale claims only
    for each time zone that has signed-in devices:
      prep  (slot-60m .. slot+30m): per reader with that slot on and no prep yet
            build_brief ─▶ pin (valid until next slot) ─▶ hook LLM (8s) ─▶ compose copy
            ─▶ push_prep {_id: user|slot|date}
      send  (slot .. slot+30m): per reader
            brief already read today? ─▶ claim "skipped/read"
            last push < 90 min ago?   ─▶ claim "skipped/gap"
            claim {_id: user|slot|date} (unique; a second replica loses here)
            ─▶ FCM v1 per device ─▶ error table ─▶ push_log ─▶ claim sent | failed
    sweep: claims still "claimed" 10 min after their window ─▶ "stale" + owner alert

Breaking (Desk, explicit): reach() counts first; send_breaking() recounts at
send time, holds per reader (quiet | cap_day | cap_week | gap | dup), sends,
and returns a receipt.
"""

import asyncio
import hashlib
import html as _html
import logging
import secrets
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Dict, List, Optional, Tuple

import brief_service
import push as P

try:  # pymongo is always present in production; tests use mongomock's.
    from pymongo.errors import DuplicateKeyError
except Exception:  # pragma: no cover
    DuplicateKeyError = Exception  # type: ignore

MAX_DEVICES_PER_USER = 10
LLM_CONCURRENCY = 5
HOOK_TIMEOUT_S = 8
RETRY_BACKOFF_S = (2, 8)
ALERT_EVERY = timedelta(hours=6)
DEDUPE_STORY = timedelta(hours=48)
FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"


def _utc(dt):
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ── Firebase sender ──────────────────────────────────────────────────────────

def parse_service_account(raw: Optional[str]) -> Tuple[Optional[dict], Optional[str]]:
    """Read FIREBASE_SERVICE_ACCOUNT as pasted into Railway. Tolerates the
    usual paste damage: surrounding quotes, base64, and the private key's
    "\\n" escapes turned into real line breaks. Returns (account, None) or
    (None, reason). The reason never contains any part of the key."""
    import base64
    import json as _json
    raw = (raw or "").strip()
    if not raw:
        return None, "FIREBASE_SERVICE_ACCOUNT isn't set on the server."
    raw = raw.lstrip("﻿")
    if not raw.startswith("{") and '"type"' in raw and ":" in raw:
        try:                                             # contents pasted without the outer { }
            wrapped = "{" + raw.strip().rstrip(",") + "}"
            if isinstance(_json.loads(wrapped, strict=False), dict):
                raw = wrapped
        except ValueError:
            pass
    if raw.startswith('"'):
        try:                                             # the JSON file pasted as a JSON string
            decoded = _json.loads(raw, strict=False)
            if isinstance(decoded, str):
                raw = decoded.strip()
        except ValueError:
            pass
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
        raw = raw[1:-1].strip()
    raw = raw.lstrip("﻿")                           # BOM from some editors
    if raw.upper().startswith("FIREBASE_SERVICE_ACCOUNT"):  # name pasted into the value
        raw = raw.split("=", 1)[1].strip() if "=" in raw else ""
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
            raw = raw[1:-1].strip()
    if not raw.startswith("{"):
        if raw.startswith("-----BEGIN"):
            return None, ("FIREBASE_SERVICE_ACCOUNT holds only the private key. Paste the WHOLE "
                          "downloaded .json file instead (it starts with { and contains the key inside).")
        if raw.lower().endswith(".json") or ":\\" in raw[:4] or raw.startswith(("/", "~", "C:", "c:")):
            return None, ("FIREBASE_SERVICE_ACCOUNT looks like a file path. Open the .json file in "
                          "Notepad and paste its contents instead.")
        if raw.startswith('"') or raw.startswith("'"):
            return None, ("FIREBASE_SERVICE_ACCOUNT starts with a quote but isn't a complete quoted "
                          "value. Paste the file contents with no quotes around them.")
        try:
            decoded = base64.b64decode(raw, validate=True).decode("utf-8").strip()
        except Exception:
            decoded = ""
        if not decoded.startswith("{"):
            hint = f"it starts with '{raw[:1]}'" if raw[:1].isalnum() else "it doesn't start with {"
            return None, (f"FIREBASE_SERVICE_ACCOUNT isn't JSON ({hint}, {len(raw)} characters). "
                          "Paste the whole downloaded file, starting with { and ending with }.")
        raw = decoded
    try:
        data = _json.loads(raw, strict=False)          # strict=False: real newlines inside strings
    except ValueError as e:
        return None, (f"FIREBASE_SERVICE_ACCOUNT couldn't be read as JSON (line {getattr(e, 'lineno', '?')}). "
                      "Paste the whole downloaded file again, unchanged.")
    if isinstance(data, str):                            # JSON pasted as a quoted JSON string
        try:
            data = _json.loads(data, strict=False)
        except ValueError:
            return None, "FIREBASE_SERVICE_ACCOUNT is a quoted string, not the JSON file itself."
    if not isinstance(data, dict):
        return None, "FIREBASE_SERVICE_ACCOUNT isn't a JSON object."
    if data.get("type") != "service_account":
        return None, ("FIREBASE_SERVICE_ACCOUNT isn't a service-account key. Use Firebase > Project settings > "
                      "Service accounts > Generate new private key (not google-services.json).")
    missing = [k for k in ("project_id", "private_key", "client_email") if not data.get(k)]
    if missing:
        return None, f"FIREBASE_SERVICE_ACCOUNT is missing {', '.join(missing)}."
    if "\\n" in data["private_key"]:                     # double-escaped newlines
        data["private_key"] = data["private_key"].replace("\\n", "\n")
    try:
        from google.oauth2 import service_account as sa
        sa.Credentials.from_service_account_info(data, scopes=[FCM_SCOPE])
    except Exception:
        return None, ("FIREBASE_SERVICE_ACCOUNT's private key couldn't be loaded. Generate a new key "
                      "in Firebase and paste the whole file again.")
    return data, None


class FCMSender:
    """FCM HTTP v1 with a service account. The OAuth token is cached until 5 min
    before expiry; google-auth's refresh is blocking, so it runs in a thread."""

    def __init__(self, service_account: dict, http=None):
        from google.oauth2 import service_account as sa
        self.project_id = service_account["project_id"]
        self._creds = sa.Credentials.from_service_account_info(service_account, scopes=[FCM_SCOPE])
        self._lock = asyncio.Lock()
        self._http = http

    async def _token(self) -> str:
        async with self._lock:
            exp = self._creds.expiry
            if not self._creds.token or not exp or exp - datetime.utcnow() < timedelta(minutes=5):
                from google.auth.transport.requests import Request
                await asyncio.to_thread(self._creds.refresh, Request())
            return self._creds.token

    async def send(self, message: dict) -> Tuple[int, Optional[dict]]:
        import httpx
        url = f"https://fcm.googleapis.com/v1/projects/{self.project_id}/messages:send"
        try:
            token = await self._token()
        except Exception as e:  # credentials broken: treat as auth failure
            return 401, {"error": {"status": "UNAUTHENTICATED", "message": f"oauth: {e}"}}
        client = self._http or httpx.AsyncClient(timeout=10)
        try:
            r = await client.post(url, json={"message": message},
                                  headers={"Authorization": f"Bearer {token}"})
            try:
                body = r.json()
            except ValueError:
                body = None
            return r.status_code, body
        except Exception as e:
            return 503, {"error": {"status": "UNAVAILABLE", "message": str(e)[:200]}}
        finally:
            if self._http is None:
                await client.aclose()


# ── the service ──────────────────────────────────────────────────────────────

class PushService:
    def __init__(self, *, db, sender, llm: Callable[[str], Awaitable[Optional[str]]],
                 send_email: Callable[[str, str, str], Awaitable[bool]],
                 alert_to: Callable[[], List[str]],
                 top_categories: Callable[[dict], Awaitable[List[str]]],
                 env_enabled: Callable[[], bool],
                 env_reason: Callable[[], Optional[str]] = lambda: None,
                 llm_daily_cap: int = 2000,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 logger: Optional[logging.Logger] = None):
        self.db = db
        self.sender = sender
        self.llm = llm
        self.send_email = send_email
        self.alert_to = alert_to
        self.top_categories = top_categories
        self.env_enabled = env_enabled
        self.env_reason = env_reason
        self.llm_daily_cap = llm_daily_cap
        self.now = now
        self.sleep = sleep
        self.log = logger or logging.getLogger("push")
        self._sem = asyncio.Semaphore(LLM_CONCURRENCY)

    # ── indexes ──────────────────────────────────────────────────────────────
    async def ensure_indexes(self):
        d = self.db
        await d.push_devices.create_index("token", unique=True)
        await d.push_devices.create_index("device_id", unique=True)
        await d.push_devices.create_index([("user_id", 1), ("last_seen", -1)])
        await d.push_devices.create_index("tz")
        await d.push_log.create_index("push_id", unique=True)
        await d.push_log.create_index([("user_id", 1), ("sent_at", -1)])
        await d.push_log.create_index([("device_id", 1), ("sent_at", -1)])
        await d.push_log.create_index([("kind", 1), ("sent_at", -1)])
        await d.push_log.create_index("sent_at_ttl", expireAfterSeconds=90 * 86400)
        await d.push_claims.create_index("status")
        await d.push_claims.create_index("expires_at", expireAfterSeconds=0)
        await d.push_prep.create_index("expires_at", expireAfterSeconds=0)

    # ── switch ───────────────────────────────────────────────────────────────
    async def state(self) -> dict:
        doc = await self.db.push_state.find_one({"_id": "global"}) or {}
        return {"enabled": bool(doc.get("enabled")), "env_enabled": bool(self.env_enabled()),
                "env_reason": None if self.env_enabled() else (self.env_reason() or "Forced off by server setting PUSH_ENABLED."),
                "updated_at": doc.get("updated_at"), "updated_by": doc.get("updated_by")}

    async def is_live(self) -> bool:
        s = await self.state()
        return s["enabled"] and s["env_enabled"]

    async def set_enabled(self, enabled: bool, by: str) -> dict:
        await self.db.push_state.update_one(
            {"_id": "global"},
            {"$set": {"enabled": bool(enabled), "updated_at": self.now(), "updated_by": by}},
            upsert=True)
        return await self.state()

    # ── devices ──────────────────────────────────────────────────────────────
    async def register(self, *, token: str, platform: str, tz: str, user_id: Optional[str],
                       app_version: str = "") -> dict:
        """Upsert by token. Identity comes only from the caller's session
        (user_id or None for a guest); a token seen before moves to whoever
        registers it now (guest → account on sign-in, R8)."""
        now = self.now()
        existing = await self.db.push_devices.find_one({"token": token})
        fields = {"platform": platform, "tz": tz, "user_id": user_id, "last_seen": now,
                  "app_version": app_version[:20]}
        if existing:
            await self.db.push_devices.update_one({"token": token}, {"$set": fields})
            device_id = existing["device_id"]
        else:
            device_id = secrets.token_urlsafe(12)
            await self.db.push_devices.insert_one({
                "device_id": device_id, "token": token, "created_at": now,
                "prefs": {"breaking": True}, **fields})
        if user_id:
            devices = await self.db.push_devices.find({"user_id": user_id}).sort("last_seen", -1).to_list(100)
            for old in devices[MAX_DEVICES_PER_USER:]:
                await self.db.push_devices.delete_one({"device_id": old["device_id"]})
        return {"device_id": device_id}

    async def unregister(self, token: str) -> bool:
        res = await self.db.push_devices.delete_one({"token": token})
        return res.deleted_count > 0

    async def get_prefs(self, user_id: Optional[str], token: Optional[str] = None) -> dict:
        if user_id:
            doc = await self.db.push_prefs.find_one({"user_id": user_id}) or {}
            return P.prefs_with_defaults(doc.get("prefs"))
        dev = await self.db.push_devices.find_one({"token": token}) if token else None
        return {"breaking": bool(((dev or {}).get("prefs") or {}).get("breaking", True))}

    async def set_prefs(self, user_id: Optional[str], patch: dict, token: Optional[str] = None) -> dict:
        clean = {k: v for k, v in (patch or {}).items() if k in P.PREF_KEYS and isinstance(v, bool)}
        if user_id:
            current = await self.get_prefs(user_id)
            current.update(clean)
            await self.db.push_prefs.update_one(
                {"user_id": user_id}, {"$set": {"prefs": current, "updated_at": self.now()}}, upsert=True)
            return current
        if not token or "breaking" not in clean:
            return await self.get_prefs(None, token)
        await self.db.push_devices.update_one({"token": token}, {"$set": {"prefs.breaking": clean["breaking"]}})
        return await self.get_prefs(None, token)

    # ── opens ────────────────────────────────────────────────────────────────
    async def opened(self, push_id: str) -> bool:
        """Mark a push opened. Unknown ids and repeats are ignored (eng 3A)."""
        if not push_id or len(push_id) > 64:
            return False
        res = await self.db.push_log.update_one(
            {"push_id": push_id, "opened_at": None}, {"$set": {"opened_at": self.now()}})
        return res.modified_count > 0

    # ── LLM with a daily cap ────────────────────────────────────────────────
    async def _capped_llm(self, prompt: str) -> Optional[str]:
        key = f"llm:{self.now().date().isoformat()}"
        await self.db.push_state.update_one({"_id": key}, {"$inc": {"n": 1}}, upsert=True)
        doc = await self.db.push_state.find_one({"_id": key}) or {}
        if doc.get("n", 0) > self.llm_daily_cap:
            return None
        async with self._sem:
            try:
                return await asyncio.wait_for(self.llm(prompt), timeout=HOOK_TIMEOUT_S * 2)
            except Exception:
                return None

    async def _hook(self, slot_key: str, headline: str, summary: str) -> Optional[dict]:
        try:
            raw = await asyncio.wait_for(self._capped_llm(P.hook_prompt(slot_key, headline, summary)),
                                         timeout=HOOK_TIMEOUT_S)
        except Exception:
            return None
        return P.parse_hook(raw)

    # ── readers ──────────────────────────────────────────────────────────────
    async def _readers(self) -> Dict[str, dict]:
        """Signed-in readers with live devices: {user_id: {tz, devices}}. A
        reader with several devices is scheduled in the zone of the most
        recently active one."""
        out: Dict[str, dict] = {}
        async for d in self.db.push_devices.find({"user_id": {"$ne": None}}).sort("last_seen", -1):
            r = out.setdefault(d["user_id"], {"tz": d.get("tz") or P.DEFAULT_TZ, "devices": []})
            r["devices"].append(d)
        return out

    async def _last_sent(self, user_id: Optional[str] = None, device_id: Optional[str] = None) -> Optional[datetime]:
        q = {"status": "sent"}
        q.update({"user_id": user_id} if user_id else {"device_id": device_id})
        docs = await self.db.push_log.find(q).sort("sent_at", -1).limit(1).to_list(1)
        return _utc(docs[0]["sent_at"]) if docs else None

    async def _read_today(self, user_id: str, brief_type: str, tz: str, now: datetime) -> bool:
        local = P.local_now(now, tz)
        midnight = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        return bool(await self.db.brief_opens.find_one(
            {"user_id": user_id, "brief_type": brief_type, "opened_at": {"$gte": midnight}}))

    # ── tick ─────────────────────────────────────────────────────────────────
    async def tick(self) -> dict:
        now = self.now()
        summary = {"prepared": 0, "sent": 0, "skipped": 0, "failed": 0, "stale": 0, "live": False}
        summary["stale"] = await self._sweep_stale(now)
        if not await self.is_live():
            return summary
        summary["live"] = True
        readers = await self._readers()
        # Cheap exit: only zones where some slot is being prepared or is due.
        busy_zones = {tz for tz in {r["tz"] for r in readers.values()}
                      if P.prep_slots(now, tz, {"sunrise": True, "noon": True, "dusk": True})}
        if not busy_zones:
            return summary
        prep_jobs, send_jobs = [], []
        for user_id, r in readers.items():
            if r["tz"] not in busy_zones:
                continue
            prefs = await self.get_prefs(user_id)
            for slot_key, day, at in P.prep_slots(now, r["tz"], prefs):
                prep_jobs.append(self._prepare(user_id, r["tz"], slot_key, day, at))
            for slot_key, day, at in P.due_slots(now, r["tz"], prefs):
                send_jobs.append((user_id, r, slot_key, day, at))
        for ok in await asyncio.gather(*prep_jobs, return_exceptions=True):
            if ok is True:
                summary["prepared"] += 1
            elif isinstance(ok, Exception):
                self.log.error(f"push prep failed: {ok}")
        for user_id, r, slot_key, day, at in send_jobs:
            outcome = await self._send_slot(user_id, r, slot_key, day, at, now)
            summary[outcome] = summary.get(outcome, 0) + 1
        return summary

    def _key(self, user_id: str, slot_key: str, day) -> str:
        return f"{user_id}|{slot_key}|{day.isoformat()}"

    async def _prepare(self, user_id: str, tz: str, slot_key: str, day, at: datetime) -> bool:
        key = self._key(user_id, slot_key, day)
        if await self.db.push_prep.find_one({"_id": key}):
            return False
        now = self.now()
        slot = P.SLOTS[slot_key]
        user = await self.db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0, "password_salt": 0})
        if not user:
            return False
        doc = await brief_service.build_brief(self.db, user, slot.brief_type, self._capped_llm, now)
        stories = [st for st in (doc.get("referenced_stories") or []) if st.get("article_id")]
        if not stories:
            return False
        # Never the same story to the same reader twice within 48h (CEO plan
        # rule; owner saw Noon and Dusk both lead with one article). Feature the
        # first brief story they haven't been pushed; if all were, skip the slot.
        recent_story_ids = await self._recent_story_ids(user_id, key, now)
        fresh = [st for st in stories if st["article_id"] not in recent_story_ids]
        if not fresh:
            try:
                await self.db.push_prep.insert_one({
                    "_id": key, "user_id": user_id, "slot": slot_key, "slot_at": at, "skip": "repeat",
                    "created_at": now, "expires_at": now + timedelta(days=3)})
            except DuplicateKeyError:
                pass
            return False
        lead = fresh[0]
        article = await self.db.articles.find_one({"article_id": lead.get("article_id")}, {"_id": 0}) or {}
        label = f"{P.local_now(at, tz).strftime('%H:%M')} {slot.label}"
        pin_id = await brief_service.create_pin(self.db, user_id, slot.brief_type, doc, now,
                                                P.pin_valid_until(at, tz), label)
        ai = await self._hook(slot_key, lead.get("title", ""), article.get("summary") or lead.get("take", ""))
        recent = await self.db.push_log.find(
            {"user_id": user_id, "sent_at": {"$gte": now - timedelta(days=7)}}, {"template_id": 1}).to_list(50)
        salt = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)
        copy = P.compose_slot_copy(slot_key, lead.get("title", ""), ai,
                                   [d.get("template_id") for d in recent], user.get("name"), salt,
                                   force_sober=bool(article.get("desk_sensitive")))
        image = P.push_image(slot_key, copy.sober, article.get("image_url"))
        try:
            await self.db.push_prep.insert_one({
                "_id": key, "user_id": user_id, "slot": slot_key, "slot_at": at, "pin_id": pin_id,
                "title": copy.title, "body": copy.body, "template_id": copy.template_id,
                "source": copy.source, "sober": copy.sober, "image": image,
                "story_id": lead.get("article_id"), "brief_type": slot.brief_type,
                "created_at": now, "expires_at": now + timedelta(days=3),
            })
        except DuplicateKeyError:
            return False
        return True

    async def _recent_story_ids(self, user_id: str, this_key: str, now: datetime) -> set:
        """Stories pushed (or already prepared for another slot) to this reader in 48h."""
        since = now - DEDUPE_STORY
        ids = {d.get("story_id") async for d in self.db.push_log.find(
            {"user_id": user_id, "status": "sent", "sent_at": {"$gte": since}}, {"story_id": 1})}
        ids |= {d.get("story_id") async for d in self.db.push_prep.find(
            {"user_id": user_id, "created_at": {"$gte": since}, "_id": {"$ne": this_key}}, {"story_id": 1})}
        ids.discard(None)
        return ids

    async def _send_slot(self, user_id: str, r: dict, slot_key: str, day, at: datetime, now: datetime) -> str:
        key = self._key(user_id, slot_key, day)
        window_end = at + P.WINDOW
        if await self.db.push_claims.find_one({"_id": key}):
            return "noop"
        slot = P.SLOTS[slot_key]
        reason = None
        if await self._read_today(user_id, slot.brief_type, r["tz"], now):
            reason = "read"
        elif not P.gap_ok(await self._last_sent(user_id=user_id), now):
            reason = "gap"
        claim = {"_id": key, "user_id": user_id, "slot": slot_key, "window_end": window_end,
                 "claimed_at": now, "expires_at": now + timedelta(days=14),
                 "status": "skipped" if reason else "claimed", "reason": reason}
        try:
            await self.db.push_claims.insert_one(claim)
        except DuplicateKeyError:
            return "noop"          # another replica or tick owns it
        if reason:
            return "skipped"
        prep = await self.db.push_prep.find_one({"_id": key})
        if not prep:
            await self._finish_claim(key, "failed", "no_prep")
            return "failed"
        if prep.get("skip"):
            await self._finish_claim(key, "skipped", prep["skip"])
            return "skipped"
        ok = await self._deliver(
            devices=r["devices"], user_id=user_id, kind="slot", slot_key=slot_key,
            title=prep["title"], body=prep["body"], image=prep.get("image"),
            subtitle=f"{slot.label} brief · 3 stories",
            route=f"/brief/{slot.brief_type}?pin={prep['pin_id']}",
            ttl=int((window_end - now).total_seconds()),
            extra={"template_id": prep.get("template_id"), "source": prep.get("source"),
                   "story_id": prep.get("story_id")})
        await self._finish_claim(key, "sent" if ok else "failed", None if ok else "all_devices_failed")
        return "sent" if ok else "failed"

    async def _finish_claim(self, key: str, status: str, reason: Optional[str]):
        await self.db.push_claims.update_one({"_id": key}, {"$set": {"status": status, "reason": reason,
                                                                     "finished_at": self.now()}})

    async def _sweep_stale(self, now: datetime) -> int:
        stale = await self.db.push_claims.find(
            {"status": "claimed", "window_end": {"$lt": now - P.STALE_CLAIM_GRACE}}).to_list(500)
        for c in stale:
            await self._finish_claim(c["_id"], "stale", "never_finished")
        if stale:
            await self.alert("stale", "Chintan push: slots were skipped",
                             f"{len(stale)} slot push(es) were claimed but never finished "
                             f"(crash or deploy mid-send). Latest: {stale[-1]['_id']}.")
        return len(stale)

    # ── delivery ─────────────────────────────────────────────────────────────
    async def _deliver(self, *, devices: List[dict], user_id: Optional[str], kind: str,
                       slot_key: Optional[str], title: str, body: str, image: Optional[str],
                       subtitle: Optional[str], route: str, ttl: int, extra: dict) -> bool:
        """Send to every device; True if at least one accepted it."""
        any_ok = False
        for d in devices:
            push_id = secrets.token_urlsafe(16)
            msg = P.build_message(
                token=d["token"], platform=d.get("platform", "android"), kind=kind, title=title, body=body,
                data={"push_id": push_id, "kind": kind, "route": route, "slot": slot_key or ""},
                ttl_seconds=ttl, now_epoch=int(self.now().timestamp()), slot_key=slot_key,
                subtitle=subtitle if d.get("platform") == "ios" else None, image=image)
            status, err_class, detail = await self._send_with_retry(msg)
            now = self.now()
            await self.db.push_log.insert_one({
                "push_id": push_id, "user_id": user_id, "device_id": d["device_id"], "kind": kind,
                "slot": slot_key, "status": status, "error": err_class, "detail": detail,
                "sent_at": now, "sent_at_ttl": now, "opened_at": None, **extra})
            if status == "sent":
                any_ok = True
            elif err_class == "dead":
                await self.db.push_devices.delete_one({"device_id": d["device_id"]})
            elif err_class == "auth":
                await self.alert("auth", "Chintan push: Firebase/Apple rejected our credentials",
                                 f"Push delivery failed with an auth error: {detail}. Tokens were kept. "
                                 "Check the Firebase service account on Railway and the APNs key in Firebase.")
        return any_ok

    async def _send_with_retry(self, msg: dict) -> Tuple[str, Optional[str], Optional[str]]:
        for attempt in range(len(RETRY_BACKOFF_S) + 1):
            status, body = await self.sender.send(msg)
            if 200 <= status < 300:
                return "sent", None, None
            cls = P.classify_fcm_error(status, body)
            detail = str(((body or {}).get("error") or {}).get("message") or status)[:200]
            if cls != "retry" or attempt == len(RETRY_BACKOFF_S):
                return "failed", cls, detail
            await self.sleep(RETRY_BACKOFF_S[attempt])
        return "failed", "retry", "exhausted"  # pragma: no cover

    # ── Breaking ─────────────────────────────────────────────────────────────
    async def _breaking_plan(self, story_id: str, category: str, national: bool) -> dict:
        """Who gets it now and who is held (and why). Readers are users (all
        their devices) plus, for national stories only, guest devices."""
        now = self.now()
        send, held = [], {"quiet": 0, "cap_day": 0, "cap_week": 0, "gap": 0, "dup": 0, "off": 0}
        since = now - timedelta(days=7)
        readers = await self._readers()
        for user_id, r in readers.items():
            prefs = await self.get_prefs(user_id)
            if not prefs.get("breaking", True):
                held["off"] += 1
                continue
            if not national:
                user = await self.db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0}) or {}
                if category not in (await self.top_categories(user))[:3]:
                    continue
            if await self.db.push_log.find_one({"user_id": user_id, "story_id": story_id, "status": "sent",
                                                "sent_at": {"$gte": now - DEDUPE_STORY}}):
                held["dup"] += 1
                continue
            logs = await self.db.push_log.find({"user_id": user_id, "kind": "breaking", "status": "sent",
                                                "sent_at": {"$gte": since}}).to_list(20)
            why = P.breaking_hold(now, r["tz"], await self._last_sent(user_id=user_id),
                                  sorted({_utc(l["sent_at"]) for l in logs}))
            if why:
                held[why] += 1
            else:
                send.append((user_id, r["devices"]))
        if national:
            async for d in self.db.push_devices.find({"user_id": None}):
                if not ((d.get("prefs") or {}).get("breaking", True)):
                    held["off"] += 1
                    continue
                logs = await self.db.push_log.find({"device_id": d["device_id"], "kind": "breaking",
                                                    "status": "sent", "sent_at": {"$gte": since}}).to_list(20)
                if any(l.get("story_id") == story_id for l in logs):
                    held["dup"] += 1
                    continue
                why = P.breaking_hold(now, d.get("tz"), await self._last_sent(device_id=d["device_id"]),
                                      sorted({_utc(l["sent_at"]) for l in logs}))
                if why:
                    held[why] += 1
                else:
                    send.append((None, [d]))
        return {"send": send, "held": held}

    async def reach(self, story_id: str, category: str, national: bool) -> dict:
        plan = await self._breaking_plan(story_id, category, national)
        return {"readers": len(plan["send"]), "devices": sum(len(d) for _, d in plan["send"]),
                "held": plan["held"], "live": await self.is_live()}

    async def send_breaking(self, *, story_id: str, text: str, category: str, national: bool) -> dict:
        """Recount at send time (counts shown in the confirm go stale), then send."""
        if not await self.is_live():
            return {"ok": False, "error": "Push is switched off."}
        title, body = P.breaking_copy(text)
        plan = await self._breaking_plan(story_id, category, national)
        sent = failed = 0
        for user_id, devices in plan["send"]:
            ok = await self._deliver(devices=devices, user_id=user_id, kind="breaking", slot_key=None,
                                     title=title, body=body, image=None, subtitle=None,
                                     route=f"/article/{story_id}", ttl=3600,
                                     extra={"story_id": story_id, "template_id": None, "source": "desk"})
            sent += ok
            failed += not ok
        return {"ok": True, "sent": sent, "failed": failed, "held": plan["held"], "title": title, "body": body}

    # ── test push ────────────────────────────────────────────────────────────
    async def test_push(self, email: str) -> dict:
        """Owner QA: works while the Desk switch is OFF (that's its purpose);
        still blocked by the env hard off."""
        if not self.env_enabled():
            return {"ok": False, "error": self.env_reason() or "Forced off by server setting PUSH_ENABLED."}
        if not email:
            return {"ok": False, "error": "PUSH_TEST_USER_EMAIL isn't set on the server."}
        user = await self.db.users.find_one({"email": email.lower()}, {"_id": 0, "user_id": 1})
        if not user:
            return {"ok": False, "error": "No app account uses that email."}
        devices = await self.db.push_devices.find({"user_id": user["user_id"]}).to_list(MAX_DEVICES_PER_USER)
        if not devices:
            return {"ok": False, "error": "That account has no devices with notifications on yet."}
        results = []
        for d in devices:
            msg = P.build_message(token=d["token"], platform=d.get("platform", "android"), kind="slot",
                                  title="A quick test from Chintan", body="If you can read this, notifications work on this phone.",
                                  data={"push_id": "test", "kind": "test", "route": "/feed", "slot": ""},
                                  ttl_seconds=600, now_epoch=int(self.now().timestamp()), slot_key="sunrise")
            status, cls, detail = await self._send_with_retry(msg)
            results.append({"platform": d.get("platform"), "app_version": d.get("app_version", ""),
                            "result": "delivered" if status == "sent" else f"failed: {cls} ({detail})"})
            if cls == "dead":
                await self.db.push_devices.delete_one({"device_id": d["device_id"]})
        return {"ok": any(r["result"] == "delivered" for r in results), "devices": results}

    # ── Desk stats ───────────────────────────────────────────────────────────
    async def stats(self, days: int = 7) -> dict:
        since = self.now() - timedelta(days=days)
        rows = {k: {"sent": 0, "tapped": 0, "skipped": 0} for k in ("sunrise", "noon", "dusk", "breaking")}
        async for l in self.db.push_log.find({"sent_at": {"$gte": since}, "status": "sent"}):
            k = "breaking" if l.get("kind") == "breaking" else l.get("slot")
            if k in rows:
                rows[k]["sent"] += 1
                rows[k]["tapped"] += 1 if l.get("opened_at") else 0
        async for c in self.db.push_claims.find({"claimed_at": {"$gte": since},
                                                 "status": {"$in": ["skipped", "stale", "failed"]}}):
            if c.get("slot") in rows:
                rows[c["slot"]]["skipped"] += 1
        errors = await self.db.push_log.find({"status": "failed", "sent_at": {"$gte": since}},
                                             {"_id": 0, "error": 1, "detail": 1, "sent_at": 1, "kind": 1}
                                             ).sort("sent_at", -1).limit(5).to_list(5)
        devices = await self.db.push_devices.count_documents({})
        readers = len(await self.db.push_devices.distinct("user_id", {"user_id": {"$ne": None}}))
        return {"state": await self.state(), "rows": rows, "errors": errors,
                "devices": devices, "readers": readers}

    async def next_slot_preview(self) -> Optional[dict]:
        """For the go-live confirm: the next slot anywhere and how many readers it reaches."""
        readers = await self._readers()
        now = self.now()
        best = None
        for user_id, r in readers.items():
            prefs = await self.get_prefs(user_id)
            nxt = P.next_slot(now, r["tz"], prefs)
            if nxt and (best is None or nxt[2] < best[2]):
                best = (nxt[0], r["tz"], nxt[2])
        if not best:
            return None
        count = 0
        for user_id, r in readers.items():
            prefs = await self.get_prefs(user_id)
            nxt = P.next_slot(now, r["tz"], prefs)
            if nxt and nxt[0] == best[0] and nxt[2] == best[2]:
                count += 1
        local = P.local_now(best[2], best[1])
        return {"slot": P.SLOTS[best[0]].label, "local_time": local.strftime("%H:%M"),
                "tz": best[1], "readers": count}

    # ── alerts ───────────────────────────────────────────────────────────────
    async def alert(self, kind: str, subject: str, text: str) -> bool:
        """Owner email, at most once per ALERT_EVERY per kind (R2)."""
        now = self.now()
        doc = await self.db.push_state.find_one({"_id": f"alert:{kind}"})
        last = _utc((doc or {}).get("last_sent"))
        if last and now - last < ALERT_EVERY:
            return False
        await self.db.push_state.update_one({"_id": f"alert:{kind}"},
                                            {"$set": {"last_sent": now, "text": text[:500]}}, upsert=True)
        self.log.error(f"push alert [{kind}]: {text}")
        sent = False
        for to in self.alert_to():
            html = f"<p>{_html.escape(text)}</p><p>Push panel: https://chintan.news/admin</p>"
            sent = await self.send_email(to, subject, html) or sent
        return sent


async def run_scheduler(service: PushService, logger: logging.Logger, interval_s: int = 60):
    """The lifespan loop. One bad tick never kills the loop."""
    while True:
        started = _time.monotonic()
        try:
            summary = await service.tick()
            if any(summary.get(k) for k in ("prepared", "sent", "failed", "stale")):
                logger.info(f"push tick: {summary}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"push tick failed: {e}")
        await asyncio.sleep(max(1.0, interval_s - (_time.monotonic() - started)))

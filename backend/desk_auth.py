"""Chintan Desk authentication. Security-first by explicit owner request
("highest level of security, not a casual build"); every control below is
from /plan-eng-review 2026-09-28.

    browser ─▶ chintan.news/admin/api/* (Vercel, server-side)
                 │ X-Desk-Proxy: <secret>        ← proves the call came via the site
                 │ X-Desk-Session: <token>       ← from the __Host-desk cookie
                 │ X-Desk-CSRF: <token>          ← mutating requests only
                 │ X-Desk-Client-IP: <real ip>   ← trusted ONLY with a valid proxy secret
                 ▼
             /api/desk/* ── proxy check fails → 404 (the route doesn't exist to you)
                           ── session check fails → 401
                           ── CSRF check fails → 403

Factors: Argon2id password + TOTP (RFC 6238, 30s, ±1 step, replay-blocked),
submitted together so the server never reveals which one was wrong.
Lockout: 5 failures in 15 min → locked 15 min, per account AND per client IP,
counted in MongoDB (always present; Redis is optional in this app and a
lockout that resets on every deploy is no lockout).
Sessions: 256-bit random token, only its SHA-256 stored; idle 30 min,
absolute 8h; revocable one-by-one or all at once.
TOTP secrets are Fernet-encrypted at rest with DESK_ENCRYPTION_KEY.
Admin accounts exist only via scripts/desk_admin.py, run by the owner.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

# OWASP's Argon2id recommendation (m=19 MiB, t=2, p=1) is the floor; this is
# above it. Parameters are stored inside each hash, so raising them later
# only needs check_needs_rehash on the next login, no migration.
_PH = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2, hash_len=32, salt_len=16)

TOTP_PERIOD = 30
TOTP_WINDOW = 1                 # accept one step either side (clock drift)
LOCK_THRESHOLD = 5
LOCK_WINDOW = timedelta(minutes=15)
LOCK_DURATION = timedelta(minutes=15)
SESSION_IDLE = timedelta(minutes=30)
SESSION_ABSOLUTE = timedelta(hours=8)
SESSION_TOUCH_EVERY = timedelta(seconds=60)
PASSWORD_MIN = 14

GENERIC_LOGIN_ERROR = "Incorrect email, password or code."


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _dt(value) -> Optional[datetime]:
    if not value:
        return None
    dt = datetime.fromisoformat(value) if isinstance(value, str) else value
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ── pure helpers ──────────────────────────────────────────────────────────────

def constant_time_equals(a: Optional[str], b: Optional[str]) -> bool:
    """Both must be non-empty. An unset secret must never match an empty
    header: that would turn a missing env var into an open door."""
    if not a or not b:
        return False
    return hmac.compare_digest(a.encode(), b.encode())


def proxy_ok(header_value: Optional[str], configured_secret: Optional[str]) -> bool:
    return constant_time_equals(header_value, configured_secret)


def clean_ip(value: Optional[str]) -> str:
    """A syntactically valid IP or 'unknown'. Only ever called on a header
    that arrived WITH a valid proxy secret, so the site vouches for it."""
    try:
        return str(ipaddress.ip_address((value or "").strip()))
    except ValueError:
        return "unknown"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password: str) -> str:
    return _PH.hash(password)


def verify_password(stored_hash: str, password: str) -> tuple[bool, bool]:
    """(ok, needs_rehash)."""
    if not stored_hash or not password:
        return False, False
    try:
        _PH.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False, False
    return True, _PH.check_needs_rehash(stored_hash)


# A real hash to verify against when the email doesn't exist, so an unknown
# account costs the same time as a known one (no user enumeration by timing).
_DUMMY_HASH = _PH.hash(secrets.token_urlsafe(32))


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password or "") < PASSWORD_MIN:
        problems.append(f"at least {PASSWORD_MIN} characters")
    if password and len(set(password)) < 6:
        problems.append("more variety of characters")
    return problems


def totp_matching_step(secret: str, code: str, at: datetime, last_step: int) -> Optional[int]:
    """The time-step the code is valid for, or None. Steps at or before
    last_step are refused: a code, once used, can't be replayed within its
    validity window (RFC 6238 §5.2)."""
    code = (code or "").strip().replace(" ", "")
    if not (len(code) == 6 and code.isdigit()):
        return None
    totp = pyotp.TOTP(secret, interval=TOTP_PERIOD)
    current = int(at.timestamp()) // TOTP_PERIOD
    for step in range(current - TOTP_WINDOW, current + TOTP_WINDOW + 1):
        if step <= (last_step or 0):
            continue
        if hmac.compare_digest(totp.at(step * TOTP_PERIOD), code):
            return step
    return None


def lock_state(doc: Optional[dict], now: datetime) -> Optional[datetime]:
    """When this key is locked until, or None."""
    until = _dt((doc or {}).get("locked_until"))
    return until if until and until > now else None


def next_failure_state(doc: Optional[dict], now: datetime) -> dict:
    """Fields to store after one more failure. Failures outside the window
    start a fresh count; reaching the threshold locks."""
    doc = doc or {}
    first = _dt(doc.get("first_failure_at"))
    count = int(doc.get("failures") or 0)
    if not first or now - first > LOCK_WINDOW:
        first, count = now, 0
    count += 1
    state = {"failures": count, "first_failure_at": _iso(first), "locked_until": None}
    if count >= LOCK_THRESHOLD:
        state["locked_until"] = _iso(now + LOCK_DURATION)
    return state


def session_alive(session: Optional[dict], now: datetime) -> bool:
    if not session or session.get("revoked"):
        return False
    created = _dt(session.get("created_at"))
    last = _dt(session.get("last_seen")) or created
    if not created or not last:
        return False
    return now - created < SESSION_ABSOLUTE and now - last < SESSION_IDLE


class Crypto:
    """Fernet wrapper for TOTP secrets. Refuses to exist without a key."""

    def __init__(self, key: Optional[str]):
        if not key:
            raise RuntimeError("DESK_ENCRYPTION_KEY is not set")
        self._f = Fernet(key.encode() if isinstance(key, str) else key)

    def encrypt(self, plaintext: str) -> str:
        return self._f.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> Optional[str]:
        try:
            return self._f.decrypt(token.encode()).decode()
        except (InvalidToken, ValueError, AttributeError):
            return None


# ── database-backed operations ────────────────────────────────────────────────

class DeskAuth:
    def __init__(self, db, encryption_key: Optional[str], now=utcnow):
        self.db = db
        self._key = encryption_key
        self.now = now

    @property
    def crypto(self) -> Crypto:
        return Crypto(self._key)

    async def audit(self, action: str, *, email: str = "", ip: str = "", ua: str = "", detail: Optional[dict] = None):
        """Append-only: nothing in the Desk updates or deletes these rows."""
        await self.db.desk_audit.insert_one({
            "ts": _iso(self.now()), "action": action, "email": email,
            "ip": ip, "ua": (ua or "")[:300], "detail": detail or {},
        })

    # lockout
    async def locked_until(self, keys: list[str]) -> Optional[datetime]:
        now = self.now()
        latest = None
        for key in keys:
            until = lock_state(await self.db.desk_lockouts.find_one({"_id": key}), now)
            if until and (latest is None or until > latest):
                latest = until
        return latest

    async def record_failure(self, keys: list[str]) -> bool:
        """Returns True if this failure caused a lock on any key."""
        now = self.now()
        locked = False
        for key in keys:
            doc = await self.db.desk_lockouts.find_one({"_id": key})
            state = next_failure_state(doc, now)
            await self.db.desk_lockouts.update_one({"_id": key}, {"$set": state}, upsert=True)
            locked = locked or bool(state["locked_until"])
        return locked

    async def clear_failures(self, keys: list[str]):
        for key in keys:
            await self.db.desk_lockouts.delete_one({"_id": key})

    # login
    async def authenticate(self, email: str, password: str, code: str) -> Optional[dict]:
        """The admin doc if ALL THREE are right, else None. Always does the
        password hash work, even for unknown emails (timing parity)."""
        email = (email or "").strip().lower()
        admin = await self.db.desk_admins.find_one({"email": email, "disabled": {"$ne": True}})
        ok, needs_rehash = verify_password(admin["pw_hash"] if admin else _DUMMY_HASH, password)
        if not admin or not ok:
            return None
        secret = self.crypto.decrypt(admin.get("totp_secret_enc") or "")
        if not secret:
            return None
        step = totp_matching_step(secret, code, self.now(), int(admin.get("totp_last_step") or 0))
        if step is None:
            return None
        update = {"totp_last_step": step, "last_login_at": _iso(self.now())}
        if needs_rehash:
            update["pw_hash"] = hash_password(password)
        # Conditional on the old step, so two simultaneous logins with the
        # same code can't both succeed.
        res = await self.db.desk_admins.update_one(
            {"admin_id": admin["admin_id"], "totp_last_step": admin.get("totp_last_step", 0)},
            {"$set": update},
        )
        if getattr(res, "modified_count", 1) == 0:
            return None
        return admin

    # sessions
    async def create_session(self, admin: dict, ip: str, ua: str) -> tuple[str, str]:
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        now = self.now()
        await self.db.desk_sessions.insert_one({
            "token_hash": hash_token(token), "admin_id": admin["admin_id"], "email": admin["email"],
            "csrf": csrf, "created_at": _iso(now), "last_seen": _iso(now),
            "ip": ip, "ua": (ua or "")[:300], "revoked": False,
        })
        return token, csrf

    async def session_for(self, token: Optional[str]) -> Optional[dict]:
        if not token:
            return None
        session = await self.db.desk_sessions.find_one({"token_hash": hash_token(token)})
        now = self.now()
        if not session_alive(session, now):
            return None
        last = _dt(session.get("last_seen"))
        if not last or now - last >= SESSION_TOUCH_EVERY:
            await self.db.desk_sessions.update_one(
                {"token_hash": session["token_hash"]}, {"$set": {"last_seen": _iso(now)}})
        return session

    async def revoke(self, token: str):
        await self.db.desk_sessions.update_one({"token_hash": hash_token(token)}, {"$set": {"revoked": True}})

    async def revoke_all(self, admin_id: str) -> int:
        res = await self.db.desk_sessions.update_many({"admin_id": admin_id, "revoked": False},
                                                      {"$set": {"revoked": True}})
        return getattr(res, "modified_count", 0)

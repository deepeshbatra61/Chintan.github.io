"""desk_auth: every control that keeps the Desk closed.

Needs the test environment (requirements-dev.txt): argon2, pyotp,
cryptography and mongomock-motor. Skipped cleanly where they're missing, so
the pure suites still run anywhere.
"""

from datetime import datetime, timedelta, timezone

import pytest

argon2 = pytest.importorskip("argon2")
pyotp = pytest.importorskip("pyotp")
mongomock_motor = pytest.importorskip("mongomock_motor")
from cryptography.fernet import Fernet  # noqa: E402

import desk_auth as A  # noqa: E402

T0 = datetime(2026, 9, 28, 12, 0, 0, tzinfo=timezone.utc)
KEY = Fernet.generate_key().decode()
SECRET = pyotp.random_base32()
PASSWORD = "correct horse battery staple 42"


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, **kw):
        self.t += timedelta(**kw)


def code_at(t, offset_steps=0):
    return pyotp.TOTP(SECRET).at(int(t.timestamp()) + offset_steps * 30)


@pytest.fixture
async def env():
    db = mongomock_motor.AsyncMongoMockClient()["t"]
    clock = Clock(T0)
    auth = A.DeskAuth(db, KEY, now=clock)
    await db.desk_admins.insert_one({
        "admin_id": "adm_1", "email": "owner@chintan.news",
        "pw_hash": A.hash_password(PASSWORD),
        "totp_secret_enc": A.Crypto(KEY).encrypt(SECRET), "totp_last_step": 0,
    })
    return db, clock, auth


# ─────────────────────── pure ───────────────────────

def test_proxy_secret_constant_time_and_never_matches_empty():
    assert A.proxy_ok("s3cret", "s3cret")
    assert not A.proxy_ok("nope", "s3cret")
    assert not A.proxy_ok("", "")          # unset secret must not open the door
    assert not A.proxy_ok(None, None)
    assert not A.proxy_ok("x", "")


def test_clean_ip():
    assert A.clean_ip(" 203.0.113.9 ") == "203.0.113.9"
    assert A.clean_ip("2001:db8::1") == "2001:db8::1"
    assert A.clean_ip("1.2.3.4, 5.6.7.8") == "unknown"
    assert A.clean_ip(None) == "unknown"


def test_password_hash_roundtrip_and_mismatch():
    h = A.hash_password(PASSWORD)
    assert h.startswith("$argon2id$")
    assert A.verify_password(h, PASSWORD) == (True, False)
    assert A.verify_password(h, PASSWORD + "x")[0] is False
    assert A.verify_password("", PASSWORD)[0] is False
    assert A.verify_password("not-a-hash", PASSWORD)[0] is False


def test_password_rules():
    assert A.password_problems("short")
    assert A.password_problems("aaaaaaaaaaaaaaaaaaaa")
    assert A.password_problems(PASSWORD) == []


def test_totp_accepts_current_and_adjacent_step_only():
    assert A.totp_matching_step(SECRET, code_at(T0), T0, 0) is not None
    assert A.totp_matching_step(SECRET, code_at(T0, -1), T0, 0) is not None
    assert A.totp_matching_step(SECRET, code_at(T0, 3), T0, 0) is None


def test_totp_replay_is_refused():
    step = A.totp_matching_step(SECRET, code_at(T0), T0, 0)
    assert A.totp_matching_step(SECRET, code_at(T0), T0, step) is None


def test_totp_rejects_malformed():
    for bad in ["", "12345", "1234567", "abcdef", None]:
        assert A.totp_matching_step(SECRET, bad, T0, 0) is None


def test_lockout_math():
    doc = None
    for i in range(A.LOCK_THRESHOLD - 1):
        doc = A.next_failure_state(doc, T0 + timedelta(minutes=i))
        assert doc["locked_until"] is None
    doc = A.next_failure_state(doc, T0 + timedelta(minutes=5))
    assert A.lock_state(doc, T0 + timedelta(minutes=6))
    assert A.lock_state(doc, T0 + timedelta(minutes=21)) is None


def test_failures_outside_window_start_fresh():
    doc = A.next_failure_state(None, T0)
    doc = A.next_failure_state(doc, T0 + timedelta(minutes=16))
    assert doc["failures"] == 1


def test_session_expiry_rules():
    s = {"created_at": T0.isoformat(), "last_seen": T0.isoformat(), "revoked": False}
    assert A.session_alive(s, T0 + timedelta(minutes=29))
    assert not A.session_alive(s, T0 + timedelta(minutes=30))                      # idle
    busy = {**s, "last_seen": (T0 + timedelta(hours=7, minutes=59)).isoformat()}
    assert A.session_alive(busy, T0 + timedelta(hours=7, minutes=59, seconds=30))
    assert not A.session_alive(busy, T0 + timedelta(hours=8))                       # absolute
    assert not A.session_alive({**s, "revoked": True}, T0)
    assert not A.session_alive(None, T0)


def test_crypto_needs_key_and_rejects_tampering():
    with pytest.raises(RuntimeError):
        A.Crypto(None)
    c = A.Crypto(KEY)
    assert c.decrypt(c.encrypt("x")) == "x"
    assert c.decrypt("garbage") is None
    assert A.Crypto(Fernet.generate_key().decode()).decrypt(c.encrypt("x")) is None


# ─────────────────────── database-backed ───────────────────────

async def test_login_needs_all_three(env):
    db, clock, auth = env
    assert await auth.authenticate("owner@chintan.news", PASSWORD, code_at(T0))
    clock.advance(seconds=60)
    assert not await auth.authenticate("owner@chintan.news", "wrong password here", code_at(clock()))
    assert not await auth.authenticate("owner@chintan.news", PASSWORD, "000000")
    assert not await auth.authenticate("nobody@chintan.news", PASSWORD, code_at(clock()))


async def test_email_is_case_insensitive(env):
    _, _, auth = env
    assert await auth.authenticate("  Owner@Chintan.News ", PASSWORD, code_at(T0))


async def test_code_cannot_be_reused(env):
    _, _, auth = env
    code = code_at(T0)
    assert await auth.authenticate("owner@chintan.news", PASSWORD, code)
    assert not await auth.authenticate("owner@chintan.news", PASSWORD, code)


async def test_disabled_admin_cannot_log_in(env):
    db, _, auth = env
    await db.desk_admins.update_one({"admin_id": "adm_1"}, {"$set": {"disabled": True}})
    assert not await auth.authenticate("owner@chintan.news", PASSWORD, code_at(T0))


async def test_lockout_blocks_and_expires(env):
    _, clock, auth = env
    keys = ["acct:owner@chintan.news", "ip:203.0.113.9"]
    for _ in range(A.LOCK_THRESHOLD - 1):
        assert not await auth.record_failure(keys)
    assert await auth.record_failure(keys)
    assert await auth.locked_until(keys)
    assert await auth.locked_until(["acct:owner@chintan.news"])
    clock.advance(minutes=16)
    assert await auth.locked_until(keys) is None


async def test_session_lifecycle(env):
    db, clock, auth = env
    admin = await db.desk_admins.find_one({"admin_id": "adm_1"})
    token, csrf = await auth.create_session(admin, "203.0.113.9", "ua")
    stored = await db.desk_sessions.find_one({})
    assert token not in str(stored)                    # only the hash is stored
    assert (await auth.session_for(token))["csrf"] == csrf
    clock.advance(minutes=20)
    assert await auth.session_for(token)               # touched → idle timer reset
    clock.advance(minutes=20)
    assert await auth.session_for(token)
    await auth.revoke(token)
    assert await auth.session_for(token) is None
    assert await auth.session_for(None) is None
    assert await auth.session_for("made-up") is None


async def test_revoke_all(env):
    db, _, auth = env
    admin = await db.desk_admins.find_one({"admin_id": "adm_1"})
    t1, _ = await auth.create_session(admin, "ip", "ua")
    t2, _ = await auth.create_session(admin, "ip", "ua")
    assert await auth.revoke_all("adm_1") == 2
    assert await auth.session_for(t1) is None and await auth.session_for(t2) is None


async def test_audit_is_written(env):
    db, _, auth = env
    await auth.audit("login_ok", email="owner@chintan.news", ip="1.2.3.4", ua="x" * 500)
    row = await db.desk_audit.find_one({})
    assert row["action"] == "login_ok" and len(row["ua"]) == 300

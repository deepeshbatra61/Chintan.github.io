#!/usr/bin/env python3
"""Owner-only Chintan Desk account tool. The ONLY way a Desk admin can be
created, reset or unlocked: there is deliberately no web signup, no web
password reset and no recovery codes (/plan-eng-review 2026-09-28, D2).

Run from backend/, with the production values in your shell (never typed on
the command line, never committed):

    MONGO_URL, DB_NAME          the app's database
    DESK_ENCRYPTION_KEY         Fernet key that encrypts TOTP secrets

Commands:
    python scripts/desk_admin.py gen-keys
        print a fresh DESK_ENCRYPTION_KEY and DESK_PROXY_SECRET to paste into
        Railway (both) and Vercel (proxy secret only)
    python scripts/desk_admin.py create you@chintan.news
        set a password, enrol an authenticator app, confirm with a code
    python scripts/desk_admin.py reset-totp you@chintan.news
        lost phone: enrol a new authenticator (password unchanged)
    python scripts/desk_admin.py reset-password you@chintan.news
    python scripts/desk_admin.py unlock you@chintan.news
        clear a lockout early
    python scripts/desk_admin.py sign-out-all you@chintan.news
    python scripts/desk_admin.py disable you@chintan.news

The email must ALSO be listed in the server's ADMIN_EMAILS for the Desk to
accept it.
"""

import argparse
import asyncio
import getpass
import os
import secrets
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import desk_auth as A  # noqa: E402

ISSUER = "Chintan Desk"


def _db():
    from motor.motor_asyncio import AsyncIOMotorClient
    url, name = os.environ.get("MONGO_URL"), os.environ.get("DB_NAME")
    if not url or not name:
        sys.exit("Set MONGO_URL and DB_NAME in this shell first.")
    return AsyncIOMotorClient(url)[name]


def _crypto():
    try:
        return A.Crypto(os.environ.get("DESK_ENCRYPTION_KEY"))
    except RuntimeError:
        sys.exit("Set DESK_ENCRYPTION_KEY in this shell first (run gen-keys if you have none).")


def _ask_password() -> str:
    while True:
        pw = getpass.getpass("New Desk password: ")
        problems = A.password_problems(pw)
        if problems:
            print("Needs " + " and ".join(problems) + ". A long passphrase is best.")
            continue
        if getpass.getpass("Again: ") != pw:
            print("Didn't match, try again.")
            continue
        return pw


def _enrol_totp(email: str) -> tuple[str, int]:
    """Show the secret, then require a working code before saving it, so a
    mistyped enrolment can't lock the owner out."""
    import pyotp
    secret = pyotp.random_base32()
    uri = pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER)
    print("\nAdd this to your authenticator app (Google Authenticator, 1Password, Authy...):")
    try:
        import qrcode  # optional: pip install qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(uri)
        qr.print_ascii(invert=True)
    except ImportError:
        print("  (for a scannable QR here: pip install qrcode)")
    print(f"  Setup key: {secret}")
    print(f"  Account:   {email}   Issuer: {ISSUER}\n")
    for _ in range(3):
        code = input("Enter the 6-digit code it shows: ")
        step = A.totp_matching_step(secret, code, datetime.now(timezone.utc), 0)
        if step is not None:
            return secret, step
        print("That code didn't match. Check the phone's clock is set automatically.")
    sys.exit("Enrolment cancelled; nothing was saved.")


async def _admin(db, email):
    doc = await db.desk_admins.find_one({"email": email})
    if not doc:
        sys.exit(f"No Desk admin {email}.")
    return doc


async def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["gen-keys", "create", "reset-totp", "reset-password",
                                       "unlock", "sign-out-all", "disable"])
    p.add_argument("email", nargs="?")
    args = p.parse_args()

    if args.command == "gen-keys":
        from cryptography.fernet import Fernet
        print("DESK_ENCRYPTION_KEY=" + Fernet.generate_key().decode())
        print("DESK_PROXY_SECRET=" + secrets.token_urlsafe(48))
        print("\nRailway: set both. Vercel: set DESK_PROXY_SECRET only.")
        print("Changing DESK_ENCRYPTION_KEY later invalidates every enrolled authenticator.")
        return

    if not args.email:
        sys.exit("Give the admin's email.")
    email = args.email.strip().lower()
    db = _db()
    now = datetime.now(timezone.utc).isoformat()

    async def log(action):
        await db.desk_audit.insert_one({"ts": now, "action": f"cli_{action}", "email": email,
                                        "ip": "cli", "ua": "desk_admin.py", "detail": {}})

    if args.command == "create":
        if await db.desk_admins.find_one({"email": email}):
            sys.exit(f"{email} already exists. Use reset-password / reset-totp.")
        crypto = _crypto()
        pw = _ask_password()
        secret, step = _enrol_totp(email)
        await db.desk_admins.insert_one({
            "admin_id": "adm_" + uuid.uuid4().hex[:12], "email": email,
            "pw_hash": A.hash_password(pw), "totp_secret_enc": crypto.encrypt(secret),
            "totp_last_step": step, "created_at": now, "disabled": False,
        })
        await db.desk_admins.create_index("email", unique=True)
        await log("create")
        print(f"\nCreated {email}. Make sure it's in ADMIN_EMAILS on Railway.")

    elif args.command == "reset-totp":
        await _admin(db, email)
        crypto = _crypto()
        secret, step = _enrol_totp(email)
        await db.desk_admins.update_one({"email": email}, {"$set": {
            "totp_secret_enc": crypto.encrypt(secret), "totp_last_step": step}})
        await db.desk_sessions.update_many({"email": email}, {"$set": {"revoked": True}})
        await log("reset_totp")
        print("New authenticator enrolled; all existing sessions signed out.")

    elif args.command == "reset-password":
        await _admin(db, email)
        pw = _ask_password()
        await db.desk_admins.update_one({"email": email}, {"$set": {"pw_hash": A.hash_password(pw)}})
        await db.desk_sessions.update_many({"email": email}, {"$set": {"revoked": True}})
        await log("reset_password")
        print("Password changed; all existing sessions signed out.")

    elif args.command == "unlock":
        res = await db.desk_lockouts.delete_many({"_id": f"acct:{email}"})
        await log("unlock")
        print(f"Cleared {res.deleted_count} account lock. (IP locks expire on their own in 15 min.)")

    elif args.command == "sign-out-all":
        res = await db.desk_sessions.update_many({"email": email, "revoked": False}, {"$set": {"revoked": True}})
        await log("sign_out_all")
        print(f"Signed out {res.modified_count} session(s).")

    elif args.command == "disable":
        await _admin(db, email)
        await db.desk_admins.update_one({"email": email}, {"$set": {"disabled": True}})
        await db.desk_sessions.update_many({"email": email}, {"$set": {"revoked": True}})
        await log("disable")
        print(f"{email} disabled and signed out.")


if __name__ == "__main__":
    asyncio.run(main())

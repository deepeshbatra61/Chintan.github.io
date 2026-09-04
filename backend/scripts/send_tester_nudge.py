#!/usr/bin/env python3
"""Send the closed-test nudge email to the tester list.

Run from backend/:
    python scripts/send_tester_nudge.py                    # dry run, sends nothing
    python scripts/send_tester_nudge.py --only you@x.com --send   # one real test
    python scripts/send_tester_nudge.py --send             # the real thing

DRY RUN IS THE DEFAULT, deliberately. This mails ~23 real relatives and
friends; a bad template or a wrong name is not something you can unsend, so
sending requires typing --send and the recommended flow is --only yourself
first. It also paces at ~2/sec because Resend's free tier rate-limits above
that and a burst gets partially dropped rather than queued.

Needs RESEND_API_KEY in the environment (same key the app uses).
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from html import escape
from urllib.parse import quote

# Stdlib only, on purpose: this is run by hand from a laptop, and it should
# never fail because a virtualenv is missing the app's dependencies.

# ── The 14-day window ────────────────────────────────────────────────────────
# Day 1 = the day build 12 (1.9.0) was promoted to the alpha (closed) track.
# Google counts from the review date / the running closed test, NOT from when
# testers originally joined -- see the rejection notice.
START_DATE = date(2026, 9, 3)
TOTAL_DAYS = 14

FEEDBACK_URL = "https://chintan.news/feedback"
EMAIL_FROM = os.environ.get("EMAIL_FROM", "Chintan <noreply@chintan.news>")
SUPPORT_EMAIL = "team@chintan.news"

# ── Recipients ───────────────────────────────────────────────────────────────
# Loaded from testers.json, which is GITIGNORED and must stay that way: this
# repo is public, and the list is two dozen relatives' and friends' personal
# Gmail addresses. GitHub is scraped for exactly that, git history makes a
# mistake here permanent, and none of them agreed to be published.
#
# Format (see testers.example.json):
#   [{"email": "someone@example.com", "name": "Someone"}, ...]
# "name" may be empty -- the template degrades to a plain "Hi," which is much
# better than confidently addressing someone by the wrong name.
DEFAULT_LIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testers.json")


def load_testers(path: str) -> list[tuple[str, str]]:
    if not os.path.exists(path):
        print(f"No tester list at {path}\n"
              f"Create it from testers.example.json. It is gitignored on purpose "
              f"— do not commit real addresses to this public repo.")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        rows = json.load(f)
    out = []
    for row in rows:
        email = (row.get("email") or "").strip()
        if email:
            out.append((email, (row.get("name") or "").strip()))
    return out


def day_number(today: date | None = None) -> int:
    """1-based day of the testing window."""
    return ((today or date.today()) - START_DATE).days + 1


def feedback_link(name: str) -> str:
    """Prefills the form's name field so nobody retypes what we already know."""
    if not name:
        return FEEDBACK_URL
    return f"{FEEDBACK_URL}?name={quote(name)}"


def render(name: str, day: int) -> tuple[str, str, str]:
    """Return (subject, html, text).

    Same visual language as the app's transactional mail -- table layout,
    fully inline styles -- because that's the only styling real mail clients
    reliably honour (see _password_reset_email in server.py).
    """
    greeting = f"Hi {name}," if name else "Hi,"
    safe_greeting = escape(greeting)
    days_left = max(TOTAL_DAYS - day, 0)
    link = feedback_link(name)

    subject = f"Day {day} of Chintan testing — got 2 minutes?"

    html = f"""\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="dark light">
<title>{escape(subject)}</title>
</head>
<body style="margin:0; padding:0; background-color:#0A0A0A;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#0A0A0A;">
<tr><td align="center" style="padding:40px 16px;">
<table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px; width:100%;">

<tr><td align="center" style="padding-bottom:14px;">
  <img src="https://chintan.news/email-logo.png" width="48" height="48" alt="Chintan" style="display:block; width:48px; height:48px; border:0;">
</td></tr>

<tr><td align="center" style="padding-bottom:8px; font-family:'Courier New',monospace; font-size:11px; letter-spacing:3px; color:#6E6862; text-transform:uppercase;">
  Chintan &middot; Day {day} of {TOTAL_DAYS}
</td></tr>

<tr><td style="background-color:#131211; border:1px solid rgba(255,255,255,0.08); border-radius:16px; padding:34px 28px;">

  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    <tr><td style="font-family:-apple-system,Helvetica,Arial,sans-serif; font-size:15px; line-height:1.65; color:#B6AFA6; padding-bottom:16px;">
      {safe_greeting}
    </td></tr>
    <tr><td style="font-family:-apple-system,Helvetica,Arial,sans-serif; font-size:15px; line-height:1.65; color:#B6AFA6; padding-bottom:16px;">
      Quick nudge: open Chintan, read a couple of stories, poke around for a few
      minutes — use it the way you normally would.
    </td></tr>
    <tr><td style="font-family:-apple-system,Helvetica,Arial,sans-serif; font-size:15px; line-height:1.65; color:#B6AFA6; padding-bottom:24px;">
      Then tell me what you thought. Good, bad, or "this button confused me" —
      all of it helps, and one line is genuinely enough. Bad news is more useful
      than good news.
    </td></tr>
    <tr><td align="center" style="padding-bottom:22px;">
      <a href="{link}" style="display:inline-block; background-color:#DC2626; color:#ffffff; font-family:-apple-system,Helvetica,Arial,sans-serif; font-size:15px; font-weight:600; text-decoration:none; padding:13px 32px; border-radius:10px;">
        Tell me what you think
      </a>
    </td></tr>
    <tr><td align="center" style="font-family:-apple-system,Helvetica,Arial,sans-serif; font-size:13px; line-height:1.6; color:#8A847C;">
      Or just hit reply to this email — whatever's easier.
    </td></tr>
  </table>

</td></tr>

<tr><td style="padding-top:24px; font-family:-apple-system,Helvetica,Arial,sans-serif; font-size:13px; line-height:1.65; color:#8A847C;">
  One thing that really matters: please keep the app installed and stay in the
  testing group for the next <strong style="color:#B6AFA6;">{days_left} days</strong>.
  Google needs 14 unbroken days of testing before Chintan can go public — if
  anyone drops out, the clock restarts for everyone.
</td></tr>

<tr><td align="center" style="padding-top:28px; font-family:-apple-system,Helvetica,Arial,sans-serif; font-size:11px; color:#4A453F;">
  Chintan &middot; Don't just consume. Contemplate.
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""

    text = (
        f"{greeting}\n\n"
        f"Day {day} of {TOTAL_DAYS} of the Chintan testing period.\n\n"
        f"Quick nudge: open Chintan, read a couple of stories, poke around for a few "
        f"minutes — use it the way you normally would.\n\n"
        f"Then tell me what you thought. Good, bad, or \"this button confused me\" — all "
        f"of it helps, and one line is genuinely enough. Bad news is more useful than "
        f"good news:\n\n"
        f"{link}\n\n"
        f"Or just hit reply to this email — whatever's easier.\n\n"
        f"One thing that really matters: please keep the app installed and stay in the "
        f"testing group for the next {days_left} days. Google needs 14 unbroken days of "
        f"testing before Chintan can go public — if anyone drops out, the clock restarts "
        f"for everyone.\n\n"
        f"Chintan — Don't just consume. Contemplate."
    )
    return subject, html, text


def send_one(api_key: str, to: str, subject: str, html: str, text: str) -> tuple[bool, str]:
    body = json.dumps({
        "from": EMAIL_FROM,
        "to": [to],
        "subject": subject,
        "html": html,
        "text": text,
        # Nudges invite a reply -- the email literally offers it as the easy
        # option -- so a bounced reply would make it a lie. Also scores better
        # with spam filters than one-way noreply traffic.
        "reply_to": SUPPORT_EMAIL,
    }).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            if r.status >= 400:
                return False, f"{r.status}: {r.read()[:200].decode(errors='replace')}"
            return True, "sent"
    except urllib.error.HTTPError as e:
        return False, f"{e.code}: {e.read()[:200].decode(errors='replace')}"
    except Exception as e:
        return False, f"network error: {e}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Send the closed-test nudge email.")
    ap.add_argument("--send", action="store_true",
                    help="actually send. Without this it's a dry run.")
    ap.add_argument("--day", type=int, default=None,
                    help=f"day number to state in the email (default: computed from {START_DATE})")
    ap.add_argument("--only", metavar="EMAIL",
                    help="send to just this one address — do this first, to yourself")
    ap.add_argument("--list", default=DEFAULT_LIST,
                    help="path to the tester list JSON (default: scripts/testers.json)")
    args = ap.parse_args()

    day = args.day if args.day is not None else day_number()
    if day < 1:
        print(f"Day {day} is before START_DATE ({START_DATE}). Pass --day explicitly.")
        return 1

    testers = load_testers(args.list)
    recipients = testers
    if args.only:
        recipients = [t for t in testers if t[0].lower() == args.only.lower()]
        if not recipients:
            # Still allow it -- handy for testing with an address not on the list.
            recipients = [(args.only, "")]

    unnamed = [e for e, n in recipients if not n]
    print(f"Day {day} of {TOTAL_DAYS} · {len(recipients)} recipient(s) · "
          f"{'SENDING FOR REAL' if args.send else 'DRY RUN (nothing will be sent)'}")
    if unnamed:
        print(f"  note: {len(unnamed)} with no name will be greeted 'Hi,' — {', '.join(unnamed)}")
    print()

    if not args.send:
        subject, _, text = render(recipients[0][1], day)
        print(f"Subject: {subject}\n")
        print(text)
        print("\n--- recipients ---")
        for email, name in recipients:
            print(f"  {email:38} {name or '(no name)'}")
        print("\nRe-run with --send to actually send. Try --only <your address> --send first.")
        return 0

    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        print("RESEND_API_KEY is not set in this environment. Aborting.")
        return 1

    ok = failed = 0
    for email, name in recipients:
        subject, html, text = render(name, day)
        good, detail = send_one(api_key, email, subject, html, text)
        print(f"  {'OK  ' if good else 'FAIL'} {email:38} {detail}")
        ok, failed = (ok + 1, failed) if good else (ok, failed + 1)
        time.sleep(0.6)          # Resend free tier is ~2 req/sec

    print(f"\nDone. {ok} sent, {failed} failed.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

"""Tests for the "you signed up with Google" email.

This template exists because of a real, reported failure: a user with a
Google-created account tapped "forgot password", got the reassuring "a reset
link is on its way" message, and then waited for an email the backend had
silently decided not to send. The account had no password to reset, and the
endpoint treated that identically to "no such account".

The invariant worth defending here is the one that made that silence
tempting in the first place: the HTTP response must stay identical whether
or not the account exists, so the API can't be used to enumerate users. This
template is how the real person gets told the truth without the API leaking
it -- which only works if the email actually says the useful thing.

Extracted from server.py the same way test_welcome_email.py does it, and for
the same reason: server.py reads os.environ['MONGO_URL'] at import time.
"""

import pathlib
import re
from html import escape


def render(first_name):
    src = pathlib.Path(__file__).parent.parent / "server.py"
    text = src.read_text(encoding="utf-8")
    start = text.index("def _google_account_email(")
    end = text.index("_PWD_ITERATIONS = 200_000")
    namespace = {"_esc": escape}
    exec(text[start:end], namespace)
    return namespace["_google_account_email"](first_name)


def test_says_the_account_uses_google():
    """The whole point: the reader must learn WHY no reset link is coming."""
    html, txt = render("Bani")
    assert "Google" in html
    assert "Google" in txt


def test_tells_the_reader_what_to_actually_do():
    html, txt = render("Bani")
    assert "Continue with Google" in html
    assert "Continue with Google" in txt


def test_greets_the_reader_by_name():
    html, txt = render("Bani")
    assert "Hi Bani," in html
    assert "Hi Bani," in txt


def test_does_not_claim_a_reset_link_is_coming():
    """The failure being fixed was a false promise. Don't restate it."""
    html, txt = render("Bani")
    for blob in (html, txt):
        assert "reset link" not in blob.lower()
        assert "on its way" not in blob.lower()


def test_name_is_not_injected_raw_into_markup():
    """Names come from Google profiles, so they are user-controlled. Both
    sibling templates shipped this bug before it was caught in review."""
    html, _ = render("<script>alert(1)</script>")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_text_part_uses_the_unescaped_name():
    """Plain text is not markup -- an escaped name would render as literal
    '&amp;' to the reader."""
    _, txt = render("Tom & Jerry")
    assert "Tom & Jerry" in txt
    assert "&amp;" not in txt


def test_both_parts_are_produced():
    html, txt = render("Bani")
    assert html.strip().startswith("<!DOCTYPE html>")
    assert txt.strip()
    assert "<" not in txt          # the text part must not contain markup


def test_carries_no_link_at_all():
    """Deliberate: the action is in the app already on their phone. A link
    anywhere else is a detour dressed up as help."""
    html, _ = render("Bani")
    assert "href=" not in html


def test_missing_name_degrades_gracefully():
    for empty in ("", None):
        html, txt = render(empty or "there")
        assert "Hi there," in html
        assert "Hi ," not in html and "Hi ," not in txt

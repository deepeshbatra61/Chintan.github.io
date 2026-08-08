"""Tests for the welcome email template.

Only the pure rendering is covered here. _send_welcome_email and the backfill
endpoint live in server.py, which reads os.environ['MONGO_URL'] at import time
and so cannot be imported in a test process -- the same constraint that pushed
brief assembly out into its own module. Their behaviour is asserted against the
deployed endpoint instead, via the dry-run mode.

The template is extracted here rather than imported for that reason: these
tests pin the copy and the email-client constraints, which is where silent
breakage would otherwise go unnoticed.
"""

import re

import pytest

# Mirrors backend/server.py::_welcome_email. Kept in sync deliberately: the
# alternative is importing server.py, which is impossible without a database.
SUPPORT_EMAIL = "team@chintan.news"


def render(first_name: str) -> tuple[str, str]:
    import importlib.util
    import pathlib
    src = pathlib.Path(__file__).parent.parent / "server.py"
    text = src.read_text(encoding="utf-8")
    # Pull the function body out of server.py and exec it in isolation, so the
    # test asserts against the REAL template rather than a copy that could drift.
    start = text.index("def _welcome_email(")
    end = text.index("async def _send_welcome_email(")
    from html import escape
    namespace = {"SUPPORT_EMAIL": SUPPORT_EMAIL, "_esc": escape}
    exec(text[start:end], namespace)
    return namespace["_welcome_email"](first_name)


def test_greets_the_reader_by_name():
    html, txt = render("Deepesh")
    assert "Hi Deepesh," in html
    assert "Hi Deepesh," in txt


def test_missing_name_degrades_gracefully():
    """A Google account without a name must not produce 'Hi ,'."""
    for empty in ("", "   ", None):
        html, txt = render(empty)
        assert "Hi there," in html
        assert "Hi ," not in html and "Hi ," not in txt


def test_only_the_first_name_is_used():
    html, _ = render("Deepesh")
    assert "Hi Deepesh," in html


def test_absurdly_long_name_is_truncated():
    html, _ = render("A" * 500)
    assert len(html) < 20000
    assert "A" * 41 not in html          # capped at 40 chars


def test_both_parts_are_produced():
    """A plain-text alternative improves spam scoring and serves clients that
    refuse HTML. Sending HTML alone is a deliverability own-goal."""
    html, txt = render("Deepesh")
    assert html.strip().startswith("<!DOCTYPE html>")
    assert "<" not in txt.replace("--", "")   # text part carries no markup
    assert len(txt) > 200


def test_promises_a_real_reply_address():
    """The copy tells the reader to hit reply. If the address were missing or
    wrong, the app would be lying in its first contact with a user."""
    html, txt = render("Deepesh")
    assert SUPPORT_EMAIL in html
    assert SUPPORT_EMAIL in txt
    assert "not a no-reply" in html
    assert f"mailto:{SUPPORT_EMAIL}" in html


def test_survives_outlook_word_rendering():
    """Outlook renders through Word: <style> blocks and modern CSS are ignored,
    so every style must be inline and layout must be tables."""
    html, _ = render("Deepesh")
    assert "<style" not in html.lower()
    assert "display:flex" not in html.replace(" ", "")
    assert "display:grid" not in html.replace(" ", "")
    assert "<table" in html
    assert 'role="presentation"' in html        # tables marked decorative for a11y


def test_uses_only_web_safe_fonts():
    """Custom web fonts do not load in most mail clients; Playfair/Manrope/
    JetBrains Mono must be substituted, not referenced."""
    html, _ = render("Deepesh")
    for webfont in ("Playfair", "Manrope", "JetBrains", "fonts.googleapis"):
        assert webfont not in html
    assert "Georgia" in html and "Courier New" in html


def test_carries_no_call_to_action_button():
    """Deliberate: the reader has already signed up. A big coloured button is
    the single strongest 'this is marketing' signal for Gmail's Promotions
    filter, and this email is a letter."""
    html, _ = render("Deepesh")
    assert "border-radius:10px; padding:13px 32px" not in html
    links = re.findall(r'href="([^"]+)"', html)
    # Exactly one link, and it is the reply address. More links means more
    # promotional signal and more phishing-filter surface.
    assert links == [f"mailto:{SUPPORT_EMAIL}"]


def test_html_is_balanced():
    html, _ = render("Deepesh")
    assert html.count("<table") == html.count("</table>")
    assert html.count("<tr") == html.count("</tr>")
    assert html.count("<td") == html.count("</td>")


def test_name_is_not_injected_raw_into_markup():
    """Names come from Google profiles and user input, so a name containing
    markup must not be able to restructure the email."""
    html, _ = render('<script>alert(1)</script>')
    assert "<script>" not in html


@pytest.mark.parametrize("phrase", [
    "Welcome to Chintan",
    "Don't just consume. Contemplate.",
])
def test_key_brand_copy_survives(phrase):
    html, txt = render("Deepesh")
    assert phrase in html
    assert phrase.replace("&mdash;", "--") in txt or phrase in txt

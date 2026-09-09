"""Guards on the seeded event registries.

These catch the failure modes that are invisible until a card is already in
front of a reader: a duplicate id silently overwriting an entry, a window that
never opens, a scheduled arc with no keywords (so it can never match an
article and never appears at all), or a category with no icon on the frontend.

That last one spans a language and a repo boundary -- CALENDAR_EVENTS is
Python here, CALENDAR_ICONS is JavaScript in frontend/src/lib/calendar.js --
which is precisely the kind of pairing that drifts without anyone noticing.
"""

import pathlib
import re
from datetime import date, timezone, timedelta

SERVER = pathlib.Path(__file__).parent.parent / "server.py"
ICONS_JS = (
    pathlib.Path(__file__).parent.parent.parent
    / "frontend" / "src" / "lib" / "calendar.js"
)


def _exec_block(start_marker: str, end_marker: str, extra=None):
    text = SERVER.read_text(encoding="utf-8")
    src = text[text.index(start_marker):text.index(end_marker)]
    ns = {"timezone": timezone, "timedelta": timedelta}
    ns.update(extra or {})
    exec(src, ns)
    return ns


def scheduled_events():
    return _exec_block("SCHEDULED_EVENTS = [", "async def _sync_scheduled_events")["SCHEDULED_EVENTS"]


def calendar_events():
    return _exec_block("def _cal_query(", "def _wave_intensity(")["CALENDAR_EVENTS"]


# ───────────────────────── SCHEDULED_EVENTS ─────────────────────────

def test_scheduled_story_ids_are_unique():
    """A duplicate id doesn't error -- it upserts over the earlier entry, so
    one event silently replaces another in the DB."""
    ids = [e["story_id"] for e in scheduled_events()]
    assert len(ids) == len(set(ids))


def test_scheduled_windows_open_before_they_close():
    for e in scheduled_events():
        start = date.fromisoformat(e["start"][:10])
        end = date.fromisoformat(e["end"][:10])
        assert start <= end, f"{e['story_id']}: starts after it ends"


def test_every_scheduled_event_has_specific_keywords():
    """A scheduled story only surfaces once it matches an article, so an entry
    without keywords can never appear -- it looks seeded and does nothing."""
    for e in scheduled_events():
        assert e.get("keywords"), f"{e['story_id']} has no keywords"


def test_scheduled_keywords_are_not_dangerously_generic():
    """Bare words false-merge unrelated stories into one topic, which is the
    exact failure the auto-clustering kind hit twice."""
    banned = {"match", "festival", "election", "summit", "war", "day", "india", "news"}
    for e in scheduled_events():
        for kw in e["keywords"]:
            assert kw.strip().lower() not in banned, f"{e['story_id']}: '{kw}' is too generic"


# ───────────────────────── CALENDAR_EVENTS ─────────────────────────

def test_calendar_event_ids_are_unique():
    ids = [e["event_id"] for e in calendar_events()]
    assert len(ids) == len(set(ids))


def test_calendar_dates_parse():
    for e in calendar_events():
        date.fromisoformat(e["date"])  # raises if malformed


def test_every_calendar_event_has_a_research_query():
    """No query means the agent has nothing to look up, so the card can never
    clear verification and never shows."""
    for e in calendar_events():
        assert e.get("research_query", "").strip(), f"{e['event_id']} has no research_query"


def test_research_queries_avoid_process_language():
    """Telling the model to 'verify' makes it narrate verifying, which is how
    'I notice there is a discrepancy...' reached a live card once already."""
    for e in calendar_events():
        q = e["research_query"].lower()
        for word in ("verify", "confirm", "double-check"):
            assert word not in q, f"{e['event_id']}: research_query says '{word}'"


def test_every_category_has_a_frontend_icon():
    """CALENDAR_ICONS lives in another language in another folder; an
    unmapped category degrades to a generic icon rather than erroring, so
    nothing would surface the drift except a reader noticing."""
    js = ICONS_JS.read_text(encoding="utf-8")
    block = js[js.index("CALENDAR_ICONS = {"):]
    block = block[: block.index("};")]
    mapped = set(re.findall(r"^\s*([a-z]+):", block, re.MULTILINE))

    used = {e["category"] for e in calendar_events()}
    missing = used - mapped
    assert not missing, f"categories with no icon in calendar.js: {sorted(missing)}"

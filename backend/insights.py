"""Reading observations for the profile card — pure logic, no I/O.

Imports only the standard library so it can be unit tested without a database.
`server.py` does the queries and the join; this module only looks at the result.

WHY THIS EXISTS
---------------
The card it replaces produced this, verbatim, on a real profile:

    "Politics led your reading recently. You haven't opened a Politics story
     in 0 days — your quietest corner."

Three separate faults, all the same root: the card had a slot to fill and
filled it whether or not it had anything to say.

  1. The "blind spot" was chosen with `never[0]` — the first zero-count entry
     in a hardcoded category list. Reading one Sports story just advanced the
     cursor to the next array element. That is iteration, not observation.
  2. Once every category had been read, it fell back to `min()` over
     last-read dates. With all dates tied at today, `min()` returns the FIRST
     list element — Politics — and the gap computed to 0 days. "You haven't
     done this in 0 days" refutes itself.
  3. Nothing stopped the blind spot from being the top category too, so the
     card called Politics both the strongest interest and the quietest corner
     in one sentence.

THE RULE THIS MODULE FOLLOWS
----------------------------
Every observation must be EARNED. Each one carries an evidence threshold and
is only emitted when the data clears it. When nothing clears, we return fewer
observations — or none — rather than inventing something to fill the space.
An empty card is honest; a fabricated one is not.

Deliberately NOT included: time-of-day habits. `created_at` is stored in UTC
and no user timezone is recorded, so "you read in the mornings" would be a
guess dressed as a fact — the exact failure mode above. It needs the client to
report its offset first.

Also avoided: anything the profile tiles already show (articles read, saved
count, day streak). Repeating a number the user can see directly above is
filler, even when it is true.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

# How far back "recently" actually reaches. The previous card said "recently"
# while querying a user's entire history with no date filter at all.
WINDOW_DAYS = 30

# Below this, a window is too thin to say anything about, so we fall back to
# all-time and label it differently rather than over-reading a handful of taps.
MIN_READS_FOR_WINDOW = 8

# Emission thresholds. Each exists so an observation cannot appear without
# evidence behind it.
BEAT_MIN_SHARE = 35          # % of reads in one category before it's a "beat"
BEAT_MIN_READS = 8
RANGE_MIN_CATEGORIES = 4
RANGE_MIN_READS = 8
DEPTH_MIN_RATE = 55          # % of opened articles actually finished
DEPTH_MIN_READS = 10
RISING_RECENT_SLICE = 10     # how many of the latest reads count as "lately"
RISING_MIN_HITS = 3          # occurrences within that slice
RISING_MULTIPLIER = 2.0      # ...and at least this much above its usual share
SAVING_MIN = 5

# Priority, strongest statement first. Fixed rather than score-ranked on
# purpose: scores across different units (a percentage vs a count) are not
# comparable, and a fixed order makes the card predictable and testable.
# `range` sits last because "you read several sections" is the least
# distinctive thing we can say about somebody.
PRIORITY = ("beat", "rising", "depth", "saving", "range")

MAX_OBSERVATIONS = 2


def _parse(value) -> Optional[datetime]:
    """Parse a stored timestamp defensively; never raise on bad data."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def observe(reads: List[dict], bookmarks_count: int, now: datetime) -> List[dict]:
    """Return up to MAX_OBSERVATIONS earned observations, strongest first.

    `reads` is one dict per article opened:
        {"category": str, "at": iso-string | datetime | None, "completed": bool}

    Returns structured data, not prose. The client owns the wording so it can
    emphasise the numbers; this module owns what is true. Every entry has a
    "kind" plus the values that justified it, so a reader of the response can
    check the claim against the numbers that produced it.
    """
    dated = [(r, _parse(r.get("at"))) for r in reads]

    # "Recently" means something now. Fall back to all-time only when the
    # window is too sparse to support a claim.
    cutoff = now - timedelta(days=WINDOW_DAYS)
    windowed = [r for r, at in dated if at and at >= cutoff]
    if len(windowed) >= MIN_READS_FOR_WINDOW:
        scope, sample = "recent", windowed
    else:
        scope, sample = "all", [r for r, _ in dated]

    total = len(sample)
    if not total:
        return []

    counts = Counter((r.get("category") or "Other") for r in sample)
    top_category, top_count = counts.most_common(1)[0]
    top_pct = round(top_count / total * 100)

    found: Dict[str, dict] = {}

    # BEAT — a genuine centre of gravity, not merely the largest slice of a
    # scattered read. Requires a real share AND enough reads to mean anything.
    if total >= BEAT_MIN_READS and top_pct >= BEAT_MIN_SHARE:
        found["beat"] = {"kind": "beat", "category": top_category,
                         "pct": top_pct, "count": top_count, "scope": scope}

    # RISING — the positive form of what "blind spot" was groping for. Instead
    # of naming a gap, name a habit that is forming: a section climbing in the
    # latest reads relative to its usual share. Excludes the top category,
    # which is already covered and would just restate the beat.
    latest = [r for r, at in sorted(
        (d for d in dated if d[1]), key=lambda d: d[1], reverse=True)][:RISING_RECENT_SLICE]
    if len(latest) >= RISING_RECENT_SLICE:
        recent_counts = Counter((r.get("category") or "Other") for r in latest)
        for category, hits in recent_counts.most_common():
            if category == top_category or hits < RISING_MIN_HITS:
                continue
            usual = counts.get(category, 0) / total
            lately = hits / len(latest)
            if usual == 0 or lately >= usual * RISING_MULTIPLIER:
                found["rising"] = {"kind": "rising", "category": category,
                                   "hits": hits, "of": len(latest), "scope": scope}
                break

    # DEPTH — finishing what you open is a habit worth naming, and it is
    # invisible in the tiles above.
    finished = sum(1 for r in sample if r.get("completed"))
    if total >= DEPTH_MIN_READS:
        rate = round(finished / total * 100)
        if rate >= DEPTH_MIN_RATE:
            found["depth"] = {"kind": "depth", "pct": rate,
                              "completed": finished, "total": total, "scope": scope}

    # SAVING — building a library to return to.
    if bookmarks_count >= SAVING_MIN:
        found["saving"] = {"kind": "saving", "count": bookmarks_count, "scope": "all"}

    # RANGE — breadth. Only interesting alongside a beat ("focused, but still
    # curious"), so it sits last in priority.
    distinct = len([c for c, n in counts.items() if n > 0])
    if total >= RANGE_MIN_READS and distinct >= RANGE_MIN_CATEGORIES:
        found["range"] = {"kind": "range", "count": distinct, "scope": scope}

    return [found[k] for k in PRIORITY if k in found][:MAX_OBSERVATIONS]

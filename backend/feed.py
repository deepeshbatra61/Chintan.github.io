"""Feed diversification — pure, no I/O, so it can be tested without a database.

THE PROBLEM THIS SOLVES
-----------------------
Read a few business stories and the next feed load is a wall of business. That
isn't a bug in any one signal; it's structural. Almost every term in
_score_article is keyed to CATEGORY -- declared interest (+20), subcategory
(+28), completion (0-20), engagement (0-20), comments (0-10), polls (+5),
likes (up to +20), relevance (±10) -- against freshness maxing out at 10. So
the "article score" is really a category score wearing an article's name, and
sorting a list by it necessarily clusters that list by category.

Re-ranking here rather than reweighting there is deliberate: the weights
encode genuine signal about what someone wants to read, and flattening them
would trade a boring feed for an irrelevant one. What was missing was any
notion that a feed is a SEQUENCE, not a leaderboard -- position 3 shouldn't be
chosen as though positions 1 and 2 didn't happen.

THREE RULES, DOING DIFFERENT JOBS
---------------------------------
1. HARD: never two of the same category back to back.
2. SOFT: a category already used in the recent window is penalised, more each
   time it repeats.
3. SOFT (News v2, many voices): a PUBLISHER already used in the window is
   penalised too, and doubly when it led the card just above. It only
   reorders -- it never swaps an event's lead (that is fixed at ingest, so
   pages stay stable). Times of India led ~20% of cards on 2026-10-03.

The hard rule alone permits B,T,B,T,B,T -- adjacency satisfied, and business
still owns half the screen, which is the complaint restated rather than fixed.
The soft rule alone permits the occasional back-to-back pair. Together they
give variety at both scales while leaving a genuinely dominant story free to
outrank a weak one from another category.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

# Points deducted per prior article of the same category inside the window.
# Sized against _score_article's real spread: a strong category advantage there
# runs 60-100+ points, so a small nudge would be swallowed whole. This is large
# enough to actually reorder, small enough that a genuinely top story still
# wins its slot.
CATEGORY_REPEAT_PENALTY = 22.0

# How far back the soft rule looks. Roughly a phone screen's worth of cards --
# the unit a reader actually perceives as "my feed right now", which is the
# thing that felt monotonous.
DIVERSITY_WINDOW = 6

# Publisher variety, as a share of the category penalty so it scales with
# whichever penalty the caller uses (22 personalised, 6 guest). Weaker than the
# category rule: variety of voices should reorder near-ties, not bury news.
PUBLISHER_REPEAT_SHARE = 0.6


def _publisher(article: dict) -> str:
    return article.get("publisher") or ""      # canonical key, set by events_service


def diversify(
    scored: List[Tuple[float, dict]],
    needed: int,
    penalty: float = CATEGORY_REPEAT_PENALTY,
    window: int = DIVERSITY_WINDOW,
    publisher_variety: bool = False,
) -> List[dict]:
    """Greedily re-rank `scored` (highest first) into a varied sequence.

    `scored` is [(score, article)]; `needed` is how many articles the caller
    will actually use, which bounds the work -- deep pagination shouldn't pay
    to order a whole candidate pool it will throw away.

    Never drops or invents an article: with a thin catalogue where everything
    left shares the previous category, the hard rule yields rather than
    returning a short feed. A repeat is a worse feed; a missing story is a
    broken one.
    """
    remaining = list(scored)
    out: List[dict] = []
    emitted: List[str] = []
    emitted_pubs: List[str] = []
    # Off until News v2 events are live (the caller passes EVENTS_MODE == live).
    pub_penalty = penalty * PUBLISHER_REPEAT_SHARE if publisher_variety else 0.0
    counts = category_counts([a for _, a in remaining])
    counts.pop("", None)  # uncategorised never conflicts, so never constrains

    while remaining and len(out) < needed:
        prev_cat = emitted[-1] if emitted else None
        recent = emitted[-window:]
        recent_pubs = emitted_pubs[-window:]
        prev_pub = emitted_pubs[-1] if emitted_pubs else None

        best_i = best_val = None      # best that also keeps the rest arrangeable
        loose_i = loose_val = None    # best that merely satisfies adjacency
        for i, (score, article) in enumerate(remaining):
            cat = article.get("category") or ""
            # An uncategorised article blocks nothing and is blocked by nothing:
            # treating "" as a category would make unrelated stories collide.
            if cat and cat == prev_cat:
                continue
            adjusted = score - penalty * (recent.count(cat) if cat else 0)
            pub = _publisher(article)
            if pub:
                adjusted -= pub_penalty * (recent_pubs.count(pub) + (1 if pub == prev_pub else 0))
            if loose_i is None or adjusted > loose_val:
                loose_i, loose_val = i, adjusted
            if _still_arrangeable(counts, len(remaining), cat) and (best_i is None or adjusted > best_val):
                best_i, best_val = i, adjusted

        pick = best_i if best_i is not None else loose_i
        if pick is None:
            # Everything left repeats the previous category. Take the best of
            # them rather than truncating the feed.
            pick = max(range(len(remaining)), key=lambda i: remaining[i][0])

        _, article = remaining.pop(pick)
        out.append(article)
        cat = article.get("category") or ""
        emitted.append(cat)
        emitted_pubs.append(_publisher(article))
        if cat:
            counts[cat] -= 1

    return out


def _still_arrangeable(counts: Dict[str, int], remaining_before: int, picking: str) -> bool:
    """Would picking a `picking` article now leave a remainder that can still be
    ordered with no two same-category neighbours?

    Why this exists: a pure greedy spends its 'separator' categories early --
    the soft penalty pushes the dominant category down, so everything else goes
    first -- then runs out and is forced to stack the dominant one at the end
    (Politics, Politics, Politics) even when a clean interleave existed. It
    passed tests only while separators were plentiful.

    The condition is the standard one for 'no two adjacent equal': with R
    items left and the next slot barred to category p, an arrangement exists
    iff every category c has count_c <= ceil(R / 2), and p itself has
    count_p <= floor(R / 2) (it can't take the first of those R slots).
    """
    r = remaining_before - 1
    after = dict(counts)
    if picking:
        after[picking] = after.get(picking, 0) - 1
    for c, n in after.items():
        limit = r // 2 if c == picking else (r + 1) // 2
        if n > limit:
            return False
    return True


def pin_first(ordered: List[dict], is_pinned) -> List[dict]:
    """Move the single pinned story (a Desk 'Breaking' item inside its pin
    window) to slot 1. Applied AFTER diversify, and only to page 1 by the
    caller, so the pin can't be undone by the variety rules and doesn't
    reappear on later pages. If several qualify, the one already ranked
    highest wins; the rest keep their (boosted) positions.

    The pinned slot is exempt from the no-two-in-a-row rule by design: a
    Breaking story outranks variety for its 6 hours."""
    for i, article in enumerate(ordered):
        if is_pinned(article):
            if i == 0:
                return ordered
            return [article] + ordered[:i] + ordered[i + 1:]
    return ordered


def max_consecutive_repeats(articles: List[dict]) -> int:
    """Longest run of one category. Used by tests, and handy in a REPL when
    someone reports the feed feeling samey again."""
    longest = current = 0
    prev = None
    for a in articles:
        cat = a.get("category") or ""
        current = current + 1 if cat and cat == prev else 1
        longest = max(longest, current)
        prev = cat
    return longest


def category_counts(articles: List[dict]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for a in articles:
        cat = a.get("category") or ""
        counts[cat] = counts.get(cat, 0) + 1
    return counts

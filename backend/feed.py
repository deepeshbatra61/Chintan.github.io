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

TWO RULES, DOING DIFFERENT JOBS
-------------------------------
1. HARD: never two of the same category back to back.
2. SOFT: a category already used in the recent window is penalised, more each
   time it repeats.

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


def diversify(
    scored: List[Tuple[float, dict]],
    needed: int,
    penalty: float = CATEGORY_REPEAT_PENALTY,
    window: int = DIVERSITY_WINDOW,
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

    while remaining and len(out) < needed:
        prev_cat = emitted[-1] if emitted else None
        recent = emitted[-window:]

        best_i = None
        best_val = 0.0
        for i, (score, article) in enumerate(remaining):
            cat = article.get("category") or ""
            # An uncategorised article blocks nothing and is blocked by nothing:
            # treating "" as a category would make unrelated stories collide.
            if cat and cat == prev_cat:
                continue
            adjusted = score - penalty * (recent.count(cat) if cat else 0)
            if best_i is None or adjusted > best_val:
                best_i, best_val = i, adjusted

        if best_i is None:
            # Everything left repeats the previous category. Take the best of
            # them rather than truncating the feed.
            best_i = max(range(len(remaining)), key=lambda i: remaining[i][0])

        _, article = remaining.pop(best_i)
        out.append(article)
        emitted.append(article.get("category") or "")

    return out


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

"""Brief assembly — pure logic, no I/O.

Deliberately imports nothing but the standard library. `server.py` performs the
database reads and the Anthropic call; everything that decides *what a brief says
and where each card points* lives here, so it can be unit tested without a
database, a network, or an API key.

WHY THIS MODULE EXISTS
----------------------
Brief cards used to open a different article than the one they described. Two
independent causes, both the same shape: a value was produced in one place and a
value was produced in another, and the code merely *assumed* they corresponded.

    BEFORE (broken)
      by_category[cat][:3] ─┬─→ [0] ───────────────→ article_id   (the LINK)
                            └─→ [0],[1],[2] → LLM → prose blob    (the TEXT)
                                                        │
                                    client re-split the blob on ". " and
                                    index-matched it back to the links
                                                        │
                        two paths, never reconciled ────┘

    AFTER (this module)
      by_category[cat] ──→ rank ──→ ONE pick per category
                                       │
                                       ├─→ article_id  ┐
                                       └─→ take        ├─ same object, one source
                                                       ┘
                              summary = " ".join(takes)   (derived, never parsed)

Two invariants hold everything together. Break either and the original bug
returns, so both are asserted in tests:

  I1. stories[i]["take"] describes stories[i]["article_id"].
      Guaranteed structurally: both are written from the same picked article.

  I2. summary.split(/\\.\\s+/) == the takes, exactly.
      Guaranteed by sanitise_take() removing every internal ". " before the
      join. This matters because app versions already shipped to the Play Store
      re-derive card text that way, and they will keep doing so for months.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

# The model is asked to emit one line per category, numbered and pipe-delimited,
# so takes are read off structurally instead of being recovered by splitting
# prose. "1|" is vanishingly rare in news copy; a sentence boundary is not.
TAKE_LINE = re.compile(r"^\s*(\d+)\s*\|\s*(.+?)\s*$")

# Titles and abbreviations that end in a period and are followed by more words.
# Left un-normalised, each one is an invisible sentence boundary to the older
# client's regex.
_ABBREVIATIONS = (
    "Dr", "Mr", "Mrs", "Ms", "Prof", "Sen", "Rep", "Gov", "Lt", "Sgt", "Capt",
    "St", "Mt", "Inc", "Ltd", "Corp", "Co", "Jr", "Sr", "vs", "etc", "No",
    "Vol", "Fig", "Est", "Approx", "Dept", "Univ", "Assn", "Bros",
    "Jan", "Feb", "Mar", "Apr", "Jun", "Jul", "Aug", "Sept", "Sep", "Oct", "Nov", "Dec",
    "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun",
)
_ABBREV_RE = re.compile(r"\b(" + "|".join(_ABBREVIATIONS) + r")\.(?=\s)", re.IGNORECASE)

# Dotted initialisms: U.S. -> US, U.K. -> UK, e.g. -> eg, a.m. -> am.
_INITIALISM_RE = re.compile(r"\b(?:[A-Za-z]\.){2,}")


# ─────────────────────────── ranking ────────────────────────────────────────

def score_candidate(article: dict, user_interests: List[str], now: datetime) -> float:
    """Rank one article against its rivals *inside the same category*.

    Deliberately NOT server.py's `_score_article`. That function ranks
    categories for the feed: its affinity, engagement, comment, poll and
    relevance signals are all keyed on `category`, so every candidate here
    shares them and they cancel to a constant. It also adds a random discovery
    bonus, which would make brief picks irreproducible and the tests below
    unassertable. This scores only signals that actually differ between two
    articles in the same category, and is fully deterministic.
    """
    score = 0.0

    # A declared *sub*-topic is the one interest signal that varies here.
    sub = article.get("subcategory")
    if sub and user_interests and sub in user_interests:
        score += 30.0

    # Real reader behaviour, capped so one runaway article can't dominate.
    score += min(float(article.get("view_count") or 0), 40.0) * 0.5
    score += min(float(article.get("likes") or 0), 20.0) * 1.0
    score -= min(float(article.get("dislikes") or 0), 20.0) * 1.0

    # Editorial richness: a story we actually have depth on makes a better brief
    # line than a bare wire item, because the model has something to work from.
    for field, points in (("what", 6.0), ("why", 4.0), ("context", 3.0), ("impact", 3.0)):
        value = article.get(field)
        if isinstance(value, str) and len(value.strip()) > 40:
            score += points
    if article.get("image_url"):
        score += 2.0

    if article.get("is_breaking"):
        score += 8.0
    elif article.get("is_developing"):
        score += 4.0

    # Freshness last and smallest — it used to be the *only* rule, which is how
    # a thin wire item published 20 minutes ago beat a substantial morning read.
    published_at = _parse_dt(article.get("published_at"))
    if published_at:
        age_hours = (now - published_at).total_seconds() / 3600.0
        if age_hours <= 6:
            score += 10.0
        elif age_hours <= 24:
            score += 5.0
        elif age_hours <= 72:
            score += 2.0

    return score


def _parse_dt(value) -> Optional[datetime]:
    """Parse an ISO timestamp defensively; return None rather than raising."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def select_stories(
    top_cats: List[str],
    by_category: Dict[str, list],
    user_interests: List[str],
    now: datetime,
) -> List[Tuple[str, dict]]:
    """Pick one article per category — the one we will both link and describe.

    Returns (category, article) PAIRS rather than a bare list. That is not
    cosmetic: a category with no usable article is skipped, so a parallel
    `categories` list would silently shift out of step with the picks. Carrying
    the pairing in one value removes that possibility, which is the same class
    of bug this whole module exists to eliminate.

    Ties break on article_id so ordering is stable across processes, not just
    within one run.
    """
    pairs: List[Tuple[str, dict]] = []
    for cat in top_cats:
        candidates = [a for a in by_category.get(cat, []) if a.get("article_id")]
        if not candidates:
            continue
        best = max(
            candidates,
            key=lambda a: (score_candidate(a, user_interests, now), str(a.get("article_id", ""))),
        )
        pairs.append((cat, best))
    return pairs


# ─────────────────────────── prompt + parsing ───────────────────────────────

def build_prompt(brief_type: str, user_name: str, pairs: List[Tuple[str, dict]]) -> str:
    """One story per line in, one take per line out.

    The model is never shown a story it cannot be quoted on, so there is no
    choice for it to make and therefore no choice for us to lose track of.
    """
    lines = []
    for idx, (cat, art) in enumerate(pairs, start=1):
        body = (art.get("what") or art.get("description") or art.get("summary") or "").strip()
        lines.append(
            f"{idx}| Category: {cat}\n"
            f"   Headline: {art.get('title', '')}\n"
            f"   Detail: {body[:400]}"
        )
    stories_block = "\n".join(lines)

    return (
        f"You are writing a personalized {brief_type} brief for {user_name}.\n"
        f"Below are {len(pairs)} stories, numbered.\n\n"
        f"{stories_block}\n\n"
        f"Write exactly ONE sentence about EACH numbered story, in the same order.\n"
        f"Be specific: use the actual names, places and numbers from that story.\n"
        f"Write only about the story with that number. Do not merge stories.\n\n"
        f"FORMAT: one line per story, starting with its number and a pipe:\n"
        f"1| <sentence about story 1>\n"
        f"2| <sentence about story 2>\n\n"
        f"RULES: no markdown, no headings, no bullet points, no preamble.\n"
        f"Do not start with the user's name or a title like 'Your Brief'.\n"
        f"Keep each sentence under 30 words. Output only the numbered lines."
    )


def parse_takes(raw: str, expected: int) -> List[Optional[str]]:
    """Read one take per numbered line. Returns `expected` slots; None where missing.

    Structural, not prose-derived: a missing or malformed line becomes a None
    the caller fills deterministically, instead of silently shifting every
    subsequent take by one — which is precisely how the original bug behaved.
    """
    takes: List[Optional[str]] = [None] * expected
    if not raw:
        return takes

    for line in raw.splitlines():
        match = TAKE_LINE.match(line)
        if not match:
            continue
        index = int(match.group(1)) - 1
        if 0 <= index < expected and takes[index] is None:
            cleaned = sanitise_take(match.group(2))
            if cleaned:
                takes[index] = cleaned
    return takes


def sanitise_take(text: str) -> str:
    """Return a single, split-safe sentence ending in exactly one period.

    Enforces invariant I2. Every internal ". " is removed, so joining takes with
    a space can only ever split back into the same takes. Without this, the
    older client's `split(/\\.\\s+/)` treats "U.S. Fed cut rates." as two
    fragments and shifts every card after it.
    """
    if not text:
        return ""

    cleaned = re.sub(r"^#+\s*", "", text).replace("**", "").replace("*", "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"\.{2,}", "", cleaned)                      # ellipses
    cleaned = _INITIALISM_RE.sub(lambda m: m.group(0).replace(".", ""), cleaned)
    cleaned = _ABBREV_RE.sub(r"\1", cleaned)

    # Anything still ending a clause mid-line means the model wrote more than
    # one sentence. Keep the content, drop the boundary — truncating would lose
    # information, and leaving it would break I2.
    cleaned = re.sub(r"\.\s+", "; ", cleaned)

    cleaned = cleaned.rstrip(" ;.,")
    return f"{cleaned}." if cleaned else ""


def fallback_take(article: dict) -> str:
    """Deterministic take for when the model fails or skips a line.

    Never uses `text.split(".")[0]` — on "U.S. officials said..." that yields
    "U", which the previous fallback shipped as an entire brief sentence.
    """
    for field in ("what", "description", "summary", "title"):
        value = article.get(field)
        if isinstance(value, str) and value.strip():
            return sanitise_take(value.strip()[:240])
    return ""


# ─────────────────────────── assembly ───────────────────────────────────────

def assemble(pairs: List[Tuple[str, dict]], llm_text: Optional[str]) -> dict:
    """Build the brief payload. `llm_text` may be None when the model call failed.

    Emits `categories` alongside the stories because the client reads
    categories[idx] for each card's label. Both lists are built in the same
    loop from the same pair, so they cannot drift apart.
    """
    parsed = parse_takes(llm_text or "", len(pairs))

    stories: List[dict] = []
    takes: List[str] = []
    used_categories: List[str] = []

    for idx, (category, article) in enumerate(pairs):
        take = parsed[idx] or fallback_take(article)
        if not take:
            continue
        takes.append(take)
        used_categories.append(category)
        stories.append({
            "title": article.get("title", ""),
            "source": article.get("source", ""),
            "article_id": article.get("article_id", ""),
            "take": take,
        })

    summary = " ".join(takes)
    word_count = len(summary.split())
    return {
        "summary": summary,
        "categories": used_categories,
        "referenced_stories": stories,
        "read_time": f"{max(1, round(word_count / 200))} min read",
    }

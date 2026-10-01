"""Chintan Desk: the pure rules. No I/O, so everything that decides what the
Desk does (dedup, placement, when a story ends, what a valid draft is) is
testable without a database. Same split as feed.py / categories.py.

Locked in /plan-eng-review 2026-09-28. The decisions each rule implements are
named inline (D8, D9, D10, D11) so a future change can find its reasoning.

HEAT
----
    1 Normal    ranked like any story of its freshness
    2 Notable   boosted, fades over 12h
    3 Big       boosted more, fades over 24h
    4 Breaking  pinned first on page 1 for 6h, then behaves as Big

DEVELOPING LIFECYCLE (kind "desk")
----------------------------------
    active ─▶ now < min_until (24h)                 → stay  (minimum run)
              now ≥ hard_end (14d, !long_running)   → end: cap
              now - last_updated ≥ quiet window     → end: quiet
              otherwise                             → stay
    quiet window by heat: Breaking/Big 36h · Notable 48h · Normal 72h.
    Every window is > 24h because API articles arrive a day late (NewsAPI
    free tier); a shorter window would close stories still in progress.
    last_updated is stamped by the ingest tagger at TAG time, so the timer
    runs on the ingest clock, not on the articles' (day-old) publish times.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional
from urllib.parse import urlparse

HEAT_NORMAL, HEAT_NOTABLE, HEAT_BIG, HEAT_BREAKING = 1, 2, 3, 4
HEAT_LABELS = {1: "Normal", 2: "Notable", 3: "Big", 4: "Breaking"}

# Personalised feed: points added to _score_article, fading linearly to 0.
# Sized against that score's real spread (a strong category signal is
# 60-100+), so Big is a real lift without steamrolling a reader's interests.
HEAT_POINTS = {HEAT_NOTABLE: (12.0, 12), HEAT_BIG: (25.0, 24)}      # (points, hours)
# Guest feed: the score there is rank position (1 apart), so the boost is in
# SLOTS, not points (D11b). Same fade windows.
HEAT_SLOTS = {HEAT_NOTABLE: (3.0, 12), HEAT_BIG: (8.0, 24)}
BREAKING_PIN_HOURS = 6

QUIET_WINDOW_H = {HEAT_NORMAL: 72, HEAT_NOTABLE: 48, HEAT_BIG: 36, HEAT_BREAKING: 36}
MIN_RUN_H = 24
HARD_CAP_DAYS = 14
EXTEND_H = 24
ABSORB_WINDOW_H = 72          # D10: fold next-day API coverage into a desk story
RESEARCHING_STALE_MIN = 5     # D11e: a job this old died with its process
DRAFT_REUSE_MIN = 10          # D3: same topic within this returns the same draft

CATEGORIES = ("Politics", "Business", "Technology", "Sports", "Entertainment", "Science", "World")
NEWS_TYPES = ("normal", "developing")

HEADLINE_MIN, HEADLINE_MAX = 8, 160
SUMMARY_MIN, SUMMARY_MAX = 20, 900
POINT_MAX, POINTS_MAX = 300, 5
TOPIC_MIN, TOPIC_MAX = 3, 600          # a pasted link can be long
REASON_MIN = 10
IMAGE_URL_MAX = 600
KEYWORDS_MIN_DEVELOPING = 3

_STOP = frozenset("""
a an the and or of in on at to for from by with about into over after before
is are was were be been has have had will would can could should may might
this that these those it its as not no new says said live update updates
today latest news report reports amid vs than more most
""".split())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value) -> Optional[datetime]:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ── ranking clock (D8) ────────────────────────────────────────────────────────

def rank_at(published_at, delay_hours: float) -> Optional[str]:
    """When a story should be treated as having arrived, for ranking only.
    published_at + the source's known delivery delay: NewsAPI's free tier
    delivers a day late, so its articles shift forward 24h (their order among
    themselves is unchanged); the Desk and real-time sources use 0. Cards keep
    showing the real published_at."""
    dt = parse_dt(published_at)
    if dt is None:
        return None
    return (dt + timedelta(hours=delay_hours)).isoformat()


# ── topic matching ────────────────────────────────────────────────────────────

def normalize_topic(topic: str) -> str:
    return re.sub(r"\s+", " ", (topic or "").strip().lower())


def topic_text(topic: str) -> str:
    """The words a topic is about. For a pasted link that's the article
    slug ("/news/sc-strikes-down-electoral-bonds-12345.html" → "sc strikes
    down electoral bonds"), which is how a link can be deduplicated before
    anything is fetched."""
    t = (topic or "").strip()
    if t.lower().startswith(("https://", "http://")) and " " not in t:
        path = urlparse(t).path
        slug = max(re.split(r"/+", path), key=len, default="")
        slug = re.sub(r"\.(html?|cms|php|aspx?)$", "", slug)
        words = [w for w in re.split(r"[-_]+", slug) if w and not w.isdigit() and len(w) < 30]
        return " ".join(words)
    return t


def topic_terms(topic: str) -> list[str]:
    """Significant words of a topic, in order, de-duplicated."""
    out: list[str] = []
    for w in re.findall(r"[a-z0-9][a-z0-9\-']*", normalize_topic(topic_text(topic))):
        w = w.strip("-'")
        if len(w) > 2 and w not in _STOP and w not in out:
            out.append(w)
    return out


def _kw_pattern(kw: str):
    """Word-boundary match for single words, escaped substring for phrases.
    Mirrors categories._kw_pattern (kept local so this module stays
    dependency-free)."""
    if " " in kw:
        return re.compile(re.escape(kw), re.IGNORECASE)
    return re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)


def keyword_hits(keywords: Iterable[str], text: str) -> int:
    return sum(1 for kw in keywords if kw and _kw_pattern(kw).search(text or ""))


_MONTHS = {"january", "february", "march", "april", "may", "june", "july", "august", "september",
           "october", "november", "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep",
           "sept", "oct", "nov", "dec"}
_PHRASE_STOP = {"the", "and", "for", "with", "from", "into", "over", "after", "amid", "about", "says",
                "said", "new", "its", "his", "her", "their", "this", "that", "was", "are", "has", "had"}


def _phrase_tokens(kw: str) -> list[str]:
    """The words of a keyword phrase that must appear for it to count. Codes,
    years and dates ('fz1073', '2026', 'september') are dropped: research
    writes them into keywords, but coverage of the same event rarely repeats
    them verbatim."""
    out = []
    for t in re.findall(r"[a-z0-9][a-z0-9'\-]*", kw.lower()):
        if any(ch.isdigit() for ch in t) or t in _MONTHS or t in _PHRASE_STOP or len(t) < 3:
            continue
        out.append(t)
    return out


def story_keyword_hits(keywords: Iterable[str], text: str) -> int:
    """Desk-story matching: a keyword counts when ALL its meaningful words
    appear (any order, word boundaries). 'dubai tel aviv flight' matches
    'a Flydubai flight from Dubai to Tel Aviv'; an exact-phrase rule missed it
    and let duplicate coverage outrank the Desk original (2026-10-01)."""
    low = (text or "").lower()
    hits = 0
    for kw in keywords:
        toks = _phrase_tokens(kw or "")
        if toks and all(re.search(r"\b" + re.escape(t) + r"\b", low) for t in toks):
            hits += 1
    return hits


def matches_story(keywords: list[str], text: str, min_hits: int = 2) -> bool:
    """The 2-hit rule shared with auto/wave stories (D-2hit, D10). A story
    with fewer than 2 keywords can never match: one generic word gluing
    unrelated news on is the failure this rule exists to prevent."""
    kws = [k for k in keywords if k]
    if len(kws) < min_hits:
        return False
    return story_keyword_hits(kws, text) >= min_hits


def dedup_candidates(topic: str, articles: list[dict], stories: list[dict], limit: int = 5) -> list[dict]:
    """Existing coverage of a topic, best first, BEFORE any research spend.

    articles: {article_id, title, description, category, published_at}
    stories:  {story_id, title, keywords, kind, article_ids}
    Returns [{type: "article"|"story", id, title, score, detail}].

    Score = share of the topic's significant terms found. A short topic
    ("Asiad") needs its one term; longer topics need at least two terms AND
    half of them, so a single shared word like "india" never counts as a
    duplicate.
    """
    terms = topic_terms(topic)
    if not terms:
        return []
    need = 1 if len(terms) == 1 else max(2, (len(terms) + 1) // 2)
    out = []

    for s in stories:
        hay = " ".join([s.get("title", "")] + list(s.get("keywords") or []))
        hits = keyword_hits(terms, hay)
        if hits >= need:
            out.append({"type": "story", "id": s.get("story_id"), "title": s.get("title", ""),
                        "score": round(hits / len(terms), 3),
                        "detail": f"{len(s.get('article_ids') or [])} updates · {s.get('kind', 'auto')}"})

    for a in articles:
        hay = f"{a.get('title', '')} {a.get('description', '')}"
        hits = keyword_hits(terms, hay)
        if hits >= need:
            out.append({"type": "article", "id": a.get("article_id"), "title": a.get("title", ""),
                        "score": round(hits / len(terms), 3),
                        "detail": f"{a.get('category', '')} · {a.get('source', '')}".strip(" ·")})

    # Stories first on ties: boosting a live thread beats duplicating it.
    out.sort(key=lambda m: (m["score"], m["type"] == "story"), reverse=True)
    return out[:limit]


# ── placement (D11b) ──────────────────────────────────────────────────────────

def _faded(amount: float, hours: float, published, now: datetime) -> float:
    dt = parse_dt(published)
    if dt is None:
        return 0.0
    age_h = (now - dt).total_seconds() / 3600.0
    if age_h < 0:
        age_h = 0.0
    if age_h >= hours:
        return 0.0
    return amount * (1.0 - age_h / hours)


def _effective_heat(heat: int, published, now: datetime) -> int:
    """For boosts, Breaking always scores as Big. The pin (slot 1, first 6h)
    is separate, and only ONE story can hold it; a second Breaking story in
    the same window still needs a Big-sized lift rather than none."""
    return HEAT_BIG if heat == HEAT_BREAKING else heat


def _heat_of(article: dict) -> tuple[int, object]:
    """(heat, when the heat started) for anything carrying heat: a desk
    article (from its publish time) or an API article the owner boosted
    (from the boost time, via heat_from). (0, None) for everything else."""
    heat = int(article.get("heat") or 0)
    if heat not in HEAT_LABELS or not (article.get("origin") == "desk" or article.get("boosted")):
        return 0, None
    return heat, article.get("heat_from") or article.get("published_at")


def heat_points(article: dict, now: datetime) -> float:
    """Personalised-feed bonus (0 for anything without heat)."""
    heat, since = _heat_of(article)
    heat = _effective_heat(heat, since, now)
    if heat not in HEAT_POINTS:
        return 0.0
    amount, hours = HEAT_POINTS[heat]
    return _faded(amount, hours, since, now)


def heat_slots(article: dict, now: datetime) -> float:
    """Guest-feed bonus, in rank slots."""
    heat, since = _heat_of(article)
    heat = _effective_heat(heat, since, now)
    if heat not in HEAT_SLOTS:
        return 0.0
    amount, hours = HEAT_SLOTS[heat]
    return _faded(amount, hours, since, now)


def is_pinned(heat: int, since, now: datetime) -> bool:
    if heat != HEAT_BREAKING:
        return False
    dt = parse_dt(since)
    return dt is not None and timedelta(0) <= now - dt < timedelta(hours=BREAKING_PIN_HOURS)


def article_is_pinned(article: dict, now: datetime) -> bool:
    heat, since = _heat_of(article)
    return is_pinned(heat, since, now)


# ── developing lifecycle ──────────────────────────────────────────────────────

def lifecycle_fields(heat: int, now: datetime, long_running: bool = False) -> dict:
    return {
        "heat": heat,
        "quiet_window_h": QUIET_WINDOW_H.get(heat, 72),
        "min_until": (now + timedelta(hours=MIN_RUN_H)).isoformat(),
        "hard_end": None if long_running else (now + timedelta(days=HARD_CAP_DAYS)).isoformat(),
        "long_running": bool(long_running),
        "last_updated": now.isoformat(),
    }


def lifecycle_decision(story: dict, now: datetime) -> tuple[str, Optional[str], Optional[str]]:
    """("stay"|"end", end_reason, closes_at_iso_if_quiet). closes_at is when
    the story will end if nothing new arrives, for the dashboard's
    "closes in ~Nh"."""
    min_until = parse_dt(story.get("min_until"))
    hard_end = parse_dt(story.get("hard_end")) if not story.get("long_running") else None
    last = parse_dt(story.get("last_updated")) or parse_dt(story.get("detected_at")) or now
    window = timedelta(hours=int(story.get("quiet_window_h") or 72) + int(story.get("extra_h") or 0))
    closes_at = last + window
    if min_until and closes_at < min_until:
        closes_at = min_until
    if hard_end and closes_at > hard_end:
        closes_at = hard_end

    if min_until and now < min_until:
        return "stay", None, closes_at.isoformat()
    if hard_end and now >= hard_end:
        return "end", "cap", None
    if now - last >= window:
        return "end", "quiet", None
    return "stay", None, closes_at.isoformat()


def extended_fields(story: dict, now: datetime) -> dict:
    """Extend: the story now closes EXTEND_H later if still quiet.

    Adds to a separate extra_h rather than moving last_updated forward:
    the app shows last_updated as "updated Xh ago", so shifting it would
    display an update from the future. If the hard cap would cut the
    extension short, the cap moves too (the owner asked for more time)."""
    last = parse_dt(story.get("last_updated")) or now
    base = int(story.get("quiet_window_h") or 72)
    extra = int(story.get("extra_h") or 0)
    # New close = the later of (current quiet close, now) + EXTEND_H, so an
    # already-overdue story still gets a full EXTEND_H from the moment you ask.
    hard_end = parse_dt(story.get("hard_end")) if not story.get("long_running") else None
    current_close = last + timedelta(hours=base + extra)
    if hard_end and hard_end < current_close:
        current_close = hard_end            # the cap is what would close it
    new_close = max(current_close, now) + timedelta(hours=EXTEND_H)
    hours_needed = -(-(new_close - last).total_seconds() // 3600)   # ceil
    fields = {"extra_h": max(extra, int(hours_needed) - base)}
    if hard_end and hard_end < new_close:
        fields["hard_end"] = new_close.isoformat()
    return fields


# ── drafts ────────────────────────────────────────────────────────────────────

def validate_submit(topic: str, category: str, news_type: str, heat) -> list[str]:
    errors = []
    t = (topic or "").strip()
    if not (TOPIC_MIN <= len(t) <= TOPIC_MAX):
        errors.append(f"Topic must be {TOPIC_MIN}-{TOPIC_MAX} characters.")
    if category not in CATEGORIES:
        errors.append("Pick a category.")
    if news_type not in NEWS_TYPES:
        errors.append("Pick Normal or Developing.")
    if heat not in HEAT_LABELS:
        errors.append("Pick a heat level.")
    return errors


def _valid_image_url(url: str) -> bool:
    if not url:
        return True
    if len(url) > IMAGE_URL_MAX or any(c.isspace() for c in url):
        return False
    p = urlparse(url)
    return p.scheme == "https" and bool(p.hostname) and "." in (p.hostname or "")


def validate_draft(d: dict) -> list[str]:
    """Everything that must hold before a draft can be published."""
    errors = []
    h = (d.get("headline") or "").strip()
    if not (HEADLINE_MIN <= len(h) <= HEADLINE_MAX):
        errors.append(f"Headline must be {HEADLINE_MIN}-{HEADLINE_MAX} characters.")
    s = (d.get("summary") or "").strip()
    if not (SUMMARY_MIN <= len(s) <= SUMMARY_MAX):
        errors.append(f"Summary must be {SUMMARY_MIN}-{SUMMARY_MAX} characters.")
    points = d.get("points") or []
    if len(points) > POINTS_MAX or any(len((p or "").strip()) > POINT_MAX for p in points):
        errors.append(f"Up to {POINTS_MAX} key points, each under {POINT_MAX} characters.")
    if d.get("category") not in CATEGORIES:
        errors.append("Pick a category.")
    if d.get("heat") not in HEAT_LABELS:
        errors.append("Pick a heat level.")
    if d.get("news_type") not in NEWS_TYPES:
        errors.append("Pick Normal or Developing.")
    if not _valid_image_url(d.get("image_url") or ""):
        errors.append("Image link must be a plain https:// URL.")
    citations = d.get("citations") or []
    domains = d.get("domain_count") or 0
    if not citations or domains < 1:
        errors.append("A story needs at least one real source.")
    elif domains == 1 and len((d.get("single_source_reason") or "").strip()) < REASON_MIN:
        # D9: one source may publish, but only with a stated reason.
        errors.append("Only one source was found. Say why it's safe to publish (at least 10 characters).")
    if d.get("news_type") == "developing" and len([k for k in (d.get("keywords") or []) if k]) < KEYWORDS_MIN_DEVELOPING:
        errors.append(f"A developing story needs at least {KEYWORDS_MIN_DEVELOPING} keywords to track follow-ups.")
    return errors


# ── attribution (D11g) ────────────────────────────────────────────────────────

_OUTLETS = {
    "thehindu.com": "The Hindu", "indianexpress.com": "Indian Express", "ndtv.com": "NDTV",
    "hindustantimes.com": "Hindustan Times", "indiatimes.com": "Times of India",
    "livemint.com": "Mint", "business-standard.com": "Business Standard",
    "financialexpress.com": "Financial Express", "thehindubusinessline.com": "BusinessLine",
    "scroll.in": "Scroll", "thewire.in": "The Wire", "theprint.in": "ThePrint",
    "deccanherald.com": "Deccan Herald", "telegraphindia.com": "The Telegraph",
    "firstpost.com": "Firstpost", "outlookindia.com": "Outlook", "reuters.com": "Reuters",
    "apnews.com": "AP", "bbc.com": "BBC", "bbc.co.uk": "BBC", "aljazeera.com": "Al Jazeera",
    "pib.gov.in": "PIB", "indiatoday.in": "India Today", "news18.com": "News18",
    "moneycontrol.com": "Moneycontrol", "economictimes.com": "Economic Times",
}


def outlet_name(url: str, registrable_domain) -> str:
    dom = registrable_domain(url)
    return _OUTLETS.get(dom, dom)


def attribution(citations: list[dict], registrable_domain, max_names: int = 2) -> str:
    """'Chintan Desk · via The Hindu, NDTV' — honest that the text is the
    Desk's synthesis, and names who reported it. Distinct outlets, citation
    order (first = strongest)."""
    names: list[str] = []
    for c in citations:
        n = outlet_name(c.get("url", ""), registrable_domain)
        if n and n not in names:
            names.append(n)
    if not names:
        return "Chintan Desk"
    return "Chintan Desk · via " + ", ".join(names[:max_names])

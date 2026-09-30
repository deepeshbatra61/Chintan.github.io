"""Brief generation with I/O: fetch candidates, ask the LLM, cache, pin.

brief.py stays pure (selection, prompt, parsing); this module owns the database
and the LLM call so both the brief page (GET /briefs/{type}) and push
preparation can build a brief for any reader, not just "whoever sent this
request".

    GET /briefs/{type} ──┐                     ┌─▶ pin for this reader+slot? ─▶ serve pin
                         ├─▶ read_brief() ─────┤
    push tap ?pin=<id> ──┘                     └─▶ fresh cache? ─▶ serve cache
                                                     └─▶ build_brief() ─▶ cache ─▶ serve
    push prep (T-60) ────▶ build_brief() ─▶ create_pin() (valid until the next slot)

A pin is the exact brief a push promised. It wins over the cache and over a fresh
build until `valid_until`, so opening Briefs from the menu shows the same stories
the push described (eng review 12A).
"""

import secrets
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Dict, List, Optional

import brief

BRIEF_TYPES = ("morning", "midday", "night")
CACHE_TTL_S = 3600
PIN_MAX_AGE = timedelta(hours=24)

# Sentence case, matching the app's own copy (BriefPage, side nav). These
# override the app's text, so Title Case here made the brief say "Good
# Afternoon" while the sidebar said "Good afternoon".
GREETINGS = {
    "morning": ("Good morning",  "while you were sleeping, we curated your morning brief"),
    "midday":  ("Good afternoon", "while you were working, we were curating your tailored afternoon brief"),
    "night":   ("Good evening",  "while you wound down, here's what shaped your world today"),
}

LLMComplete = Callable[[str], Awaitable[Optional[str]]]


def cache_key(brief_type: str, user_id: Optional[str]) -> str:
    # The "v2:" prefix is a schema version, not decoration. Brief documents
    # carry a per-story `take`; bumping the prefix makes every stale-shape
    # entry a miss instead of serving v1 documents after a deploy.
    return f"v2:{brief_type}:{user_id or 'anon'}"


def _as_dt(value) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


async def cached_brief(db, brief_type: str, user_id: Optional[str], now: datetime) -> Optional[dict]:
    doc = await db.brief_cache.find_one({"_id": cache_key(brief_type, user_id)})
    if not doc or not doc.get("brief"):
        return None
    gen = _as_dt(doc.get("generated_at"))
    if gen and gen.tzinfo is None:
        gen = gen.replace(tzinfo=now.tzinfo)
    if gen and (now - gen).total_seconds() < CACHE_TTL_S:
        return doc["brief"]
    return None


async def store_cache(db, brief_type: str, user_id: Optional[str], brief_doc: dict, now: datetime) -> None:
    await db.brief_cache.update_one(
        {"_id": cache_key(brief_type, user_id)},
        {"$set": {
            "brief": brief_doc,
            # Kept as a string because the freshness check parses it that way.
            # The TTL index needs a real BSON date, so both are written -- the
            # string stays authoritative for reads, the date only expires.
            "generated_at": now.isoformat(),
            "generated_at_dt": now,
        }},
        upsert=True,
    )


async def build_brief(db, user: Optional[dict], brief_type: str, llm: LLMComplete, now: datetime) -> dict:
    """Build a brief for `user` (None = signed-out reader). Never raises for LLM
    failure: brief.assemble() falls back to a deterministic take per story.
    Returns the brief document WITHOUT saved_for_you (that is attached at read
    time and must never be cached or pinned)."""
    if brief_type not in BRIEF_TYPES:
        raise ValueError(f"invalid brief type: {brief_type}")
    user_interests: List[str] = (user.get("interests") or []) if user else []
    raw_name: str = (user.get("name") or "") if user else ""
    user_name = raw_name.split()[0] if raw_name else "there"
    greeting, subtitle = GREETINGS[brief_type]

    # Interests can be broad categories or specific niches — match either.
    category_query: dict = (
        {"$or": [{"category": {"$in": user_interests}}, {"subcategory": {"$in": user_interests}}]}
        if user_interests else {}
    )

    # ── 1. Cascade: 24 h → 72 h → no time filter → drop interest filter ──────
    fresh_articles: list = []
    for hours in (24, 72):
        cutoff_str = (now - timedelta(hours=hours)).isoformat()
        fresh_articles = await db.articles.find(
            {"published_at": {"$gte": cutoff_str}, **category_query},
            {"_id": 0},
        ).sort("published_at", -1).to_list(300)
        if len(fresh_articles) >= 3:
            break

    if len(fresh_articles) < 3:
        fresh_articles = await db.articles.find(
            category_query if category_query else {},
            {"_id": 0},
        ).sort("published_at", -1).to_list(50)

    if len(fresh_articles) < 3 and user_interests:
        fresh_articles = await db.articles.find({}, {"_id": 0}).sort("published_at", -1).to_list(50)

    # ── 2. Group by category, no minimum threshold ───────────────────────────
    by_category: Dict[str, list] = {}
    for a in fresh_articles:
        cat = a.get("category")
        if cat:
            by_category.setdefault(cat, []).append(a)

    if user_interests:
        ordered = [c for c in user_interests if c in by_category]
        ordered += [c for c in sorted(by_category, key=lambda x: len(by_category[x]), reverse=True)
                    if c not in ordered]
    else:
        ordered = sorted(by_category, key=lambda c: len(by_category[c]), reverse=True)
    top_cats = ordered[:3]

    # ── 3. Hard fallback — only if DB is completely empty ────────────────────
    if not top_cats:
        any_articles = await db.articles.find({}, {"_id": 0}).sort("published_at", -1).limit(3).to_list(3)
        # Same shape as the main path, deliberately: BriefPage looks up
        # categories[idx] and every story needs a `take`.
        return {
            "greeting": greeting,
            "subtitle": subtitle,
            "summary": "No stories are available right now. Check back soon.",
            "categories": [a.get("category", "") for a in any_articles],
            "referenced_stories": [
                {"title": a.get("title", ""), "source": a.get("source", ""),
                 "article_id": a.get("article_id", ""), "take": brief.fallback_take(a)}
                for a in any_articles
            ],
            "read_time": "1 min read",
        }

    # ── 4. One ranked article per category ───────────────────────────────────
    # Exactly one, so the card's link and the card's text come from the same
    # object and cannot disagree.
    pairs = brief.select_stories(top_cats, by_category, user_interests, now)

    # ── 5. One line per story from the LLM; assemble() covers failure ───────
    llm_text = None
    try:
        llm_text = await llm(brief.build_prompt(brief_type, user_name, pairs))
    except Exception:
        llm_text = None
    assembled = brief.assemble(pairs, llm_text)

    return {
        "greeting":           greeting,
        "subtitle":           subtitle,
        "summary":            assembled["summary"],
        "categories":         assembled["categories"],
        "referenced_stories": assembled["referenced_stories"],
        "read_time":          assembled["read_time"],
    }


async def create_pin(db, user_id: str, brief_type: str, brief_doc: dict,
                     now: datetime, valid_until: datetime, slot_label: str = "") -> str:
    """Store the exact brief a push is about to promise. Returns its pin_id.
    `slot_label` is the reader-facing origin line, e.g. "07:30 Sunrise"."""
    pin_id = secrets.token_urlsafe(16)
    await db.push_briefs.insert_one({
        "pin_id": pin_id,
        "user_id": user_id,
        "brief_type": brief_type,
        "brief": brief_doc,
        "slot_label": slot_label[:40],
        "created_at": now,
        "valid_until": valid_until,
        "expires_at": now + PIN_MAX_AGE,   # TTL index
    })
    return pin_id


def _live(pin: Optional[dict], user_id: str, brief_type: str, now: datetime, until_key: str) -> bool:
    if not pin or pin.get("user_id") != user_id or pin.get("brief_type") != brief_type:
        return False
    until = _as_dt(pin.get(until_key))
    if until is None:
        return False
    if until.tzinfo is None:
        until = until.replace(tzinfo=now.tzinfo)
    return now < until


async def pinned_brief(db, user_id: Optional[str], brief_type: str, now: datetime,
                       pin_id: Optional[str] = None) -> Optional[dict]:
    """The pin document this reader should see, or None.
    With pin_id (a push tap): that pin, if it is theirs, this type, < 24h old.
    Without: their latest pin for this type that is still before the next slot."""
    if not user_id:
        return None
    if pin_id:
        pin = await db.push_briefs.find_one({"pin_id": str(pin_id)[:64]})
        if _live(pin, user_id, brief_type, now, "expires_at"):
            return pin
        # A stale or foreign pin id falls through to the reader's current pin.
    cursor = db.push_briefs.find({"user_id": user_id, "brief_type": brief_type}).sort("created_at", -1).limit(1)
    pins = await cursor.to_list(1)
    pin = pins[0] if pins else None
    return pin if _live(pin, user_id, brief_type, now, "valid_until") else None


async def read_brief(db, user: Optional[dict], brief_type: str, llm: LLMComplete, now: datetime,
                     pin_id: Optional[str] = None) -> dict:
    """What the brief page serves: pin → fresh cache → build (and cache).
    Returns the document without saved_for_you; the caller attaches it."""
    if brief_type not in BRIEF_TYPES:
        raise ValueError(f"invalid brief type: {brief_type}")
    user_id = user.get("user_id") if user else None
    pin = await pinned_brief(db, user_id, brief_type, now, pin_id)
    if pin:
        return {**pin["brief"], "pinned_from": pin.get("slot_label") or ""}
    cached = await cached_brief(db, brief_type, user_id, now)
    if cached:
        return cached
    doc = await build_brief(db, user, brief_type, llm, now)
    await store_cache(db, brief_type, user_id, doc, now)
    return doc

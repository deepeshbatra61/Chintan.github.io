"""Verified web research — locked by /plan-eng-review on 2026-08-09.

WHY THIS EXISTS
---------------
Chintan Calendar entries (Independence Day, festivals, sports fixtures, later
concerts/events) have no source article to summarise from -- unlike every other
"developing story" kind, which pulls its card text from a matched article. This
module answers "what should the card say" by asking Claude to search the live
web and cite sources, then enforcing that citation as a real check in code
rather than trusting a prompt instruction.

THE RULE THIS MODULE ENFORCES (non-negotiable, per D3/D5)
-----------------------------------------------------------
A topic is "verified" only when its citations span >= RESEARCH_MIN_INDEPENDENT_
DOMAINS distinct registrable domains. Two URLs on the same site never count as
two sources. If verification fails -- one source, zero sources, a timeout, an
API error, a rate limit -- there is NO fallback. The topic is simply not
returned, and the caller (server.py's calendar sync) must treat "unverified"
and "hidden" as the same thing. This was an explicit, deliberate call: the
user rejected a static-blurb fallback specifically because it re-opens the
"confidently wrong" failure this whole feature exists to prevent (see the
Gemini date error that started this conversation, and the profile "blind
spot" bug from the same session).

WHAT'S PURE vs WHAT NEEDS I/O
------------------------------
_registrable_domain, _independent_domain_count, and _extract_search_result are
pure -- they take data, not a live client, so they're fully unit-testable with
synthetic API-response-shaped dicts. research_topic is the orchestration shell
(cache, cost cap, timeout, the actual API call) and is what needs mocking in
integration-style tests. Same split as brief.py: push everything that matters
into the part that doesn't need a network.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ── Tunables (all D2-D8 decisions made concrete) ─────────────────────────────
RESEARCH_TOOL_VERSION = "web_search_20250305"   # basic search; dynamic filtering
                                                 # (20260209+) is for search-heavy
                                                 # multi-entity research, which a
                                                 # single-topic lookup doesn't need
RESEARCH_MAX_SEARCHES_PER_CALL = 3              # tool's own max_uses -- caps
                                                 # search count WITHIN one topic
RESEARCH_TIMEOUT_SECONDS = 25                   # D8: hard per-call timeout so a
                                                 # slow call fails fast, not hangs
RESEARCH_MIN_INDEPENDENT_DOMAINS = 2            # D3: the actual verification bar
RESEARCH_CACHE_TTL_HOURS = 20                   # D4: don't re-research same day

# BUMP THIS whenever extraction, cleaning, or the system prompt changes.
# Cached entries are keyed by version, so old rows are ignored rather than
# migrated. Without it, a fix ships but users keep seeing the cached bad
# text until the TTL lapses — which is exactly what happened when the
# model's "I notice there is a discrepancy..." narration went out on a card
# and was still being served from cache after the code fix landed.
#   v1: initial
#   v2: answer taken from post-search blocks only + narration stripped
#   v3: longer, more substantive copy + citation-fragment spacing fixed
RESEARCH_CACHE_VERSION = 3
# Length budget. The list card line-clamps to 4 lines regardless, so this
# really governs the DETAIL page, where a reader has deliberately tapped in
# and wants substance. Raised from 3/400 after the first live entry read as
# a single thin fact with nothing behind it.
RESEARCH_MAX_SENTENCES = 6
RESEARCH_MAX_CHARS = 900                        # backstop for very long sentences

# Block types the API emits for the search itself. Text blocks BEFORE the last
# one of these are the model narrating its own process, not the answer.
_TOOL_BLOCK_TYPES = ("web_search_tool_result", "server_tool_use")

# Sentence openers that mean the model is describing its own research rather
# than answering. Matched case-insensitively and ONLY at the start of a
# leading sentence: "I found the claim credible" mid-paragraph is content,
# "I found one reference citing..." opening the card is not.
_META_OPENERS = (
    "based on my search", "based on the search", "based on my web search",
    "based on these search", "based on those search", "based on the above",
    "let me search", "let me look", "let me verify", "let me check",
    "let me find", "let me confirm", "let me clarify",
    "i'll search", "i will search", "i'll look", "i will look",
    "i'll verify", "i will verify", "i'll check", "i will check",
    "i need to search", "i should search", "i need to verify",
    "i can now provide", "i can now write", "i now have enough",
    "i notice there is", "i notice that there", "i notice a", "i notice one",
    "here is a factual", "here's a factual", "here is one factual",
    "here's one factual", "here is the factual", "here's the factual",
    "here is the paragraph", "here's the paragraph",
    "my search results", "the search results", "searching for",
    "i have searched", "i've searched", "i searched",
)


def _split_sentences(text: str) -> list[str]:
    """Naive sentence split — good enough for trimming card copy. Abbreviations
    ('Aug. 11') can over-split; the cost is a slightly shorter card, not a
    wrong one, which is the right way for this to fail."""
    return [s for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if s]


def _clean_answer(text: str) -> str:
    """Turn the model's raw reply into card-ready copy.

    Two jobs, both learned from a live card that shipped "I notice there is a
    discrepancy in one source... Let me search for additional clarification":
      1. drop leading sentences that narrate the research process
      2. cap the length, because this renders in a fixed-size card

    Deliberately only strips from the FRONT. A meta-sounding clause in the
    middle of an otherwise good paragraph is far more likely to be real
    content than narration, and silently deleting the middle of a factual
    sentence is a worse failure than leaving one clumsy phrase in."""
    text = re.sub(r"\s+", " ", text or "").strip()
    # The API splits an answer into fragments at citation boundaries, and each
    # fragment already carries its own leading/trailing spaces. Concatenating
    # them is therefore correct, but a stray space can still land in front of
    # punctuation ("at the age of 18 , making him" reached a live card).
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    # ...and the mirror case: two fragments meeting with no space at a
    # sentence boundary ("...on August 11.He was 18").
    text = re.sub(r"([.!?])([A-Z])", r"\1 \2", text)
    if not text:
        return ""

    sentences = _split_sentences(text)
    while sentences and sentences[0].lower().lstrip("*_# ").startswith(_META_OPENERS):
        sentences.pop(0)

    out = " ".join(sentences[:RESEARCH_MAX_SENTENCES]).strip()
    if len(out) <= RESEARCH_MAX_CHARS:
        return out

    # Too long: trim back to the last COMPLETE sentence that fits, so a card
    # never ends mid-thought. If even the first sentence overruns, hard-cut it
    # on a word boundary rather than shipping a wall of text.
    kept, total = [], 0
    for s in _split_sentences(out):
        if total + len(s) + 1 > RESEARCH_MAX_CHARS:
            break
        kept.append(s)
        total += len(s) + 1
    if kept:
        return " ".join(kept).strip()
    return out[:RESEARCH_MAX_CHARS].rsplit(" ", 1)[0].rstrip(",;:") + "…"

# Domains where the registrable part is the last THREE labels, not two
# (bbc.co.uk, not co.uk). Not a full public-suffix-list -- deliberately a small,
# curated set covering the TLDs most likely to appear in Indian/UK/AU/NZ news
# sourcing, which is this app's actual audience. A domain not in this set falls
# back to the standard last-two-labels rule.
_THREE_LABEL_TLDS = frozenset({
    "co.uk", "co.in", "co.jp", "co.nz", "co.za", "co.id",
    "com.au", "com.br", "org.in", "gov.in", "ac.in", "net.in",
})


def _registrable_domain(url: str) -> str:
    """Best-effort registrable domain, so bbc.co.uk and news.bbc.co.uk count as
    ONE source, while two different *.github.io sites still count as two.

    Not a full public-suffix-list implementation -- see _THREE_LABEL_TLDS. Good
    enough for verification counting; not meant for anything security-sensitive.
    """
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return url.lower()  # malformed URL: treat the whole string as its own "domain"
    labels = host.split(".")
    if len(labels) < 2:
        return host
    last_two = ".".join(labels[-2:])
    if last_two in _THREE_LABEL_TLDS and len(labels) >= 3:
        return ".".join(labels[-3:])
    return last_two


def _independent_domain_count(citations: list[dict]) -> int:
    """How many DISTINCT registrable domains back these citations.

    citations: [{"url": "...", ...}, ...] -- the shape research_topic collects
    from every text block's `citations` array in the API response.
    """
    return len({_registrable_domain(c["url"]) for c in citations if c.get("url")})


def _extract_search_result(content_blocks: list) -> Optional[dict]:
    """Parse one Messages API response's content blocks into verified content,
    or None if verification doesn't clear the bar.

    Handles the two ways this can legitimately fail without raising:
      - a web_search_tool_result block carrying a
        web_search_tool_result_error (rate limit, max_uses_exceeded, etc.) --
        these come back as HTTP 200, so this is the only way to detect them
      - citations that don't reach RESEARCH_MIN_INDEPENDENT_DOMAINS

    `content_blocks` is `response.content` from the SDK -- a list of objects
    with a `.type` attribute (SDK objects in production, plain dicts with a
    "type" key are also accepted so tests don't need to construct SDK types).
    """
    def block_type(b):
        return getattr(b, "type", None) or (b.get("type") if isinstance(b, dict) else None)

    for block in content_blocks:
        if block_type(block) == "web_search_tool_result":
            inner = getattr(block, "content", None)
            if inner is None and isinstance(block, dict):
                inner = block.get("content")
            inner_type = block_type(inner) if not isinstance(inner, list) else None
            if inner_type == "web_search_tool_result_error":
                error_code = getattr(inner, "error_code", None) or (
                    inner.get("error_code") if isinstance(inner, dict) else "unknown"
                )
                logger.warning(f"web_search_tool_result_error: {error_code}")
                return None

    # The model narrates between searches — one text block before EACH tool
    # call ("Let me search for additional clarification...", "Based on my
    # search results, I can now provide...") and the real answer last. Only
    # the blocks after the LAST search result are the answer. Joining all of
    # them is exactly what put "I notice there is a discrepancy in one source"
    # onto a live card, so this slice is the fix, not a nicety.
    last_tool = -1
    for i, block in enumerate(content_blocks):
        if block_type(block) in _TOOL_BLOCK_TYPES:
            last_tool = i
    answer_blocks = content_blocks[last_tool + 1:]

    text_parts: list[str] = []
    citations: list[dict] = []
    for block in answer_blocks:
        if block_type(block) != "text":
            continue
        text = getattr(block, "text", None) or (block.get("text") if isinstance(block, dict) else "")
        if text:
            text_parts.append(text)
        block_citations = getattr(block, "citations", None) or (
            block.get("citations") if isinstance(block, dict) else None
        )
        for c in (block_citations or []):
            url = getattr(c, "url", None) or (c.get("url") if isinstance(c, dict) else None)
            title = getattr(c, "title", None) or (c.get("title") if isinstance(c, dict) else None)
            if url:
                citations.append({"url": url, "title": title or ""})

    # Citations are counted from the ANSWER blocks only, deliberately: the
    # claim this module makes is "the text being shown is backed by 2+
    # independent domains." Counting sources the model merely looked at
    # earlier, while displaying different text, would make that claim a lie.
    # It's a stricter bar than pooling everything, and that's the point.
    # Concatenated, NOT space-joined: these are contiguous fragments of one
    # continuous answer, split where citations attach, and they carry their
    # own spacing. _clean_answer repairs either kind of seam defensively.
    content = _clean_answer("".join(text_parts))
    if not content or _independent_domain_count(citations) < RESEARCH_MIN_INDEPENDENT_DOMAINS:
        return None

    return {"content": content, "citations": citations}


def _cache_key(topic: str, scope: str) -> str:
    return f"v{RESEARCH_CACHE_VERSION}:{topic}:{scope}"


def _is_fresh(cached: dict) -> bool:
    researched_at = cached.get("researched_at")
    if not researched_at:
        return False
    try:
        dt = datetime.fromisoformat(researched_at)
    except (ValueError, TypeError):
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt) < timedelta(hours=RESEARCH_CACHE_TTL_HOURS)


async def _under_daily_cap(db, daily_cap: int) -> bool:
    """True if another research call is allowed today. Counts calls MADE, not
    calls that succeeded -- a call that fails verification still cost money."""
    if daily_cap <= 0:
        return False
    today = datetime.now(timezone.utc).date().isoformat()
    doc = await db.research_agent_stats.find_one({"_id": today})
    return (doc or {}).get("calls", 0) < daily_cap


async def _record_call(db) -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    await db.research_agent_stats.update_one(
        {"_id": today}, {"$inc": {"calls": 1}}, upsert=True
    )


async def research_topic(
    anthropic_client,
    db,
    model: str,
    topic: str,
    context: str,
    scope: str,
    daily_cap: int,
) -> Optional[dict]:
    """Research one topic; return verified {content, citations} or None.

    `scope` distinguishes cache entries for the same topic across different
    occurrences (e.g. "2026-08-15" for this year's Independence Day) so a
    yearly-recurring entry doesn't serve last year's cached content.

    D5 in full: None means "hidden" to every caller. There is no fallback
    value this function can return that means "show something anyway" --
    that was the point of the decision.
    """
    key = _cache_key(topic, scope)
    cached = await db.research_cache.find_one({"_id": key})
    if cached and _is_fresh(cached):
        return {"content": cached["content"], "citations": cached["citations"]} if cached.get("verified") else None

    if not await _under_daily_cap(db, daily_cap):
        logger.info(f"research_topic: daily cap reached, skipping '{topic}'")
        return None

    result: Optional[dict] = None
    try:
        response = await asyncio.wait_for(
            anthropic_client.messages.create(
                model=model,
                # Covers the model's between-search narration (which is
                # discarded but still counts) plus a 4-6 sentence answer.
                max_tokens=1200,
                system=(
                    "You write copy that goes DIRECTLY onto a card in a live news app. "
                    "Search the web, then reply with ONLY the finished paragraph: 4-6 "
                    "sentences of plain factual prose.\n\n"
                    "Make it genuinely informative — a reader who taps in wants to come "
                    "away knowing something. Do not restate the headline, and do not pad "
                    "with generalities like 'a significant occasion' or 'remembered by "
                    "many'. Every sentence must carry NEW information: what actually "
                    "happened, the specifics (names, places, ages, numbers, outcomes), "
                    "why it mattered at the time, and what it connects to today. Prefer "
                    "one concrete detail over three vague ones.\n\n"
                    "Never narrate your own process. Do not write 'based on my search', "
                    "'let me search', 'I notice', 'I can now provide', or any sentence "
                    "about searching, sources, or yourself. No preamble, no sign-off, no "
                    "headings, no bullet points, no quotes around the paragraph. The "
                    "reader must never be able to tell a search happened.\n\n"
                    "State only what your results support. If the weight of sources "
                    "materially conflicts on a central fact, state that conflict as a "
                    "fact ('accounts differ on whether...'). Ignore lone outliers that "
                    "the bulk of sources contradict — do not mention them."
                ),
                messages=[{"role": "user", "content": context}],
                tools=[{
                    "type": RESEARCH_TOOL_VERSION,
                    "name": "web_search",
                    "max_uses": RESEARCH_MAX_SEARCHES_PER_CALL,
                }],
            ),
            timeout=RESEARCH_TIMEOUT_SECONDS,
        )
        result = _extract_search_result(response.content)
    except asyncio.TimeoutError:
        logger.warning(f"research_topic: timed out researching '{topic}' (>{RESEARCH_TIMEOUT_SECONDS}s)")
    except Exception as e:
        # Deliberately broad: an API error, a malformed response, anything --
        # treated identically to "verification failed" (D7). One bad topic
        # must never take down the sync cycle processing every other entry.
        logger.error(f"research_topic: error researching '{topic}': {e}")

    await _record_call(db)  # a call was attempted regardless of outcome

    await db.research_cache.update_one(
        {"_id": key},
        {"$set": {
            "topic": topic,
            "scope": scope,
            "verified": result is not None,
            "content": result["content"] if result else None,
            "citations": result["citations"] if result else [],
            "researched_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    return result

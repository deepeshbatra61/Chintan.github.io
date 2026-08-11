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

    text_parts: list[str] = []
    citations: list[dict] = []
    for block in content_blocks:
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

    content = "".join(text_parts).strip()
    if not content or _independent_domain_count(citations) < RESEARCH_MIN_INDEPENDENT_DOMAINS:
        return None

    return {"content": content, "citations": citations}


def _cache_key(topic: str, scope: str) -> str:
    return f"{topic}:{scope}"


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
                max_tokens=500,
                system=(
                    "You are a careful research assistant. Search the web and write "
                    "ONE short, factual paragraph (2-3 sentences) answering the "
                    "user's question. State only what your search results support. "
                    "If your sources disagree on a specific detail (a date, a score, "
                    "a name), say so rather than picking one confidently."
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

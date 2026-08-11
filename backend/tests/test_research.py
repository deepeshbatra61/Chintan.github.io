"""Tests for backend/research.py.

The invariant this whole module exists to defend: a topic is only ever
returned as "verified" when its citations reach 2+ independent registrable
domains. Everything else -- one source, zero sources, a tool error, a
timeout -- must produce None, never a guessed-at fallback. Most of these
tests are aimed straight at that boundary because it's the one place a
regression would be invisible until a wrong, confident calendar card shipped.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import research


# ─────────────────────── _registrable_domain ───────────────────────

def test_same_domain_different_paths_are_one_domain():
    a = research._registrable_domain("https://www.bbc.co.uk/news/world-1")
    b = research._registrable_domain("https://news.bbc.co.uk/live-updates")
    assert a == b


def test_different_domains_are_different():
    a = research._registrable_domain("https://olympics.com/en/x")
    b = research._registrable_domain("https://telanganatoday.com/y")
    assert a != b


def test_three_label_tld_uses_last_three_labels():
    assert research._registrable_domain("https://blog.example.co.in") == "example.co.in"


def test_two_label_tld_uses_last_two_labels():
    assert research._registrable_domain("https://sub.example.com") == "example.com"


def test_malformed_url_does_not_raise():
    # no scheme -> urlparse won't find a hostname; must degrade, not crash
    assert research._registrable_domain("not a url") == "not a url"


# ─────────────────────── _independent_domain_count ───────────────────────

def test_two_urls_same_domain_count_as_one():
    citations = [
        {"url": "https://www.bbc.co.uk/a"},
        {"url": "https://news.bbc.co.uk/b"},
    ]
    assert research._independent_domain_count(citations) == 1


def test_two_urls_different_domains_count_as_two():
    citations = [
        {"url": "https://olympics.com/a"},
        {"url": "https://telanganatoday.com/b"},
    ]
    assert research._independent_domain_count(citations) == 2


def test_citations_missing_url_are_ignored():
    citations = [{"title": "no url here"}, {"url": "https://example.com/x"}]
    assert research._independent_domain_count(citations) == 1


def test_empty_citations_is_zero():
    assert research._independent_domain_count([]) == 0


# ─────────────────────── _extract_search_result ───────────────────────

def _text_block(text, citations=None):
    return {"type": "text", "text": text, "citations": citations or []}


def test_two_independent_domains_verifies():
    blocks = [
        _text_block(
            "Independence Day falls on Aug 15.",
            [
                {"url": "https://olympics.com/a", "title": "Olympics"},
                {"url": "https://telanganatoday.com/b", "title": "TT"},
            ],
        )
    ]
    result = research._extract_search_result(blocks)
    assert result is not None
    assert result["content"] == "Independence Day falls on Aug 15."
    assert len(result["citations"]) == 2


def test_one_domain_across_two_blocks_does_not_verify():
    blocks = [
        _text_block("Part one.", [{"url": "https://olympics.com/a"}]),
        _text_block("Part two.", [{"url": "https://olympics.com/b"}]),
    ]
    assert research._extract_search_result(blocks) is None


def test_citations_are_pooled_across_multiple_text_blocks():
    """A single verified answer often spans more than one text block --
    the domain count must be pooled, not evaluated per-block."""
    blocks = [
        _text_block("Part one.", [{"url": "https://olympics.com/a"}]),
        _text_block("Part two.", [{"url": "https://telanganatoday.com/b"}]),
    ]
    result = research._extract_search_result(blocks)
    assert result is not None
    assert result["content"] == "Part one.Part two."


def test_no_citations_does_not_verify():
    blocks = [_text_block("Confident-sounding but unsourced claim.")]
    assert research._extract_search_result(blocks) is None


def test_no_text_blocks_at_all_does_not_verify():
    assert research._extract_search_result([]) is None


def test_search_tool_error_short_circuits_to_none():
    blocks = [
        {
            "type": "web_search_tool_result",
            "content": {"type": "web_search_tool_result_error", "error_code": "too_many_requests"},
        },
        _text_block(
            "Text that arrived anyway.",
            [{"url": "https://a.com"}, {"url": "https://b.com"}],
        ),
    ]
    assert research._extract_search_result(blocks) is None


def test_search_tool_result_without_error_is_not_treated_as_failure():
    blocks = [
        {"type": "web_search_tool_result", "content": [{"type": "web_search_result", "url": "https://a.com"}]},
        _text_block(
            "Verified content.",
            [{"url": "https://a.com"}, {"url": "https://b.com"}],
        ),
    ]
    result = research._extract_search_result(blocks)
    assert result is not None


def test_accepts_sdk_style_objects_not_just_dicts():
    """Production response.content holds SDK objects with attributes, not
    dict keys -- the parser must handle both without special-casing callers."""
    citation = SimpleNamespace(url="https://a.com", title="A")
    citation2 = SimpleNamespace(url="https://b.com", title="B")
    block = SimpleNamespace(type="text", text="Verified via SDK objects.", citations=[citation, citation2])
    result = research._extract_search_result([block])
    assert result is not None
    assert result["content"] == "Verified via SDK objects."


# ─────────────────────── _is_fresh ───────────────────────

def test_fresh_cache_within_ttl():
    now = datetime.now(timezone.utc)
    cached = {"researched_at": (now - timedelta(hours=1)).isoformat()}
    assert research._is_fresh(cached) is True


def test_stale_cache_past_ttl():
    now = datetime.now(timezone.utc)
    cached = {"researched_at": (now - timedelta(hours=25)).isoformat()}
    assert research._is_fresh(cached) is False


def test_missing_timestamp_is_not_fresh():
    assert research._is_fresh({}) is False


# ─────────────────────── research_topic (orchestration shell) ───────────────────────

class FakeCollection:
    def __init__(self):
        self.docs = {}

    async def find_one(self, query):
        return self.docs.get(query.get("_id"))

    async def update_one(self, query, update, upsert=False):
        doc_id = query["_id"]
        doc = self.docs.get(doc_id, {"_id": doc_id})
        doc.update(update.get("$set", {}))
        if "$inc" in update:
            for k, v in update["$inc"].items():
                doc[k] = doc.get(k, 0) + v
        self.docs[doc_id] = doc


class FakeDB:
    def __init__(self):
        self.research_cache = FakeCollection()
        self.research_agent_stats = FakeCollection()


def _client_returning(content_blocks):
    client = SimpleNamespace()
    client.messages = SimpleNamespace()
    response = SimpleNamespace(content=content_blocks)
    client.messages.create = AsyncMock(return_value=response)
    return client


@pytest.mark.asyncio
async def test_verified_result_is_cached_and_returned():
    db = FakeDB()
    blocks = [
        _text_block(
            "Verified fact.",
            [{"url": "https://a.com"}, {"url": "https://b.com"}],
        )
    ]
    client = _client_returning(blocks)

    result = await research.research_topic(
        client, db, "claude-x", "Independence Day", "context", "2026-08-15", daily_cap=10
    )

    assert result["content"] == "Verified fact."
    cached = db.research_cache.docs["Independence Day:2026-08-15"]
    assert cached["verified"] is True


@pytest.mark.asyncio
async def test_unverified_result_returns_none_and_caches_as_unverified():
    db = FakeDB()
    blocks = [_text_block("Only one source.", [{"url": "https://a.com"}])]
    client = _client_returning(blocks)

    result = await research.research_topic(
        client, db, "claude-x", "Some Topic", "context", "scope", daily_cap=10
    )

    assert result is None
    cached = db.research_cache.docs["Some Topic:scope"]
    assert cached["verified"] is False


@pytest.mark.asyncio
async def test_fresh_verified_cache_hit_skips_the_api_call():
    db = FakeDB()
    now = datetime.now(timezone.utc).isoformat()
    db.research_cache.docs["Topic:scope"] = {
        "_id": "Topic:scope",
        "verified": True,
        "content": "Cached content.",
        "citations": [{"url": "https://a.com"}],
        "researched_at": now,
    }
    client = _client_returning([])  # would fail loudly if called

    result = await research.research_topic(
        client, db, "claude-x", "Topic", "context", "scope", daily_cap=10
    )

    assert result == {"content": "Cached content.", "citations": [{"url": "https://a.com"}]}
    client.messages.create.assert_not_called()


@pytest.mark.asyncio
async def test_fresh_unverified_cache_hit_returns_none_without_recalling():
    db = FakeDB()
    now = datetime.now(timezone.utc).isoformat()
    db.research_cache.docs["Topic:scope"] = {
        "_id": "Topic:scope",
        "verified": False,
        "content": None,
        "citations": [],
        "researched_at": now,
    }
    client = _client_returning([])

    result = await research.research_topic(
        client, db, "claude-x", "Topic", "context", "scope", daily_cap=10
    )

    assert result is None
    client.messages.create.assert_not_called()


@pytest.mark.asyncio
async def test_daily_cap_reached_skips_the_call_entirely():
    db = FakeDB()
    today = datetime.now(timezone.utc).date().isoformat()
    db.research_agent_stats.docs[today] = {"_id": today, "calls": 5}
    client = _client_returning([])

    result = await research.research_topic(
        client, db, "claude-x", "Topic", "context", "scope", daily_cap=5
    )

    assert result is None
    client.messages.create.assert_not_called()
    # no cache entry written -- the call was never attempted
    assert "Topic:scope" not in db.research_cache.docs


@pytest.mark.asyncio
async def test_daily_cap_zero_blocks_immediately():
    db = FakeDB()
    client = _client_returning([])

    result = await research.research_topic(
        client, db, "claude-x", "Topic", "context", "scope", daily_cap=0
    )

    assert result is None
    client.messages.create.assert_not_called()


@pytest.mark.asyncio
async def test_api_error_is_swallowed_and_treated_as_unverified():
    db = FakeDB()
    client = SimpleNamespace()
    client.messages = SimpleNamespace()
    client.messages.create = AsyncMock(side_effect=RuntimeError("API exploded"))

    result = await research.research_topic(
        client, db, "claude-x", "Topic", "context", "scope", daily_cap=10
    )

    assert result is None
    cached = db.research_cache.docs["Topic:scope"]
    assert cached["verified"] is False
    # a call was still counted -- it cost money even though it failed
    today = datetime.now(timezone.utc).date().isoformat()
    assert db.research_agent_stats.docs[today]["calls"] == 1


@pytest.mark.asyncio
async def test_timeout_is_swallowed_and_treated_as_unverified(monkeypatch):
    db = FakeDB()

    async def hang(*args, **kwargs):
        import asyncio
        await asyncio.sleep(10)

    client = SimpleNamespace()
    client.messages = SimpleNamespace()
    client.messages.create = hang

    monkeypatch.setattr(research, "RESEARCH_TIMEOUT_SECONDS", 0.05)

    result = await research.research_topic(
        client, db, "claude-x", "Topic", "context", "scope", daily_cap=10
    )

    assert result is None
    cached = db.research_cache.docs["Topic:scope"]
    assert cached["verified"] is False


@pytest.mark.asyncio
async def test_a_failed_call_still_counts_against_the_daily_cap():
    db = FakeDB()
    client = SimpleNamespace()
    client.messages = SimpleNamespace()
    client.messages.create = AsyncMock(side_effect=RuntimeError("boom"))

    await research.research_topic(client, db, "claude-x", "Topic", "context", "scope", daily_cap=10)

    today = datetime.now(timezone.utc).date().isoformat()
    assert db.research_agent_stats.docs[today]["calls"] == 1

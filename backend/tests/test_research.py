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
    # Joined with a space, not glued -- the "date.Based on my search" that
    # reached a live card came from a bare "".join().
    assert result["content"] == "Part one. Part two."


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


# ────────────── narration leak (regression: shipped to a live card) ──────────

def _tool_result_block(url="https://a.com"):
    return {"type": "web_search_tool_result", "content": [{"type": "web_search_result", "url": url}]}


def test_narration_before_the_last_search_is_not_part_of_the_answer():
    """THE regression test. This exact shape reached a real user's screen:
    the model's between-search commentary was concatenated onto the front of
    the Khudiram Bose card because every text block was being joined."""
    blocks = [
        _text_block("I'll search for information about Khudiram Bose."),
        _tool_result_block(),
        _text_block(
            "I notice there is a discrepancy in one source about the execution date. "
            "Let me search for additional clarification about the exact date."
        ),
        _tool_result_block(),
        _text_block(
            "Khudiram Bose was executed by the British government on August 11, 1908.",
            [{"url": "https://britannica.com/x"}, {"url": "https://thehindu.com/y"}],
        ),
    ]
    result = research._extract_search_result(blocks)
    assert result is not None
    assert result["content"] == (
        "Khudiram Bose was executed by the British government on August 11, 1908."
    )
    assert "Let me search" not in result["content"]
    assert "I notice" not in result["content"]


def test_citations_come_only_from_the_answer_blocks():
    """Sources the model merely looked at earlier must not prop up a verified
    claim about text it did not back -- otherwise 'backed by 2 domains' lies."""
    blocks = [
        _text_block("Looking into this.", [{"url": "https://early1.com/a"}]),
        _tool_result_block(),
        _text_block("More context.", [{"url": "https://early2.com/b"}]),
        _tool_result_block(),
        _text_block("The final answer.", [{"url": "https://only-one.com/c"}]),
    ]
    # Only one domain backs the ANSWER, even though three were seen overall.
    assert research._extract_search_result(blocks) is None


def test_meta_preamble_is_stripped_from_the_answer_block_itself():
    """Narration can also open the final block, not just earlier ones."""
    blocks = [
        _tool_result_block(),
        _text_block(
            "Based on my search results, I can now provide a factual paragraph. "
            "Vikram Sarabhai founded the Indian space programme.",
            [{"url": "https://isro.gov.in/a"}, {"url": "https://thehindu.com/b"}],
        ),
    ]
    result = research._extract_search_result(blocks)
    assert result is not None
    assert result["content"] == "Vikram Sarabhai founded the Indian space programme."


def test_answer_that_is_only_narration_does_not_verify():
    blocks = [
        _tool_result_block(),
        _text_block(
            "Let me search for more detail. I can now provide a factual paragraph.",
            [{"url": "https://a.com"}, {"url": "https://b.com"}],
        ),
    ]
    assert research._extract_search_result(blocks) is None


# ─────────────────────── _clean_answer ───────────────────────

def test_clean_answer_caps_sentence_count():
    text = "One. Two. Three. Four. Five. Six. Seven. Eight."
    out = research._clean_answer(text)
    assert out == "One. Two. Three. Four. Five. Six."
    assert len(research._split_sentences(out)) == research.RESEARCH_MAX_SENTENCES


def test_clean_answer_removes_space_before_punctuation():
    """Citation fragments carry their own spacing, so a naive space-join put
    'at the age of 18 , making him' and 'to be executed .' on a live card."""
    text = "He was hanged in 1908 , at the age of 18 , and was executed ."
    assert research._clean_answer(text) == "He was hanged in 1908, at the age of 18, and was executed."


def test_clean_answer_inserts_missing_space_at_a_sentence_seam():
    """The mirror case: fragments meeting with no space between them."""
    assert research._clean_answer("Hanged on August 11.He was 18.") == "Hanged on August 11. He was 18."


def test_answer_fragments_are_concatenated_not_space_joined():
    """End to end through _extract_search_result, since the join lives there."""
    blocks = [
        _tool_result_block(),
        _text_block("Khudiram Bose was hanged on August 11, 1908, at the age of 18",
                    [{"url": "https://byjus.com/a"}]),
        _text_block(", making him one of the youngest revolutionaries executed",
                    [{"url": "https://en.wikipedia.org/b"}]),
        _text_block("."),
    ]
    result = research._extract_search_result(blocks)
    assert result is not None
    assert result["content"] == (
        "Khudiram Bose was hanged on August 11, 1908, at the age of 18, making him "
        "one of the youngest revolutionaries executed."
    )


def test_clean_answer_only_strips_leading_narration():
    """A meta-sounding clause mid-paragraph is far likelier to be real content
    than narration, so it stays -- deleting the middle of a factual sentence
    would be the worse failure."""
    text = "Bose was executed in 1908. I found the record in colonial archives."
    assert research._clean_answer(text) == text


def test_clean_answer_collapses_whitespace():
    assert research._clean_answer("  A   sentence.\n\nAnother.  ") == "A sentence. Another."


def test_clean_answer_trims_to_a_whole_sentence_when_too_long():
    # Sized off the constant, not a literal, so raising the cap doesn't
    # silently turn this into a test of nothing.
    long_first = "A" * (research.RESEARCH_MAX_CHARS - 20) + "."
    text = f"{long_first} This second sentence pushes it over the character cap."
    out = research._clean_answer(text)
    assert out == long_first
    assert len(out) <= research.RESEARCH_MAX_CHARS


def test_clean_answer_hard_cuts_a_single_runaway_sentence():
    text = "word " * (research.RESEARCH_MAX_CHARS // 2)  # no sentence boundary at all
    out = research._clean_answer(text)
    assert len(out) <= research.RESEARCH_MAX_CHARS + 1  # +1 for the ellipsis
    assert out.endswith("…")


def test_clean_answer_on_empty_input():
    assert research._clean_answer("") == ""
    assert research._clean_answer(None) == ""


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
    cached = db.research_cache.docs[research._cache_key("Independence Day", "2026-08-15")]
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
    cached = db.research_cache.docs[research._cache_key("Some Topic", "scope")]
    assert cached["verified"] is False


@pytest.mark.asyncio
async def test_fresh_verified_cache_hit_skips_the_api_call():
    db = FakeDB()
    now = datetime.now(timezone.utc).isoformat()
    db.research_cache.docs[research._cache_key("Topic", "scope")] = {
        "_id": research._cache_key("Topic", "scope"),
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
    db.research_cache.docs[research._cache_key("Topic", "scope")] = {
        "_id": research._cache_key("Topic", "scope"),
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
    assert research._cache_key("Topic", "scope") not in db.research_cache.docs


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
    cached = db.research_cache.docs[research._cache_key("Topic", "scope")]
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
    cached = db.research_cache.docs[research._cache_key("Topic", "scope")]
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

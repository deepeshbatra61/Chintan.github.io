"""Desk research contract (research.research_desk and its pure parts).

What matters here, per /plan-eng-review 2026-09-28:
  - the labelled reply parses robustly (the API splits text at citation
    boundaries, models bold labels, bullets vary)
  - domain_count is reported, not collapsed to pass/fail, so 1 source can
    reach the single-source override and 0 sources never can
  - failures are never cached (a breaking story must be retryable at once)
  - the Desk has its own daily cap, separate from the calendar's
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import research


def _text(text, urls=()):
    return {"type": "text", "text": text,
            "citations": [{"url": u, "title": f"t{i}"} for i, u in enumerate(urls)]}


GOOD = (
    "HEADLINE: Supreme Court strikes down electoral bond scheme\n"
    "SUMMARY: The Supreme Court on Thursday struck down the electoral bond scheme. "
    "It ordered SBI to disclose donor data.\n"
    "POINTS:\n"
    "- A five-judge bench ruled unanimously.\n"
    "* SBI must share details with the EC within three weeks.\n"
    "• The EC will publish the data online.\n"
    "KEYWORDS: electoral bonds; supreme court; sbi; election commission"
)


# ─────────────────────── _parse_desk_answer ───────────────────────

def test_parses_all_sections():
    out = research._parse_desk_answer(GOOD)
    assert out["headline"] == "Supreme Court strikes down electoral bond scheme"
    assert out["summary"].startswith("The Supreme Court on Thursday")
    assert len(out["points"]) == 3
    assert out["points"][1] == "SBI must share details with the EC within three weeks."
    assert out["keywords"] == ["electoral bonds", "supreme court", "sbi", "election commission"]


def test_bold_labels_and_split_fragments_still_parse():
    raw = "**HEADLINE:** Floods hit Assam\n**SUMMARY:** Rivers ro" + "se overnight.\nKEYWORDS: assam; brahmaputra"
    out = research._parse_desk_answer(raw)
    assert out["headline"] == "Floods hit Assam"
    assert out["summary"] == "Rivers rose overnight."
    assert out["keywords"] == ["assam", "brahmaputra"]


def test_missing_headline_or_summary_is_unusable():
    assert research._parse_desk_answer("SUMMARY: only a summary") is None
    assert research._parse_desk_answer("HEADLINE: only a headline") is None
    assert research._parse_desk_answer("") is None


def test_keywords_are_deduped_lowercased_and_capped():
    raw = "HEADLINE: h\nSUMMARY: s\nKEYWORDS: A; a; B; C; D; E; F"
    assert research._parse_desk_answer(raw)["keywords"] == ["a", "b", "c", "d", "e"]


def test_points_are_capped_at_five():
    raw = "HEADLINE: h\nSUMMARY: s\nPOINTS:\n" + "\n".join(f"- p{i}" for i in range(9))
    assert len(research._parse_desk_answer(raw)["points"]) == 5


def test_overlong_headline_is_cut_on_a_word():
    raw = "HEADLINE: " + "word " * 60 + "\nSUMMARY: s"
    h = research._parse_desk_answer(raw)["headline"]
    assert len(h) <= research.DESK_HEADLINE_MAX + 1 and h.endswith("…")


# ─────────────────────── _desk_result_from_blocks ───────────────────────

def test_two_domains_is_ok_with_count():
    blocks = [_text(GOOD, ["https://www.thehindu.com/a", "https://indianexpress.com/b"])]
    out = research._desk_result_from_blocks(blocks)
    assert out["ok"] and out["domain_count"] == 2
    assert out["citations"][0]["url"] == "https://www.thehindu.com/a"


def test_one_domain_is_ok_but_reports_single_source():
    blocks = [_text(GOOD, ["https://www.thehindu.com/a", "https://thehindu.com/b"])]
    out = research._desk_result_from_blocks(blocks)
    assert out["ok"] and out["domain_count"] == 1


def test_zero_sources_fails():
    out = research._desk_result_from_blocks([_text(GOOD)])
    assert out == {"ok": False, "reason": "no_sources"}


def test_tool_error_fails():
    blocks = [{"type": "web_search_tool_result",
               "content": {"type": "web_search_tool_result_error", "error_code": "max_uses_exceeded"}}]
    assert research._desk_result_from_blocks(blocks)["reason"] == "tool_error"


def test_narration_before_last_search_is_ignored():
    blocks = [
        _text("HEADLINE: wrong\nSUMMARY: narration", ["https://a.com/x", "https://b.com/y"]),
        {"type": "server_tool_use"},
        {"type": "web_search_tool_result", "content": []},
        _text(GOOD, ["https://c.com/1", "https://d.com/2"]),
    ]
    out = research._desk_result_from_blocks(blocks)
    assert out["headline"].startswith("Supreme Court")
    assert {c["url"] for c in out["citations"]} == {"https://c.com/1", "https://d.com/2"}


def test_duplicate_citation_urls_collapse():
    blocks = [_text(GOOD, ["https://a.com/x", "https://a.com/x", "https://b.com/y"])]
    assert len(research._desk_result_from_blocks(blocks)["citations"]) == 2


# ─────────────────────── research_desk (orchestration) ───────────────────────

class FakeCollection:
    def __init__(self):
        self.docs = {}

    async def find_one(self, query):
        return self.docs.get(query.get("_id"))

    async def update_one(self, query, update, upsert=False):
        doc = self.docs.setdefault(query["_id"], {"_id": query["_id"]})
        for k, v in update.get("$inc", {}).items():
            doc[k] = doc.get(k, 0) + v


class FakeDB:
    def __init__(self):
        self.desk_research_stats = FakeCollection()
        self.research_agent_stats = FakeCollection()
        self.research_cache = FakeCollection()


def _client(blocks=None, exc=None):
    c = SimpleNamespace(messages=SimpleNamespace())
    c.messages.create = AsyncMock(side_effect=exc) if exc else AsyncMock(
        return_value=SimpleNamespace(content=blocks))
    return c


async def test_success_counts_against_desk_cap_only():
    db = FakeDB()
    client = _client([_text(GOOD, ["https://a.com/x", "https://b.com/y"])])
    out = await research.research_desk(client, db, "m", "bonds", daily_cap=5)
    assert out["ok"]
    assert list(db.desk_research_stats.docs.values())[0]["calls"] == 1
    assert db.research_agent_stats.docs == {}          # calendar budget untouched
    assert db.research_cache.docs == {}                # nothing cached


async def test_cap_reached_makes_no_call():
    db = FakeDB()
    client = _client([_text(GOOD, ["https://a.com/x"])])
    out = await research.research_desk(client, db, "m", "t", daily_cap=0)
    assert out == {"ok": False, "reason": "cap"}
    client.messages.create.assert_not_called()


async def test_failure_is_not_cached_so_retry_calls_again():
    db = FakeDB()
    client = _client(exc=RuntimeError("boom"))
    assert (await research.research_desk(client, db, "m", "t", daily_cap=5))["reason"] == "error"
    assert (await research.research_desk(client, db, "m", "t", daily_cap=5))["reason"] == "error"
    assert client.messages.create.call_count == 2


async def test_timeout_is_reported(monkeypatch):
    monkeypatch.setattr(research, "DESK_TIMEOUT_SECONDS", 0.01)

    async def slow(**_):
        await asyncio.sleep(1)

    client = SimpleNamespace(messages=SimpleNamespace(create=slow))
    out = await research.research_desk(client, FakeDB(), "m", "t", daily_cap=5)
    assert out == {"ok": False, "reason": "timeout"}


def test_prompt_plain_topic():
    assert research.desk_prompt("Asiad medals") == "Topic: Asiad medals"


def test_prompt_anchors_on_pasted_article():
    p = research.desk_prompt("x", {"url": "https://ndtv.com/a", "title": "SC verdict", "site_name": "NDTV",
                                   "description": "Court rules."})
    assert "https://ndtv.com/a" in p and "SC verdict" in p and "NDTV" in p and "Court rules." in p
    assert "\n" in p

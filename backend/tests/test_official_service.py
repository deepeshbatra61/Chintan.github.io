"""The Bureau service against an in-memory Mongo, a fake web and a fake AI.

    shadow   ─ ceremonial stored as filtered (no page fetched); decisions fetched,
               extracted, verified, stored in official_items; articles untouched
    rerun    ─ nothing new, nothing refetched
    off      ─ does nothing
    errors   ─ 403 backs off; malformed feed counts as a parse error; bad AI JSON
               keeps the item with the source title and a Desk flag; AI cap
    SEBI     ─ enforcement never fetched; release text read from its PDF
    AI kind  ─ may reclassify, may hide as ceremonial, can never promote noise
    health   ─ counts, silence alarm, broken after repeated parse errors
    lease    ─ a second runner skips while the first holds the lease
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")

import official as O  # noqa: E402
import official_service as S  # noqa: E402
from official_sources import ADAPTERS  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "official"
NOW = datetime(2026, 10, 5, 6, 0, tzinfo=timezone.utc)          # Monday 11:30 IST


def fb(name: str) -> bytes:
    return (FIX / name).read_bytes()


class FakeFetcher:
    def __init__(self, pages: dict):
        self.pages = pages
        self.calls = []

    async def get(self, url: str) -> bytes:
        self.calls.append(url)
        v = self.pages.get(url)
        if v is None:
            raise S.FetchError("http", "404")
        if isinstance(v, Exception):
            raise v
        return v


def good_json(**over):
    d = {"kind": "policy", "what_changed": "Five new centres will study classical languages",
         "key_number": None, "facts": ["Five centres", "Classical languages"],
         "who": ["Universities", "Students"], "dates": [], "analogy": "", "sectors": ["Education"],
         "summary": "The ministry approved new centres.", "importance": 6}
    d.update(over)
    return json.dumps(d)


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    async def __call__(self, system, user, max_tokens=900, model=None):
        self.calls.append((system, user, model))
        r = self.replies.pop(0) if self.replies else good_json()
        if isinstance(r, Exception):
            raise r
        return r


def pib_pages(extra=None):
    """The real Sunday feed: every non-ceremonial item maps to one saved page."""
    pages = {ADAPTERS["pib"].list_url: fb("pib_rss.xml")}
    page = fb("pib_release_2318843.html")
    for r in ADAPTERS["pib"].parse_list(fb("pib_rss.xml").decode()):
        if ADAPTERS["pib"].needs_detail(r):
            pages[ADAPTERS["pib"].detail_url(r)] = page
    pages.update(extra or {})
    return pages


def make(db, fetcher, llm, mode="shadow", sources=("pib",), cap=300, now=NOW):
    return S.OfficialService(db, llm, fetcher=fetcher, now=lambda: now, mode=lambda: mode,
                             sources=lambda: list(sources), llm_daily_cap=cap,
                             classify_topic=lambda t, b: ("Politics", None))


@pytest.fixture
def db():
    return mongomock_motor.AsyncMongoMockClient()["t"]


async def test_shadow_run_filters_fetches_extracts_and_never_touches_articles(db):
    fetcher, llm = FakeFetcher(pib_pages()), FakeLLM([])
    svc = make(db, fetcher, llm)
    await svc.ensure_indexes()
    s = await svc.run_once()
    pib = s["sources"]["pib"]
    assert pib["new"] == S.NEW_PER_SOURCE_PER_RUN and pib["error"] is None
    items = await db.official_items.find({}, {"_id": 0}).to_list(50)
    filtered = [i for i in items if i["status"] == "filtered"]
    kept = [i for i in items if i["status"] == "shadow"]
    assert filtered and kept
    assert all(i["kind"] == "ceremonial" for i in filtered)
    # ceremonial items never cost a page fetch or an AI call
    fetched_details = [u for u in fetcher.calls if "PressReleaseIframePage" in u]
    assert len(fetched_details) == len(kept) == len(llm.calls)
    k = kept[0]
    assert k["source_name"] == "PIB" and k["ministry"] == "Ministry of Road Transport & Highways"
    assert k["what_changed"] and k["importance"] in ("low", "normal", "high")
    assert await db.articles.count_documents({}) == 0
    assert "Chintan" in llm.calls[0][0] and llm.calls[0][2] == S.FAST_MODEL


async def test_rerun_is_idempotent(db):
    fetcher = FakeFetcher(pib_pages())
    svc = make(db, fetcher, FakeLLM([]))
    for _ in range(4):                       # the backlog drains 8 per run
        await svc.run_once()
    n_items = await db.official_items.count_documents({})
    assert n_items == 20
    calls_before = len(fetcher.calls)
    s = await svc.run_once()
    assert s["sources"]["pib"]["new"] == 0
    assert len(fetcher.calls) == calls_before + 1          # only the feed itself
    assert await db.official_items.count_documents({}) == 20


async def test_off_mode_does_nothing(db):
    fetcher = FakeFetcher(pib_pages())
    s = await make(db, fetcher, FakeLLM([]), mode="off").run_once()
    assert s == {"mode": "off", "sources": {}} and fetcher.calls == []


async def test_blocked_feed_backs_off(db):
    fetcher = FakeFetcher({ADAPTERS["pib"].list_url: S.FetchError("blocked", "403")})
    svc = make(db, fetcher, FakeLLM([]))
    s = await svc.run_once()
    assert s["sources"]["pib"]["error"].startswith("list blocked")
    s2 = await svc.run_once()
    assert s2["sources"]["pib"]["error"] == "backing off" and len(fetcher.calls) == 1
    later = make(db, fetcher, FakeLLM([]), now=NOW + timedelta(minutes=S.BACKOFF_MIN + 1))
    await later.run_once()
    assert len(fetcher.calls) == 2


async def test_malformed_feed_is_a_parse_error_and_health_goes_broken(db):
    fetcher = FakeFetcher({ADAPTERS["pib"].list_url: b"<rss><channel><item><title>x"})
    svc = make(db, fetcher, FakeLLM([]))
    for _ in range(3):
        s = await svc.run_once()
    assert s["sources"]["pib"]["error"] == "parse"
    h = await svc.health()
    assert h["sources"]["pib"]["broken"] and h["alarm"]


async def test_bad_ai_json_keeps_item_with_title_and_desk_flag(db):
    fetcher = FakeFetcher(pib_pages())
    llm = FakeLLM(["not json at all", "```still not json```"] + [good_json()] * 20)
    await make(db, fetcher, llm).run_once()
    first = await db.official_items.find_one({"verified_dropped": "bad_json"})
    assert first and first["needs_desk"] and first["what_changed"] == first["title"]


async def test_ai_numbers_not_in_source_are_dropped(db):
    fetcher = FakeFetcher(pib_pages())
    bogus = good_json(what_changed="₹9,99,999 crore for highways",
                      key_number={"value": "9,99,999", "unit": "crore", "label": "outlay"},
                      facts=["₹9,99,999 crore", "Highway safety"])
    await make(db, fetcher, FakeLLM([bogus] * 20)).run_once()
    it = await db.official_items.find_one({"status": "shadow"})
    assert it["key_number"] is None and it["facts"] == ["Highway safety"]
    assert "key_number" in it["verified_dropped"] and it["what_changed"] == it["title"]


async def test_llm_daily_cap(db):
    fetcher = FakeFetcher(pib_pages())
    llm = FakeLLM([])
    await make(db, fetcher, llm, cap=2).run_once()
    assert len(llm.calls) == 2
    capped = await db.official_items.find_one({"verified_dropped": "llm_cap"})
    assert capped is not None


async def test_ai_may_hide_as_ceremonial_but_never_promote_noise(db):
    fetcher = FakeFetcher(pib_pages())
    await make(db, fetcher, FakeLLM([good_json(kind="ceremonial")] + [good_json()] * 20)).run_once()
    hidden = await db.official_items.find_one({"status": "filtered", "kind": "ceremonial", "ministry": {"$ne": None}})
    assert hidden is not None
    assert O.importance("pib", "ceremonial", "x") == "never"


async def test_sebi_skips_enforcement_and_reads_the_pdf(db):
    refs = ADAPTERS["sebi"].parse_list(fb("sebi_rss.xml").decode())
    keep = [r for r in refs if ADAPTERS["sebi"].needs_detail(r)]
    pages = {ADAPTERS["sebi"].list_url: fb("sebi_rss.xml"),
             "https://www.sebi.gov.in/sebi_data/attachdocs/oct-2026/1790853960291.pdf": fb("sebi_release.pdf")}
    for r in keep:
        pages[r.url] = fb("sebi_release.html")
    fetcher = FakeFetcher(pages)
    llm = FakeLLM([good_json(kind="statement", what_changed="SEBI letters now verifiable by subject",
                             facts=["Since April 2025"])] * 10)
    svc = make(db, fetcher, llm, sources=("sebi",))
    for _ in range(4):
        await svc.run_once()
    assert not any("/enforcement/" in u for u in fetcher.calls)
    assert any(u.endswith(".pdf") for u in fetcher.calls)
    assert "Document Number Verification System" in llm.calls[0][1]
    kept = await db.official_items.find({"status": "shadow"}).to_list(20)
    assert len(kept) == len(keep)
    assert kept[0]["facts"] == ["Since April 2025"]
    assert any(r.endswith("17/2025") for r in kept[0]["refs"])          # cites its April 2025 release


async def test_rbi_needs_no_page_fetch(db):
    fetcher = FakeFetcher({ADAPTERS["rbi_press"].list_url: fb("rbi_press_rss.xml")})
    llm = FakeLLM([])
    await make(db, fetcher, llm, sources=("rbi_press",)).run_once()
    assert fetcher.calls == [ADAPTERS["rbi_press"].list_url]
    assert await db.official_items.count_documents({"issuer": "RBI"}) >= 1


async def test_health_counts_and_silence(db):
    svc = make(db, FakeFetcher(pib_pages()), FakeLLM([]))
    await svc.run_once()
    h = await svc.health()
    p = h["sources"]["pib"]
    assert p["kept_24h"] + p["filtered_24h"] == S.NEW_PER_SOURCE_PER_RUN
    assert not p["silent"] and h["llm_today"] >= 1 and h["mode"] == "shadow"
    quiet = make(db, FakeFetcher(pib_pages()), FakeLLM([]), now=NOW + timedelta(days=1, hours=2))
    h2 = await quiet.health()
    assert h2["sources"]["pib"]["silent"]                  # Mon 11:30 -> Tue 13:30 IST, nothing new


async def test_lease_blocks_a_second_runner(db):
    svc = make(db, FakeFetcher(pib_pages()), FakeLLM([]))
    assert await svc._lease()
    s = await svc.run_once()
    assert s.get("skipped") == "lease held"
    await svc._release()
    assert (await svc.run_once()).get("skipped") is None


def test_parse_extraction_tolerates_fences_and_rejects_junk():
    assert S.parse_extraction("```json\n" + good_json() + "\n```")["what_changed"]
    assert S.parse_extraction("") is None
    assert S.parse_extraction('{"what_changed": 5}') is None
    assert S.parse_extraction('{"what_changed": "x", "facts": "not a list"}') is None
    assert S.parse_extraction(good_json(importance="eleven"))["importance"] is None
    assert S.parse_extraction(good_json(importance=42))["importance"] == 10


async def test_pdf_text_rejects_non_pdf_and_reads_real_pdf():
    assert await S.pdf_text(b"<html>not a pdf</html>") == ""
    text = await S.pdf_text(fb("sebi_release.pdf"))
    assert "Document Number Verification System" in text and "Page 1 of 2" not in text

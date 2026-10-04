"""The Bureau, more sources: DGFT, MoSPI and Parliament on real saved data.

    DGFT       ─ table rows → refs with encoded PDF links, IST timestamps; PDFs are
                 scans, so the official description is the text
    MoSPI      ─ home-data API → release refs; PDF text read; embargo held until it lifts
    Parliament ─ one ref per dated stage, shared bill reference, clean titles,
                 body = Statement of Objects and Reasons from the bill's last pages
    service    ─ history older than 21 days is never imported
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import official as O
import official_service as S
from official_sources import ADAPTERS

FIX = Path(__file__).parent / "fixtures" / "official"


def fx(name):
    return (FIX / name).read_text(encoding="utf-8")


def fb(name):
    return (FIX / name).read_bytes()


# ── DGFT ──────────────────────────────────────────────────────────────────────

def test_dgft_notifications_table():
    refs = ADAPTERS["dgft_notif"].parse_list(fx("dgft_notifications.html"))
    assert len(refs) > 100
    r = refs[0]
    assert r.title.startswith("DGFT Notification 37/2026-27: Amendment to Notification No. 65/2025-26")
    assert " " not in r.url and r.url.endswith(".pdf")
    assert r.published_at == "2026-09-30T11:50:19+00:00"          # 17:20:19 IST
    assert "Notification No. 37/2026-27" in r.summary
    assert not ADAPTERS["dgft_notif"].needs_detail(r)
    assert O.classify_kind("dgft_notif", r.title) == "notification"
    assert O.official_id(r.url) != O.official_id(refs[1].url)


def test_dgft_public_notices_and_issuer():
    refs = ADAPTERS["dgft_public"].parse_list(fx("dgft_public_notices.html"))
    assert refs and refs[0].title.startswith("DGFT Public Notice 31/2026-27")
    assert ADAPTERS["dgft_public"].issuer_key == "dgft" and O.ISSUERS["dgft"] == "DGFT"


def test_dgft_missing_table_is_a_parse_error():
    with pytest.raises(ValueError):
        ADAPTERS["dgft_notif"].parse_list("<html><body>maintenance</body></html>")


# ── MoSPI ─────────────────────────────────────────────────────────────────────

def test_mospi_release_list():
    refs = ADAPTERS["mospi"].parse_list(fx("mospi_home.json"))
    assert len(refs) == 4
    iip = next(r for r in refs if "Industrial Production" in r.title)
    assert iip.url.startswith("https://www.mospi.gov.in/uploads/latestReleases/") and iip.url.endswith(".pdf")
    assert O.classify_kind("mospi", iip.title) == "data_release"
    assert O.importance("mospi", "data_release", iip.title) == "high"


async def test_mospi_pdf_text_and_embargo():
    text = await S.pdf_text(fb("mospi_iip.pdf"), ADAPTERS["mospi"].pdf_pages)
    assert "8.0%" in text
    assert O.embargo_until(text) == datetime(2026, 9, 28, 10, 30, tzinfo=timezone.utc)   # 4 PM IST
    assert O.embargo_until("No embargo here") is None


# ── Parliament ────────────────────────────────────────────────────────────────

def test_parliament_one_ref_per_stage():
    refs = ADAPTERS["parliament_ls"].parse_list(fx("sansad_ls_bills.json"))
    tribunal = [r for r in refs if r.extra["ref"] == "BILL 153/2026"]
    assert [r.extra["stage"] for r in tribunal] == ["introduced", "passed_ls", "passed_rs", "assented"]
    titles = [r.title for r in tribunal]
    assert titles[0] == "Introduced in Lok Sabha: Tribunals Reforms Bill, 2026"
    assert titles[1] == "Lok Sabha passes the Tribunals Reforms Bill, 2026"
    assert titles[3] == "President gives assent to the Tribunals Reforms Bill, 2026"
    assert len({r.url for r in refs}) == len(refs)                       # one id per stage
    assert O.importance("parliament_ls", "bill", titles[1]) == "high"
    assert O.importance("parliament_ls", "bill", titles[3]) == "high"
    assert O.importance("parliament_ls", "bill", titles[0]) == "normal"


def test_parliament_titles_and_roman_numbers():
    refs = ADAPTERS["parliament_rs"].parse_list(fx("sansad_rs_bills.json"))
    assert refs and all(" the The " not in r.title for r in refs)
    assert any(r.extra["ref"].startswith("BILL L") for r in refs)          # Rajya Sabha numbers bills in Roman


async def test_parliament_body_is_objects_and_reasons():
    a = ADAPTERS["parliament_ls"]
    text = await S.pdf_text(fb("sansad_bill.pdf"), a.pdf_pages)
    body = a.pdf_body(text)
    assert body.startswith("STATEMENT OF OBJECTS AND REASONS") and len(body) <= 5000


# ── service: PDFs as documents, embargo, age limit ────────────────────────────

mongomock_motor = pytest.importorskip("mongomock_motor")


class Fetch:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    async def get(self, url):
        self.calls.append(url)
        if url not in self.pages:
            raise S.FetchError("http", "404")
        return self.pages[url]


async def llm(system, user, max_tokens=900, model=None):
    return json.dumps({"kind": "data_release", "what_changed": "Factory output grew 8.0% in August",
                       "key_number": {"value": "8.0", "unit": "%", "label": "IIP growth"},
                       "facts": ["Manufacturing up 9.0%"], "who": ["Industry"], "dates": [],
                       "analogy": "", "sectors": ["Manufacturing"], "summary": "", "importance": 8})


def svc(db, fetcher, sources, now):
    return S.OfficialService(db, llm, fetcher=fetcher, now=lambda: now, mode=lambda: "shadow",
                             sources=lambda: list(sources), classify_topic=lambda t, b: ("Business", None))


def mospi_pages():
    refs = ADAPTERS["mospi"].parse_list(fx("mospi_home.json"))
    pages = {ADAPTERS["mospi"].list_url: fb("mospi_home.json")}
    for r in refs:
        pages[r.url] = fb("mospi_iip.pdf")
    return pages


async def test_mospi_embargo_holds_then_publishes():
    db = mongomock_motor.AsyncMongoMockClient()["t"]
    before = datetime(2026, 9, 28, 9, 0, tzinfo=timezone.utc)            # 2:30 PM IST, embargo till 4 PM
    await svc(db, Fetch(mospi_pages()), ["mospi"], before).run_once()
    assert await db.official_items.count_documents({}) == 0
    after = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    await svc(db, Fetch(mospi_pages()), ["mospi"], after).run_once()
    items = await db.official_items.find({}).to_list(10)
    assert len(items) == 4 and all(i["issuer"] == "MoSPI" for i in items)
    iip = next(i for i in items if "Industrial Production" in i["title"])
    assert iip["key_number"]["value"] == "8.0" and iip["facts"] == ["Manufacturing up 9.0%"]
    assert iip["importance"] == "high"


async def test_history_older_than_21_days_is_skipped():
    db = mongomock_motor.AsyncMongoMockClient()["t"]
    fetcher = Fetch({ADAPTERS["dgft_notif"].list_url: fb("dgft_notifications.html")})
    now = datetime(2026, 10, 5, 6, 0, tzinfo=timezone.utc)
    s = await svc(db, fetcher, ["dgft_notif"], now).run_once()
    stored = await db.official_items.find({}, {"published_at": 1}).to_list(50)
    assert stored and all(d["published_at"] >= (now - timedelta(days=S.MAX_AGE_DAYS)).isoformat() for d in stored)
    assert s["sources"]["dgft_notif"]["new"] <= S.NEW_PER_SOURCE_PER_RUN
    assert fetcher.calls == [ADAPTERS["dgft_notif"].list_url]            # scans: no PDF downloads


async def test_parliament_items_carry_the_bill_reference():
    db = mongomock_motor.AsyncMongoMockClient()["t"]
    refs = ADAPTERS["parliament_ls"].parse_list(fx("sansad_ls_bills.json"))
    pages = {ADAPTERS["parliament_ls"].list_url: fb("sansad_ls_bills.json")}
    for r in refs:
        pages[r.extra["pdf"]] = fb("sansad_bill.pdf")
    now = datetime(2026, 8, 20, 6, 0, tzinfo=timezone.utc)
    await svc(db, Fetch(pages), ["parliament_ls"], now).run_once()
    it = await db.official_items.find_one({"refs": "BILL 153/2026"})
    assert it is not None and it["issuer"] == "Parliament" and it["kind"] == "bill"
    assert it["source_text"].startswith("STATEMENT OF OBJECTS AND REASONS")

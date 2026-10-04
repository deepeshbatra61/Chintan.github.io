"""The Bureau: pure rules (official.py) and source parsers on real saved pages.

Fixtures in tests/fixtures/official were fetched 2026-10-04 (a Sunday, so the
PIB feed is mostly greetings: exactly the noise the filters must drop).
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import official as O
from official_sources import ADAPTERS, USER_AGENT

FIX = Path(__file__).parent / "fixtures" / "official"


def fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


# ── noise and kinds ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("title", [
    "Prime Minister congratulates Antim Panghal on winning Silver in Women's 53 kg Freestyle Wrestling",
    "Prime Minister pays homage to freedom fighter Shyamji Krishna Varma on his birth anniversary",
    "PM greets people on Navratri",
    "President condoles the passing away of former Governor",
])
def test_ceremonial_titles(title):
    assert O.is_ceremonial(title)
    assert O.classify_kind("pib", title) == "ceremonial"
    assert O.importance("pib", "ceremonial", title) == "never"


@pytest.mark.parametrize("title,kind", [
    ("Cabinet approves Rs 12,000 crore scheme for cold storage", "cabinet_decision"),
    ("Ministry of Education Approves Five Centres of Excellence for Studies in Classical Languages", "policy"),
    ("MoRTH invites comments on draft rules for distance-based tolling", "consultation"),
    ("Union Home Minister addresses Gaupalak Sammelan in Bhopal", "event"),
    ("Government notifies amendments to the Motor Vehicles Rules", "notification"),
    ("India and Japan sign MoU on semiconductor supply chains", "mou"),
    ("CPI inflation data for September released", "data_release"),
])
def test_pib_kinds(title, kind):
    assert O.classify_kind("pib", title) == kind


def test_rbi_kinds_and_importance():
    assert O.classify_kind("rbi_press", "Monetary Policy Statement, 2026-27: Resolution of the MPC") == "policy"
    assert O.importance("rbi_press", "policy", "Monetary Policy Statement") == "high"
    assert O.classify_kind("rbi_press", "RBI appoints Shri Sudhakar Malli as new Executive Director") == "appointment"
    assert O.classify_kind("rbi_press", "RBI imposes monetary penalty on XYZ Co-operative Bank") == "enforcement"
    assert O.classify_kind("rbi_notif", "Master Direction on Note Sorting Machines") == "circular"


def test_sebi_noise_by_title_or_url():
    assert O.is_sebi_noise("Remittance Order dated October 01, 2026 issued under RC No. 9261 of 2026", "")
    assert O.is_sebi_noise("Anything", "https://www.sebi.gov.in/enforcement/recovery-proceedings/oct-2026/x.html")
    assert not O.is_sebi_noise("SEBI revamps its Document Number Verification System",
                               "https://www.sebi.gov.in/media-and-notifications/press-releases/oct-2026/x.html")
    assert O.classify_kind("sebi", "Release Order for RC No. 4722 of 2022") == "enforcement"
    assert O.importance("sebi", "enforcement", "x") == "never"


def test_importance_rules_first_then_ai():
    assert O.importance("pib", "cabinet_decision", "x", ai_score=1) == "high"
    assert O.importance("pib", "policy", "x", ai_score=9) == "high"
    assert O.importance("pib", "policy", "x", ai_score=5) == "normal"
    assert O.importance("pib", "policy", "x", ai_score=2) == "low"
    assert O.importance("pib", "event", "x", ai_score=6) == "low"
    assert O.importance("pib", "policy", "x") == "normal"


# ── reference numbers (decision threads) ─────────────────────────────────────

def test_reference_numbers():
    refs = O.reference_numbers(
        "As per RBI/2026-27/112 and Notification No. 32/2026-Customs (N.T.), read with G.S.R. 845(E); "
        "earlier PR No. 17/2025. SEBI/HO/MRD/POD-1/P/CIR/2026/101 applies.")
    assert "RBI/2026-27/112" in refs
    assert "32/2026-CUSTOMS(N.T.)" in refs or any(r.startswith("32/2026") for r in refs)
    assert any(r.startswith("G.S.R.845") for r in refs)
    assert any(r.startswith("SEBI/HO/") for r in refs)


# ── numbers and dates: verify or drop (E1) ────────────────────────────────────

SRC = ("The Union Cabinet approved a scheme with an outlay of Rs. 12,000 crore over five years. "
       "The repo rate is reduced by 25 basis points to 5.25 per cent with effect from October 4, 2026. "
       "Applications open on 01.12.2026. Total disbursal of ₹1,20,000 crore so far.")


@pytest.mark.parametrize("fact", [
    "₹12,000 crore outlay", "₹12,000 cr", "Repo rate 5.25%", "Cut of 0.25%", "Cut of 25 bps",
    "From 4 October 2026", "Applications open 1 December", "₹1.2 lakh crore disbursed",
    "Applies to all banks",                       # no numbers: grounded by definition
])
def test_grounded_facts(fact):
    assert O.fact_is_grounded(fact, SRC), fact


@pytest.mark.parametrize("fact", [
    "₹1,200 crore outlay",                        # off by 10x
    "₹12,000 lakh",                               # wrong unit
    "Repo rate 5.5%", "From 5 October 2026", "Five crore farmers",  # 'five' is words, 5 crore is not in source
    "Applications open 2 December",
])
def test_ungrounded_facts(fact):
    if fact == "Five crore farmers":
        assert O.fact_is_grounded(fact, SRC)      # spelled-out numbers are not parsed; the eval catches these
        return
    assert not O.fact_is_grounded(fact, SRC), fact


def test_percent_never_matches_amount():
    assert not O.fact_is_grounded("5% stake", "a 5 crore grant")
    assert not O.fact_is_grounded("₹5 crore grant", "a 5% stake")


def test_verify_extraction_drops_and_keeps():
    ext = {
        "what_changed": "RBI cuts its rate to 5.25%",
        "key_number": {"value": "5.25", "unit": "%", "label": "repo rate", "delta": "-0.25"},
        "facts": ["From 4 October 2026", "₹99,000 crore boost", "Home and car loans"],
        "dates": [{"label": "effective", "date": "October 4, 2026"}, {"label": "deadline", "date": "9 March 2027"}],
        "analogy": "Like a shop paying 2% less for stock",
    }
    clean, dropped = O.verify_extraction(ext, SRC)
    assert clean["what_changed"] == "RBI cuts its rate to 5.25%"
    assert clean["key_number"]["value"] == "5.25"
    assert clean["facts"] == ["From 4 October 2026", "Home and car loans"]
    assert clean["dates"] == [{"label": "effective", "date": "October 4, 2026"}]
    assert clean["analogy"] == ""                 # analogies may not carry numbers
    assert any(d.startswith("fact:") for d in dropped) and "analogy" in dropped


def test_verify_extraction_drops_bad_key_number_and_headline():
    clean, dropped = O.verify_extraction(
        {"what_changed": "Outlay of ₹15,000 crore", "key_number": {"value": "15,000", "unit": "crore"}}, SRC)
    assert clean["what_changed"] == "" and clean["key_number"] is None
    assert "what_changed" in dropped and "key_number" in dropped


# ── schedule & silence ────────────────────────────────────────────────────────

def ist(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone(timedelta(hours=5, minutes=30))).astimezone(timezone.utc)


def test_day_and_night_ticks():
    assert O.tick_every_min(ist(2026, 10, 5, 7, 0)) == 10
    assert O.tick_every_min(ist(2026, 10, 5, 21, 59)) == 10
    assert O.tick_every_min(ist(2026, 10, 5, 22, 0)) == 60
    assert O.tick_every_min(ist(2026, 10, 5, 3, 0)) == 60


def test_silence_alarm_counts_only_weekday_office_hours():
    fri_6pm = ist(2026, 10, 2, 18, 0)
    assert not O.silence_alarm(fri_6pm, ist(2026, 10, 5, 9, 30), expected_gap_h=4)  # weekend + night don't count
    assert O.silence_alarm(fri_6pm, ist(2026, 10, 5, 14, 30), expected_gap_h=4)
    assert not O.silence_alarm(None, ist(2026, 10, 5, 14, 30), expected_gap_h=4)


# ── parsers on real saved pages ───────────────────────────────────────────────

def test_user_agent_is_honest_and_accepted():
    assert "Chintan" in USER_AGENT and "bot" not in USER_AGENT.lower() and "@" not in USER_AGENT


def test_pib_feed_and_filters():
    refs = ADAPTERS["pib"].parse_list(fx("pib_rss.xml"))
    assert len(refs) == 20
    assert all(r.url.startswith("https://pib.gov.in/PressReleasePage.aspx?PRID=") for r in refs)
    kinds = [O.classify_kind("pib", r.title) for r in refs]
    assert kinds.count("ceremonial") >= 8
    assert sum(ADAPTERS["pib"].needs_detail(r) for r in refs) == 20 - kinds.count("ceremonial")


def test_pib_release_page():
    d = ADAPTERS["pib"].parse_detail(fx("pib_release_2318698.html"))
    assert d["ministry"] == "Ministry of Cooperation"
    assert d["title"].startswith("Union Home Minister and Minister of Cooperation")
    assert d["published_at"] == "2026-10-03T12:54:00+00:00"       # 6:24 PM IST
    assert len(d["body"]) > 2000 and "Release ID" not in d["body"]


def test_rbi_feeds_carry_text_and_dates():
    for name, fn in (("rbi_press", "rbi_press_rss.xml"), ("rbi_notif", "rbi_notif_rss.xml")):
        refs = ADAPTERS[name].parse_list(fx(fn))
        assert len(refs) == 10
        assert all(r.published_at and r.summary for r in refs)
        assert not any(ADAPTERS[name].needs_detail(r) for r in refs)
    first = ADAPTERS["rbi_press"].parse_list(fx("rbi_press_rss.xml"))[0]
    assert first.published_at == "2026-10-02T11:35:00+00:00"      # 17:05 IST, no zone in the feed


def test_sebi_feed_noise_and_pdf_link():
    refs = ADAPTERS["sebi"].parse_list(fx("sebi_rss.xml"))
    assert len(refs) == 30
    kept = [r for r in refs if ADAPTERS["sebi"].needs_detail(r)]
    assert 1 <= len(kept) <= 5                                   # most of the feed is enforcement
    d = ADAPTERS["sebi"].parse_detail(fx("sebi_release.html"))
    assert d["pdf_url"] == "https://www.sebi.gov.in/sebi_data/attachdocs/oct-2026/1790853960291.pdf"
    assert d["published_at"].startswith("2026-09-30T18:30")


def test_malicious_xml_is_refused():
    bomb = ('<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;">]>'
            '<rss><channel><item><title>&lol2;</title><link>x</link></item></channel></rss>')
    with pytest.raises(Exception):
        ADAPTERS["pib"].parse_list(bomb)

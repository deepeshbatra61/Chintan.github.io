"""Parliament (sansad.in): government bills, one item per stage.

The bills API returns each bill with the date of every stage (introduced,
passed by Lok Sabha, passed by Rajya Sabha, assent) and links to the texts. A
bill moving a stage is the news, so each dated stage becomes its own item
("Lok Sabha passes the X Bill"); all of a bill's items share its reference
("BILL <number>/<year>") so decision threads can link them.

The summary is written from the bill's "Statement of Objects and Reasons",
the plain-language part near the END of the bill text, so the PDF reader takes
the first two and last ten pages.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import quote, urlsplit, urlunsplit

import official
from .common import IST, Adapter, to_utc_iso

_API = ("https://sansad.in/api_rs/legislation/getBills?loksabha=&sessionNo=&billName=&house={house}"
        "&ministryName=&billType=Government&billCategory=&billStatus=&introductionDateFrom="
        "&introductionDateTo=&passedInLsDateFrom=&passedInLsDateTo=&passedInRsDateFrom=&passedInRsDateTo="
        "&page=1&size=20&locale=en&sortOn=billIntroducedDate&sortBy=desc")
LS_URL = _API.format(house="Lok%20Sabha")
RS_URL = _API.format(house="Rajya%20Sabha")
PAGE = "https://sansad.in/ls/legislation/bills"

_STAGES = (  # (field, slug, headline verb)
    ("billIntroducedDate", "introduced", "Introduced in {house}:"),
    ("billPassedInLSDate", "passed_ls", "Lok Sabha passes"),
    ("billPassedInRSDate", "passed_rs", "Rajya Sabha passes"),
    ("billAssentedDate", "assented", "President gives assent to"),
)


def _safe(u: str) -> str:
    parts = urlsplit((u or "").strip())
    return urlunsplit((parts.scheme, parts.netloc, quote(parts.path), parts.query, parts.fragment))


def _date(raw: str):
    raw = (raw or "").strip()
    if not raw or raw == "None":
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y"):
        try:
            return to_utc_iso(datetime.strptime(raw, fmt).replace(hour=12, tzinfo=IST))
        except ValueError:
            continue
    return None


_SMALL = {"And", "Of", "The", "For", "In", "On", "To", "By", "With", "At"}


def _title_case(name: str) -> str:
    """'THE MINES AND MINERALS BILL' -> 'Mines and Minerals Bill' (leading 'The' dropped)."""
    words = re.sub(r"\b([A-Z])([A-Z]+)\b", lambda m: m.group(1) + m.group(2).lower(), name or "").split()
    if words and words[0] == "The":
        words = words[1:]
    return " ".join(w.lower() if i and w in _SMALL else w for i, w in enumerate(words))


def _parser(source: str):
    def parse_list(text: str) -> list:
        data = json.loads(text)
        out, seen = [], set()
        for b in data.get("records") or []:
            name = official.clean_space(_title_case(b.get("billName") or ""))
            num, year = str(b.get("billNumber") or "").strip(), str(b.get("billYear") or "").strip()
            pdf = str(b.get("billIntroducedFile") or "")
            if not name or not num or not pdf or pdf == "None":
                continue
            house = b.get("billIntroducedInHouse") or "Parliament"
            for field, slug, verb in _STAGES:
                when = _date(b.get(field))
                key = (num, year, slug)
                if not when or key in seen:
                    continue
                seen.add(key)
                out.append(official.Ref(
                    source=source, url=f"{PAGE}#bill-{num}-{year}-{slug}",
                    title=(f"{verb.format(house=house)} {name}" if verb.endswith(":")
                           else f"{verb.format(house=house)} the {name}"),
                    published_at=when,
                    summary=f"Bill No. {num} of {year}. Ministry: {_title_case(b.get('ministryName') or '')}. "
                            f"Stage: {slug.replace('_', ' ')}.",
                    extra={"pdf": _safe(pdf), "ref": f"BILL {num}/{year}", "stage": slug}))
        return out
    return parse_list


def _needs(ref) -> bool:
    return True


def _pdf_url(ref) -> str:
    return ref.extra.get("pdf") or ref.url


def _unused(text: str) -> dict:
    return {}


def objects_and_reasons(text: str) -> str:
    i = (text or "").upper().find("STATEMENT OF OBJECTS AND REASONS")
    return (text[i:i + 5000] if i >= 0 else (text or "")[:5000]).strip()


def _pages(n: int) -> list:
    return sorted(set(list(range(min(n, 2))) + list(range(max(0, n - 10), n))))


LOK_SABHA = Adapter(name="parliament_ls", issuer_key="parliament", source_name="Parliament", list_url=LS_URL,
                    expected_gap_h=10_000, parse_list=_parser("parliament_ls"), needs_detail=_needs,
                    parse_detail=_unused, detail_url=_pdf_url, detail_is_pdf=True,
                    pdf_pages=_pages, pdf_body=objects_and_reasons)
RAJYA_SABHA = Adapter(name="parliament_rs", issuer_key="parliament", source_name="Parliament", list_url=RS_URL,
                      expected_gap_h=10_000, parse_list=_parser("parliament_rs"), needs_detail=_needs,
                      parse_detail=_unused, detail_url=_pdf_url, detail_is_pdf=True,
                      pdf_pages=_pages, pdf_body=objects_and_reasons)

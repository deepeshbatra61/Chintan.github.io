"""SEBI: press releases, circulars, consultation papers.

Feed: title + description (same as title) + link + pubDate ("01 Oct, 2026
+0530"). About half the items are enforcement orders against individuals,
dropped by official.is_sebi_noise. The real text of a release is a PDF shown
in an iframe on the item page (`../../../web/?file=<pdf url>`), so the detail
step finds the PDF and the service extracts its text (with S1 limits).
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

import official
from .common import Adapter, parse_day_mon_year, rss_items

LIST_URL = "https://www.sebi.gov.in/sebirss.xml"
_PDF_IN_IFRAME = re.compile(r"[?&]file=(https://www\.sebi\.gov\.in/[^'\"&\s]+\.pdf)", re.I)


def parse_list(text: str) -> list:
    out = []
    for it in rss_items(text):
        if not it["link"] or not it["title"]:
            continue
        out.append(official.Ref(source="sebi", url=it["link"].strip(),
                                title=official.clean_space(it["title"]),
                                published_at=parse_day_mon_year(it["pubDate"])))
    return out


def needs_detail(ref: official.Ref) -> bool:
    return not official.is_sebi_noise(ref.title, ref.url)


def parse_detail(text: str) -> dict:
    soup = BeautifulSoup(text, "html.parser")
    h1 = soup.find("h1")
    date_el = soup.select_one(".date_value")
    m = _PDF_IN_IFRAME.search(text)
    # The visible page text is a stub (title, date, PR number); the PDF is the body.
    stub = official.clean_space((soup.select_one("#member-wrapper") or soup).get_text(" ", strip=True))
    return {
        "title": official.clean_space(h1.get_text(" ", strip=True)) if h1 else "",
        "ministry": "",
        "published_at": parse_day_mon_year(date_el.get_text(" ", strip=True)) if date_el else None,
        "body": stub[:2000],
        "pdf_url": m.group(1) if m else None,
    }


ADAPTER = Adapter(name="sebi", issuer_key="sebi", source_name="SEBI", list_url=LIST_URL,
                  expected_gap_h=10, parse_list=parse_list, needs_detail=needs_detail,
                  parse_detail=parse_detail)

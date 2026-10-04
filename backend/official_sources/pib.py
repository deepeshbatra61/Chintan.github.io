"""PIB (Press Information Bureau): all ministries' releases, Cabinet decisions.

Feed: English, national (Lang=1, Regid=3, reg=3; without reg the site may
redirect to Hindi). Titles + links only, no dates and no text, so every
non-ceremonial item needs its release page. ~20 newest items; polled every
10 min by day.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

import official
from .common import Adapter, parse_day_mon_year, rss_items

LIST_URL = "https://www.pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3&reg=3"
_PRID = re.compile(r"PRID=(\d+)")


def canonical(link: str) -> str:
    m = _PRID.search(link or "")
    return f"https://pib.gov.in/PressReleasePage.aspx?PRID={m.group(1)}" if m else (link or "").strip()


def detail_url(ref: official.Ref) -> str:
    m = _PRID.search(ref.url)
    return f"https://pib.gov.in/PressReleaseIframePage.aspx?PRID={m.group(1)}" if m else ref.url


def parse_list(text: str) -> list:
    out = []
    for it in rss_items(text):
        if not it["link"] or not it["title"]:
            continue
        out.append(official.Ref(source="pib", url=canonical(it["link"]),
                                title=official.clean_space(it["title"])))
    return out


def needs_detail(ref: official.Ref) -> bool:
    return not official.is_ceremonial(ref.title)


_BOILER = re.compile(r"^(\*+|\(Release ID.*|Visitor Counter.*|[A-Z]{2,4}/[A-Z]{2,4}(/[A-Z]{2,4})?)$")


def parse_detail(text: str) -> dict:
    soup = BeautifulSoup(text, "html.parser")
    root = soup.select_one(".innner-page-main-about-us-content-right-part") or soup
    ministry = root.select_one("#MinistryName")
    head = root.select_one(".event-heading-background") or root.find("h2")
    date_el = root.select_one("#PrDateTime")
    paras = []
    for p in root.find_all("p"):
        t = official.clean_space(p.get_text(" ", strip=True))
        if t and not _BOILER.match(t):
            paras.append(t)
    return {
        "title": official.clean_space(head.get_text(" ", strip=True)) if head else "",
        "ministry": official.clean_space(ministry.get_text(" ", strip=True)) if ministry else "",
        "published_at": parse_day_mon_year(date_el.get_text(" ", strip=True)) if date_el else None,
        "body": "\n".join(paras),
        "pdf_url": None,
    }


ADAPTER = Adapter(name="pib", issuer_key="pib", source_name="PIB", list_url=LIST_URL,
                  expected_gap_h=4, parse_list=parse_list, needs_detail=needs_detail,
                  parse_detail=parse_detail, detail_url=detail_url)

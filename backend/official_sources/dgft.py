"""DGFT (Directorate General of Foreign Trade): notifications and public notices.

The list pages are plain HTML tables: number, year, description, date, a
creation timestamp and a PDF link. The PDFs are scanned images (checked
2026-10-04: no text layer), so until OCR exists (TODOS #16) an item is built
from the official description line; the reader taps through to the PDF.
"""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import quote, urlsplit, urlunsplit

from bs4 import BeautifulSoup

import official
from .common import IST, Adapter, to_utc_iso

NOTIF_URL = "https://www.dgft.gov.in/CP/?opt=notification"
PUBLIC_URL = "https://www.dgft.gov.in/CP/?opt=public-notice"


def _safe_url(u: str) -> str:
    """DGFT links carry raw spaces ('Notif 39 E.pdf'); encode the path only."""
    parts = urlsplit((u or "").strip())
    return urlunsplit((parts.scheme, parts.netloc, quote(parts.path), parts.query, parts.fragment))


def _when(created: str, day: str):
    for fmt, val in (("%d/%m/%Y %H:%M:%S", created), ("%d/%m/%Y", day)):
        try:
            return to_utc_iso(datetime.strptime((val or "").strip(), fmt).replace(tzinfo=IST))
        except ValueError:
            continue
    return None


def _parser(source: str, label: str):
    def parse_list(text: str) -> list:
        soup = BeautifulSoup(text, "html.parser")
        table = soup.find("table")
        if table is None:
            raise ValueError("DGFT list table not found")
        out = []
        for row in table.find_all("tr")[1:]:
            cells = [official.clean_space(c.get_text(" ", strip=True)) for c in row.find_all("td")]
            link = next((a.get("href") for a in row.find_all("a") if a.get("href")), None)
            if len(cells) < 6 or not link or not cells[3]:
                continue
            number, desc = cells[1], cells[3]
            out.append(official.Ref(
                source=source, url=_safe_url(link),
                title=f"DGFT {label} {number}: {desc}".strip(),
                published_at=_when(cells[5], cells[4]),
                summary=f"{label} No. {number} ({cells[2]}), issued {cells[4]}: {desc}",
                extra={"number": number}))
        return out
    return parse_list


def _no_detail(ref) -> bool:
    return False


def _unused(text: str) -> dict:
    return {}


NOTIFICATIONS = Adapter(name="dgft_notif", issuer_key="dgft", source_name="DGFT", list_url=NOTIF_URL,
                        expected_gap_h=40, parse_list=_parser("dgft_notif", "Notification"),
                        needs_detail=_no_detail, parse_detail=_unused)
PUBLIC_NOTICES = Adapter(name="dgft_public", issuer_key="dgft", source_name="DGFT", list_url=PUBLIC_URL,
                         expected_gap_h=40, parse_list=_parser("dgft_public", "Public Notice"),
                         needs_detail=_no_detail, parse_detail=_unused)

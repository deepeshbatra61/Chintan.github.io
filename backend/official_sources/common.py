"""Shared parsing helpers for official sources (pure)."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, Optional

from defusedxml import ElementTree as SafeET   # untrusted XML: no entity expansion

IST = timezone(timedelta(hours=5, minutes=30))


@dataclass(frozen=True)
class Adapter:
    name: str
    issuer_key: str
    source_name: str
    list_url: str
    expected_gap_h: float
    parse_list: Callable
    needs_detail: Callable
    parse_detail: Callable
    detail_url: Callable = lambda ref: ref.url


def strip_html(s: str) -> str:
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s or "")
    s = re.sub(r"(?i)<br\s*/?>|</p>|</tr>|</li>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s).replace("\xa0", " ")
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()


def rss_items(text: str) -> list:
    """[{title, link, description, pubDate}] from an RSS 2.0 document."""
    root = SafeET.fromstring(text.lstrip("﻿").encode("utf-8"))
    out = []
    for item in root.iter("item"):
        def g(tag):
            el = item.find(tag)
            return (el.text or "").strip() if el is not None and el.text else ""
        out.append({"title": g("title"), "link": g("link"), "description": g("description"),
                    "pubDate": g("pubDate")})
    return out


def to_utc_iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)          # Indian government sites mean IST
    return dt.astimezone(timezone.utc).isoformat()


def parse_rfc822(s: str) -> Optional[str]:
    if not s:
        return None
    try:
        return to_utc_iso(parsedate_to_datetime(s))
    except (TypeError, ValueError, IndexError):
        return None


_MON = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def parse_day_mon_year(s: str) -> Optional[str]:
    """'03 OCT 2026 6:24PM', '01 Oct, 2026 +0530', 'Oct 01, 2026' (IST)."""
    s = s or ""
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})[a-z]*,?\s+(\d{4})(?:\s+(\d{1,2}):(\d{2})\s*([AP]M))?", s)
    if not m:
        m2 = re.search(r"([A-Za-z]{3})[a-z]*\s+(\d{1,2}),\s*(\d{4})", s)
        if not m2:
            return None
        d, mon, y, hh, mm, ap = m2.group(2), m2.group(1), m2.group(3), None, None, None
    else:
        d, mon, y, hh, mm, ap = m.groups()
    try:
        h = int(hh) % 12 + (12 if (ap or "").upper() == "PM" else 0) if hh else 0
        dt = datetime(int(y), _MON[mon[:3].lower()], int(d), h, int(mm or 0), tzinfo=IST)
    except (KeyError, ValueError):
        return None
    return to_utc_iso(dt)

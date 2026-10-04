"""MoSPI (statistics ministry): official data releases (GDP, CPI, IIP, PLFS ...).

The site is a single-page app; its home-page data call returns
`latestReleasesData`: title, published date and the release PDF (`file_one`,
a stringified dict). The PDFs have real text. Releases are often embargoed
("embargoed ... till 4.00 PM 28th September 2026"): the service holds them
until the embargo lifts (official.embargo_until).
"""

from __future__ import annotations

import ast
import json
from datetime import datetime

import official
from .common import IST, Adapter, to_utc_iso

LIST_URL = "https://www.mospi.gov.in/api/main-site/get-home-main-site-data?lang=en"
BASE = "https://www.mospi.gov.in/"


def _file_path(raw) -> str:
    if isinstance(raw, dict):
        return raw.get("path") or ""
    try:
        val = ast.literal_eval(raw) if isinstance(raw, str) and raw.startswith("{") else None
    except (ValueError, SyntaxError):
        val = None
    return (val or {}).get("path") or ""


def parse_list(text: str) -> list:
    data = json.loads(text)
    out = []
    for rel in data.get("latestReleasesData") or []:
        title = official.clean_space(rel.get("title") or "")
        path = _file_path(rel.get("file_one"))
        if not title or not path:
            continue
        day = rel.get("published_date") or ""
        try:
            published = to_utc_iso(datetime.strptime(day, "%Y-%m-%d").replace(hour=16, tzinfo=IST))
        except ValueError:
            published = None
        out.append(official.Ref(source="mospi", url=BASE + path.lstrip("/"), title=title,
                                published_at=published, extra={"id": rel.get("id")}))
    return out


def _needs(ref) -> bool:
    return True


def _unused(text: str) -> dict:
    return {}


ADAPTER = Adapter(name="mospi", issuer_key="mospi", source_name="MoSPI", list_url=LIST_URL,
                  expected_gap_h=60, parse_list=parse_list, needs_detail=_needs, parse_detail=_unused,
                  detail_is_pdf=True, pdf_pages=lambda n: list(range(min(n, 6))))

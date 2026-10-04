"""RBI: press releases and notifications (circulars to banks / NBFCs).

Both feeds carry the full text in <description> (HTML) and a pubDate with no
time zone (IST), so no detail fetch is needed.
"""

from __future__ import annotations

import official
from .common import Adapter, parse_rfc822, rss_items, strip_html

PRESS_URL = "https://www.rbi.org.in/pressreleases_rss.xml"
NOTIF_URL = "https://www.rbi.org.in/notifications_rss.xml"


def _parser(source: str):
    def parse_list(text: str) -> list:
        out = []
        for it in rss_items(text):
            if not it["link"] or not it["title"]:
                continue
            out.append(official.Ref(source=source, url=it["link"].strip(),
                                    title=official.clean_space(it["title"]),
                                    published_at=parse_rfc822(it["pubDate"]),
                                    summary=strip_html(it["description"])))
        return out
    return parse_list


def _no_detail(ref: official.Ref) -> bool:
    return False


def _unused(text: str) -> dict:
    return {}


PRESS = Adapter(name="rbi_press", issuer_key="rbi", source_name="RBI", list_url=PRESS_URL,
                expected_gap_h=8, parse_list=_parser("rbi_press"), needs_detail=_no_detail,
                parse_detail=_unused)
NOTIFICATIONS = Adapter(name="rbi_notif", issuer_key="rbi", source_name="RBI", list_url=NOTIF_URL,
                        expected_gap_h=30, parse_list=_parser("rbi_notif"), needs_detail=_no_detail,
                        parse_detail=_unused)

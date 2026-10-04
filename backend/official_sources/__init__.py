"""Source adapters for The Bureau (eng review 2B).

Each adapter is a small module with pure parsers (no network): the service
fetches, caches, rate-limits and handles errors once, for all of them.

    Adapter fields
      name            "pib", "rbi_press", ...
      issuer_key      official.ISSUERS key ("pib" is refined to "cabinet" per item)
      source_name     shown to readers ("PIB", "RBI", "SEBI")
      list_url        the feed / list page
      expected_gap_h  weekday office hours without a new item before the
                      silence alarm fires (official.silence_alarm)
      parse_list(text)   -> [official.Ref]
      needs_detail(ref)  -> bool  (RBI's feed already carries the full text)
      parse_detail(text) -> {title, ministry, published_at, body, pdf_url}
"""

from __future__ import annotations

from . import dgft, mospi, parliament, pib, rbi, sebi

ADAPTERS = {a.name: a for a in (
    pib.ADAPTER, rbi.PRESS, rbi.NOTIFICATIONS, sebi.ADAPTER,
    dgft.NOTIFICATIONS, dgft.PUBLIC_NOTICES, mospi.ADAPTER,
    parliament.LOK_SABHA, parliament.RAJYA_SABHA,
)}

# Honest identity that the sites accept. PIB's CDN refuses user agents that
# contain "bot", an email address or a "+http" link (tested 2026-10-04), so the
# contact lives on chintan.news rather than in the header.
USER_AGENT = "Chintan News Reader/1.0 (chintan.news)"

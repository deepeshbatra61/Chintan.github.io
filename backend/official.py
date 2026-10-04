"""The Bureau (Government Tracker): pure rules, no I/O.

Official announcements (PIB, Cabinet, RBI, SEBI, ...) become short, verified,
structured items. Everything here is deterministic and unit-tested; the
fetching, AI and storage live in official_service.py.

    source list (RSS / page) ─▶ Ref ─▶ noise filters ─▶ kind + issuer
         ─▶ AI extraction (service) ─▶ verify_extraction ─▶ importance
         ─▶ item document (official_items in shadow; articles when live)

Product voice (CEO review, owner): "indulging, simple, creative". One plain
line, a few facts, a "think of it like" analogy. Analogies never carry numbers,
names or dates of their own, and every number / date we show must appear in
the source text (E1: verify, else drop).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Iterable, Optional

# ── issuers ───────────────────────────────────────────────────────────────────

ISSUERS = {
    "cabinet": "Cabinet",
    "pib": "PIB",          # a ministry release; the ministry name is kept separately
    "rbi": "RBI",
    "sebi": "SEBI",
}

KINDS = ("cabinet_decision", "policy", "circular", "notification", "scheme", "consultation",
         "appointment", "data_release", "mou", "statement", "event", "enforcement", "ceremonial")


@dataclass
class Ref:
    """One entry from a source's list (feed item or list row)."""
    source: str                       # adapter name, e.g. "pib", "rbi_press"
    url: str
    title: str
    published_at: Optional[str] = None  # ISO UTC when the list gives one
    summary: str = ""                 # plain text the list already carries (RBI: full body)
    extra: dict = field(default_factory=dict)


def official_id(url: str) -> str:
    """Stable id from the canonical URL (query kept: PIB's id lives in PRID=)."""
    return "official_" + hashlib.md5(url.strip().encode()).hexdigest()[:12]


def clean_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


# ── noise filters ─────────────────────────────────────────────────────────────

# PIB publishes the PM's and ministers' greetings, condolences and tributes as
# releases. On a Sunday that's most of the feed (2026-10-04: 10 of 20).
_CEREMONIAL = re.compile(
    r"\b(congratulat\w*|greets?|greetings|condol\w*|pays? (homage|tribute)|homage|tributes?|"
    r"wishes|felicitat\w*|birth anniversary|death anniversary|jayanti|salutes|bows to|"
    r"remembers|extends? (best )?wishes|on the occasion of)\b", re.I)

# Events: real, but not decisions. Kept (low importance) so the record is complete.
_EVENT = re.compile(
    r"\b(address(es|ed)?|chairs?|to chair|inaugurat\w*|visits?|participat\w*|observes?|"
    r"celebrat\w*|conclave|summit|conference|workshop|seminar|webinar|meet(s|ing)? with|"
    r"interacts?|felicitates|flags? off|launch(es)? (of )?(a )?(campaign|drive)|concludes?|"
    r"organis\w+|organiz\w+|calls? (for|on)|exhorts?|urges?)\b", re.I)

_DECISION = re.compile(
    r"\b(approves?|approved|notif(y|ies|ied)|amend(s|ed|ment)?|issues? (guidelines|directions|"
    r"order|circular|notification)|allocat\w*|sanction\w*|extends? (the )?(deadline|validity|"
    r"scheme)|revis(es|ed|ion)|hikes?|cuts?|reduc\w*|raises?|increases?|exempt\w*|bans?|"
    r"prohibit\w*|mandat\w*|launch(es|ed)? (a |the )?(scheme|portal|mission|yojana|policy)|"
    r"signs? (an? )?(mou|agreement|pact)|clears?|introduces?|enacts?|repeal\w*|"
    r"rate|repo|policy|tariff|duty|subsidy|msp|tender|auction|guidelines|framework|regulations?|"
    r"rules?|scheme|yojana|mission|budget|draft)\b", re.I)

# SEBI's feed is about half enforcement against individuals and small firms:
# recovery certificates, remittance / release / attachment orders. Not news for
# readers; drop them. Market-wide circulars, consultation papers and board
# decisions stay.
_SEBI_NOISE_TITLE = re.compile(
    r"\b(remittance order|release order|recovery certificate|rc no\.?|attachment order|"
    r"demand notice|order for compliance|adjudication order|settlement order|"
    r"order in the matter of|exemption order|order under section)\b", re.I)
_SEBI_NOISE_URL = re.compile(r"/enforcement/|/recovery-proceedings/|/orders/", re.I)


def is_ceremonial(title: str) -> bool:
    return bool(_CEREMONIAL.search(title or ""))


def is_sebi_noise(title: str, url: str) -> bool:
    return bool(_SEBI_NOISE_URL.search(url or "") or _SEBI_NOISE_TITLE.search(title or ""))


def is_cabinet(title: str, ministry: str = "") -> bool:
    t = f"{ministry} {title}".lower()
    return ("cabinet" in t and ("approv" in t or "decision" in t or "committee" in t)) or \
        "ccea" in t or "cabinet committee on economic affairs" in t


def classify_kind(source: str, title: str, ministry: str = "", url: str = "") -> str:
    """Rules-first kind. The AI may refine within the non-noise kinds."""
    t = title or ""
    if source.startswith("sebi") and is_sebi_noise(t, url):
        return "enforcement"
    if is_ceremonial(t):
        return "ceremonial"
    if is_cabinet(t, ministry):
        return "cabinet_decision"
    tl = t.lower()
    if source.startswith("rbi"):
        if re.search(r"monetary policy|repo rate|policy rate|mpc", tl):
            return "policy"
        if re.search(r"appoint|executive director|deputy governor|takes charge", tl):
            return "appointment"
        if re.search(r"penalt|cancels? (the )?(certificate|licen[cs]e)|imposes|monetary penalty", tl):
            return "enforcement"
        if re.search(r"data|statistics|survey|results? of|money supply|reserves", tl):
            return "data_release"
        if source == "rbi_notif":
            return "circular"
        return "statement"
    if source.startswith("sebi"):
        if "consultation" in tl:
            return "consultation"
        if "circular" in tl:
            return "circular"
        if re.search(r"board meeting|press release|pr no", tl):
            return "policy"
        return "statement"
    if re.search(r"\b(mou|memorandum of understanding|agreement)\b", tl):
        return "mou"
    if re.search(r"\b(draft|comments|consultation|stakeholder)\b", tl):
        return "consultation"
    if re.search(r"\b(scheme|yojana|mission)\b", tl):
        return "scheme"
    if re.search(r"\bnotif(y|ies|ied|ication)\b", tl):
        return "notification"
    if re.search(r"\b(gdp|cpi|wpi|iip|inflation|index of|data|survey|statistics)\b", tl):
        return "data_release"
    if re.search(r"\b(appoint\w*|takes charge|assumes charge)\b", tl):
        return "appointment"
    if _DECISION.search(t):
        return "policy"
    if _EVENT.search(t):
        return "event"
    return "statement"


# What is never shown to readers (kept only as counts on the health page).
HIDDEN_KINDS = {"ceremonial", "enforcement"}

_HIGH_RBI = re.compile(r"monetary policy|repo rate|policy rate|crr|slr|mpc", re.I)


def importance(source: str, kind: str, title: str, ai_score: Optional[int] = None) -> str:
    """Rules first, AI second (CEO P1). Returns never | low | normal | high.
    The Desk can override later; that override is stored on the item."""
    if kind in HIDDEN_KINDS:
        return "never"
    if kind == "cabinet_decision":
        return "high"
    if source.startswith("rbi") and (kind == "policy" or _HIGH_RBI.search(title or "")):
        return "high"
    if source.startswith("sebi") and kind in ("circular", "policy"):
        return "high" if (ai_score or 0) >= 6 else "normal"
    if kind in ("event", "appointment", "statement"):
        return "low" if (ai_score or 0) < 8 else "normal"
    if ai_score is not None:
        return "high" if ai_score >= 8 else ("normal" if ai_score >= 4 else "low")
    return "normal"


# ── reference numbers (decision threads, eng 2A/A2) ───────────────────────────

_REF_PATTERNS = [
    re.compile(r"\bRBI/\d{4}-\d{2,4}/\d+\b", re.I),
    re.compile(r"\bSEBI/[A-Z0-9/\-_.]+/\d{4}/\d+\b", re.I),
    re.compile(r"\b(?:Notification|Circular|Order|Resolution|O\.M\.|OM)\s*No\.?\s*[:\-]?\s*"
               r"([A-Z0-9][A-Z0-9/\-.()]*\d[A-Z0-9/\-.()]*)", re.I),
    re.compile(r"\b(?:PR|Press Release)\s*No\.?\s*:?\s*\d+/\d{4}\b", re.I),   # SEBI / RBI press releases
    re.compile(r"\bG\.S\.R\.\s*\d+\s*\(E\)", re.I),
    re.compile(r"\bS\.O\.\s*\d+\s*\(E\)", re.I),
]


def reference_numbers(text: str) -> list:
    """Document numbers cited in a text, normalised (uppercase, no spaces)."""
    out = []
    for pat in _REF_PATTERNS:
        for m in pat.finditer(text or ""):
            ref = (m.group(1) if m.groups() else m.group(0)).upper()
            ref = re.sub(r"\s+", "", ref).rstrip(".,;)")
            if len(ref) >= 4 and ref not in out:
                out.append(ref)
    return out


# ── numbers and dates: the verify-or-drop check (CEO E1) ─────────────────────

_MULT = {"lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "crore": 1e7, "crores": 1e7, "cr": 1e7,
         "thousand": 1e3, "million": 1e6, "mn": 1e6, "billion": 1e9, "bn": 1e9,
         "trillion": 1e12, "k": 1e3}
_NUM = re.compile(
    r"(?<![\w.])(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(\s*%| ?per ?cent| ?percent| ?bps| ?basis points)?"
    r"((?:\s*(?:lakh|lakhs|lac|crore|crores|cr|thousand|million|mn|billion|bn|trillion|k)\b)*)",
    re.I)
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_DATE_PATTERNS = [
    # 1 November 2026 / 1st Nov, 2026 / 01 OCT 2026
    re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?,?\s*(\d{4})?\b", re.I),
    # November 1, 2026 / Nov 1
    re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})?\b", re.I),
    # 01.11.2026 / 01/11/2026 / 01-11-2026 (Indian day-first)
    re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b"),
    # 2026-11-01
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
]


def _to_float(s: str) -> Optional[float]:
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def number_mentions(text: str) -> list:
    """Each number in a text as the set of values it may match. A scaled
    amount is its full value ('amt:<v>'), so '1.2 lakh crore' and '1,20,000
    crore' agree, but '12,000 lakh' never matches '12,000 crore'. Percentages
    are tagged ('pct:5') so 5% never matches 5 crore; basis points also count
    as their percentage."""
    out = []
    for m in _NUM.finditer(text or ""):
        v = _to_float(m.group(1))
        if v is None:
            continue
        unit = (m.group(2) or "").strip().lower()
        if unit in ("%", "per cent", "percent"):
            out.append({f"pct:{round(v, 4)}"})
            continue
        if unit in ("bps", "basis points"):
            out.append({f"bps:{round(v, 4)}", f"pct:{round(v / 100, 4)}"})
            continue
        mult = 1.0
        for w in re.findall(r"[a-z]+", (m.group(3) or "").lower()):
            mult *= _MULT.get(w, 1.0)
        # A scaled amount must match by its full value: '12,000 lakh' is not
        # '12,000 crore' even though both say 12,000.
        out.append({f"amt:{round(v * mult, 2)}"} if mult != 1.0 else {round(v, 4)})
    return out


def number_values(text: str) -> set:
    """Every value the numbers in a source can be matched against: bare
    figures, and each scaled amount by its full value ('amt:<v>')."""
    out = set()
    for m in _NUM.finditer(text or ""):
        v = _to_float(m.group(1))
        if v is None:
            continue
        out |= {round(v, 4)}
    for vals in number_mentions(text):
        out |= vals
    return out


def date_values(text: str, default_year: Optional[int] = None) -> set:
    """(year|None, month, day) tuples. Year-less mentions match any year."""
    out = set()
    for i, pat in enumerate(_DATE_PATTERNS):
        for m in pat.finditer(text or ""):
            try:
                if i == 0:
                    d, mon, y = int(m.group(1)), _MONTHS[m.group(2)[:3].lower()], m.group(3)
                elif i == 1:
                    mon, d, y = _MONTHS[m.group(1)[:3].lower()], int(m.group(2)), m.group(3)
                elif i == 2:
                    d, mon, y = int(m.group(1)), int(m.group(2)), m.group(3)
                else:
                    y, mon, d = m.group(1), int(m.group(2)), int(m.group(3))
                y = int(y) if y else None
                date(y or 2000, mon, d)          # validates day/month
            except (ValueError, KeyError):
                continue
            out.add((y, mon, d))
    return out


def _date_ok(found: tuple, source_dates: set) -> bool:
    y, mon, d = found
    for (sy, smon, sd) in source_dates:
        if smon == mon and sd == d and (y is None or sy is None or sy == y):
            return True
    return False


def fact_is_grounded(fact: str, source_text: str) -> bool:
    """True when every number and date in `fact` appears in the source. A fact
    with no numbers or dates is grounded by definition (words are judged by
    the eval and the Desk, not here)."""
    mentions = number_mentions(fact)
    dates = date_values(fact)
    if not mentions and not dates:
        return True
    src_nums = number_values(source_text)
    src_dates = date_values(source_text)
    # A date's day, month and year also read as bare numbers; they are checked
    # as a date, not demanded as amounts.
    date_parts = set()
    for (y, mon, d) in dates:
        date_parts |= {float(d), float(mon)} | ({float(y)} if y else set())
    for vals in mentions:
        if len(vals) == 1 and next(iter(vals)) in date_parts:
            continue
        if not (vals & src_nums):
            return False
    return all(_date_ok(dt, src_dates) for dt in dates)


def verify_extraction(ext: dict, source_text: str) -> tuple:
    """Apply E1 to an AI extraction. Returns (clean_extraction, dropped_fields).
    Unverifiable facts, key number, dates or a number-bearing headline are
    removed; an analogy carrying any number is removed outright."""
    clean = dict(ext or {})
    dropped = []
    # Headline line: if it carries an unverified number, keep the item but blank
    # the line so the service falls back to the source title.
    if clean.get("what_changed") and not fact_is_grounded(clean["what_changed"], source_text):
        dropped.append("what_changed")
        clean["what_changed"] = ""
    kn = clean.get("key_number") or {}
    if kn:
        unit = str(kn.get("unit") or "")
        val = f"{kn.get('value', '')} {unit}".strip()
        delta = str(kn.get("delta") or "").strip()
        if delta:
            delta = f"{delta.lstrip('+-−▲▼ ')} {unit}".strip()   # a change carries the number's unit
        if not val or not fact_is_grounded(val, source_text) or (delta and not fact_is_grounded(delta, source_text)):
            dropped.append("key_number")
            clean["key_number"] = None
    facts = []
    for f in clean.get("facts") or []:
        if isinstance(f, str) and f.strip() and fact_is_grounded(f, source_text):
            facts.append(f.strip())
        else:
            dropped.append(f"fact:{str(f)[:40]}")
    clean["facts"] = facts[:3]
    dates = []
    for d in clean.get("dates") or []:
        if not isinstance(d, dict):
            continue
        when = str(d.get("date", ""))
        if when and fact_is_grounded(when, source_text) and date_values(when):
            dates.append({"label": str(d.get("label", ""))[:60], "date": when})
        else:
            dropped.append(f"date:{when[:20]}")
    clean["dates"] = dates
    analogy = (clean.get("analogy") or "").strip()
    if analogy and (number_values(analogy) or date_values(analogy)):
        dropped.append("analogy")
        analogy = ""
    clean["analogy"] = analogy
    return clean, dropped


# ── schedule (CEO E2 + owner: GNews sweeps by day only) ──────────────────────

IST_OFFSET_MIN = 330
DAY_START_H, DAY_END_H = 7, 22
DAY_EVERY_MIN, NIGHT_EVERY_MIN = 10, 60


def ist_hour(now: datetime) -> float:
    m = (now.astimezone(timezone.utc).hour * 60 + now.astimezone(timezone.utc).minute + IST_OFFSET_MIN) % 1440
    return m / 60.0


def is_daytime(now: datetime) -> bool:
    return DAY_START_H <= ist_hour(now) < DAY_END_H


def tick_every_min(now: datetime) -> int:
    return DAY_EVERY_MIN if is_daytime(now) else NIGHT_EVERY_MIN


def ist_weekday(now: datetime) -> int:
    """0 = Monday … 6 = Sunday, in India."""
    from datetime import timedelta
    return (now.astimezone(timezone.utc) + timedelta(minutes=IST_OFFSET_MIN)).weekday()


def silence_alarm(last_new_at: Optional[datetime], now: datetime, expected_gap_h: float) -> bool:
    """A source is 'silent' when nothing new has arrived for longer than its
    usual gap, counted only in weekday office hours (09:00-19:00 IST), so a
    quiet night or weekend never raises an alarm."""
    if last_new_at is None:
        return False
    from datetime import timedelta
    office_hours = 0.0
    t = last_new_at
    step = timedelta(minutes=30)
    while t < now and office_hours <= expected_gap_h + 1:
        if ist_weekday(t) < 5 and 9 <= ist_hour(t) < 19:
            office_hours += 0.5
        t += step
    return office_hours > expected_gap_h


# ── item document ─────────────────────────────────────────────────────────────

def build_item(*, ref: Ref, detail: dict, kind: str, ext: dict, dropped: list, importance_level: str,
               topic: tuple, now: datetime, source_name: str, issuer_key: str) -> dict:
    """The one shape of an official item. Stored in official_items while in
    shadow; the same fields become an article's `official` block when live."""
    title = clean_space(detail.get("title") or ref.title)
    ministry = clean_space(detail.get("ministry") or "")
    body = detail.get("body") or ref.summary or ""
    what = (ext.get("what_changed") or "").strip() or title
    category, subcategory = topic
    return {
        "official_id": official_id(ref.url),
        "source": ref.source,
        "source_name": source_name,
        "source_url": ref.url,
        "issuer": ISSUERS.get(issuer_key, issuer_key.upper()),
        "issuer_key": issuer_key,
        "ministry": ministry or None,
        "kind": kind,
        "title": title,
        "published_at": detail.get("published_at") or ref.published_at or now.isoformat(),
        "fetched_at": now.isoformat(),
        "what_changed": what,
        "key_number": ext.get("key_number"),
        "facts": ext.get("facts") or [],
        "who": [str(w)[:40] for w in (ext.get("who") or [])][:4],
        "dates": ext.get("dates") or [],
        "analogy": ext.get("analogy") or "",
        "sectors": [str(s)[:30] for s in (ext.get("sectors") or [])][:4],
        "summary": (ext.get("summary") or "").strip(),
        "ai_score": ext.get("importance"),
        "importance": importance_level,
        "verified_dropped": dropped,
        "needs_desk": len(dropped) >= 3 or not ext,
        "refs": reference_numbers(f"{title} {body}"),
        "category": category,
        "subcategory": subcategory,
        "body_chars": len(body),
        "status": "shadow",
    }

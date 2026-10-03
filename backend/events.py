"""News v2 events: which articles describe the same real-world event. Pure, no
I/O (events_service.py does the Mongo work), so every rule is unit-testable and
the golden set can replay it offline.

    article ─▶ vectorize (IDF-weighted terms, names ×2) ─▶ assign
                 │                                          │
                 │       candidate events: last member ≤36h old, < MAX_MEMBERS,
                 │       article not blocked by the Desk
                 │                                          ▼
                 │       join best event when BOTH hold:
                 │         cosine(article, event centroid)      ≥ T_JOIN
                 │         max cosine(article, founding members) ≥ T_FOUND   (drift guard)
                 └──────▶ otherwise it founds a new event

Two existing events are never merged automatically (that's how snowballs
start); the Desk can merge or split by hand.

STATUS (D7, plan-ceo-review 2026-10-03)
    forming ──(2+ independent outlets, reports ≥2h apart, within 6h)──▶ developing
       │  └─(Desk promote / member of a scheduled|calendar|wave container)──▲
       ├─(1 outlet + scout flag)──▶ early_report ──(2nd independent outlet)─┘
       ▼                                                                    │
    settled ◀──(8h with no independent report; Desk events 24h)──── developing
       │
       └─(36h with no member at all)──▶ closed          (closed is terminal)
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timedelta
from typing import Iterable, Optional

import textutil

# Tuned on the golden set (tests/fixtures/events_golden.json); see test_events_golden.
T_JOIN = 0.40
T_FOUND = 0.30
JOIN_WINDOW_H = 36
MAX_MEMBERS = 40
CENTROID_TERMS = 30
FOUNDING = 3

DEVELOPING_WINDOW_H = 6
DEVELOPING_SPREAD_H = 2
SETTLE_AFTER_H = 8
SETTLE_AFTER_DESK_H = 24
CLOSE_AFTER_H = 36
DEVELOPING_CAP = 15
LEAD_PIN_H = 4

# Coverage alarm (D4): a flood would trip this within one cycle.
ALARM_LABEL_RATIO = 0.30
ALARM_OPEN = 25

STATUSES = ("forming", "early_report", "developing", "settled", "closed")


# ── vectors ───────────────────────────────────────────────────────────────────

def term_weights(title: str, description: str = "", content: str = "") -> Counter:
    """Raw term weights for one article: title words count 2, description 1,
    the first 300 chars of content 0.5; a Capitalised name doubles its weight."""
    w: Counter = Counter()
    for text, base in ((title, 2.0), (description, 1.0), ((content or "")[:300], 0.5)):
        for term, entity in textutil.tokens(text):
            w[term] += base * (2.0 if entity else 1.0)
    return w


class DocFreq:
    """Document frequencies over the rolling window, updated incrementally as
    articles enter (add) and age out (remove). rebuilt == incremental is a test."""

    def __init__(self):
        self.df: Counter = Counter()
        self.n = 0

    def add(self, terms: Iterable[str]) -> None:
        self.n += 1
        self.df.update(set(terms))

    def remove(self, terms: Iterable[str]) -> None:
        self.n = max(0, self.n - 1)
        for t in set(terms):
            if self.df[t] <= 1:
                self.df.pop(t, None)
            else:
                self.df[t] -= 1

    def idf(self, term: str) -> float:
        return math.log((self.n + 1) / (self.df.get(term, 0) + 1)) + 1.0


def vectorize(weights: Counter, df: DocFreq) -> dict:
    """L2-normalised TF-IDF vector."""
    v = {t: w * df.idf(t) for t, w in weights.items() if w > 0}
    norm = math.sqrt(sum(x * x for x in v.values()))
    return {t: x / norm for t, x in v.items()} if norm else {}


def cosine(a: dict, b: dict) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0.0) for t, x in a.items())


def merge_centroid(centroid: dict, n: int, vec: dict) -> dict:
    """Running mean of member vectors, trimmed to the top CENTROID_TERMS and
    re-normalised. n = members already in the centroid."""
    out = {t: x * n for t, x in centroid.items()}
    for t, x in vec.items():
        out[t] = out.get(t, 0.0) + x
    top = sorted(out.items(), key=lambda kv: kv[1], reverse=True)[:CENTROID_TERMS]
    norm = math.sqrt(sum(x * x for _, x in top))
    return {t: x / norm for t, x in top} if norm else {}


# ── assignment ────────────────────────────────────────────────────────────────

def choose_event(vec: dict, article_id: str, published: datetime, candidates: Iterable[dict]) -> Optional[str]:
    """Best event for this article, or None (it founds a new one).
    candidate: {event_id, centroid, founding: [vec], size, first_member_at: datetime,
                blocked: set[article_id], closed: bool}"""
    best, best_sim = None, 0.0
    for ev in candidates:
        if ev.get("closed") or ev.get("size", 0) >= MAX_MEMBERS:
            continue
        if article_id in (ev.get("blocked") or ()):
            continue
        # Measured from the event's FIRST article, not its last: chaining on
        # the last member let a week of daily market reports become one
        # "event" (replay of 1,950 live articles, 2026-10-03). Stories that
        # run for days belong to containers (scheduled/wave/desk).
        first = ev.get("first_member_at")
        if first and abs((published - first).total_seconds()) > JOIN_WINDOW_H * 3600:
            continue
        sim = cosine(vec, ev.get("centroid") or {})
        if sim < T_JOIN:
            continue
        if max((cosine(vec, f) for f in ev.get("founding") or []), default=0.0) < T_FOUND:
            continue
        if sim > best_sim:
            best, best_sim = ev["event_id"], sim
    return best


def event_id_for(article_id: str) -> str:
    """Deterministic: re-running a cycle never forks the same founder twice."""
    return f"ev-{article_id}"


def plan_batch(new_articles: list, candidates: list, df: DocFreq) -> tuple:
    """Assign one cycle's new articles, in publish order. Pure: mutates only
    the passed-in df and candidate dicts, returns what to write.

    new_articles: [{article_id, title, description, content, published_at: datetime,
                    publisher}]   (publisher = canonical key)
    candidates:   events as loaded by the service: {event_id, centroid, founding,
                  size, first_member_at, last_member_at, blocked, closed, members}
                  members = [{article_id, title, content, publisher, published_at}]
    returns (assignments, touched): assignments = [{article_id, event_id, vec_terms,
             syndicated_of, syndicated_publisher}], touched = {event_id: event dict}
    """
    by_id = {c["event_id"]: c for c in candidates}
    assignments, touched = [], {}
    for a in sorted(new_articles, key=lambda x: x["published_at"]):
        w = term_weights(a.get("title", ""), a.get("description", ""), a.get("content", ""))
        df.add(w)
        vec = vectorize(w, df)
        brief = {"article_id": a["article_id"], "title": a.get("title", ""),
                 "content": (a.get("content") or "")[:300], "publisher": a["publisher"],
                 "published_at": a["published_at"]}
        eid = choose_event(vec, a["article_id"], a["published_at"], by_id.values()) if vec else None
        syn_of = syn_pub = None
        if eid:
            ev = by_id[eid]
            for mbr in ev.get("members", []):
                if mbr["publisher"] != a["publisher"] and is_syndicated(mbr, brief):
                    syn_of, syn_pub = mbr["article_id"], mbr.get("syndicated_publisher") or mbr["publisher"]
                    break
            ev["centroid"] = merge_centroid(ev.get("centroid") or {}, ev.get("size", 0), vec)
            if len(ev.get("founding", [])) < FOUNDING:
                ev.setdefault("founding", []).append(vec)
            ev["size"] = ev.get("size", 0) + 1
            ev["last_member_at"] = max(ev.get("last_member_at") or a["published_at"], a["published_at"])
            ev.setdefault("members", []).append({**brief, "syndicated_publisher": syn_pub})
        else:
            eid = event_id_for(a["article_id"])
            by_id[eid] = {"event_id": eid, "centroid": vec, "founding": [vec] if vec else [], "size": 1,
                          "first_member_at": a["published_at"], "last_member_at": a["published_at"],
                          "blocked": set(), "closed": False, "members": [{**brief, "syndicated_publisher": None}],
                          "is_new": True}
        touched[eid] = by_id[eid]
        assignments.append({"article_id": a["article_id"], "event_id": eid, "vec_terms": dict(w),
                            "syndicated_of": syn_of, "syndicated_publisher": syn_pub})
    return assignments, touched


def _words(s: str) -> set:
    return {w for w, _ in textutil.tokens(s, stop=frozenset())}


def is_syndicated(a: dict, b: dict) -> bool:
    """b is a reprint of a (wire copy under another masthead): near-identical
    titles, or the same opening of the body text."""
    ta, tb = _words(a.get("title", "")), _words(b.get("title", ""))
    if ta and tb and len(ta & tb) / len(ta | tb) >= 0.8:
        return True
    ca = " ".join((a.get("content") or "").split())[:200].lower()
    cb = " ".join((b.get("content") or "").split())[:200].lower()
    return len(ca) >= 120 and ca == cb


# ── voices, lead ──────────────────────────────────────────────────────────────

def voice(member: dict) -> str:
    """The outlet whose reporting this is: a syndicated copy speaks with the
    original's voice, so ANI reprinted by three papers is one voice."""
    return member.get("syndicated_publisher") or member["publisher"]


def independent_outlets(members: Iterable[dict]) -> list:
    seen, out = set(), []
    for m in sorted(members, key=lambda m: m["published_at"]):
        v = voice(m)
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def pick_lead(members: list, now: datetime, current: Optional[str] = None,
              pinned_until: Optional[datetime] = None, overrepresented: frozenset = frozenset()) -> Optional[str]:
    """D6 + 1C: Desk article › earliest original (non-syndicated) report ›
    skip a publisher that already leads too much of the live window when an
    alternative exists. A current lead is kept while its 4h pin holds (and it
    is still a member), so cards don't reshuffle under the reader."""
    ids = {m["article_id"] for m in members}
    desk = [m for m in members if m.get("origin") == "desk"]
    if desk:
        return min(desk, key=lambda m: m["published_at"])["article_id"]
    if current in ids and pinned_until and now < pinned_until:
        return current
    originals = sorted((m for m in members if not m.get("syndicated_of")), key=lambda m: m["published_at"])
    pool = originals or sorted(members, key=lambda m: m["published_at"])
    if not pool:
        return None
    for m in pool:
        if m["publisher"] not in overrepresented:
            return m["article_id"]
    return pool[0]["article_id"]


# ── status ────────────────────────────────────────────────────────────────────

def _hours(a: datetime, b: datetime) -> float:
    return (a - b).total_seconds() / 3600


def next_status(prev: str, members: list, now: datetime, *, desk_promoted=False, in_container=False,
                scout_flag=False, desk_event=False, hidden=False) -> str:
    """Pure status transition (diagram in the module docstring)."""
    if prev == "closed":
        return "closed"
    if hidden:
        return prev          # the Desk hid it: never displayed, status frozen
    if not members:
        return "closed"
    last_any = max(m["published_at"] for m in members)
    if _hours(now, last_any) >= CLOSE_AFTER_H:
        return "closed"
    # first report of each independent voice
    firsts: dict = {}
    for m in sorted(members, key=lambda m: m["published_at"]):
        firsts.setdefault(voice(m), m["published_at"])
    voices_recent = {v: t for v, t in firsts.items() if _hours(now, t) <= DEVELOPING_WINDOW_H}
    last_independent = max(firsts.values())
    settle_h = SETTLE_AFTER_DESK_H if desk_event else SETTLE_AFTER_H

    if desk_promoted or in_container:
        return "developing" if _hours(now, last_independent) < settle_h or in_container else "settled"
    if prev == "developing":
        return "developing" if _hours(now, last_independent) < settle_h else "settled"
    recent_times = sorted(voices_recent.values())
    if len(recent_times) >= 2 and _hours(recent_times[-1], recent_times[0]) >= DEVELOPING_SPREAD_H:
        return "developing"
    if prev == "settled":
        return "settled"
    if len(firsts) == 1 and scout_flag:
        return "early_report"
    return "forming"


def updates_last_hours(members: list, now: datetime, hours: int = DEVELOPING_WINDOW_H) -> int:
    """Independent reports in the last `hours` (ranks developing events for the cap)."""
    firsts: dict = {}
    for m in sorted(members, key=lambda m: m["published_at"]):
        firsts.setdefault(voice(m), m["published_at"])
    return sum(1 for t in firsts.values() if _hours(now, t) <= hours)


def alarm(label_ratio: float, developing_open: int) -> bool:
    return label_ratio > ALARM_LABEL_RATIO or developing_open > ALARM_OPEN


def lead_pin_until(now: datetime) -> datetime:
    return now + timedelta(hours=LEAD_PIN_H)

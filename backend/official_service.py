"""The Bureau: fetching, AI extraction, storage and health (eng review 1B).

    run_scheduler ── every 10 min by day / 60 min at night (official.tick_every_min)
      └─▶ run_once (lease-locked: one replica at a time)
           for each enabled adapter (OFFICIAL_SOURCES):
             fetch list ──(error / 403 / 429)──▶ state.error, backoff, next tick
               └─▶ parse_list ─▶ new refs only (official_id not stored yet)
                    ├─ ceremonial / SEBI enforcement ─▶ stored as status="filtered" (counts only)
                    └─▶ detail page (PIB, SEBI) ─▶ PDF text (SEBI; S1 limits, worker thread)
                         └─▶ extract (fast model, JSON; retry once) ─▶ verify (E1)
                              └─▶ importance (rules ▸ AI) ─▶ topic ─▶ official_items
    OFFICIAL_MODE: off | shadow (default) | live
      shadow: items live only in `official_items`; readers see nothing.
      live:   (lane L4, after the Desk gate) items move into `articles` with an
              `official` block; until then this module never touches articles.

Nothing here raises into the scheduler: every failure is recorded on the
source's state document and shown on /api/health/official.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional
from urllib.parse import urlparse

import official
from official_sources import ADAPTERS, USER_AGENT

log = logging.getLogger("official")

MODES = ("off", "shadow", "live")
NEW_PER_SOURCE_PER_RUN = 8          # bounds AI calls when a feed backlog appears at once
LLM_DAILY_CAP_DEFAULT = 300
MAX_BYTES = 8 * 1024 * 1024         # S1: pages and PDFs
PDF_MAX_PAGES = 40
PDF_TIMEOUT_S = 20
BACKOFF_MIN = 30                    # after 403 / 429
BODY_CHARS_FOR_AI = 9000
LEASE_S = 15 * 60
MAX_AGE_DAYS = 21                   # never import history older than this (first runs, DGFT, bills)

FAST_MODEL = "claude-haiku-4-5-20251001"

LLMCall = Callable[..., Awaitable[str]]


def mode_from_env() -> str:
    m = (os.environ.get("OFFICIAL_MODE") or "shadow").strip().lower()
    return m if m in MODES else "shadow"


def sources_from_env() -> list:
    raw = os.environ.get("OFFICIAL_SOURCES")
    names = [s.strip() for s in raw.split(",")] if raw else list(ADAPTERS)
    return [n for n in names if n in ADAPTERS]


# ── the AI instructions (product voice + neutrality + strict JSON) ────────────

SYSTEM_PROMPT = """You turn an official Indian government announcement into a short, plain-language item for Chintan's "The Bureau".

Voice (owner's rule): INDULGING (never text-stuffed), SIMPLE (plain words; when money, investing, finance or legal process is involved, add a short everyday comparison), CREATIVE (fresh, vivid, never bureaucratic).

Hard rules:
- Report only what the government or regulator DID or ANNOUNCED: decisions, rules, money, dates, who is affected. Leave out praise, party politics, attacks on opponents and slogans, even if the release contains them. Never take sides.
- Every number, amount, percentage and date you write must appear in the source text. Never compute, convert or estimate a number. If unsure, leave it out.
- "analogy" must contain NO numbers, dates or names. It explains the idea, not the facts. Leave it empty when the item is simple.
- Use Indian conventions (lakh, crore, ₹). Keep the issuer's terms correct (repo rate, circular, notification).
- If the release is ceremonial, a speech with no decision, or an event, say so in "kind" and keep everything brief.

Return ONLY a JSON object, no prose, with these keys:
{
 "kind": one of ["cabinet_decision","policy","circular","notification","scheme","consultation","appointment","data_release","mou","statement","event","ceremonial"],
 "what_changed": one sentence, <= 18 words, plain words, what is new for people,
 "key_number": {"value": "5.25", "unit": "%", "label": "repo rate", "delta": "-0.25"} or null when there is no single headline number,
 "facts": up to 3 very short facts (<= 8 words each), e.g. "From 1 November", "Home and car loans",
 "who": up to 4 groups affected, 1-3 words each,
 "dates": [{"label": "effective", "date": "1 November 2026"}] for effective dates and deadlines only, copied from the source,
 "analogy": one sentence "think of it like" comparison, no numbers or names, or "",
 "sectors": up to 3 sectors (e.g. "Banking", "Agriculture"),
 "summary": 2-3 plain sentences for the detail page,
 "importance": integer 0-10 for how much this matters to an ordinary Indian reader or investor
}"""


def build_user_prompt(*, source_name: str, ministry: str, title: str, published: str, body: str) -> str:
    return (f"Issuer: {source_name}{' / ' + ministry if ministry else ''}\n"
            f"Title: {title}\nPublished: {published or 'unknown'}\n\n"
            f"Source text:\n{(body or '')[:BODY_CHARS_FOR_AI]}")


_JSON_OBJ = re.compile(r"\{.*\}", re.S)


def parse_extraction(text: str) -> Optional[dict]:
    """The model's JSON, or None. Tolerates code fences and stray prose."""
    if not text:
        return None
    m = _JSON_OBJ.search(text)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("what_changed", ""), str):
        return None
    if not isinstance(data.get("facts", []), list) or not isinstance(data.get("dates", []), list):
        return None
    try:
        data["importance"] = max(0, min(10, int(data.get("importance") or 0)))
    except (TypeError, ValueError):
        data["importance"] = None
    kn = data.get("key_number")
    if kn is not None and not isinstance(kn, dict):
        data["key_number"] = None
    return data


# ── fetching (polite: honest UA, 1 request / second / host, size caps) ───────

class FetchError(Exception):
    def __init__(self, kind: str, detail: str = ""):
        super().__init__(f"{kind}: {detail}")
        self.kind = kind          # "network" | "blocked" | "http" | "too_big"
        self.detail = detail


class PoliteFetcher:
    def __init__(self, client=None, min_gap_s: float = 1.0):
        self._client = client
        self._own = client is None
        self._last: dict = {}
        self._gap = min_gap_s
        self._lock = asyncio.Lock()

    async def _ensure(self):
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(timeout=20.0, follow_redirects=True,
                                             headers={"User-Agent": USER_AGENT})

    async def get(self, url: str) -> bytes:
        await self._ensure()
        host = urlparse(url).netloc
        async with self._lock:
            wait = self._gap - (time.monotonic() - self._last.get(host, 0.0))
            if wait > 0:
                await asyncio.sleep(wait)
            self._last[host] = time.monotonic()
        try:
            resp = await self._client.get(url)
        except Exception as e:                       # httpx.HTTPError and friends
            raise FetchError("network", str(e)[:160])
        if resp.status_code in (403, 429):
            raise FetchError("blocked", str(resp.status_code))
        if resp.status_code != 200:
            raise FetchError("http", str(resp.status_code))
        content = resp.content
        if len(content) > MAX_BYTES:
            raise FetchError("too_big", str(len(content)))
        return content

    async def aclose(self):
        if self._own and self._client is not None:
            await self._client.aclose()


_pdf_slots = asyncio.Semaphore(2)    # eng 4A: at most two PDFs at once


def _pdf_text_sync(data: bytes, pages=None) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    n = len(reader.pages)
    picks = [i for i in (pages(n) if pages else range(n)) if 0 <= i < n][:PDF_MAX_PAGES]
    parts = []
    for i in picks:
        try:
            parts.append(reader.pages[i].extract_text() or "")
        except Exception:            # one broken page must not lose the rest
            continue
    return "\n".join(parts)


async def pdf_text(data: bytes, pages=None) -> str:
    """Text of a PDF in a worker thread, two at a time, 20 s budget, at most
    40 pages (`pages(n)` picks which). Empty string for scans or failures
    (the item falls back to title-only)."""
    if not data or len(data) > MAX_BYTES or not data[:5] == b"%PDF-":
        return ""
    async with _pdf_slots:
        try:
            text = await asyncio.wait_for(asyncio.to_thread(_pdf_text_sync, data, pages), PDF_TIMEOUT_S)
        except (asyncio.TimeoutError, Exception) as e:
            log.warning(f"official: PDF text failed: {type(e).__name__}: {str(e)[:120]}")
            return ""
    text = re.sub(r"Page \d+ of \d+", " ", text)
    return re.sub(r"[ \t]+", " ", text).strip()


# ── the service ───────────────────────────────────────────────────────────────

class OfficialService:
    def __init__(self, db, llm: LLMCall, *, fetcher: Optional[PoliteFetcher] = None,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 classify_topic: Callable = None, llm_daily_cap: Optional[int] = None,
                 fast_model: str = FAST_MODEL, mode: Callable[[], str] = mode_from_env,
                 sources: Callable[[], list] = sources_from_env):
        self.db = db
        self.llm = llm
        self.fetcher = fetcher or PoliteFetcher()
        self.now = now
        self.classify_topic = classify_topic or (lambda title, body: ("Politics", None))
        self.llm_cap = llm_daily_cap or int(os.environ.get("OFFICIAL_LLM_DAILY_CAP") or LLM_DAILY_CAP_DEFAULT)
        self.fast_model = fast_model
        self.mode = mode
        self.sources = sources

    async def ensure_indexes(self):
        await self.db.official_items.create_index("official_id", unique=True)
        await self.db.official_items.create_index([("status", 1), ("published_at", -1)])
        await self.db.official_items.create_index([("source", 1), ("fetched_at", -1)])
        await self.db.official_items.create_index("refs")

    # ── state ────────────────────────────────────────────────────────────────
    async def _state(self, name: str) -> dict:
        return await self.db.official_state.find_one({"_id": f"src:{name}"}) or {}

    async def _set_state(self, name: str, **fields):
        await self.db.official_state.update_one({"_id": f"src:{name}"}, {"$set": fields}, upsert=True)

    async def _take_llm(self) -> bool:
        day = (self.now() + timedelta(minutes=official.IST_OFFSET_MIN)).date().isoformat()
        doc = await self.db.official_state.find_one_and_update(
            {"_id": f"llm:{day}"}, {"$inc": {"n": 1}}, upsert=True, return_document=True)
        return (doc or {}).get("n", 0) <= self.llm_cap

    async def _lease(self) -> bool:
        now = self.now()
        try:
            res = await self.db.official_state.update_one(
                {"_id": "lease", "$or": [{"until": {"$lt": now.isoformat()}}, {"until": {"$exists": False}}]},
                {"$set": {"until": (now + timedelta(seconds=LEASE_S)).isoformat()}}, upsert=True)
        except Exception:            # duplicate key: another replica holds it
            return False
        return bool(res.modified_count or res.upserted_id)

    async def _release(self):
        await self.db.official_state.update_one({"_id": "lease"}, {"$set": {"until": "1970-01-01T00:00:00"}})

    # ── one cycle ────────────────────────────────────────────────────────────
    async def run_once(self) -> dict:
        mode = self.mode()
        summary = {"mode": mode, "sources": {}}
        if mode == "off":
            return summary
        if not await self._lease():
            summary["skipped"] = "lease held"
            return summary
        try:
            for name in self.sources():
                summary["sources"][name] = await self._run_source(ADAPTERS[name])
        finally:
            await self._release()
        return summary

    async def _run_source(self, adapter) -> dict:
        now = self.now()
        st = await self._state(adapter.name)
        out = {"new": 0, "filtered": 0, "kept": 0, "error": None}
        blocked_until = st.get("blocked_until")
        if blocked_until and blocked_until > now.isoformat():
            out["error"] = "backing off"
            return out
        try:
            raw = await self.fetcher.get(adapter.list_url)
            refs = adapter.parse_list(raw.decode("utf-8", errors="replace"))
        except FetchError as e:
            fields = {"last_error": f"list {e.kind}: {e.detail}", "last_error_at": now.isoformat(),
                      "error_streak": st.get("error_streak", 0) + 1}
            if e.kind == "blocked":
                fields["blocked_until"] = (now + timedelta(minutes=BACKOFF_MIN)).isoformat()
            await self._set_state(adapter.name, **fields)
            out["error"] = fields["last_error"]
            return out
        except Exception as e:                      # malformed XML (defusedxml raises on attacks too)
            await self._set_state(adapter.name, last_error=f"parse: {type(e).__name__}: {str(e)[:120]}",
                                  last_error_at=now.isoformat(), error_streak=st.get("error_streak", 0) + 1,
                                  parse_error_streak=st.get("parse_error_streak", 0) + 1)
            out["error"] = "parse"
            return out

        oldest = (now - timedelta(days=MAX_AGE_DAYS)).isoformat()
        refs = [r for r in refs if not r.published_at or r.published_at >= oldest]
        ids = [official.official_id(r.url) for r in refs]
        known = {d["official_id"] async for d in self.db.official_items.find(
            {"official_id": {"$in": ids}}, {"_id": 0, "official_id": 1})}
        fresh = [r for r in refs if official.official_id(r.url) not in known]
        for ref in fresh[:NEW_PER_SOURCE_PER_RUN]:
            try:
                kept = await self._process(adapter, ref)
            except Exception as e:                  # one bad item never stops the source
                log.error(f"official {adapter.name}: item failed {ref.url}: {type(e).__name__}: {e}")
                continue
            out["new"] += 1
            out["kept" if kept else "filtered"] += 1

        fields = {"last_ok": now.isoformat(), "list_size": len(refs), "error_streak": 0,
                  "parse_error_streak": 0 if refs else st.get("parse_error_streak", 0) + 1,
                  "blocked_until": None}
        if out["new"]:
            fields["last_new_at"] = now.isoformat()
        await self._set_state(adapter.name, **fields)
        return out

    async def _process(self, adapter, ref: official.Ref) -> bool:
        """Store one new ref. Returns True when it becomes a reader-facing item."""
        now = self.now()
        oid = official.official_id(ref.url)
        kind = official.classify_kind(adapter.name, ref.title, url=ref.url)
        if kind in official.HIDDEN_KINDS:
            await self.db.official_items.update_one(
                {"official_id": oid},
                {"$setOnInsert": {"official_id": oid, "source": adapter.name, "source_url": ref.url,
                                  "title": ref.title, "kind": kind, "status": "filtered",
                                  "fetched_at": now.isoformat(), "published_at": ref.published_at or now.isoformat()}},
                upsert=True)
            return False

        detail = {}
        body = ref.summary
        if adapter.needs_detail(ref) and adapter.detail_is_pdf:
            try:
                text = await pdf_text(await self.fetcher.get(adapter.detail_url(ref)), adapter.pdf_pages)
            except FetchError as e:
                log.warning(f"official {adapter.name}: pdf {e} for {ref.url}")
                return False                         # not stored: retried next tick
            if text:
                body = adapter.pdf_body(text)
        elif adapter.needs_detail(ref):
            try:
                detail = adapter.parse_detail((await self.fetcher.get(adapter.detail_url(ref))).decode("utf-8", errors="replace"))
            except FetchError as e:
                log.warning(f"official {adapter.name}: detail {e} for {ref.url}")
                return False                         # not stored: retried next tick
            body = detail.get("body") or body
            if detail.get("pdf_url"):
                try:
                    text = await pdf_text(await self.fetcher.get(detail["pdf_url"]))
                except FetchError as e:
                    log.warning(f"official {adapter.name}: pdf {e}")
                    text = ""
                if text:
                    body = text
        # Embargoed releases (MoSPI) wait, unstored, until the embargo lifts.
        lift = official.embargo_until(body)
        if lift and lift > now:
            log.info(f"official {adapter.name}: embargoed till {lift.isoformat()}: {ref.title[:60]}")
            return False
        ministry = detail.get("ministry") or ""
        title = detail.get("title") or ref.title
        kind = official.classify_kind(adapter.name, title, ministry, url=ref.url)
        if kind in official.HIDDEN_KINDS:
            ext, dropped = {}, []
        else:
            ext, dropped = await self._extract(adapter, ministry, title, detail.get("published_at") or ref.published_at, body)
            ai_kind = (ext or {}).get("kind")
            # The AI may only move an item between reader-facing kinds, or mark
            # a release ceremonial; it can never promote noise into a decision.
            # Bill stages come from Parliament's own records, so they stay bills.
            if (ai_kind in official.KINDS and kind not in ("cabinet_decision", "bill")
                    and ai_kind not in ("enforcement", "bill")):
                kind = ai_kind
        issuer_key = "cabinet" if kind == "cabinet_decision" else adapter.issuer_key
        level = official.importance(adapter.name, kind, title, (ext or {}).get("importance"))
        item = official.build_item(ref=ref, detail={**detail, "body": body, "title": title}, kind=kind,
                                   ext=ext or {}, dropped=dropped, importance_level=level,
                                   topic=self.classify_topic(title, body), now=now,
                                   source_name=adapter.source_name, issuer_key=issuer_key)
        if kind in official.HIDDEN_KINDS:
            item["status"] = "filtered"
        if not body.strip():
            item["title_only"] = True
        await self.db.official_items.update_one({"official_id": item["official_id"]},
                                                {"$setOnInsert": item}, upsert=True)
        return item["status"] != "filtered"

    async def _extract(self, adapter, ministry: str, title: str, published: Optional[str], body: str):
        if not body.strip():
            return {}, ["no_text"]
        prompt = build_user_prompt(source_name=adapter.source_name, ministry=ministry, title=title,
                                   published=published or "", body=body)
        for attempt in (1, 2):
            if not await self._take_llm():
                return {}, ["llm_cap"]
            try:
                text = await self.llm(SYSTEM_PROMPT, prompt, max_tokens=900, model=self.fast_model)
            except Exception as e:
                log.warning(f"official {adapter.name}: extraction call failed: {type(e).__name__}: {str(e)[:120]}")
                text = ""
            ext = parse_extraction(text)
            if ext is not None:
                return official.verify_extraction(ext, f"{title}\n{body}")
        return {}, ["bad_json"]

    # ── health ───────────────────────────────────────────────────────────────
    async def health(self) -> dict:
        now = self.now()
        since = (now - timedelta(hours=24)).isoformat()
        day = (now + timedelta(minutes=official.IST_OFFSET_MIN)).date().isoformat()
        llm = await self.db.official_state.find_one({"_id": f"llm:{day}"}) or {}
        out = {"mode": self.mode(), "sources": {}, "llm_today": llm.get("n", 0), "llm_cap": self.llm_cap,
               "alarm": False}
        for name in self.sources():
            a = ADAPTERS[name]
            st = await self._state(name)
            kept = await self.db.official_items.count_documents(
                {"source": name, "status": {"$ne": "filtered"}, "fetched_at": {"$gte": since}})
            filtered = await self.db.official_items.count_documents(
                {"source": name, "status": "filtered", "fetched_at": {"$gte": since}})
            last_new = st.get("last_new_at")
            silent = official.silence_alarm(datetime.fromisoformat(last_new) if last_new else None, now,
                                            a.expected_gap_h)
            broken = st.get("error_streak", 0) >= 6 or st.get("parse_error_streak", 0) >= 3
            out["sources"][name] = {
                "last_ok": st.get("last_ok"), "last_new_at": last_new, "last_error": st.get("last_error"),
                "error_streak": st.get("error_streak", 0), "kept_24h": kept, "filtered_24h": filtered,
                "silent": silent, "broken": broken, "blocked_until": st.get("blocked_until"),
            }
            out["alarm"] = out["alarm"] or silent or broken
        return out


# ── Desk quality gate (CEO T1): the owner checks hidden items ────────────────

GATE = {"facts": 0.95, "readable": 0.85, "min_checked": 30}
IMPORTANCE_LEVELS = ("never", "low", "normal", "high")
_REVIEW_FIELDS = {"_id": 0}


async def review_queue(db, limit: int = 10) -> list:
    """Hidden, reader-facing items the owner hasn't checked yet: important
    first, then newest, never more than half from one source."""
    done = {d["official_id"] async for d in db.official_labels.find({}, {"_id": 0, "official_id": 1})}
    rank = {"high": 0, "normal": 1, "low": 2, "never": 3}
    pool = [d async for d in db.official_items.find(
        {"status": "shadow", "official_id": {"$nin": list(done)}}, _REVIEW_FIELDS
    ).sort("fetched_at", -1).limit(200)]
    pool.sort(key=lambda d: (rank.get(d.get("importance_override") or d.get("importance"), 4),
                             d.get("title_only", False)))
    out, per_source = [], {}
    cap = max(1, limit // 2)
    for d in pool:
        if per_source.get(d.get("source"), 0) >= cap:
            continue
        per_source[d.get("source")] = per_source.get(d.get("source"), 0) + 1
        out.append(d)
        if len(out) >= limit:
            break
    return out


async def record_label(db, official_id: str, facts_ok: bool, readable: bool, note: str, by: str,
                       now: datetime) -> None:
    item = await db.official_items.find_one({"official_id": official_id}, {"_id": 0, "source": 1, "status": 1})
    if not item or item.get("status") == "filtered":
        raise ValueError("unknown item")
    await db.official_labels.update_one({"official_id": official_id}, {"$set": {
        "official_id": official_id, "source": item.get("source"), "facts_ok": bool(facts_ok),
        "readable": bool(readable), "note": (note or "")[:500], "by": by, "at": now.isoformat()}}, upsert=True)


async def review_summary(db) -> dict:
    rows = [r async for r in db.official_labels.find({}, {"_id": 0})]
    n = len(rows)

    def rate(key, subset):
        return round(sum(1 for r in subset if r.get(key)) / len(subset), 3) if subset else None

    by_source = {}
    for r in rows:
        by_source.setdefault(r.get("source") or "?", []).append(r)
    facts, readable = rate("facts_ok", rows), rate("readable", rows)
    passed = (n >= GATE["min_checked"] and facts is not None and readable is not None
              and facts >= GATE["facts"] and readable >= GATE["readable"])
    return {"checked": n, "facts_ok": facts, "readable": readable, "gate": GATE, "passed": passed,
            "by_source": {k: {"checked": len(v), "facts_ok": rate("facts_ok", v), "readable": rate("readable", v)}
                          for k, v in sorted(by_source.items())},
            "notes": [{"official_id": r["official_id"], "note": r["note"]} for r in rows if r.get("note")][-10:]}


async def set_importance(db, official_id: str, level: str) -> bool:
    if level not in IMPORTANCE_LEVELS:
        raise ValueError("bad level")
    res = await db.official_items.update_one({"official_id": official_id},
                                             {"$set": {"importance_override": level}})
    return bool(res.matched_count)


# ── readers (app 1.14): the chip feed and the item page ──────────────────────
#
#   who sees what
#     OFFICIAL_MODE=live    everyone, admins included, sees the reader view;
#                           items the Desk hasn't cleared stay hidden (needs_desk,
#                           importance "never", facts marked wrong). Admins check
#                           flagged items on the Desk, not in the app.
#     OFFICIAL_MODE=shadow  Desk admins only ("preview"), everything kept, flagged
#     OFFICIAL_MODE=off     nobody
#   Items are read from official_items in both modes; lane L4 decides whether
#   they are also copied into `articles` for the "All" feed.

LENSES = {  # sub-pill key -> issuer_key (the app shows these labels)
    "cabinet": "cabinet", "rbi": "rbi", "sebi": "sebi", "ministries": "pib",
    "trade": "dgft", "data": "mospi", "parliament": "parliament",
}
READER_LIMIT_MAX = 30
_READER_FIELDS = {"_id": 0, "official_id": 1, "source": 1, "source_name": 1, "source_url": 1, "issuer": 1,
                  "issuer_key": 1, "ministry": 1, "kind": 1, "title": 1, "published_at": 1, "what_changed": 1,
                  "key_number": 1, "facts": 1, "who": 1, "dates": 1, "analogy": 1, "sectors": 1, "summary": 1,
                  "importance": 1, "importance_override": 1, "title_only": 1, "needs_desk": 1, "refs": 1,
                  "category": 1, "subcategory": 1}


def reader_access(mode: str, is_admin: bool) -> Optional[str]:
    """"public", "preview" (shadow, admins) or None (hidden)."""
    if mode == "live":
        return "public"
    if mode == "shadow" and is_admin:
        return "preview"
    return None


async def _hidden_ids(db) -> list:
    return [d["official_id"] async for d in db.official_labels.find({"facts_ok": False}, {"_id": 0, "official_id": 1})]


async def _reader_query(db, access: str, extra: dict) -> dict:
    q = {"status": {"$ne": "filtered"}, **extra}
    if access == "public":
        q["needs_desk"] = {"$ne": True}
        q["importance"] = {"$ne": "never"}
        q["importance_override"] = {"$ne": "never"}
        hidden = await _hidden_ids(db)
        if hidden:
            # $and, so a caller adding its own official_id filter can't undo this one.
            q["$and"] = [{"official_id": {"$nin": hidden}}]
    return q


def _reader_item(d: dict, access: str) -> dict:
    d = dict(d)
    d["importance"] = d.pop("importance_override", None) or d.get("importance")
    if access != "preview":
        d.pop("needs_desk", None)
    return d


def _ist_day(now: datetime) -> str:
    return (now + timedelta(minutes=official.IST_OFFSET_MIN)).date().isoformat()


async def reader_feed(db, *, access: str, lens: Optional[str], before: Optional[str], limit: int,
                      now: datetime, health: Optional[dict] = None) -> dict:
    extra = {}
    if lens in LENSES:
        extra["issuer_key"] = LENSES[lens]
    q = await _reader_query(db, access, extra)
    page_q = {**q, "published_at": {"$lt": before}} if before else q
    limit = max(1, min(limit, READER_LIMIT_MAX))
    rows = await db.official_items.find(page_q, _READER_FIELDS).sort("published_at", -1).limit(limit).to_list(limit)
    # "Today" is the reader's day in India, counted for the whole lens, not one page.
    start = datetime.fromisoformat(_ist_day(now)).replace(tzinfo=timezone.utc) - timedelta(minutes=official.IST_OFFSET_MIN)
    today = await db.official_items.count_documents({**q, "published_at": {"$gte": start.isoformat()}})
    delayed = sorted({ADAPTERS[n].source_name for n, s in ((health or {}).get("sources") or {}).items()
                      if s.get("broken") and n in ADAPTERS})
    return {"items": [_reader_item(r, access) for r in rows], "today_count": today,
            "has_more": len(rows) == limit, "delayed": delayed, "preview": access == "preview"}


async def reader_item(db, official_id: str, *, access: str) -> Optional[dict]:
    q = await _reader_query(db, access, {})
    doc = await db.official_items.find_one({**q, "official_id": official_id}, _READER_FIELDS)
    if not doc:
        return None
    item = _reader_item(doc, access)
    earlier = []
    refs = [r for r in (doc.get("refs") or []) if r]
    if refs:
        rows = await db.official_items.find(
            {**q, "refs": {"$in": refs}, "official_id": {"$ne": official_id}},
            {"_id": 0, "official_id": 1, "title": 1, "what_changed": 1, "published_at": 1, "issuer": 1, "kind": 1},
        ).sort("published_at", -1).limit(6).to_list(6)
        earlier = rows
    item["earlier"] = earlier
    return item


async def run_scheduler(svc: OfficialService, logger=None):
    """Forever: one cycle, then wait 10 min by day / 60 min at night."""
    lg = logger or log
    await asyncio.sleep(45)                     # let startup migrations settle
    while True:
        try:
            summary = await svc.run_once()
            news = {k: v for k, v in summary.get("sources", {}).items() if v.get("new") or v.get("error")}
            if news:
                lg.info(f"Bureau: {summary['mode']} {news}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            lg.error(f"Bureau cycle failed: {type(e).__name__}: {e}")
        await asyncio.sleep(official.tick_every_min(svc.now()) * 60)

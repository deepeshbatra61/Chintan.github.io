"""News v2 events: the Mongo side of events.py. Called once per ingest cycle
(server._run_ingest_cycle_body, step 11) and never from a request handler.

    run_cycle
      1. mode off ─▶ return             EVENTS_MODE env: off | shadow | live
      2. cache: DocFreq over the 72h window (built from articles.ev_terms once,
         then updated as articles arrive / age out)
      3. unassigned articles (≤72h, no event_id) ─┐
         candidate events (first article ≤36h)  ─┴─▶ to_thread(events.plan_batch)
      4. write article.event_id (+ publisher, syndication, ev_terms)
      5. upsert touched events; recompute_event() for touched + developing ones
      6. close events quiet for 36h; store metrics + alarm in app_meta events_state

    Membership truth is articles.event_id; events.article_ids/members are derived.
    recompute_event is the ONLY writer of lead / status / hidden fields.
    Shadow mode writes events + article assignment fields only; it never sets
    event_hidden or rewrites categories, so the feed is untouched.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import random
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional

import categories as C
import events as E
import textutil
import publishers as P

logger = logging.getLogger(__name__)

WINDOW_H = 72
BATCH_LIMIT = 400              # first shadow cycle backfills 72h in a few cycles
OVERREP_SHARE = 0.20           # a publisher leading >20% of live events yields the lead when it can
MODES = ("off", "shadow", "live")

_cache: dict = {"df": None, "window": {}}   # window: article_id -> (published dt, terms)


def current_mode() -> str:
    m = (os.environ.get("EVENTS_MODE") or "shadow").strip().lower()
    return m if m in MODES else "shadow"


def _dt(v) -> Optional[datetime]:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str) and v:
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).isoformat()


def reset_cache() -> None:
    _cache["df"], _cache["window"] = None, {}


async def _ensure_cache(db, now: datetime) -> E.DocFreq:
    """Build the DocFreq once per process from stored ev_terms, then age out
    articles older than the window. Rebuilt == incremental is tested."""
    if _cache["df"] is None:
        df, window = E.DocFreq(), {}
        since = _iso(now - timedelta(hours=WINDOW_H))
        async for a in db.articles.find({"ev_terms": {"$exists": True}, "published_at": {"$gte": since}},
                                        {"_id": 0, "article_id": 1, "published_at": 1, "ev_terms": 1}):
            terms = a.get("ev_terms") or {}
            df.add(terms)
            window[a["article_id"]] = (_dt(a["published_at"]) or now, terms)
        _cache["df"], _cache["window"] = df, window
    df, window = _cache["df"], _cache["window"]
    cutoff = now - timedelta(hours=WINDOW_H)
    for aid in [k for k, (pub, _) in window.items() if pub < cutoff]:
        df.remove(window.pop(aid)[1])
    return df


def _member_from_doc(doc: dict) -> dict:
    return {**doc, "published_at": _dt(doc.get("published_at"))}


async def _load_candidates(db, now: datetime) -> list:
    since = _iso(now - timedelta(hours=E.JOIN_WINDOW_H))
    out = []
    async for ev in db.events.find({"first_member_at": {"$gte": since}, "status": {"$ne": "closed"}}, {"_id": 0}):
        out.append({
            "event_id": ev["event_id"], "centroid": ev.get("centroid") or {}, "founding": ev.get("founding") or [],
            "size": ev.get("size", 0), "first_member_at": _dt(ev.get("first_member_at")),
            "last_member_at": _dt(ev.get("last_member_at")),
            "blocked": set((ev.get("desk") or {}).get("blocked_members") or []),
            "closed": bool((ev.get("desk") or {}).get("hidden")),
            "members": [_member_from_doc(m) for m in ev.get("members") or []],
        })
    return out


FOLLOW_NEW_HEADLINE = 0.6      # word overlap below this = a new development, not a copy (D8)


def _overlap(a: str, b: str) -> float:
    wa = {w for w, _ in textutil.tokens(a, stop=frozenset())}
    wb = {w for w, _ in textutil.tokens(b, stop=frozenset())}
    return len(wa & wb) / len(wa | wb) if wa and wb else 0.0


async def run_cycle(db, now: Optional[datetime] = None, mode: Optional[str] = None,
                    batch_limit: int = BATCH_LIMIT, notify=None) -> dict:
    """One events pass. Returns the metrics it stored (also for tests).
    notify(story_id=, story_title=, headline=, outlet=) is awaited once per
    developing event that gained a new independent outlet with a new headline
    (follow pushes; push_service.send_follow_update)."""
    mode = mode or current_mode()
    if mode == "off":
        return {"mode": "off"}
    now = now or datetime.now(timezone.utc)
    t0 = time.perf_counter()
    df = await _ensure_cache(db, now)

    since = _iso(now - timedelta(hours=WINDOW_H))
    raw = await db.articles.find(
        {"event_id": {"$exists": False}, "published_at": {"$gte": since}, "desk_hidden": {"$ne": True}},
        {"_id": 0, "article_id": 1, "title": 1, "description": 1, "content": 1, "published_at": 1,
         "source": 1, "url": 1, "origin": 1, "gnews_category": 1, "category": 1, "subcategory": 1},
    ).sort("published_at", 1).limit(batch_limit).to_list(batch_limit)
    prepared, pubs, taxo = [], {}, {}
    for a in raw:
        pub_at = _dt(a.get("published_at"))
        if not pub_at or not a.get("title"):
            continue
        p = P.canonical(a.get("source") or "", a.get("url") or "")
        if a.get("origin") == "desk":
            p = P.Publisher("chintan.news", "Chintan Desk", "CD", "national", "national")
        pubs[a["article_id"]] = p
        body = f"{a.get('description') or ''} {(a.get('content') or '')[:600]}"
        if a.get("origin") == "desk":         # the Desk chose its category; keep it
            cat2, sub2 = a.get("category") or "Politics", a.get("subcategory")
        else:
            cat2, sub2 = C.classify(a.get("title", ""), body, a.get("gnews_category"))
        taxo[a["article_id"]] = (cat2, sub2, C.detect_state(a.get("title", ""), body, p.state))
        prepared.append({"article_id": a["article_id"], "title": a.get("title", ""),
                         "description": a.get("description", ""), "content": a.get("content", ""),
                         "published_at": pub_at, "publisher": p.key})

    candidates = await _load_candidates(db, now)
    before = {c["event_id"]: ({m.get("syndicated_publisher") or m["publisher"] for m in c["members"]},
                              [m.get("title", "") for m in c["members"]]) for c in candidates}
    assignments, touched = await asyncio.to_thread(E.plan_batch, prepared, candidates, df)
    developments: dict = {}       # event_id -> the newest genuinely new report this cycle
    for asg in assignments:
        prior = before.get(asg["event_id"])
        if not prior or asg["syndicated_of"]:
            continue
        art = next(x for x in prepared if x["article_id"] == asg["article_id"])
        voices, titles = prior
        if art["publisher"] in voices or any(_overlap(art["title"], t) >= FOLLOW_NEW_HEADLINE for t in titles):
            continue
        cur = developments.get(asg["event_id"])
        if not cur or art["published_at"] > cur["published_at"]:
            developments[asg["event_id"]] = {**art, "outlet": pubs[art["article_id"]].name}

    for asg in assignments:
        p = pubs[asg["article_id"]]
        published = next(x["published_at"] for x in prepared if x["article_id"] == asg["article_id"])
        _cache["window"][asg["article_id"]] = (published, asg["vec_terms"])
        await db.articles.update_one({"article_id": asg["article_id"]}, {"$set": {
            "event_id": asg["event_id"], "ev_terms": asg["vec_terms"],
            "publisher": p.key, "publisher_name": p.name, "publisher_type": p.type,
            "publisher_group": p.group, "publisher_state": p.state,
            "syndicated_of": asg["syndicated_of"], "syndicated_publisher": asg["syndicated_publisher"],
            "category_v2": taxo[asg["article_id"]][0], "subcategory_v2": taxo[asg["article_id"]][1],
            "state": taxo[asg["article_id"]][2],
        }})

    for eid, ev in touched.items():
        await db.events.update_one({"event_id": eid}, {
            "$set": {
                "centroid": ev["centroid"], "founding": ev["founding"], "size": ev["size"],
                "first_member_at": _iso(ev["first_member_at"]), "last_member_at": _iso(ev["last_member_at"]),
                "members": [{**m, "published_at": _iso(m["published_at"])} for m in ev["members"]][-E.MAX_MEMBERS:],
                "updated_at": _iso(now),
            },
            "$setOnInsert": {"event_id": eid, "status": "forming", "created_at": _iso(now)},
        }, upsert=True)

    overrep = await _overrepresented(db, now)
    scout_ids = await _scout_article_ids(db)
    developing = [d["event_id"] async for d in db.events.find({"status": {"$in": ["developing", "early_report"]}},
                                                             {"_id": 0, "event_id": 1})]
    for eid in set(touched) | set(developing):
        await recompute_event(db, eid, now, mode=mode, overrepresented=overrep, scout_ids=scout_ids)

    if notify:
        for eid, art in developments.items():
            ev = await db.events.find_one({"event_id": eid}, {"_id": 0, "status": 1, "lead_article_id": 1})
            if not ev or ev.get("status") != "developing" or not await db.follows.find_one({"story_id": eid}):
                continue
            lead = await db.articles.find_one({"article_id": ev.get("lead_article_id")}, {"_id": 0, "title": 1}) or {}
            try:
                await notify(story_id=eid, story_title=lead.get("title") or art["title"],
                             headline=art["title"], outlet=art["outlet"])
            except Exception as e:  # noqa: BLE001 -- a push failure must not cost the cycle
                logger.warning(f"Follow push for {eid} failed: {e}")

    closed = await db.events.update_many(
        {"status": {"$ne": "closed"}, "last_member_at": {"$lt": _iso(now - timedelta(hours=E.CLOSE_AFTER_H))}},
        {"$set": {"status": "closed", "updated_at": _iso(now)}})

    await backfill_taxonomy(db, now)
    metrics = await _metrics(db, now, mode)
    metrics.update(cluster_ms=round((time.perf_counter() - t0) * 1000), assigned=len(assignments),
                   new_events=sum(1 for e in touched.values() if e.get("is_new")), closed=closed.modified_count)
    await db.app_meta.update_one({"_id": "events_state"}, {"$set": metrics}, upsert=True)
    if metrics["alarm"]:
        logger.error(f"Events alarm: label ratio {metrics['developing_label_ratio']}, open {metrics['developing_open']}")
    logger.info(f"Events ({mode}): {metrics['assigned']} assigned, {metrics['new_events']} new, "
                f"{metrics['developing_open']} developing, {metrics['cluster_ms']}ms")
    return metrics


async def notify_container_follows(db, notify, now: Optional[datetime] = None) -> int:
    """Follow pings for the Developing stories readers can follow today (the
    developing_stories containers, ids without "ev-"). run_cycle only pings
    for events, so before this a followed container never sent anything.

        per followed story, a watch doc remembers the article ids already seen
        (the first look only records, so nothing old is announced)
        new ids ─▶ newest article whose headline is new (overlap < 0.6 with the
                   story's recent headlines) ─▶ notify once per story per cycle;
                   push_service holds it for quiet hours / gaps / daily caps
    Returns how many stories were pinged."""
    now = now or datetime.now(timezone.utc)
    pinged = 0
    story_ids = {f["story_id"] for f in await db.follows.find({}, {"_id": 0, "story_id": 1}).to_list(5000)}
    for sid in sorted(s for s in story_ids if s and not s.startswith("ev-")):
        st = await db.developing_stories.find_one({"story_id": sid}, {"_id": 0, "title": 1, "article_ids": 1,
                                                                      "is_active": 1, "member_kinds": 1})
        if not st or not st.get("is_active"):
            continue
        ids = list(dict.fromkeys(st.get("article_ids") or []))
        watch = await db.follow_watch.find_one({"story_id": sid})
        if watch is None:
            await db.follow_watch.insert_one({"story_id": sid, "seen_ids": ids, "updated_at": _iso(now)})
            continue
        seen = set(watch.get("seen_ids") or [])
        new_ids = [i for i in ids if i not in seen]
        if not new_ids:
            continue
        await db.follow_watch.update_one({"story_id": sid},
                                         {"$set": {"seen_ids": ids[-500:], "updated_at": _iso(now)}})
        fields = {"_id": 0, "article_id": 1, "title": 1, "source": 1, "published_at": 1}
        fresh = await db.articles.find({"article_id": {"$in": new_ids}}, fields).to_list(len(new_ids))
        older = await db.articles.find({"article_id": {"$in": [i for i in ids if i in seen][-20:]}},
                                       {"_id": 0, "title": 1}).to_list(20)
        titles = [o.get("title") or "" for o in older]
        kinds = st.get("member_kinds") or {}
        fresh = [a for a in fresh if a.get("title")
                 and kinds.get(a["article_id"], "development") == "development"     # never ping a tribute
                 and not any(_overlap(a["title"], t) >= FOLLOW_NEW_HEADLINE for t in titles)]
        if not fresh:
            continue
        art = max(fresh, key=lambda a: a.get("published_at") or "")
        try:
            await notify(story_id=sid, story_title=st.get("title") or art["title"], headline=art["title"],
                         outlet=art.get("source") or "")
            pinged += 1
        except Exception as e:  # noqa: BLE001 -- a push failure must not cost the cycle
            logger.warning(f"Follow push for {sid} failed: {e}")
    return pinged


async def backfill_taxonomy(db, now: datetime, limit: int = 300) -> int:
    """Give older articles (the feed shows 7 days; events only covers 72h) their
    v2 category and state, a few hundred per cycle, so 1.13's Health / sub /
    States filters see the whole window."""
    since = _iso(now - timedelta(days=7))
    n = 0
    async for a in db.articles.find(
            {"category_v2": {"$exists": False}, "published_at": {"$gte": since}, "origin": {"$ne": "desk"}},
            {"_id": 0, "article_id": 1, "title": 1, "description": 1, "content": 1, "url": 1, "source": 1,
             "gnews_category": 1}).limit(limit):
        body = f"{a.get('description') or ''} {(a.get('content') or '')[:600]}"
        cat2, sub2 = C.classify(a.get("title", ""), body, a.get("gnews_category"))
        st = C.detect_state(a.get("title", ""), body, P.canonical(a.get("source") or "", a.get("url") or "").state)
        await db.articles.update_one({"article_id": a["article_id"]},
                                     {"$set": {"category_v2": cat2, "subcategory_v2": sub2, "state": st}})
        n += 1
    return n


async def _overrepresented(db, now: datetime) -> frozenset:
    since = _iso(now - timedelta(hours=24))
    leads = Counter()
    async for ev in db.events.find({"last_member_at": {"$gte": since}, "size": {"$gte": 2},
                                    "lead_publisher": {"$exists": True}}, {"_id": 0, "lead_publisher": 1}):
        leads[ev["lead_publisher"]] += 1
    total = sum(leads.values())
    if total < 10:
        return frozenset()
    return frozenset(p for p, n in leads.items() if n / total > OVERREP_SHARE)


async def _scout_article_ids(db) -> set:
    ids: set = set()
    async for s in db.developing_stories.find({"kind": "scout", "is_active": True}, {"_id": 0, "article_ids": 1}):
        ids.update(s.get("article_ids") or [])
    return ids


def _vote(values: list, lead_value):
    c = Counter(v for v in values if v)
    if not c:
        return lead_value
    top = c.most_common()
    best_n = top[0][1]
    tied = [v for v, n in top if n == best_n]
    return lead_value if lead_value in tied else tied[0]


async def recompute_event(db, event_id: str, now: datetime, *, mode: str = "shadow",
                          overrepresented: frozenset = frozenset(), scout_ids: Optional[set] = None) -> Optional[dict]:
    """The only writer of an event's derived fields (lead, status, outlets,
    vote) and, in live mode, of its members' hidden/lead fields. Call it after
    every membership change, including every Desk action."""
    ev = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not ev:
        return None
    docs = await db.articles.find(
        # An unpublished Desk article is no longer part of anything (desk_routes.unpublish).
        {"event_id": event_id, "desk_hidden": {"$ne": True}},
        {"_id": 0, "article_id": 1, "publisher": 1, "publisher_group": 1, "published_at": 1, "origin": 1,
         "syndicated_of": 1, "syndicated_publisher": 1, "category": 1, "subcategory": 1,
         "category_v2": 1, "subcategory_v2": 1, "state": 1, "rank_at": 1, "desk_story_id": 1,
         "publisher_name": 1},
    ).to_list(E.MAX_MEMBERS * 2)
    members = [m for m in (_member_from_doc(d) for d in docs) if m["published_at"] and m.get("publisher")]
    desk = ev.get("desk") or {}
    if not members:
        await db.events.update_one({"event_id": event_id}, {"$set": {"status": "closed", "article_ids": [],
                                                                    "updated_at": _iso(now)}})
        return None

    voices = E.independent_outlets(members)
    group_of = {m["publisher"]: m.get("publisher_group") or "other" for m in members}
    mix = Counter(group_of.get(v, "wire") for v in voices)
    scout_flag = bool(scout_ids and any(m["article_id"] in scout_ids for m in members))
    status = E.next_status(ev.get("status") or "forming", members, now,
                           desk_promoted=bool(desk.get("promoted")), scout_flag=scout_flag,
                           desk_event=any(m.get("origin") == "desk" for m in members),
                           hidden=bool(desk.get("hidden")))
    lead = E.pick_lead(members, now, current=ev.get("lead_article_id"),
                       pinned_until=_dt(ev.get("lead_pinned_until")), overrepresented=overrepresented)
    lead_doc = next((m for m in members if m["article_id"] == lead), members[0])
    pinned = ev.get("lead_pinned_until") if lead == ev.get("lead_article_id") else _iso(E.lead_pin_until(now))
    category_v2 = _vote([m.get("category_v2") or m.get("category") for m in members],
                        lead_doc.get("category_v2") or lead_doc.get("category"))
    subcategory_v2 = _vote([m.get("subcategory_v2") for m in members
                            if (m.get("category_v2") or m.get("category")) == category_v2],
                           lead_doc.get("subcategory_v2"))
    if lead_doc.get("origin") == "desk":     # the Desk chose its category; members follow it
        category_v2 = lead_doc.get("category_v2") or lead_doc.get("category") or category_v2
        subcategory_v2 = lead_doc.get("subcategory_v2") or lead_doc.get("subcategory")
    category, subcategory = C.legacy_category(category_v2, subcategory_v2)
    state = _vote([m.get("state") for m in members], lead_doc.get("state"))
    # Up to 3 outlets for the card's coverage strip: the lead's first, tinted
    # by outlet TYPE, never a logo (design review 5A).
    name_of = {m["publisher"]: m.get("publisher_name") or m["publisher"] for m in members}
    order = [lead_doc["publisher"]] + [v for v in voices if v != lead_doc["publisher"]]
    strip = [{"i": P.initials_of(v, name_of.get(v, v)), "g": group_of.get(v, "wire"),
              "n": name_of.get(v, v)} for v in order[:3]]
    fields = {
        "outlet_strip": strip,
        "status": status, "lead_article_id": lead, "lead_publisher": lead_doc["publisher"],
        "lead_pinned_until": pinned, "outlets": voices, "outlets_count": len(voices),
        "coverage_mix": dict(mix), "category": category, "subcategory": subcategory,
        "category_v2": category_v2, "subcategory_v2": subcategory_v2, "state": state,
        "article_ids": sorted(m["article_id"] for m in members), "size": len(members),
        "scout_flag": scout_flag, "updated_at": _iso(now),
    }
    if status != ev.get("status"):
        fields["status_changed_at"] = _iso(now)
    await db.events.update_one({"event_id": event_id}, {"$set": fields})

    if mode == "live":
        vote = {"category": category, "subcategory": subcategory, "category_v2": category_v2,
                "subcategory_v2": subcategory_v2, "state": state}
        ids = [m["article_id"] for m in members]
        others = [i for i in ids if i != lead]
        hidden = bool(desk.get("hidden"))
        if others:
            await db.articles.update_many({"article_id": {"$in": others}},
                                          {"$set": {"event_hidden": True, **vote}})
        await db.articles.update_one({"article_id": lead}, {
            "$set": {"event_hidden": hidden, "outlets_count": len(voices), "coverage_mix": dict(mix),
                     "outlet_strip": strip, "event_status": status, **vote}})
        if lead_doc.get("origin") == "desk":
            await _fold_into_desk(db, lead_doc, others, now)
    return fields


async def _fold_into_desk(db, host: dict, others: list, now: datetime) -> None:
    """1A: a Desk story's event members ARE its absorbed coverage. Written as
    merged_into (merged_by "events") so the Desk's absorbed list and Undo work
    unchanged; members that left the event (Undo, split) are released. The
    host's rank moves up with the newest member (FlyDubai, 2026-10-01) and a
    developing Desk story gets the members in its timeline."""
    lead = host["article_id"]
    await db.articles.update_many(
        {"merged_into": lead, "merged_by": "events", "article_id": {"$nin": others}},
        {"$unset": {"merged_into": "", "merged_by": ""}})
    if not others:
        return
    await db.articles.update_many(
        {"article_id": {"$in": others}, "merged_into": {"$exists": False}, "absorb_exempt": {"$ne": True}},
        {"$set": {"merged_into": lead, "merged_by": "events"}})
    newest = await db.articles.find({"article_id": {"$in": others}}, {"_id": 0, "rank_at": 1})         .sort("rank_at", -1).limit(1).to_list(1)
    if newest and newest[0].get("rank_at"):
        await db.articles.update_one({"article_id": lead}, {"$max": {"rank_at": newest[0]["rank_at"]}})
    if host.get("desk_story_id"):
        await db.developing_stories.update_one(
            {"story_id": host["desk_story_id"]},
            {"$addToSet": {"article_ids": {"$each": others}}, "$set": {"last_updated": _iso(now)}})


async def block_member(db, article_id: str, now: datetime, mode: str = None) -> Optional[str]:
    """Desk Undo / remove: the article leaves its event for good (sticky
    blocked_member) and is re-clustered next cycle anywhere else. Returns the
    event it left."""
    a = await db.articles.find_one({"article_id": article_id}, {"_id": 0, "event_id": 1})
    eid = (a or {}).get("event_id")
    if not eid:
        return None
    await db.events.update_one({"event_id": eid}, {"$addToSet": {"desk.blocked_members": article_id},
                                                   "$pull": {"members": {"article_id": article_id}}})
    await db.articles.update_one({"article_id": article_id},
                                 {"$unset": {"event_id": "", "event_hidden": "", "merged_by": ""}})
    await recompute_event(db, eid, now, mode=mode or current_mode())
    return eid


# ── Desk Newsroom (design 7B): see what's forming, steer it by hand ─────────
#    Every action ends in recompute_event, the single writer (OV7).

async def _event_brief(db, ev: dict, now: datetime) -> dict:
    lead = await db.articles.find_one({"article_id": ev.get("lead_article_id")}, {"_id": 0, "title": 1}) or {}
    hour_ago = _iso(now - timedelta(hours=1))
    recent = await db.articles.count_documents({"event_id": ev["event_id"], "published_at": {"$gte": hour_ago}})
    return {"event_id": ev["event_id"], "title": lead.get("title") or "(no lead)", "status": ev.get("status"),
            "size": ev.get("size", 0), "outlets_count": ev.get("outlets_count", 0),
            "coverage_mix": ev.get("coverage_mix") or {}, "category": ev.get("category_v2") or ev.get("category"),
            "last_member_at": ev.get("last_member_at"), "new_last_hour": recent,
            "promoted": bool((ev.get("desk") or {}).get("promoted")),
            "hidden": bool((ev.get("desk") or {}).get("hidden"))}


async def newsroom(db, now: Optional[datetime] = None) -> dict:
    """Building now / Developing / Settling, plus the switch + alarm strip."""
    now = now or datetime.now(timezone.utc)
    since = _iso(now - timedelta(hours=E.JOIN_WINDOW_H))
    sections = {"building": [], "developing": [], "settling": []}
    async for ev in db.events.find({"last_member_at": {"$gte": since}, "size": {"$gte": 2},
                                    "status": {"$ne": "closed"}}, {"_id": 0}):
        key = {"developing": "developing", "settled": "settling"}.get(ev.get("status"), "building")
        # One outlet posting repeatedly isn't a story forming (seen on real data:
        # a PR site's four near-identical pieces led "Building now").
        if key == "building" and ev.get("outlets_count", 0) < 2:
            continue
        sections[key].append(await _event_brief(db, ev, now))
    sections["building"].sort(key=lambda e: (e["outlets_count"], e["new_last_hour"]), reverse=True)
    for k in ("developing", "settling"):
        sections[k].sort(key=lambda e: e.get("last_member_at") or "", reverse=True)
    state = await db.app_meta.find_one({"_id": "events_state"}, {"_id": 0}) or {}
    return {"mode": current_mode(), "alarm": bool(state.get("alarm")), "developing_cap": E.DEVELOPING_CAP,
            "developing_open": len(sections["developing"]), "building": sections["building"][:40],
            "developing": sections["developing"], "settling": sections["settling"][:40]}


async def event_detail(db, event_id: str) -> Optional[dict]:
    ev = await db.events.find_one({"event_id": event_id}, {"_id": 0, "centroid": 0, "founding": 0, "members": 0})
    if not ev:
        return None
    members = await db.articles.find(
        {"event_id": event_id},
        {"_id": 0, "article_id": 1, "title": 1, "publisher_name": 1, "publisher_group": 1, "published_at": 1,
         "syndicated_of": 1, "origin": 1, "url": 1}).sort("published_at", -1).to_list(E.MAX_MEMBERS * 2)
    return {**ev, "members": members}


async def set_desk_flag(db, event_id: str, flag: str, value: bool, now: datetime) -> bool:
    if flag not in ("promoted", "hidden"):
        raise ValueError(flag)
    res = await db.events.update_one({"event_id": event_id}, {"$set": {f"desk.{flag}": value}})
    if not res.matched_count:
        return False
    await recompute_event(db, event_id, now, mode=current_mode())
    return True


async def merge_events(db, source_id: str, target_id: str, now: datetime) -> bool:
    """Everything in source joins target; source closes and points at target
    (follows move with it, OV7)."""
    if source_id == target_id:
        return False
    src = await db.events.find_one({"event_id": source_id})
    dst = await db.events.find_one({"event_id": target_id})
    if not src or not dst:
        return False
    await db.articles.update_many({"event_id": source_id}, {"$set": {"event_id": target_id}})
    centroid = E.merge_centroid(dst.get("centroid") or {}, dst.get("size", 0), src.get("centroid") or {})
    await db.events.update_one({"event_id": target_id}, {
        "$set": {"centroid": centroid, "size": dst.get("size", 0) + src.get("size", 0),
                 "first_member_at": min(dst.get("first_member_at") or "", src.get("first_member_at") or "") or
                 dst.get("first_member_at"),
                 "members": ((dst.get("members") or []) + (src.get("members") or []))[-E.MAX_MEMBERS:]}})
    await db.events.update_one({"event_id": source_id}, {"$set": {"status": "closed", "desk.merged_into": target_id,
                                                                  "article_ids": [], "updated_at": _iso(now)}})
    await _move_follows(db, source_id, target_id)
    await recompute_event(db, target_id, now, mode=current_mode())
    return True


async def split_event(db, event_id: str, article_ids: list, now: datetime) -> Optional[str]:
    """The ticked members break out into a new event; they are blocked from
    the old one so the engine never folds them back."""
    ev = await db.events.find_one({"event_id": event_id})
    if not ev or not article_ids:
        return None
    docs = await db.articles.find({"event_id": event_id, "article_id": {"$in": article_ids}},
                                  {"_id": 0, "article_id": 1, "title": 1, "content": 1, "publisher": 1,
                                   "published_at": 1, "ev_terms": 1}).sort("published_at", 1).to_list(len(article_ids))
    if not docs or len(docs) == ev.get("size", 0):
        return None                    # splitting off everything is not a split
    ids = [d["article_id"] for d in docs]
    new_id = f"ev-split-{ids[0]}"
    df = _cache["df"] or E.DocFreq()
    vecs = [E.vectorize(Counter(d.get("ev_terms") or {}), df) for d in docs]
    centroid = {}
    for i, v in enumerate(vecs):
        centroid = E.merge_centroid(centroid, i, v)
    await db.events.update_one({"event_id": new_id}, {"$set": {
        "event_id": new_id, "status": "forming", "created_at": _iso(now), "centroid": centroid,
        "founding": vecs[:E.FOUNDING], "size": len(ids), "first_member_at": docs[0]["published_at"],
        "last_member_at": docs[-1]["published_at"], "split_from": event_id,
        "members": [{"article_id": d["article_id"], "title": d.get("title", ""), "content": (d.get("content") or "")[:300],
                     "publisher": d.get("publisher"), "published_at": d["published_at"]} for d in docs]}}, upsert=True)
    await db.articles.update_many({"article_id": {"$in": ids}}, {"$set": {"event_id": new_id}})
    await db.events.update_one({"event_id": event_id}, {
        "$addToSet": {"desk.blocked_members": {"$each": ids}},
        "$pull": {"members": {"article_id": {"$in": ids}}},
        "$inc": {"size": -len(ids)}})
    mode = current_mode()
    await recompute_event(db, event_id, now, mode=mode)
    await recompute_event(db, new_id, now, mode=mode)
    return new_id


async def _move_follows(db, source_id: str, target_id: str) -> None:
    async for f in db.follows.find({"story_id": source_id}, {"_id": 0, "user_id": 1}):
        if not await db.follows.find_one({"user_id": f["user_id"], "story_id": target_id}):
            await db.follows.update_one({"user_id": f["user_id"], "story_id": source_id},
                                        {"$set": {"story_id": target_id}})
        else:
            await db.follows.delete_one({"user_id": f["user_id"], "story_id": source_id})
    await db.story_seen.delete_many({"story_id": source_id})


# ── golden set (eng review 3A / OV5): the owner checks the engine's calls ────
#    Pairs are of two kinds, so both errors are measured:
#      grouped    : two articles the engine put in ONE event   (over-merge?)
#      near_miss  : leads of two DIFFERENT events that look alike (under-merge?)


def _pair_id(a: str, b: str) -> str:
    x, y = sorted((a, b))
    return hashlib.sha1(f"{x}|{y}".encode()).hexdigest()[:16]


async def golden_pairs(db, now: Optional[datetime] = None, n: int = 40, seed: Optional[int] = None) -> list:
    now = now or datetime.now(timezone.utc)
    rng = random.Random(seed)
    since = _iso(now - timedelta(hours=E.JOIN_WINDOW_H * 2))
    done = {d["pair_id"] async for d in db.golden_labels.find({}, {"_id": 0, "pair_id": 1})}
    evs = [e async for e in db.events.find({"last_member_at": {"$gte": since}, "size": {"$gte": 1}},
                                           {"_id": 0, "event_id": 1, "article_ids": 1, "centroid": 1,
                                            "lead_article_id": 1, "first_member_at": 1})]
    grouped, near = [], []
    for ev in evs:
        ids = ev.get("article_ids") or []
        if len(ids) >= 2:
            a, b = rng.sample(ids, 2)
            grouped.append((a, b, "grouped"))
    by_time = sorted((e for e in evs if e.get("centroid") and e.get("lead_article_id")),
                     key=lambda e: e.get("first_member_at") or "")
    scored = []
    for i, x in enumerate(by_time):
        for y in by_time[i + 1:i + 60]:          # neighbours in time only: cheap and relevant
            sim = E.cosine(x["centroid"], y["centroid"])
            if sim >= 0.15:
                scored.append((sim, x["lead_article_id"], y["lead_article_id"]))
    scored.sort(reverse=True)
    near = [(a, b, "near_miss") for _, a, b in scored[: n * 2]]
    rng.shuffle(grouped)
    want_grouped = n * 3 // 5
    picked = [p for p in grouped if _pair_id(p[0], p[1]) not in done][:want_grouped]
    picked += [p for p in near if _pair_id(p[0], p[1]) not in done][: n - len(picked)]
    rng.shuffle(picked)
    ids = list({i for a, b, _ in picked for i in (a, b)})
    arts = {d["article_id"]: d async for d in db.articles.find(
        {"article_id": {"$in": ids}},
        {"_id": 0, "article_id": 1, "title": 1, "description": 1, "publisher_name": 1, "source": 1,
         "published_at": 1, "event_id": 1})}
    out = []
    for a, b, kind in picked:
        if a in arts and b in arts:
            out.append({"pair_id": _pair_id(a, b), "kind": kind,
                        "engine_same": arts[a].get("event_id") == arts[b].get("event_id"),
                        "a": {k: arts[a].get(k) for k in ("article_id", "title", "description", "publisher_name", "published_at")},
                        "b": {k: arts[b].get(k) for k in ("article_id", "title", "description", "publisher_name", "published_at")}})
    return out


async def golden_label(db, pair_id: str, a_id: str, b_id: str, same: bool, engine_same: bool, by: str,
                       now: Optional[datetime] = None) -> None:
    if _pair_id(a_id, b_id) != pair_id:
        raise ValueError("pair_id does not match the articles")
    await db.golden_labels.update_one({"pair_id": pair_id}, {"$set": {
        "pair_id": pair_id, "a": a_id, "b": b_id, "owner_same": bool(same), "engine_same": bool(engine_same),
        "by": by, "at": _iso(now or datetime.now(timezone.utc))}}, upsert=True)


async def golden_summary(db) -> dict:
    """How often the engine agrees with the owner, and merge precision
    (of pairs the engine grouped, how many the owner calls the same story)."""
    rows = [r async for r in db.golden_labels.find({}, {"_id": 0})]
    agree = sum(1 for r in rows if r["owner_same"] == r["engine_same"])
    grouped = [r for r in rows if r["engine_same"]]
    same_owner = [r for r in rows if r["owner_same"]]
    precision = sum(1 for r in grouped if r["owner_same"]) / len(grouped) if grouped else None
    recall = sum(1 for r in same_owner if r["engine_same"]) / len(same_owner) if same_owner else None
    return {"labelled": len(rows), "agree": agree,
            "merge_precision": round(precision, 3) if precision is not None else None,
            "merge_recall": round(recall, 3) if recall is not None else None,
            "gate": {"precision": 0.95, "recall": 0.80},
            "sweep": await golden_sweep(db, rows)}


SWEEP_THRESHOLDS = (0.25, 0.28, 0.30, 0.32, 0.35, 0.38, 0.40, 0.45)


def sweep_rows(pairs: list, thresholds=SWEEP_THRESHOLDS) -> list:
    """pairs: [(cosine, owner_same)]. For each threshold, the precision and
    recall of "same story iff cosine >= t" against the owner's labels."""
    out = []
    for t in thresholds:
        tp = sum(1 for c, same in pairs if c >= t and same)
        fp = sum(1 for c, same in pairs if c >= t and not same)
        fn = sum(1 for c, same in pairs if c < t and same)
        out.append({"t": t,
                    "precision": round(tp / (tp + fp), 3) if tp + fp else None,
                    "recall": round(tp / (tp + fn), 3) if tp + fn else None})
    return out


async def golden_sweep(db, rows: list, now: Optional[datetime] = None) -> dict:
    """What-if for tuning T_JOIN from the owner's own labels: the pairwise
    similarity of each labelled pair (same vectors the engine uses), scored at
    several thresholds. Pairwise is a proxy for the engine's centroid join, so
    it guides the pick; the live score above stays the gate."""
    if not rows:
        return {"rows": [], "current": E.T_JOIN, "pairs": 0}
    df = await _ensure_cache(db, now or datetime.now(timezone.utc))
    ids = list({i for r in rows for i in (r["a"], r["b"])})
    terms = {d["article_id"]: d.get("ev_terms") or {} async for d in db.articles.find(
        {"article_id": {"$in": ids}}, {"_id": 0, "article_id": 1, "ev_terms": 1})}
    vec = {i: E.vectorize(Counter(t), df) for i, t in terms.items() if t}
    pairs = [(E.cosine(vec[r["a"]], vec[r["b"]]), bool(r["owner_same"]))
             for r in rows if r["a"] in vec and r["b"] in vec]
    return {"rows": sweep_rows(pairs), "current": E.T_JOIN, "pairs": len(pairs)}


# ── read side: the Developing list and story page project events at read time
#    (eng review 1B: no copies in developing_stories, so nothing can drift) ────

def event_as_story(ev: dict, title: str) -> dict:
    """An event in the developing_stories document shape, so the existing
    detail endpoint (timeline, momentum, "Where it stands") serves it as is.
    1.12 apps render kind "event" through their default branch."""
    return {
        "story_id": ev["event_id"], "title": title, "kind": "event",
        "theme": (ev.get("category") or "news").lower(),
        "article_ids": ev.get("article_ids") or [], "last_updated": ev.get("last_member_at"),
        "state_summary": ev.get("state_summary"), "state_summary_count": ev.get("state_summary_count"),
        "outlets_count": ev.get("outlets_count"), "coverage_mix": ev.get("coverage_mix"),
        "status": ev.get("status"),
    }


async def story_for(db, story_id: str) -> Optional[dict]:
    if not story_id.startswith("ev-"):
        return None
    ev = await db.events.find_one({"event_id": story_id}, {"_id": 0})
    if not ev or (ev.get("desk") or {}).get("hidden"):
        return None
    lead = await db.articles.find_one({"article_id": ev.get("lead_article_id")}, {"_id": 0, "title": 1}) or {}
    return event_as_story(ev, lead.get("title") or "Developing story")


async def developing_list_items(db, now: Optional[datetime] = None) -> list:
    """Developing events for /developing-stories, capped (D7) at the
    DEVELOPING_CAP most active by independent updates in the last 6h."""
    now = now or datetime.now(timezone.utc)
    evs = [e async for e in db.events.find({"status": "developing", "desk.hidden": {"$ne": True}}, {"_id": 0})]
    ranked = []
    for ev in evs:
        docs = await db.articles.find({"event_id": ev["event_id"]},
                                      {"_id": 0, "article_id": 1, "title": 1, "image_url": 1, "published_at": 1,
                                       "source": 1, "publisher": 1, "syndicated_publisher": 1}).to_list(E.MAX_MEMBERS * 2)
        members = [m for m in (_member_from_doc(d) for d in docs) if m["published_at"] and m.get("publisher")]
        if not members:
            continue
        ranked.append((E.updates_last_hours(members, now), ev, members))
    ranked.sort(key=lambda r: (r[0], r[1].get("last_member_at") or ""), reverse=True)
    items = []
    for _, ev, members in ranked[:E.DEVELOPING_CAP]:
        latest = max(members, key=lambda m: m["published_at"])
        lead = next((m for m in members if m["article_id"] == ev.get("lead_article_id")), latest)
        items.append({
            "story_id": ev["event_id"], "title": lead.get("title", ""), "kind": "event",
            "theme": (ev.get("category") or "news").lower(), "article_count": len(members),
            "last_updated": _iso(latest["published_at"]),
            "latest_article": {"article_id": latest["article_id"], "title": latest.get("title"),
                               "image_url": latest.get("image_url"), "published_at": _iso(latest["published_at"]),
                               "source": latest.get("source")},
            "outlets_count": ev.get("outlets_count"), "coverage_mix": ev.get("coverage_mix"), "heat": None,
        })
    return items


async def _metrics(db, now: datetime, mode: str) -> dict:
    since = _iso(now - timedelta(hours=24))
    fresh = await db.articles.count_documents({"published_at": {"$gte": since}, "event_id": {"$exists": True}})
    dev_events = [e async for e in db.events.find({"status": "developing"},
                                                   {"_id": 0, "event_id": 1, "size": 1, "article_ids": 1})]
    dev_ids = {a for e in dev_events for a in (e.get("article_ids") or [])}
    dev_fresh = await db.articles.count_documents(
        {"published_at": {"$gte": since}, "article_id": {"$in": list(dev_ids)}}) if dev_ids else 0
    recent = [e async for e in db.events.find({"last_member_at": {"$gte": since}},
                                               {"_id": 0, "size": 1, "outlets_count": 1})]
    multi = [e for e in recent if e.get("size", 1) > 1]
    members_recent = sum(e.get("size", 1) for e in recent)
    ratio = round(dev_fresh / fresh, 3) if fresh else 0.0
    return {
        "mode": mode, "at": _iso(now),
        "events_24h": len(recent), "multi_outlet_events_24h": len(multi),
        "avg_outlets": round(sum(e.get("outlets_count", 1) for e in multi) / len(multi), 2) if multi else 0.0,
        "collapse_ratio": round(1 - len(recent) / members_recent, 3) if members_recent else 0.0,
        "developing_open": len(dev_events), "developing_label_ratio": ratio,
        "alarm": E.alarm(ratio, len(dev_events)),
    }

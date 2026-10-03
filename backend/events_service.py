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
import logging
import os
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional

import categories as C
import events as E
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


async def run_cycle(db, now: Optional[datetime] = None, mode: Optional[str] = None,
                    batch_limit: int = BATCH_LIMIT) -> dict:
    """One events pass. Returns the metrics it stored (also for tests)."""
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
    assignments, touched = await asyncio.to_thread(E.plan_batch, prepared, candidates, df)

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
         "category_v2": 1, "subcategory_v2": 1, "state": 1, "rank_at": 1, "desk_story_id": 1},
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
    fields = {
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
                     "event_status": status, **vote}})
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

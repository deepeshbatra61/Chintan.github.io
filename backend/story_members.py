"""Who belongs in a Developing story, and how its timeline reads (2026-10-05).

Owner report: an Apple App Store story and a Delhi hit-and-run sat inside the
"CJP / Jantar Mantar" story; a Fahadh Faasil film's earnings and a Doraemon
release sat inside "Drishyam 3 box office"; stories ran to 60-70 "updates" that
mostly said the same thing. Causes: candidates join on shared words alone
("delhi", "box office" + "crore"), the promotion step adds every article that
shares one trending word, and the timeline lists every outlet's copy.

    tagging / promotion ─▶ pending_ids        (word matches are only candidates)
    verify_members      ─▶ fast-model check per story, 20 reports per call:
                           "same specific event?"  yes ─▶ article_ids
                                                   no  ─▶ rejected_ids (never re-asked)
                           existing members are checked once too (verified_ids),
                           which cleans the stories already live
    group_updates       ─▶ the timeline: reports with the same facts (headline
                           overlap) fold into one update, "+N outlets"

If the model is unavailable nothing joins (pending waits); existing members stay.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Awaitable, Callable, Optional

import textutil

log = logging.getLogger("story_members")

FAST_MODEL = "claude-haiku-4-5-20251001"
BATCH = 20
CYCLE_BUDGET = 240          # reports checked per cycle across all stories (bounds cost)
SAME_FACTS = 0.5            # headline-term overlap at which two reports are one update
KEEP_IDS = 2000

SYSTEM = (
    "You check whether news reports belong to ONE specific developing story. A report belongs ONLY if it "
    "is about the SAME specific event: the same incident, case, protest, decision, match or film run that the "
    "story is about. Sharing a city, country, person, party, company, industry or topic is NOT enough "
    "(a Delhi hit-and-run does not belong to a Delhi protest story; another film's earnings do not belong "
    "to one film's box-office story). When unsure, leave it out. Respond ONLY with JSON."
)

LLMCall = Callable[..., Awaitable[str]]


def _terms(title: str) -> set:
    return set(textutil.headline_terms(title or ""))


def same_facts(a: str, b: str) -> bool:
    ta, tb = _terms(a), _terms(b)
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= SAME_FACTS


def group_updates(articles: list) -> list:
    """Newest-first articles -> newest-first updates. Each update is the first
    report of a set of facts plus the outlets that repeated it:
    {"lead": article, "also": [articles]}."""
    groups: list = []
    for a in sorted(articles, key=lambda x: x.get("published_at") or ""):      # oldest first
        home = next((g for g in groups if same_facts(a.get("title", ""), g["lead"].get("title", ""))), None)
        if home:
            home["also"].append(a)
        else:
            groups.append({"lead": a, "also": []})
    groups.sort(key=lambda g: max([g["lead"].get("published_at") or ""] +
                                  [x.get("published_at") or "" for x in g["also"]]), reverse=True)
    return groups


FOLD_OVERLAP = 0.3          # share of the smaller story's reports that makes two stories one


def fold_duplicates(items: list) -> list:
    """One entry per event in the Developing list. Detection opens a story per
    trending word and the scout per wording, so one match showed up as four
    stories ("India vs West Indies 3rd ODI", "West Indies Chase 352",
    "Shai Hope's Record 162", ...). Among auto/scout stories, one that shares
    FOLD_OVERLAP of its reports with a stronger one is left out. Desk,
    scheduled and wave stories are never hidden. Items carry their ids in
    "_ids" (removed here)."""
    order = {"desk": 0, "scheduled": 1, "wave": 2}
    ranked = sorted(items, key=lambda it: (order.get(it.get("kind"), 3), -(it.get("article_count") or 0)))
    kept, kept_sets = [], []
    for it in ranked:
        ids = set(it.get("_ids") or [])
        foldable = it.get("kind") in ("auto", "scout")
        # An auto story (a trending word) also folds into a scheduled story it
        # duplicates ("India's Performance at Asian Games" vs "Asian Games 2026");
        # a scout story (one specific match, verdict...) can stand beside it.
        hosts = ("auto", "scout", "desk", "scheduled") if it.get("kind") == "auto" else ("auto", "scout", "desk")
        if foldable and ids and any(
                k_kind in hosts and len(ids & k) >= FOLD_OVERLAP * min(len(ids), len(k))
                for k_kind, k in kept_sets):
            continue
        kept.append(it)
        kept_sets.append((it.get("kind"), ids))
    keep_ids = {id(it) for it in kept}
    out = [it for it in items if id(it) in keep_ids]          # original order
    for it in out:
        it.pop("_ids", None)
    return out


def _parse_same(text: str, n: int) -> Optional[set]:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except (ValueError, json.JSONDecodeError):
        return None
    same = data.get("same")
    if not isinstance(same, list):
        return None
    return {i for i in same if isinstance(i, int) and 0 <= i < n}


async def _judge(llm: LLMCall, story: dict, known: list, reports: list) -> Optional[set]:
    lines = []
    for i, a in enumerate(reports):
        d = (a.get("description") or "").strip()
        lines.append(f"{i}: {a.get('title', '')}" + (f" | {d[:160]}" if d else ""))
    ref = ("\nReports already confirmed in this story:\n- " + "\n- ".join(known[:4])) if known else ""
    if story.get("kind") in ("wave", "scheduled"):
        # A long-running storyline or a multi-day event (a war, a tournament):
        # each new development in THAT storyline belongs, a lookalike does not.
        ref += ("\nThis is a long-running story or multi-day event: a report belongs if it is a development "
                "in this same storyline or event, not merely the same country, person or sport.")
    user =(f"Story: {story.get('title', '')}{ref}\n\nNew reports (index: headline | description):\n"
            + "\n".join(lines)
            + '\n\nReturn ONLY: {"same": [indexes of reports about this exact story]}')
    try:
        return _parse_same(await llm(system=SYSTEM, user_content=user, max_tokens=200, model=FAST_MODEL),
                           len(reports))
    except Exception as e:  # noqa: BLE001
        log.warning(f"Member check failed for {story.get('story_id')}: {type(e).__name__}: {e}")
        return None


async def verify_members(db, llm: LLMCall, now: datetime, budget: int = CYCLE_BUDGET) -> dict:
    """Check unverified members and pending candidates of every active story."""
    out = {"checked": 0, "kept": 0, "rejected": 0, "closed": 0}
    stories = await db.developing_stories.find(
        {"is_active": True, "kind": {"$ne": "calendar"}},
        {"_id": 0, "story_id": 1, "title": 1, "kind": 1, "article_ids": 1, "pending_ids": 1,
         "verified_ids": 1, "rejected_ids": 1},
    ).to_list(2000)
    for st in stories:
        if budget <= 0:
            break
        members = list(dict.fromkeys(st.get("article_ids") or []))
        pending = [i for i in dict.fromkeys(st.get("pending_ids") or []) if i not in members]
        verified = set(st.get("verified_ids") or [])
        rejected = set(st.get("rejected_ids") or [])
        todo = [i for i in members + pending if i not in verified and i not in rejected][:budget]
        if not todo:
            if pending:
                await db.developing_stories.update_one({"story_id": st["story_id"]}, {"$set": {"pending_ids": []}})
            continue
        docs = {d["article_id"]: d for d in await db.articles.find(
            {"article_id": {"$in": todo}}, {"_id": 0, "article_id": 1, "title": 1, "description": 1}
        ).to_list(len(todo))}
        known_docs = await db.articles.find({"article_id": {"$in": list(verified)[-4:]}},
                                            {"_id": 0, "title": 1}).to_list(4)
        known = [d.get("title", "") for d in known_docs]
        decided_yes, decided_no = set(), set()
        reports = [docs[i] for i in todo if i in docs]
        decided_no |= {i for i in todo if i not in docs}               # article gone: drop it
        for b in range(0, len(reports), BATCH):
            chunk = reports[b:b + BATCH]
            same = await _judge(llm, st, known, chunk)
            budget -= len(chunk)
            out["checked"] += len(chunk)
            if same is None:
                continue                                               # undecided: ask again next cycle
            for i, a in enumerate(chunk):
                (decided_yes if i in same else decided_no).add(a["article_id"])
        verified |= decided_yes
        rejected |= decided_no
        undecided_pending = [i for i in pending if i not in decided_yes and i not in decided_no]
        new_members = [i for i in members + pending if i in verified or (i in members and i not in rejected)]
        new_members = [i for i in dict.fromkeys(new_members) if i not in rejected]
        fields = {"article_ids": new_members, "pending_ids": undecided_pending,
                  "verified_ids": list(verified)[-KEEP_IDS:], "rejected_ids": list(rejected)[-KEEP_IDS:],
                  "members_checked_at": now.isoformat()}
        if not new_members and not undecided_pending and st.get("kind") in ("auto", "scout"):
            fields["is_active"] = False
            out["closed"] += 1
        await db.developing_stories.update_one({"story_id": st["story_id"]}, {"$set": fields})
        out["kept"] += len(decided_yes)
        out["rejected"] += len(decided_no)
    if out["checked"]:
        log.info(f"Developing members: {out}")
    return out

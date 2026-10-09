"""Who belongs in a Developing story, and how its timeline reads.

2026-10-05, owner report: an Apple App Store story and a Delhi hit-and-run sat
inside the "CJP / Jantar Mantar" story; another film's earnings sat inside
"Drishyam 3 box office"; stories ran to 60-70 "updates" that mostly said the same
thing. Causes: candidates joined on shared words alone, and the timeline listed
every outlet's copy.

2026-10-09, owner report: Nana Patekar's death reached 242 updates, CJP 134, the
RBI hike 117. Every report really was about the event; most just did not ADD
anything (tributes, memories, "what it means for your EMI"). So the check now
also says what each report adds, and only developments make the timeline:

    tagging / promotion ─▶ pending_ids           (word matches are only candidates)
    verify_members      ─▶ fast-model check per story, 20 reports per call, label each:
                             no          ─▶ rejected_ids (never re-asked)
                             development ─▶ the timeline (something new happened)
                             repeat      ─▶ a source on the development it repeats
                             reaction    ─▶ bundle "Reactions & tributes"
                             explainer   ─▶ bundle "Explainers & analysis"
                           kinds live in member_kinds {article_id: kind}; members
                           from before labels existed are labelled once
    build_timeline      ─▶ developments folded by facts (group_updates), each with at
                           most MAX_SOURCES outlets named (owner: 7-8, never 15-20),
                           then the bundles

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
CYCLE_BUDGET = 400          # reports checked per cycle across all stories (bounds cost)
SAME_FACTS = 0.5            # headline-term overlap at which two reports are one update
KEEP_IDS = 2000
MAX_SOURCES = 8             # outlets shown for one development: the lead + 7 (owner, 2026-10-09)
TIMELINE_MAX = 40           # developments sent to the app (newest first)
BUNDLE_ITEMS = 30           # reports listed inside each bundle

KINDS = ("development", "repeat", "reaction", "explainer")
BUNDLES = (("reaction", "Reactions & tributes"), ("explainer", "Explainers & analysis"))

SYSTEM = (
    "You sort news reports for ONE specific developing story. For each report give exactly one label:\n"
    "- \"no\": NOT about this exact event. Sharing a city, country, person, party, company, industry or topic "
    "is not enough (a Delhi hit-and-run is not part of a Delhi protest story; another film's earnings are not "
    "part of one film's box-office story).\n"
    "- \"development\": reports something NEW that happened in this story: an action, decision, ruling, arrest, "
    "death, announcement, schedule change, official statement of fact, or a new number.\n"
    "- \"repeat\": reports a development already listed under Known developments, with nothing new.\n"
    "- \"reaction\": tributes, condolences, memories and old anecdotes, praise or criticism, opinions, what "
    "celebrities or politicians said about it.\n"
    "- \"explainer\": explains, analyses, predicts or guides: what it means, how it affects you, why, lists, "
    "what's open or closed, market or expert outlook.\n"
    "When unsure between development and anything else, do NOT choose development. Respond ONLY with JSON."
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


def kind_of(article_id: str, kinds: dict) -> str:
    """Members checked before labels existed (or not yet labelled) count as
    developments, which is how they were shown before."""
    k = (kinds or {}).get(article_id)
    return k if k in KINDS else "development"


def build_timeline(reports: list, kinds: dict) -> tuple:
    """(updates, bundles, n_updates) for a story page.

    updates: newest first, one per development; the lead report carries
    also_sources (up to MAX_SOURCES - 1 other outlets, repeats included) and
    also_count = len(also_sources), so no update ever reads "+20 outlets".
    bundles: [{"kind", "label", "count", "items"}] for reactions and explainers."""
    devs = [r for r in reports if kind_of(r.get("article_id"), kinds) == "development"]
    repeats = [r for r in reports if kind_of(r.get("article_id"), kinds) == "repeat"]
    groups = group_updates(devs)
    for r in repeats:                                       # a repeat is one more source for its development
        if not groups:
            break
        rt = _terms(r.get("title", ""))
        home = max(groups, key=lambda g: len(rt & _terms(g["lead"].get("title", ""))))
        home["also"].append(r)
    updates = []
    for g in groups[:TIMELINE_MAX]:
        lead = dict(g["lead"])
        others = [a.get("source") for a in sorted(g["also"], key=lambda x: x.get("published_at") or "")]
        names = [s for s in dict.fromkeys(others) if s and s != lead.get("source")][:MAX_SOURCES - 1]
        lead["also_sources"] = names
        lead["also_count"] = len(names)
        updates.append(lead)
    bundles = []
    for kind, label in BUNDLES:
        items = [r for r in reports if kind_of(r.get("article_id"), kinds) == kind]
        if items:
            items.sort(key=lambda x: x.get("published_at") or "", reverse=True)
            bundles.append({"kind": kind, "label": label, "count": len(items), "items": items[:BUNDLE_ITEMS]})
    return updates, bundles, len(groups)


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


def _parse_labels(text: str, n: int) -> Optional[dict]:
    """{index: label} from {"labels": {"0": "development", ...}}. The older
    {"same": [indexes]} answer still parses (same = development, rest = no)."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except (ValueError, json.JSONDecodeError):
        return None
    labels = data.get("labels")
    if isinstance(labels, dict):
        out = {}
        for k, v in labels.items():
            try:
                i = int(k)
            except (TypeError, ValueError):
                continue
            if 0 <= i < n and v in KINDS + ("no",):
                out[i] = v
        return out
    same = data.get("same")
    if isinstance(same, list):
        yes = {i for i in same if isinstance(i, int) and 0 <= i < n}
        return {i: ("development" if i in yes else "no") for i in range(n)}
    return None


async def _judge(llm: LLMCall, story: dict, known: list, reports: list) -> Optional[dict]:
    lines = []
    for i, a in enumerate(reports):
        d = (a.get("description") or "").strip()
        lines.append(f"{i}: {a.get('title', '')}" + (f" | {d[:160]}" if d else ""))
    ref = ("\nKnown developments in this story:\n- " + "\n- ".join(known[:8])) if known else ""
    if story.get("kind") in ("wave", "scheduled"):
        # A long-running storyline or a multi-day event (a war, a tournament):
        # each new development in THAT storyline belongs, a lookalike does not.
        ref += ("\nThis is a long-running story or multi-day event: a report belongs if it is part of this same "
                "storyline or event, not merely the same country, person or sport.")
    user = (f"Story: {story.get('title', '')}{ref}\n\nNew reports (index: headline | description):\n"
            + "\n".join(lines)
            + '\n\nReturn ONLY: {"labels": {"<index>": "no" | "development" | "repeat" | "reaction" | "explainer"}}')
    try:
        return _parse_labels(await llm(system=SYSTEM, user_content=user, max_tokens=400, model=FAST_MODEL),
                             len(reports))
    except Exception as e:  # noqa: BLE001
        log.warning(f"Member check failed for {story.get('story_id')}: {type(e).__name__}: {e}")
        return None


async def verify_members(db, llm: LLMCall, now: datetime, budget: int = CYCLE_BUDGET) -> dict:
    """Check and label unlabelled members and pending candidates of every active story."""
    out = {"checked": 0, "kept": 0, "rejected": 0, "closed": 0}
    stories = await db.developing_stories.find(
        {"is_active": True, "kind": {"$ne": "calendar"}},
        {"_id": 0, "story_id": 1, "title": 1, "kind": 1, "article_ids": 1, "pending_ids": 1,
         "verified_ids": 1, "rejected_ids": 1, "member_kinds": 1},
    ).to_list(2000)
    for st in stories:
        if budget <= 0:
            break
        members = list(dict.fromkeys(st.get("article_ids") or []))
        pending = [i for i in dict.fromkeys(st.get("pending_ids") or []) if i not in members]
        kinds = dict(st.get("member_kinds") or {})
        verified = set(st.get("verified_ids") or [])
        rejected = set(st.get("rejected_ids") or [])
        todo = [i for i in members + pending if i not in kinds and i not in rejected][:budget]
        if not todo:
            if pending:
                await db.developing_stories.update_one({"story_id": st["story_id"]}, {"$set": {"pending_ids": []}})
            continue
        docs = {d["article_id"]: d for d in await db.articles.find(
            {"article_id": {"$in": todo}}, {"_id": 0, "article_id": 1, "title": 1, "description": 1}
        ).to_list(len(todo))}
        dev_ids = [i for i in members if kinds.get(i) == "development"][-8:]
        known_docs = await db.articles.find({"article_id": {"$in": dev_ids}},
                                            {"_id": 0, "title": 1}).to_list(8)
        known = [d.get("title", "") for d in known_docs]
        decided_no = {i for i in todo if i not in docs}                # article gone: drop it
        labelled: dict = {}
        reports = [docs[i] for i in todo if i in docs]
        for b in range(0, len(reports), BATCH):
            chunk = reports[b:b + BATCH]
            labels = await _judge(llm, st, known, chunk)
            budget -= len(chunk)
            out["checked"] += len(chunk)
            if labels is None:
                continue                                               # undecided: ask again next cycle
            for i, a in enumerate(chunk):
                lab = labels.get(i, "no")
                if lab == "no":
                    decided_no.add(a["article_id"])
                else:
                    labelled[a["article_id"]] = lab
                    if lab == "development":
                        known.append(a.get("title", ""))
        kinds.update(labelled)
        verified |= set(labelled)
        rejected |= decided_no
        undecided_pending = [i for i in pending if i not in labelled and i not in decided_no]
        new_members = [i for i in dict.fromkeys(members + pending)
                       if i not in rejected and (i in members or i in labelled)]
        fields = {"article_ids": new_members, "pending_ids": undecided_pending,
                  "member_kinds": {i: kinds[i] for i in new_members if i in kinds},
                  "verified_ids": list(verified)[-KEEP_IDS:], "rejected_ids": list(rejected)[-KEEP_IDS:],
                  "members_checked_at": now.isoformat()}
        if not new_members and not undecided_pending and st.get("kind") in ("auto", "scout"):
            fields["is_active"] = False
            out["closed"] += 1
        await db.developing_stories.update_one({"story_id": st["story_id"]}, {"$set": fields})
        out["kept"] += len(labelled)
        out["rejected"] += len(decided_no)
    if out["checked"]:
        log.info(f"Developing members: {out}")
    return out

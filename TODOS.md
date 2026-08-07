# TODOS

Deferred work with enough context to pick up cold. Each item was surfaced during a
review and consciously deferred, not forgotten.

---

## 1. Group briefs by the interest the user actually selected

**What:** `get_brief` matches a user's interests against `category` OR `subcategory`, but
then groups the matched articles by `category` only.

**Why:** A user who chose a narrow subcategory (say "Formula 1") gets brief sections
labelled with the parent category ("Sports") they never picked. Worse, the prompt at
`server.py:3673` tells Claude "Their top interests are: Sports" — so the generated prose
is steered by an interest the user did not express.

**Pros:** Briefs finally reflect the interests people actually chose during onboarding;
the category badge on each card stops lying.

**Cons:** Interest matching is shared with the feed, so changing the grouping has a wider
blast radius than briefs alone and needs feed regression checks.

**Context:** `server.py:3588-3591` builds the query:
```python
{"$or": [{"category": {"$in": user_interests}}, {"subcategory": {"$in": user_interests}}]}
```
but `server.py:3620-3622` groups results with `cat = a.get("category")` and ignores
`subcategory` entirely. Surfaced by /plan-eng-review (2026-08-07) while binding brief cards
to a single ranked article — one arbitrary article per category now carries the mislabeled
badge, so the mismatch became more visible rather than being newly introduced.

**Depends on / blocked by:** Nothing blocking. Best done after the brief binding work
lands, so the two changes to `get_brief` don't collide.

---

## 2. Prune dead fields from the brief payload

**What:** The backend generates and caches `subtitle` and `greeting` that the client never
renders.

**Why:** `BriefPage.js:139` renders its own client-side `meta.sub`, and `:76` falls back to
`meta.greeting` with different casing than the server's "Good Morning". Both server fields
are dead weight that now get versioned into the brief cache.

**Pros:** Smaller cached documents; removes the confusion of two sources of truth for the
same greeting; one less thing to keep in sync when the brief shape changes again.

**Cons:** Older app builds might read these fields, so removing them needs the same
version-skew care as the rest of the brief work — the Play Store update cycle means old
clients stay in the field for weeks.

**Context:** Backend sets them at `server.py:3585` and returns them at `:3721-3722`.
Client ignores them at `BriefPage.js:76` and `:139`. Surfaced by the outside-voice pass
during /plan-eng-review (2026-08-07) while reshaping the brief payload.

**Depends on / blocked by:** Should land after the brief cache is already versioned, so the
field removal rides an invalidation that is happening anyway.

---

## 3. Route brief generation through the shared `_llm()` helper

**What:** Brief generation calls `_anthropic_client.messages.create(...)` directly instead
of the `_llm()` helper every other model call in the file uses.

**Why:** Duplicated model-call plumbing — model selection, token limits, and text
extraction — drifts out of sync. A future change to how the app calls Claude (retries,
timeouts, model aliasing) would silently skip briefs.

**Pros:** One place to change model behaviour; brief generation inherits any hardening
added to `_llm()` for free.

**Cons:** Touches shared infrastructure used by polls, Other Side, deep dives and
developing-story summaries, so a mistake here reaches well beyond briefs.

**Context:** Helper is defined at `server.py:126`:
```python
async def _llm(system: str, user_content: str, max_tokens: int = 1024, model: str = None) -> str:
```
Brief bypasses it at `server.py:3685`. Note `_llm` takes a separate `system` argument while
the brief currently packs everything into one user message, so this is a small rewrite of
the prompt shape rather than a drop-in swap. Surfaced by /plan-eng-review (2026-08-07),
deferred to keep an already-large release focused.

**Depends on / blocked by:** Do this after `backend/brief.py` exists, so the prompt
construction being moved is already isolated from the endpoint.

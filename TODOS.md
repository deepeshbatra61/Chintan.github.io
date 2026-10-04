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

---

## 4. Decouple the research agent from the ingest sync cycle at scale

**What:** `backend/research.py`'s topic research runs inline inside the same sync cycle as
`_sync_wave_topics` and friends, with a hard per-call timeout as the only safety valve.

**Why:** At the stated volume (1-2 calendar entries/day), inline is simpler and reuses
infrastructure that already runs reliably. If either Chintan Calendar's own volume grows, or
the same `research.py` module gets used for trending-topic research (a separate planned
feature), several research calls landing in one sync cycle could meaningfully slow down or
time out the shared ingest cycle that also fetches new articles.

**Pros:** Isolates research latency from article ingestion at any volume; removes the
per-call timeout as a single point of failure for the whole cycle.

**Cons:** Real infrastructure (a queue, or a separately scheduled job) for a problem that
doesn't exist yet — building it now would be solving for a scale not yet reached.

**Context:** Decided in `/plan-eng-review` (2026-08-09), issue D8. Revisit once either
Chintan Calendar's entry volume grows meaningfully, or the trending-topics feature starts
calling `research.py` too.

**Depends on / blocked by:** Nothing blocking. Trigger is observed volume/latency, not a
prerequisite piece of work.

---

## 5. Extend `research.py` to power trending topics

**What:** The user's stated plan for a future feature: surface trending topics using the
same verified-web-research capability being built for Chintan Calendar.

**Why:** Requested explicitly during the research-agent architecture review — the module is
deliberately designed to take an arbitrary topic string, not a calendar-specific shape, so
this door stays open without rework.

**Pros:** Reuses verification, caching, and cost-control work that already has to be built
once, for a second feature.

**Cons:** Trending-topic discovery itself (what counts as "trending," how often to check) is
a separate design question not explored in this review — this TODO is a pointer, not a plan.

**Context:** Raised by the user during `/plan-eng-review` (2026-08-09) while scoping the
research agent. No design work done yet beyond keeping `research.py`'s interface general.

**Depends on / blocked by:** The research agent itself must ship first.

---

## 6. Real-time RSS ingestion (next after the Desk)

**What:** Add real-time RSS feeds from the Indian outlets already in the NewsAPI domain list
(The Hindu, Indian Express, NDTV, Hindustan Times, Mint, and others) alongside NewsAPI.

**Why:** NewsAPI's free Developer tier delays every article by ~24h (confirmed 2026-09-28:
newest stored article is always ~24h old at ingest; 4 requests x 24 cycles = 96 of the
100/day cap). Nothing is ever "breaking", the LIVE badge rarely fires, and developing-story
detection runs a day behind.

**Pros:** Every story gets fresh with no human in the loop; free; makes the freshness
signal and developing detection work as designed.

**Cons:** Per-feed parsing quirks, duplicate stories across RSS and NewsAPI (URL-md5
dedup covers exact URLs only), and more volume through the categoriser.

**Context:** The user chose to build the Desk first for editorial control and take this on
"right after" (`/plan-eng-review` 2026-09-28, D7). The Desk introduces `rank_at` =
published_at + per-source delay (NewsAPI 24h, Desk 0h), so RSS slots in with delay 0 and
no ranking changes. Start at `fetch_from_newsapi()` in `backend/server.py`; reuse the
blacklist, India-relevance filter and URL-md5 article_id.

**Depends on / blocked by:** The Desk's `rank_at` field landing first.

---

## 7. Stop trusting forwarded client IPs from anywhere

**What:** `backend/Procfile` runs uvicorn with `--proxy-headers --forwarded-allow-ips=*`,
so any client can send a fake `X-Forwarded-For` and pick its own IP.

**Why:** slowapi's per-IP limits on the app's login/signup key off that IP, so password-
guessing limits on the main app can be bypassed with one header.

**Pros:** Restores the rate limits that already exist on paper.

**Cons:** A wrong value makes every request look like the same IP (Railway's proxy), which
would rate-limit all users together. Must be verified, not guessed.

**Context:** Found by the outside voice in `/plan-eng-review` (2026-09-28). The Desk avoids
it separately (the website passes the client IP in a header the backend trusts only with
the proxy secret). Check Railway's docs for its proxy address range, or read the
right-most trusted hop, before changing.

**Depends on / blocked by:** Nothing.

---

## 8. iOS "Time Sensitive" level for Breaking pushes

**What:** Breaking pushes on iPhone use Apple's Time Sensitive interruption level so they
break through Focus modes and notification summaries.

**Why:** v1 sends Breaking at the normal "active" level; a reader in a Focus mode may not
see it until later.

**Pros:** Breaking behaves like breaking news on iPhone, matching Android's high-importance
channel.

**Cons:** Apple expects sparing use (our 1/day, 2/week cap satisfies it); needs a Mac session.

**Context:** From `/plan-ceo-review` of push (2026-09-30). Add the "Time Sensitive
Notifications" capability in Xcode, regenerate the provisioning profile, then set
`interruption-level: time-sensitive` in the APNs payload for Breaking only (backend push
sender). **Effort:** S. **Priority:** P3.

**Depends on / blocked by:** iOS push working (phase 1 Mac build with the APNs key).

---

## 9. Phase 2 native Android notification renderer (for Read / Save buttons)

**What:** Replace phase 1's standard FCM notification messages on Android with data
messages drawn by our own `ChintanMessagingService`, so "Read" / "Save for later" action
buttons can be added.

**Why:** Action buttons with an authenticated background save need native rendering; FCM's
standard notification can't do them.

**Pros:** Action buttons and full control of layout, later without another format change.

**Cons:** Native code, plus a payload format switch (the sender must send data-only to
Android builds that have the new service, and notification messages to older builds).

**Context:** Deferred from phase 1 by `/plan-eng-review` (2026-09-30, decision 11B) to keep
vc15 low-risk. Three traps found in review:
1. `@capacitor/push-notifications` declares its own `MessagingService`; remove it in
   `AndroidManifest.xml` with `tools:node="remove"` and subclass it (call `super`) so token
   refresh and JS delivery keep working.
2. The tap `PendingIntent` must carry the `google.message_id` extra (and our data), or
   Capacitor never fires `pushNotificationActionPerformed` and the `?pin=` link is lost.
3. Check whether the app is in the foreground before drawing: slot pushes must stay silent
   there (R4), Breaking goes to the in-app banner.
**Effort:** M. **Priority:** P2.

**Depends on / blocked by:** Phase 1 shipped; a versioned payload (send `v` in data) so the
sender knows which builds can render data messages.

---

## 10. DESIGN.md for the app

**What:** One DESIGN.md capturing the app's design system: Surya tokens (dark + light),
type (Playfair Display headings, Manrope body, JetBrains Mono small caps), the sheet,
switch, segmented-control and toast patterns, and the push copy rules.

**Why:** The push design review (2026-09-30) had to reconstruct the system from
`frontend/src/index.css`, `SignInPrompt.jsx` and `AppearanceControl.js`. Push adds new
patterns (bottom sheet ask, notification settings rows, Breaking banner) that later
screens should match.

**Pros:** Reviews and builds calibrate against one file; fewer one-off inline styles.

**Cons:** One more doc to keep current.

**Context:** The website (`chintan-website`) has PRODUCT.md; the app has none. Generate
from code with `/impeccable document` (documents what exists, no redesign). Include the
push copy rules from the CEO plan's "Design review" section. **Effort:** S. **Priority:** P3.

**Depends on / blocked by:** Best after phase 1's push UI ships.

---

## 11. "Every angle" on event pages

**What:** On an event covered by 3+ outlets, list each outlet's headline side by side
with one AI-written line on what each emphasises ("focuses on the court's reasoning").

**Why:** Makes "many voices" visible. News v2 groups outlets into events but only shows
the count and the type mix, not how the coverage differs.

**Pros:** A feature no Indian news app does well. Cheap once events exist: one cached
AI call per big event.

**Cons:** The framing line must stay neutral and factual, never "biased" or a lean
label. It adds AI cost and needs wording rules plus an eval.

**Context:** Deferred by the owner in the News v2 CEO review (2026-10-03). The spec is in
`~/.gstack/projects/deepeshbatra61-Chintan.github.io/ceo-plans/2026-10-03-news-v2-events.md`.
Build on `events.article_ids`, the publisher registry (`publishers.py`) and `_llm()`.
**Effort:** M → with CC: S. **Priority:** P2.

**Depends on / blocked by:** News v2 events live in production with the golden-set gate met.

---

## 12. Delete the legacy "same story" paths after events go live

**What:** Remove `_absorb_into_desk`, `_fold_recent_into_desk`, `desk.story_keyword_hits`,
`_scout_developing_candidates` and `_detect_developing_stories`, along with their tests and
the `EVENTS_MODE=off` branch that keeps them running.

**Why:** The News v2 eng review (OV4, 2026-10-03) keeps these paths behind the flag for
one release so a rollback is instant. Left in place for good, they become a second,
untested "same story" engine. That is the bug class behind 4 keyword-matching incidents:
"take", "loc/pok", the "india" scout flood, and the Desk phrases.

**Pros:** Developing and Desk folding have one source of truth, and server.py shrinks.

**Cons:** After this, rolling back events means a code revert, not a flag change.

**Context:** The spec is in
`~/.gstack/projects/deepeshbatra61-Chintan.github.io/designs/news-v2-20261003/PLAN.md`
(task T17). `events_flip.go_back` and the legacy branch are removed together.
**Effort:** S. **Priority:** P2.

**Depends on / blocked by:** `EVENTS_MODE=live` running cleanly through one full release.

---

## 13. Keep the Developing list to stories that are really moving (no hard cap)

**What:** Replace "everything that ever qualified" with rules that let a story into
Developing only while it is actually moving, and move it out on its own when it stops.
No fixed maximum; the list grows on a heavy news day and shrinks on a quiet one.

**Why:** The owner counted 33 topics in Developing on 2026-10-04. That is too many to
scan, so the list stops meaning "this is moving right now". The owner does not want a
hard cap (a big day really can have many live stories), so the fix has to be logic,
not a number.

**Pros:** Developing means something again. The banner and sidebar stay readable, and
follow pushes fire only for stories that are alive.

**Cons:** Too strict and real stories vanish. Needs replay on a few days of
production data before it ships, and a Desk view of what dropped out and why.

**Context:** Candidate rules, to tune together:
1. **Momentum to enter:** at least 2 independent outlets (syndicated copies count once)
   within 6h, and at least one new independent report in the last 3h to stay listed.
2. **Relative bar on busy days:** rank by independent updates in the last 6h and list
   stories above a share of the day's busiest (for example 25% of the top story's
   momentum), so the bar rises with volume instead of a fixed count.
3. **Faster settling:** quiet for 4–6h (not 8h) means "settled". Settled stories leave
   the banner but stay reachable from the story page and from Following.
4. **Fold near-duplicates:** two developing events whose centroids are very similar
   (≥0.55) and that started within 12h of each other show as one (Desk can split).
5. **Show the top few, tuck the rest:** the feed banner already shows 4. The Developing
   page lists "Moving now" first and puts the rest under a collapsed "Also developing".
Today the legacy engine (`_detect_developing_stories` in `backend/server.py`) makes the
33. News v2 events (`events.py` `next_status`, `events_service.developing_list_items`,
`DEVELOPING_CAP = 15`) are in shadow. Build this on events, and turn the cap into
rules 1–5. Owner request 2026-10-04. **Effort:** M. **Priority:** P1.

**Depends on / blocked by:** EVENTS_MODE=live (golden-set gate met). If that slips past
launch, apply rules 1 and 3 to the legacy engine as a stopgap.

---

## 14. "Developing" means new facts, not the same story from more outlets

**What:** A story becomes Developing, and a timeline entry counts as an update, only when
a report adds something new to the previous one. Several outlets carrying the same report
are coverage of one moment, not a developing story.

**Why:** The owner's example (2026-10-04): "Ukraine accepts India's proposal for a
ceasefire" carried by 2 or 3 outlets is ONE report and should not be Developing. A
follow-up that moves the story, such as an MEA statement, Russia's response, or the
ceasefire starting or breaking, is an update and should make it Developing. Today the rules
count independent outlets (News v2 D7: 2+ outlets, ≥2h apart, within 6h), so the
same quote from several sources qualifies.

**Pros:** Developing and its timeline show how a story moved, not the same headline
repeated. This also shrinks the list on its own (works with #13), and follow pushes fire
only on real updates.

**Cons:** "Is there anything new here?" is a judgement. It needs either an AI call per
candidate update (cost: bound it to events that are already candidates, and cache per
article) or a novelty measure on text (new named entities, a new speaker or body, new
numbers or dates compared with the event so far), plus a golden set of "update or
repeat?" pairs from the owner, like the same-story check.

**Context:** Proposed shape:
1. Within an event, group members that report the same facts as one **report** (high
   similarity to an earlier member, no new entities, speakers or numbers). Show it as one
   timeline entry: "Reported by The Hindu, NDTV, Reuters".
2. A member with new facts starts a new **update** (new speaker or body such as the MEA,
   new numbers, a new action verb or outcome). An optional cheap AI check settles
   borderline cases, with "update"/"repeat" and a one-line "what changed".
3. Developing needs **at least 2 updates** (not 2 outlets) within the window, the newest
   in the last few hours. Momentum (`updates_last_hours`) counts updates, not members.
4. The timeline shows "what changed" for each update. That also feeds "Where it stands"
   and the follow push copy ("MEA responds: …").
5. Add a Desk check for "update or repeat?" pairs with a go-live bar, as in #12's golden set.
Code: `events.py` (`next_status`, `independent_outlets`, `updates_last_hours`),
`events_service.recompute_event`, story timeline in `DevelopingStoryDetail.js`.
Owner request 2026-10-04. **Effort:** M–L. **Priority:** P1 (do with #13).

**Depends on / blocked by:** News v2 events (shadow today). The engine can build and replay
this in shadow before EVENTS_MODE=live.

---

## 15. Make "Since you looked" impossible to miss

**What:** The "SINCE YOU LOOKED · 9:40 AM" divider on a developing story is a 10px
grey mono label between two faint hairlines. The owner was looking for it and still
struggled to spot it (2026-10-04).

**Why:** Its whole job is to say "start reading here". If it can't be seen, the feature
doesn't exist for readers.

**Pros:** Small change, big gain for anyone following a story.

**Cons:** It must stand out without shouting. It sits inside a calm timeline that already
uses red for the Developing rail.

**Context:** `frontend/src/pages/DevelopingStoryDetail.js` (`since-divider`). Direction:
an accent-red rule that crosses the timeline rail, with a filled pill label in red tint
reading "New since you looked · 9:40 AM" and the count ("3 new"). New entries above
it get a small red "NEW" dot on the rail. When the page opens, scroll to the divider
(dividerRef already exists) and give the pill one soft fade-in. Respect reduced motion.
Run `/impeccable` or `/design-review` to pick between 2–3 variants. **Effort:** S.
**Priority:** P1 (next app build).

**Depends on / blocked by:** Nothing.

---

## 16. Read scanned PDFs in the Government Tracker (OCR)

**What:** Some DGFT and Gazette notices are scanned images with no text layer. The tracker
v1 shows them as title + link only; OCR would let them be summarised like the rest.

**Why:** A complete record. The notices that matter most to traders are sometimes scans.

**Pros:** Fewer "summary pending" items; the tracker covers every notice.

**Cons:** CPU-heavy on Railway or a paid OCR service; OCR errors on numbers must still pass
the verify-or-drop check (E1), so many scanned items may still fall back to title-only.

**Context:** Government Tracker CEO review (2026-10-04, S1). v1 limits: PDFs <= 8 MB, <= 40
pages, 20 s worker timeout, no OCR. The Desk Sources panel will show how many PDFs per
source have no text; decide on that number. CEO plan:
`~/.gstack/projects/deepeshbatra61-Chintan.github.io/ceo-plans/2026-10-04-government-tracker.md`.
**Effort:** M -> with CC: S. **Priority:** P3.

**Depends on / blocked by:** Tracker live with DGFT + eGazette readers and a few weeks of
health-panel data.

---

## 17. Hindi and regional-language official sources

**What:** Add PIB's Hindi and regional feeds (and, later, state government sources that
publish only in their own language) to the Government Tracker.

**Why:** Reach readers beyond English when Chintan supports other languages.

**Pros:** A large audience no English-only news app serves well.

**Cons:** Needs a multi-language Chintan first (UI, summaries, number checks in other scripts).

**Context:** PIB's RSS serves Hindi when `Lang=2` (seen 2026-10-04: the URL Gemini suggested
redirected to Hindi). The tracker v1 pins English (`Lang=1&Regid=3&reg=3`). CEO plan as #16.
**Effort:** L -> with CC: M. **Priority:** P3.

**Depends on / blocked by:** A product decision to support other languages.

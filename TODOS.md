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

**Depends on / blocked by:** A few weeks of health-panel data. DGFT is live (2026-10-04) and
every DGFT PDF checked so far is a scan, so DGFT items are summarised from the one-line
official description only. That makes this more valuable than first thought.

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

---

## 18. CBIC (GST and customs) notifications in The Bureau

**What:** Add a reader for CBIC's GST, customs and excise notifications and circulars.

**Why:** GST rate changes and customs duty changes are some of the most reader-relevant
official decisions, and they are not always covered by a PIB release.

**Pros:** Covers tax decisions directly at the source, with the notification number.

**Cons:** The real notifications live on taxinformation.cbic.gov.in, a heavy single-page app
whose data calls are not yet worked out. The main site's ticker feed
(`www.cbic.gov.in/api/getTickerData/Tickers`) is not usable: it is mostly exams, recruitment
and tenders, and was two weeks stale when checked. Some CBIC PDFs may be scans.

**Context:** Checked 2026-10-04 while adding DGFT, MoSPI and Parliament (commit 8876ae7).
Documents on the main site sit at `https://www.cbic.gov.in/content/anotherfile/media/<filePathEn>`.
Adapter pattern: `backend/official_sources/` (see `dgft.py`). CEO plan as #16.
**Effort:** M -> with CC: S (if the portal's API can be found). **Priority:** P2.

**Depends on / blocked by:** Working out the taxinformation.cbic.gov.in data calls; ideally
OCR (#16) first in case the PDFs are scans.

---

## 19. eGazette in The Bureau (only if the Desk shows gaps)

**What:** Add a reader for the Gazette of India (egazette.gov.in).

**Why:** The Gazette is the legal record; some notifications appear there first.

**Pros:** Completeness; catches notifications no press release mentions.

**Cons:** Hard and noisy. `RecentUploads.aspx` needs a per-session path (`(S(...))` taken
from the home page redirect); downloads go through ASP.NET postbacks, not plain links; the
list is mostly land-acquisition and railway notices; PDFs are likely scans. Most important
items also come through PIB or the ministry, which The Bureau already reads.

**Context:** Checked 2026-10-04 (same pass as #18). Decision: skip unless Desk review shows
real stories that only the Gazette had.
**Effort:** M -> with CC: M. **Priority:** P4.

**Depends on / blocked by:** OCR (#16), and Desk evidence that the Gazette adds stories.

---

## 20. The Bureau: follow an issuer ("Follow RBI")

**What:** A Follow button for each issuer (RBI, SEBI, Cabinet, ministries, Parliament, DGFT,
MoSPI). It sits in the pinned bar at the bottom of each Bureau item page, after the
"Think of it like" box, and on a long-press of an issuer pill. Followers get a push when that
issuer announces something important, and followed issuers are listed under Following in the
side menu.

**Why:** It's in the approved design (CEO/design review 2026-10-04, P3/P7-A). It turns The
Bureau from a page you visit into something that comes to you.

**Pros:** Gives readers a reason to return; reuses the push holds (quiet hours, gaps, daily caps)
and the Following list built for stories.

**Cons:** Needs new server work: an issuer-follow store and a push trigger on new live Bureau
items (importance rules decide what is worth a ping). Also a new push copy style.

**Context:** Deferred by the owner on 2026-10-05 ("keep this in to do for now"). Bureau reader
endpoints: `backend/official_routes.py` (`/bureau`, `/bureau/items/{id}`). Item page:
`frontend/src/pages/BureauItemPage.jsx` (bottom bar is Original + Share today). Story follows to
copy from: `backend/events_routes.py` (`/follows`), `push_service.send_follow_update`. CEO plan:
`~/.gstack/projects/deepeshbatra61-Chintan.github.io/ceo-plans/2026-10-04-government-tracker.md`.
**Effort:** M -> with CC: S. **Priority:** P2.

**Depends on / blocked by:** Nothing. The Bureau is live (OFFICIAL_MODE=live since 2026-10-04).

---

## 21. The Bureau: "Add to Calendar" for key dates

**What:** Each key date on a Bureau item page (effective date, deadline, comments close,
applications open) gets an "Add to Calendar" action that adds an event to the phone's calendar
with the issuer, what changes and a link to the original.

**Why:** It's in the approved design (item page, key dates). Deadlines are the most
actionable part of an official announcement.

**Pros:** Small and self-contained, and useful from day one.

**Cons:** Dates come from the AI extraction as text ("1 November 2026"). They must parse
reliably, or the action is hidden for that date. On the phone, either an .ics file or a native
calendar plugin is needed; check what works on both Android and iOS.

**Context:** Deferred with #20 on 2026-10-05. Dates live in each item's `dates` field
(`[{label, date}]`), are verified against the source (E1), and are shown as tiles or a "Key dates"
list in `BureauItemPage.jsx`.
**Effort:** S -> with CC: S. **Priority:** P2.

**Depends on / blocked by:** Nothing.

---

## 22. Make iPhone releases push-button (no Terminal on the Mac)

**What:** Build and upload the iOS app from the cloud whenever a release is tagged, so the
owner never has to run Terminal commands on the Mac. Options, best first:
1. **GitHub Actions on a macOS runner + fastlane**: on a tag like `ios-v1.14.2`, check out,
   `npm ci`, build, `cap sync ios`, set version/build, sign with an App Store Connect API
   key and upload to TestFlight. The owner then only clicks "Submit for Review".
2. **Xcode Cloud**: Apple's own CI, set up once in Xcode; needs the `ios/` folder in git.
3. Interim (done 2026-10-05): `frontend/scripts/ios-release.sh` does pull / install / build /
   sync / version bump / open Xcode in one command.

**Why:** Every iOS release has stalled on the Mac (wrong folder, missing @capacitor/ios,
ERESOLVE on `npm install`). Android builds come straight from the Windows machine.

**Pros:** Releases in minutes; same steps every time; no machine-specific state.

**Cons:** One-time setup: the `ios/` folder must be committed (today it exists only on the
Mac), plus an App Store Connect API key and signing certificate stored as GitHub secrets (the
owner adds them; never pasted in chat). macOS runner minutes cost money on private repos
(~10 min per build).

**Context:** 2026-10-05, iOS 1.14.2 release; `npm install` failed with ERESOLVE (react-day-picker
8 vs date-fns 4), fixed by `frontend/.npmrc` (legacy-peer-deps). iOS share links also still need
Associated Domains (see [[share links]] notes), which committing `ios/` would make reviewable.
**Effort:** M -> with CC: S. **Priority:** P2.

**Depends on / blocked by:** The owner copying the Mac's `frontend/ios` folder into git once.

---

## 23. Feed freshness and uniqueness (and a refresh that visibly changes the feed)

**What:** Rework `/articles` ranking so that (a) everyone still gets the day's top news, but
(b) each reader's feed has a real share of fresh and less-seen stories, and (c) pull-to-refresh
visibly changes what is on top. Ideas to evaluate:
- **Per-article signals**, not only per-category: importance or "top story of the day" (multi-outlet
  coverage from the events engine, Desk heat), how much of the story the reader has already seen,
  and a penalty for stories already shown to this reader in earlier sessions.
- **A wider candidate pool**: today only the newest 200 by `rank_at` are scored (60 for guests),
  out of ~800 a day, so anything older than about 6 hours never reaches anyone's top 30. Score
  the whole day, or sample deliberately from the long tail.
- **Slots, not one sorted list**: e.g. the first 20 cards = ~12 top stories everyone should see,
  ~5 from your interests that few others were shown, ~3 discovery picks outside your interests.
- **Refresh that means something**: a new seed already reorders the feed, but the jitter (0-8
  points) is small next to the 20-48 point category tiers, so the top cards often look the
  same. Refresh should bring up unseen stories first and move ones already seen down.
- **Measure it**: overlap between two readers' top 20, share of the day's articles shown to
  anyone, and repeat impressions per reader.

**Why:** Owner, 2026-10-10: "the news I see in my feed is very similar to news others see";
"pull to refresh does not always work" (it works, but rarely changes the top of the feed);
"everyone should get to read the top news for the day but there needs to be a little quotient
of freshness as well".

**Pros:** Feeds that feel personal and alive; more of what we fetch actually gets read.

**Cons:** Needs per-reader "seen" tracking (impressions); ranking changes are easy to get wrong.
OWNER RULES still apply (pull-to-refresh reshuffles; back from an article keeps your place;
`backend/tests/test_feed_rules.py`, `frontend/src/__tests__/feedRules.test.jsx`).

**Context:** `server.py` `get_articles` and `_score_article`: category affinity 20-48, engagement,
comments, polls, likes are all per CATEGORY; per-article only freshness (+10 under 6h, +5 under
24h), a 20% wildcard (+10), the refresh jitter (`_feed_jitter`, 0-8) and Desk heat.
`feed.diversify` stops category runs. Events engine (shadow) already knows multi-outlet
"top stories" (~266 a day).
**Effort:** M -> with CC: M. **Priority:** P1 (the owner notices it daily).

**Depends on / blocked by:** Nothing to start the measuring; impressions logging first.

---

## 24. Courtroom: a section for cases that matter, explained for everyone

**What:** A new section, like The Bureau, for court cases of significance: cases in the news,
cases with controversy, and cases with a lesson for ordinary people. It is NOT every case.
Courts: Supreme Court, High Courts, district and sessions courts, consumer courts (district,
state, NCDRC), NGT (green tribunal), and special courts (NDPS, NIA, CBI, POCSO). Each case reads
so a normal person gets it: background, what was argued, the outcome or what is next, and the
takeaway. The shape changes by court:
- **Consumer court**: what went wrong, the compensation, and "what you can do if it happens to you".
- **Criminal / NDPS / NIA**: charges, bail or verdict, what happens next; careful, neutral
  language (accused, not guilty, until convicted); no naming of victims or minors.
- **Civil / constitutional (SC/HC)**: the question before the court, the ruling, who it affects.
- **NGT**: the environmental harm, the order, penalties or deadlines.

**Why:** Owner, 2026-10-10. Court news is high interest and widely misunderstood; plain-language
explainers with lessons are a USP, in the same family as The Bureau.

**Pros:** Reuses The Bureau's pipeline: source readers, AI extraction with verify-or-drop
numbers, Desk quality gate, flashcard feed and item page.

**Cons:** Legal accuracy and fairness risk is high: contempt, defamation, sub judice, and
naming rules (rape survivors, minors under POCSO/JJ Act). The legal-language voice must be
checked by the Desk before launch, with a stricter gate than The Bureau. Sources vary:
eCourts/NJDG, SC and HC sites and cause lists, NCDRC/CONFONET, NGT orders, plus GNews for
"in the news". Many orders are scanned PDFs (OCR, TODOS #16).

**Context:** Pattern to copy: The Bureau (`backend/official.py`, `official_service.py`,
`official_sources/`, `frontend/src/components/bureau/`, `pages/BureauItemPage.jsx`), its CEO
plan at `~/.gstack/projects/deepeshbatra61-Chintan.github.io/ceo-plans/2026-10-04-government-tracker.md`,
and the Desk review gate. Start with an /office-hours or /plan-ceo-review pass: which courts
first (likely SC + consumer courts + NGT), how "significance" is picked, and the legal-safety rules.
**Effort:** L -> with CC: M. **Priority:** P2.

**Depends on / blocked by:** A legal-safety style guide reviewed by the owner (ideally a lawyer)
before anything is public.

# Chintan - AI-Powered News App PRD

## Original Problem Statement
Build an AI-based news app named "Chintan" with the motto "Don't just consume. Contemplate." Transform passive news scrolling into active contemplation with personalized feeds, AI-powered analysis, and engagement features.

## User Personas
1. **Critical Thinkers (18-35)**: Tech-savvy professionals who want depth over headlines
2. **News Enthusiasts (25-45)**: Regular news consumers seeking balanced perspectives  
3. **Casual Readers**: Users who prefer curated briefs over endless scrolling

## Core Requirements
- Google OAuth authentication
- Personalized news feed based on interests
- Time-based briefs (Morning, Midday, Night) - each with distinct theme
- AI-powered "Ask AI" chat for article discussions
- "The Other Side" - alternative perspectives on stories
- Polls with 7-day expiry and history tracking
- Comments with agree/disagree reactions
- Notifications for comment reactions
- Bookmarks and reading stats
- Dark premium aesthetic with red (#DC2626) accent

## Architecture
- **Frontend**: React + Tailwind CSS + Framer Motion
- **Backend**: FastAPI + MongoDB
- **AI**: Claude Sonnet 4.5 via Emergent Integrations
- **Auth**: Emergent-managed Google OAuth

## What's Been Implemented

### Iteration 1 (Feb 8, 2026)
- [x] Full MVP: Feed, Articles, Briefs, AI features, Polls, Comments, Bookmarks

### Iteration 2 (Feb 9, 2026)
- [x] **Horizontal swipe navigation** - Swipe left/right for next/prev article with haptic feedback
- [x] **Back button fix** - Now goes to /feed instead of previous article
- [x] **Developing Stories** - Single breathing button in sidebar with red glow
- [x] **Notifications system** - Shows when others agree/disagree with your comments
- [x] **Professional onboarding** - No emojis, checkbox design, only 3 topics required
- [x] **Poll history** - Track polls voted in with 7-day expiry status
- [x] **Poll expiry** - 7-day voting window, results always visible
- [x] **Simplified profile stats** - Removed reading time/completed, kept bookmarks/articles
- [x] **Custom section labels** - Category-specific labels instead of emojis
- [x] **Better "Other Side"** - Natural paragraphs, no markdown
- [x] **Reduced AI questions** - Max 3 questions per article

### Iteration 3 (Feb 15, 2026)
- [x] **User Registration API Integration** - POST user data to RecSys API (`https://news-recsys-api-513550308951.europe-west1.run.app/users`) on:
  - New user creation (during first login)
  - Onboarding completion (when interests are first set)
  - Payload: `{ "id": user_id, "name": name, "declared_interests": "cat1,cat2,cat3" }`

### Pages Implemented
1. Login (Google OAuth)
2. Onboarding (3-step interest selection - professional design)
3. Feed (news cards, developing stories banner, category filters)
4. Article (collapsible sections, action bar, horizontal swipe)
5. Ask AI (full-screen chat)
6. Brief (Morning/Midday/Night with distinct themes)
7. Developing Stories (dedicated page with auto-refresh)
8. Bookmarks
9. Profile (stats, poll history, weekly report, edit interests)

## Mocked/Sample Data
- **News articles**: 12 realistic Indian news articles (MOCK DATA, not live API)
- Categories: Politics, Technology, Business, Sports, Entertainment, Science

## Prioritized Backlog

### P0 (Critical - Next Phase)
- [ ] Integrate live NewsAPI when API key provided
- [ ] Fix double-login issue (OAuth redirect handling)

### P1 (Important)
- [ ] Breakout Rooms feature (1-on-1 debates)
- [ ] Push notifications for briefs
- [ ] Share to WhatsApp/Twitter/LinkedIn

### P2 (Nice to Have)
- [ ] Offline reading support
- [ ] Advanced search with filters
- [ ] Reading streak gamification

## Technical Notes
- All MongoDB queries exclude `_id` with `{"_id": 0}` projection
- Sessions expire after 7 days
- Polls expire after 7 days (can't vote, but can see results)
- AI responses are cached in MongoDB
- Horizontal swipe uses touch events, not drag
- Haptic feedback via navigator.vibrate()
- **User Registration**: Users are registered with external RecSys API on creation and onboarding completion

## API Keys Required
- `EMERGENT_LLM_KEY`: For Claude Sonnet 4.5 (universal key) - configured
- `NEWS_API_KEY`: For live news (currently set to 'demo')

## External API Integrations
- **News RecSys API** (https://news-recsys-api-513550308951.europe-west1.run.app):
  - `GET /articles` - Fetch news articles
  - `POST /users` - Register users with recommendation system

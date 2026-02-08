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
- Time-based briefs (Morning, Midday, Night)
- AI-powered "Ask AI" chat for article discussions
- "The Other Side" - alternative perspectives on stories
- Polls and comments/discussions
- Bookmarks and reading stats
- Dark premium aesthetic with red (#DC2626) accent

## Architecture
- **Frontend**: React + Tailwind CSS + Framer Motion
- **Backend**: FastAPI + MongoDB
- **AI**: Claude Sonnet 4.5 via Emergent Integrations
- **Auth**: Emergent-managed Google OAuth

## What's Been Implemented (Feb 8, 2026)

### Backend
- [x] FastAPI server with all API routes prefixed with `/api`
- [x] MongoDB models for users, sessions, articles, polls, comments, bookmarks
- [x] Google OAuth via Emergent Auth (session-based)
- [x] 12 realistic Indian news articles across categories (MOCK DATA)
- [x] AI endpoints using Claude Sonnet 4.5
  - `/api/ai/ask` - Ask AI about articles
  - `/api/ai/other-side/{article_id}` - Alternative perspectives
  - `/api/ai/questions/{article_id}` - AI-generated questions
- [x] Poll voting system
- [x] Comments with agree/disagree stance
- [x] Bookmarks CRUD
- [x] Reading history tracking
- [x] User stats and interests management
- [x] Time-based briefs (morning/midday/night)

### Frontend
- [x] Login page with Google sign-in and Surya logo
- [x] Onboarding flow (3-step interest selection)
- [x] Feed page with:
  - Developing stories banner
  - Current brief button
  - Category filters
  - News cards with images, badges, metadata
- [x] Article page with:
  - Hero image
  - Collapsible sections (What, Why, Context, Impact)
  - Like/dislike feedback
  - Action bar (Discuss, Poll, Other Side, Ask AI)
- [x] Ask AI full-screen chat interface
- [x] Morning/Midday/Night brief pages with themed gradients
- [x] Bookmarks page
- [x] Profile page with reading stats
- [x] Dark premium design with glassmorphism
- [x] Responsive mobile layout

## Mocked/Sample Data
- **News articles**: 12 realistic Indian news articles (mock data, not live API)
- Categories: Politics, Technology, Business, Sports, Entertainment, Science

## Prioritized Backlog

### P0 (Critical - Next Phase)
- [ ] Integrate live NewsAPI when API key provided
- [ ] Implement swipe navigation between articles
- [ ] Add relevance feedback ("Is this relevant?") in early scrolls

### P1 (Important)
- [ ] Breakout Rooms feature (1-on-1 debates)
- [ ] Push notifications for briefs
- [ ] Reading behavior tracking for algorithm refinement
- [ ] Share to WhatsApp/Twitter/LinkedIn

### P2 (Nice to Have)
- [ ] Offline reading support
- [ ] Dark/Light theme toggle
- [ ] Advanced search with filters
- [ ] Interest subcategory selection in settings
- [ ] Reading streak gamification

## Technical Notes
- All MongoDB queries exclude `_id` with `{"_id": 0}` projection
- Sessions expire after 7 days
- AI responses are cached in MongoDB
- CORS configured for all origins
- Environment variables in `/app/backend/.env` and `/app/frontend/.env`

## API Keys Required
- `EMERGENT_LLM_KEY`: For Claude Sonnet 4.5 (universal key)
- `NEWS_API_KEY`: For live news (currently set to 'demo')

# Chintan

News reading app for people who want to understand a story, not just skim its
headline. FastAPI + MongoDB backend, React (Capacitor) frontend for web + Android.

## Repo layout

- `backend/` — FastAPI app (`server.py`), single-file. Deployed on Railway.
- `frontend/` — React app (Craco). Builds to a web app and, via Capacitor, the
  Android app (`frontend/android/`).
- Marketing site (`chintan.news`) and its `/contact`, `/about`, `/reset-password`
  pages live in a separate repo, `chintan-website`.

## Running locally

Backend:
```
cd backend
pip install -r requirements.txt
uvicorn server:app --reload
```

Frontend:
```
cd frontend
npm install
npm start
```

## Environment variables

Set these in Railway (backend) — nothing here is read by the frontend directly,
it talks to the deployed backend URL.

### Required — the app won't start without these

| Variable | What it's for |
|---|---|
| `MONGO_URL` | MongoDB connection string. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google sign-in. |

### Optional — each degrades gracefully when unset, rather than crashing

| Variable | What breaks/degrades without it |
|---|---|
| `ANTHROPIC_API_KEY` | No contemplation beats, deep dives, or AI-generated content — articles fall back to their raw publisher summary. |
| `REDIS_URL` | Affinity scoring falls back to an in-memory cache instead of Redis — works fine on a single instance, resets on every deploy/restart. |
| `NEWSAPI_KEY` | Article ingestion has nothing to pull from — the feed stops getting new articles. |
| `RESEND_API_KEY` / `EMAIL_FROM` | Password-reset requests succeed (same generic response either way, so this never surfaces as an error) but no email actually sends — logged as a warning instead. Get a key at resend.com. `EMAIL_FROM` defaults to `Chintan <noreply@chintan.news>` if unset. |
| `ADMIN_EMAILS` | Comma-separated allowlist for `/admin/*` routes. Empty = nobody has admin access. |
| `ALLOWED_ORIGINS` | CORS allowlist. |
| `INGEST_SCHEDULE_ENABLED` | Whether the hourly ingest cycle runs at all. |
| `LLM_CATEGORIZATION_ENABLED` | Whether category detection uses the LLM vs. keyword matching. |
| `AI_MODEL` / `DEEP_DIVE_MODEL` | Override which Claude model is used where. Sensible defaults if unset. |
| `DB_NAME` | Mongo database name. Defaults if unset. |

## Android build

See `frontend/android/`. Release builds need `versionCode`/`versionName` bumped
in `frontend/android/app/build.gradle` before running `gradlew bundleRelease`.

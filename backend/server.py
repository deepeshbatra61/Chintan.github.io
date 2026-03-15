from fastapi import FastAPI, APIRouter, HTTPException, Response, Request, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import traceback
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
import time
import random
import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
import hashlib
import re
import httpx
import redis.asyncio as aioredis
import anthropic
import pytz

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# CORS allowed origins — comma-separated in ALLOWED_ORIGINS env var, defaults to localhost:3000
# Always include Capacitor Android WebView origins (https://localhost, capacitor://localhost)
# so native-poll and other API calls work from the APK regardless of env config.
_raw_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000")
ALLOWED_ORIGINS = list({
    *[o.strip() for o in _raw_origins.split(",") if o.strip()],
    "https://localhost",       # Capacitor WebView (androidScheme: https)
    "capacitor://localhost",   # Capacitor WebView (androidScheme: capacitor)
    "http://localhost",        # Capacitor WebView fallback
})

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Redis connection (initialised in lifespan only when REDIS_URL is set)
REDIS_URL: Optional[str] = os.environ.get("REDIS_URL")
_redis: Optional[aioredis.Redis] = None

# Anthropic client (initialised in lifespan)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Google OAuth credentials
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "")
_anthropic_client: Optional[anthropic.AsyncAnthropic] = None

async def _llm(system: str, user_content: str, max_tokens: int = 1024) -> str:
    """Single-turn Anthropic API call. Returns the text of the first content block."""
    msg = await _anthropic_client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    return msg.content[0].text


async def _generate_poll_for_article(article: dict) -> None:
    """Ask the LLM for a question + 4 options, then persist the poll."""
    article_id = article["article_id"]
    prompt = (
        'Create a reader poll for this news article. '
        'Return ONLY a JSON object: {"question": "...", "options": ["A", "B", "C", "D"]}\n\n'
        f'Title: {article["title"]}\n'
        f'Summary: {article.get("description", "")}'
    )
    response = await _llm(
        system="You generate JSON polls for news articles. Respond with ONLY valid JSON, no explanation, no markdown.",
        user_content=prompt,
        max_tokens=512,
    )

    # Strip optional markdown code fences
    raw = response.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    # Locate the JSON object
    start, end = raw.find("{"), raw.rfind("}") + 1
    data = json.loads(raw[start:end])

    options = data["options"][:4]
    poll_doc = {
        "poll_id": f"poll_{uuid.uuid4().hex[:12]}",
        "article_id": article_id,
        "question": data["question"],
        "options": options,
        "votes": {opt: 0 for opt in options},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.polls.insert_one(poll_doc)
    logger.info(f"Auto-generated poll for {article_id}: {data['question']}")


_CREDIT_EXHAUSTED_MSG = "credit balance is too low"

def _is_credit_exhausted(err) -> bool:
    return _CREDIT_EXHAUSTED_MSG in str(err).lower()


async def _run_ingest_cycle() -> None:
    """Single fetch+categorise+summarise pass. Returns early on credit exhaustion."""
    # ── 0. Distributed lock (Redis only) ────────────────────────────────────
    if _redis:
        acquired = await _redis.set("ingestion:lock", "1", nx=True, ex=4 * 60 * 60)
        if not acquired:
            logger.info("Ingest cycle: lock held by another instance, skipping")
            return

    # ── 1. Fetch & upsert articles ───────────────────────────────────────────
    api_articles = await fetch_from_newsapi()
    if api_articles:
        new_count = 0
        updated_count = 0
        for article in api_articles:
            existing = await db.articles.find_one({"article_id": article["article_id"]})
            if not existing:
                await db.articles.insert_one(article)
                new_count += 1
            else:
                await db.articles.update_one(
                    {"article_id": article["article_id"]},
                    {"$set": {
                        "title": article["title"],
                        "description": article["description"],
                        "content": article["content"],
                        "image_url": article["image_url"],
                        "published_at": article["published_at"],
                        "is_developing": article["is_developing"],
                        "is_breaking": article["is_breaking"],
                    }},
                )
                updated_count += 1
        logger.info(
            f"Background ingestor: {new_count} new, {updated_count} updated "
            f"(total fetched: {len(api_articles)})"
        )
    else:
        logger.warning("Background ingestor: fetch_from_newsapi returned 0 articles")

    # ── 2. Poll generation removed — handled on-demand only ─────────────────

    # ── 3. Claude categorization (Haiku — cheap, good enough) ───────────────
    if ANTHROPIC_API_KEY:
        _valid_cats = {"Technology", "Politics", "Business", "Sports", "Entertainment", "Health", "Science", "World"}
        to_categorize = await db.articles.find(
            {"claude_categorized": {"$ne": True}, "claude_skip": {"$ne": True}},
            {"_id": 0, "article_id": 1, "title": 1},
        ).limit(30).to_list(30)

        for art in to_categorize:
            try:
                msg = await _anthropic_client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=20,
                    system="You categorize news articles. Return only the category name, nothing else.",
                    messages=[{"role": "user", "content": (
                        "Categorize this news article into exactly one of these categories: "
                        "Technology, Politics, Business, Sports, Entertainment, Health, Science, World. "
                        f"Article title: {art['title']}. Return only the category name, nothing else."
                    )}],
                )
                cat = msg.content[0].text.strip()
                if cat in _valid_cats:
                    await db.articles.update_one(
                        {"article_id": art["article_id"]},
                        {"$set": {"category": cat, "claude_categorized": True}},
                    )
            except Exception as cat_err:
                if _is_credit_exhausted(cat_err):
                    logger.warning("Credits exhausted — stopping ingest cycle")
                    return
                logger.error(f"Claude categorization error for {art['article_id']}: {cat_err}")
                result = await db.articles.find_one_and_update(
                    {"article_id": art["article_id"]},
                    {"$inc": {"claude_fail_count": 1}},
                    return_document=True,
                    projection={"_id": 0, "claude_fail_count": 1},
                )
                if result and result.get("claude_fail_count", 0) >= 3:
                    await db.articles.update_one(
                        {"article_id": art["article_id"]},
                        {"$set": {"claude_skip": True}},
                    )
                    logger.info(f"Marked claude_skip=True for {art['article_id']} after 3 failures")

    # ── 4. Claude summarization (Sonnet) ────────────────────────────────────
    if ANTHROPIC_API_KEY:
        to_summarize = await db.articles.find(
            {"claude_summarized": {"$ne": True}, "claude_skip": {"$ne": True}},
            {"_id": 0, "article_id": 1, "title": 1, "content": 1},
        ).limit(30).to_list(30)

        for art in to_summarize:
            try:
                raw = await _llm(
                    system="You summarize news articles into structured sections. Return only valid JSON.",
                    user_content=(
                        "You are summarizing a news article for the Chintan app. "
                        "Generate four distinct sections for this article. "
                        "Return as JSON only with keys: what, why, context, impact. "
                        "Each value must be 40-80 words, maximum 6 lines, specific to this article only, not generic. "
                        f"Article title: {art['title']}. "
                        f"Article content: {art.get('content', '')}"
                    ),
                    max_tokens=512,
                )
                raw_s = raw.strip()
                if raw_s.startswith("```"):
                    raw_s = raw_s.split("```")[1]
                    if raw_s.startswith("json"):
                        raw_s = raw_s[4:]
                    raw_s = raw_s.strip()
                start = raw_s.find("{")
                end = raw_s.rfind("}") + 1
                if start >= 0 and end > start:
                    data = json.loads(raw_s[start:end])
                    await db.articles.update_one(
                        {"article_id": art["article_id"]},
                        {"$set": {
                            "what": str(data.get("what", ""))[:500],
                            "why": str(data.get("why", ""))[:500],
                            "context": str(data.get("context", ""))[:500],
                            "impact": str(data.get("impact", ""))[:500],
                            "claude_summarized": True,
                        }},
                    )
            except Exception as sum_err:
                if _is_credit_exhausted(sum_err):
                    logger.warning("Credits exhausted — stopping ingest cycle")
                    return
                logger.error(f"Claude summarization error for {art['article_id']}: {sum_err}")
                result = await db.articles.find_one_and_update(
                    {"article_id": art["article_id"]},
                    {"$inc": {"claude_fail_count": 1}},
                    return_document=True,
                    projection={"_id": 0, "claude_fail_count": 1},
                )
                if result and result.get("claude_fail_count", 0) >= 3:
                    await db.articles.update_one(
                        {"article_id": art["article_id"]},
                        {"$set": {"claude_skip": True}},
                    )
                    logger.info(f"Marked claude_skip=True for {art['article_id']} after 3 failures")

    # ── 5. Tag new articles to watched developing stories ────────────────────
    if api_articles:
        watched = await db.developing_stories.find(
            {"is_active": True}, {"_id": 0, "story_id": 1, "keywords": 1}
        ).to_list(100)
        for topic in watched:
            keywords = topic.get("keywords", [])
            matched_ids = []
            for article in api_articles:
                haystack = (
                    article.get("title", "") + " " + article.get("description", "")
                ).lower()
                if any(kw.lower() in haystack for kw in keywords):
                    matched_ids.append(article["article_id"])
            if matched_ids:
                await db.developing_stories.update_one(
                    {"story_id": topic["story_id"]},
                    {
                        "$addToSet": {"article_ids": {"$each": matched_ids}},
                        "$set": {"last_updated": datetime.now(timezone.utc).isoformat()},
                    },
                )
                logger.info(f"Developing stories: +{len(matched_ids)} article(s) → {topic['story_id']}")


async def _run_cleanup_cycle() -> None:
    """Delete stale documents per retention policy."""
    now = datetime.now(timezone.utc)
    articles_cutoff = (now - timedelta(days=7)).isoformat()
    polls_cutoff    = (now - timedelta(days=30)).isoformat()
    cache_cutoff    = (now - timedelta(days=7)).isoformat()

    a_res  = await db.articles.delete_many({"published_at": {"$lt": articles_cutoff}})
    p_res  = await db.polls.delete_many({"created_at": {"$lt": polls_cutoff}})
    os_res = await db.other_side_cache.delete_many({"created_at": {"$lt": cache_cutoff}})
    aq_res = await db.ai_questions_cache.delete_many({"created_at": {"$lt": cache_cutoff}})
    logger.info(
        f"Cleanup: {a_res.deleted_count} articles, {p_res.deleted_count} polls, "
        f"{os_res.deleted_count} other-side, {aq_res.deleted_count} ai-questions deleted"
    )


async def _background_news_ingestor() -> None:
    """IST time-based scheduler: ingest at 6 AM, 1 PM, 8 PM; cleanup at 3 AM."""
    IST = pytz.timezone("Asia/Kolkata")
    INGEST_HOURS  = [6, 13, 20]
    CLEANUP_HOUR  = 3
    ALL_RUN_HOURS = sorted(INGEST_HOURS + [CLEANUP_HOUR])  # [3, 6, 13, 20]

    # Run one ingest immediately on startup to populate fresh content
    try:
        logger.info("Ingestor: running initial ingest cycle on startup")
        await _run_ingest_cycle()
    except Exception as exc:
        logger.error(f"Ingestor startup cycle error: {exc}")

    while True:
        try:
            now = datetime.now(IST)
            next_hour = next((h for h in ALL_RUN_HOURS if now.hour < h), None)

            if next_hour is None:
                # Past 8 PM — sleep until 3 AM tomorrow
                tomorrow = (now + timedelta(days=1)).replace(
                    hour=3, minute=0, second=0, microsecond=0
                )
                sleep_seconds = (tomorrow - now).total_seconds()
                next_hour = 3
            else:
                next_run = now.replace(hour=next_hour, minute=0, second=0, microsecond=0)
                sleep_seconds = (next_run - now).total_seconds()

            logger.info(f"Ingestor: next run at {next_hour:02d}:00 IST in {sleep_seconds/3600:.1f}h")
            await asyncio.sleep(sleep_seconds)

            now_run = datetime.now(IST)
            if now_run.hour == CLEANUP_HOUR:
                await _run_cleanup_cycle()
            else:
                await _run_ingest_cycle()

        except asyncio.CancelledError:
            logger.info("Background news ingestor cancelled")
            raise
        except Exception as exc:
            logger.error(f"Background news ingestor error: {exc}")
            await asyncio.sleep(3600)  # 1h back-off on unexpected error


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    global _redis, _anthropic_client
    if REDIS_URL:
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
        logger.info("Redis client connected")
    else:
        logger.info("REDIS_URL not set — using in-memory affinity cache")
    _anthropic_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    logger.info("Anthropic client initialised")

    await db.users.create_index("email", unique=True)
    await db.articles.create_index("article_id")
    await db.reading_history.create_index(
        [("user_id", 1), ("article_id", 1)], unique=True
    )
    await db.poll_votes.create_index(
        [("poll_id", 1), ("user_id", 1)], unique=True
    )
    await db.article_likes.create_index(
        [("user_id", 1), ("article_id", 1)], unique=True
    )
    await db.article_dislikes.create_index(
        [("user_id", 1), ("article_id", 1)], unique=True
    )
    await db.user_sessions.create_index("expires_at", expireAfterSeconds=0)
    await db.developing_stories.create_index("story_id", unique=True)
    logger.info("MongoDB indexes created")

    # Upsert watched topics — updates title/theme/keywords, preserves article_ids
    for topic in WATCHED_TOPICS:
        await db.developing_stories.update_one(
            {"story_id": topic["story_id"]},
            {
                "$setOnInsert": {
                    "article_ids": [],
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                    "is_active": True,
                },
                "$set": {
                    "title": topic["title"],
                    "theme": topic["theme"],
                    "keywords": topic["keywords"],
                },
            },
            upsert=True,
        )
    logger.info(f"Developing stories: upserted {len(WATCHED_TOPICS)} watched topics")

    ingestor_task = asyncio.create_task(_background_news_ingestor())
    logger.info("Background news ingestor started")

    yield  # ── App is running ────────────────────────────────────────────────

    # ── Shutdown ─────────────────────────────────────────────────────────────
    ingestor_task.cancel()
    try:
        await ingestor_task
    except asyncio.CancelledError:
        pass
    client.close()
    if _redis:
        await _redis.aclose()
    await _anthropic_client.close()
    logger.info("Background news ingestor stopped; DB connection closed")


# Create the main app
app = FastAPI(lifespan=lifespan)

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ===================== RECOMMENDATION SCORE CACHE =====================
# Redis is used when REDIS_URL is set; otherwise falls back to an in-memory dict.
_affinity_cache: Dict[str, Any] = {}
_AFFINITY_CACHE_TTL_SEC: int = 300  # 5 minutes


async def _get_user_affinity_scores(user_id: str) -> dict:
    """
    Returns per-category scores from reading_history. Cached for 5 min.
    Shape: {"completion": {cat: 0-20}, "engagement": {cat: 0-20}}
    """
    if _redis:
        cached_json = await _redis.get(f"affinity:{user_id}")
        if cached_json:
            return json.loads(cached_json)
    else:
        cached = _affinity_cache.get(user_id)
        if cached and (time.time() - cached["ts"]) < _AFFINITY_CACHE_TTL_SEC:
            return cached["scores"]

    history_docs = await db.reading_history.find(
        {"user_id": user_id},
        {"_id": 0, "article_id": 1, "time_spent": 1, "completed": 1}
    ).to_list(1000)

    if not history_docs:
        empty = {"completion": {}, "engagement": {}, "comments": {}, "poll_votes": {}, "likes": {}, "dislikes": {}}
        if _redis:
            await _redis.setex(f"affinity:{user_id}", 300, json.dumps(empty))
        else:
            _affinity_cache[user_id] = {"scores": empty, "ts": time.time()}
        return empty

    article_ids = [h["article_id"] for h in history_docs]
    article_docs = await db.articles.find(
        {"article_id": {"$in": article_ids}},
        {"_id": 0, "article_id": 1, "category": 1, "reading_time_sec": 1}
    ).to_list(len(article_ids))
    article_map: Dict[str, dict] = {a["article_id"]: a for a in article_docs}

    completion_stats: Dict[str, dict] = {}
    engagement_stats: Dict[str, dict] = {}

    for h in history_docs:
        meta = article_map.get(h["article_id"])
        if not meta:
            continue
        cat = meta.get("category")
        if not cat:
            continue

        if cat not in completion_stats:
            completion_stats[cat] = {"total": 0, "completed": 0}
        completion_stats[cat]["total"] += 1
        if h.get("completed", False):
            completion_stats[cat]["completed"] += 1

        rts = meta.get("reading_time_sec", 0)
        if rts and rts > 0:
            ratio = min(h.get("time_spent", 0) / rts, 1.0)
            if cat not in engagement_stats:
                engagement_stats[cat] = {"total_ratio": 0.0, "count": 0}
            engagement_stats[cat]["total_ratio"] += ratio
            engagement_stats[cat]["count"] += 1

    completion_scores = {
        cat: (s["completed"] / s["total"]) * 20.0
        for cat, s in completion_stats.items() if s["total"] > 0
    }
    engagement_scores = {
        cat: (s["total_ratio"] / s["count"]) * 20.0
        for cat, s in engagement_stats.items() if s["count"] > 0
    }

    # ── Comments signal (1 comment → +3, 3+ → +10 per category) ─────────────
    comment_docs = await db.comments.find(
        {"user_id": user_id},
        {"_id": 0, "article_id": 1}
    ).to_list(5000)

    comment_article_counts: Dict[str, int] = {}
    for c in comment_docs:
        aid = c["article_id"]
        comment_article_counts[aid] = comment_article_counts.get(aid, 0) + 1

    comment_scores: Dict[str, float] = {}
    if comment_article_counts:
        comment_meta = await db.articles.find(
            {"article_id": {"$in": list(comment_article_counts)}},
            {"_id": 0, "article_id": 1, "category": 1}
        ).to_list(len(comment_article_counts))
        for a in comment_meta:
            cat = a.get("category")
            if not cat:
                continue
            count = comment_article_counts[a["article_id"]]
            comment_scores[cat] = max(
                comment_scores.get(cat, 0.0),
                10.0 if count >= 3 else count * 3.0
            )

    # ── Poll-vote signal (+5 per category where user has voted) ──────────────
    vote_docs = await db.poll_votes.find(
        {"user_id": user_id},
        {"_id": 0, "poll_id": 1}
    ).to_list(5000)

    poll_vote_scores: Dict[str, float] = {}
    if vote_docs:
        voted_poll_ids = list({v["poll_id"] for v in vote_docs})
        poll_meta = await db.polls.find(
            {"poll_id": {"$in": voted_poll_ids}},
            {"_id": 0, "article_id": 1}
        ).to_list(len(voted_poll_ids))
        voted_article_ids = [p["article_id"] for p in poll_meta if p.get("article_id")]
        if voted_article_ids:
            voted_article_meta = await db.articles.find(
                {"article_id": {"$in": voted_article_ids}},
                {"_id": 0, "category": 1}
            ).to_list(len(voted_article_ids))
            for a in voted_article_meta:
                cat = a.get("category")
                if cat:
                    poll_vote_scores[cat] = 5.0

    # ── Like signal (+8 per liked article's category, cap +20) ──────────────
    like_docs = await db.article_likes.find(
        {"user_id": user_id},
        {"_id": 0, "article_id": 1}
    ).to_list(5000)

    like_scores: Dict[str, float] = {}
    if like_docs:
        liked_article_ids = [d["article_id"] for d in like_docs]
        liked_article_meta = await db.articles.find(
            {"article_id": {"$in": liked_article_ids}},
            {"_id": 0, "category": 1}
        ).to_list(len(liked_article_ids))
        for a in liked_article_meta:
            cat = a.get("category")
            if cat:
                like_scores[cat] = min(like_scores.get(cat, 0.0) + 8.0, 20.0)

    # ── Dislike signal (-5 per disliked article's category, cap -10) ─────────
    dislike_docs = await db.article_dislikes.find(
        {"user_id": user_id},
        {"_id": 0, "article_id": 1}
    ).to_list(5000)

    dislike_scores: Dict[str, float] = {}
    if dislike_docs:
        disliked_article_ids = [d["article_id"] for d in dislike_docs]
        disliked_article_meta = await db.articles.find(
            {"article_id": {"$in": disliked_article_ids}},
            {"_id": 0, "category": 1}
        ).to_list(len(disliked_article_ids))
        for a in disliked_article_meta:
            cat = a.get("category")
            if cat:
                dislike_scores[cat] = max(dislike_scores.get(cat, 0.0) - 5.0, -10.0)

    scores = {
        "completion": completion_scores,
        "engagement": engagement_scores,
        "comments": comment_scores,
        "poll_votes": poll_vote_scores,
        "likes": like_scores,
        "dislikes": dislike_scores,
    }
    if _redis:
        await _redis.setex(f"affinity:{user_id}", 300, json.dumps(scores))
    else:
        _affinity_cache[user_id] = {"scores": scores, "ts": time.time()}
    return scores


def _score_article(
    article: dict,
    user_interests: List[str],
    affinity: dict,
    relevance_by_category: Dict[str, float],
    now: datetime
) -> float:
    """Score one article. Pure function — no I/O."""
    score = 0.0
    cat = article.get("category", "")

    # Signal 1: Category affinity (40 pts max)
    if cat and cat in user_interests:
        score += 20.0                                          # declared interest
    score += affinity.get("completion", {}).get(cat, 0.0)     # behaviour completion 0-20
    # (engagement handled by signal 2 below)

    # Signal 2: Engagement (20 pts max)
    score += affinity.get("engagement", {}).get(cat, 0.0)

    # Signal 3a: Comment engagement (+10 max: 1→+3, 3+→+10)
    score += affinity.get("comments", {}).get(cat, 0.0)

    # Signal 3b: Poll vote (+5)
    score += affinity.get("poll_votes", {}).get(cat, 0.0)

    # Signal 3c: Explicit like (+8/article, cap +20) and dislike (-5/article, cap -10)
    score += affinity.get("likes", {}).get(cat, 0.0)
    score += affinity.get("dislikes", {}).get(cat, 0.0)

    # Signal 4: Relevance feedback (±10 pts)
    if cat in relevance_by_category:
        avg = relevance_by_category[cat]
        if avg > 0.5:
            score += 10.0
        elif avg < 0.3:
            score -= 10.0

    # Signal 5: Freshness (10 pts max)
    published_at = article.get("published_at")
    if isinstance(published_at, str):
        try:
            published_at = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            published_at = None
    if published_at:
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        age_hours = (now - published_at).total_seconds() / 3600.0
        if age_hours <= 6:
            score += 10.0
        elif age_hours <= 24:
            score += 5.0

    # Signal 5: Discovery wildcard (10 pts, 20% probability)
    if random.random() < 0.20:
        score += 10.0

    return score


# ===================== MODELS =====================

class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    interests: List[str] = []
    onboarding_completed: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class UserSession(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    session_token: str
    expires_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Article(BaseModel):
    model_config = ConfigDict(extra="ignore")
    article_id: str = Field(default_factory=lambda: f"article_{uuid.uuid4().hex[:12]}")
    title: str
    description: str
    content: str
    what: str
    why: str
    context: str
    impact: str
    category: str
    subcategory: Optional[str] = None
    image_url: str
    source: str
    author: Optional[str] = None
    published_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_developing: bool = False
    is_breaking: bool = False
    likes: int = 0
    dislikes: int = 0
    view_count: int = 0

class Poll(BaseModel):
    model_config = ConfigDict(extra="ignore")
    poll_id: str = Field(default_factory=lambda: f"poll_{uuid.uuid4().hex[:12]}")
    article_id: str
    question: str
    options: List[str]
    votes: Dict[str, int] = {}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Comment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    comment_id: str = Field(default_factory=lambda: f"comment_{uuid.uuid4().hex[:12]}")
    article_id: str
    user_id: str
    user_name: str
    user_picture: Optional[str] = None
    content: str
    stance: str  # "agree" or "disagree"
    likes: int = 0
    agrees: int = 0
    disagrees: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Bookmark(BaseModel):
    model_config = ConfigDict(extra="ignore")
    bookmark_id: str = Field(default_factory=lambda: f"bookmark_{uuid.uuid4().hex[:12]}")
    user_id: str
    article_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ReadingHistory(BaseModel):
    model_config = ConfigDict(extra="ignore")
    history_id: str = Field(default_factory=lambda: f"history_{uuid.uuid4().hex[:12]}")
    user_id: str
    article_id: str
    time_spent: int = 0  # seconds
    completed: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message_id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:12]}")
    session_id: str
    user_id: str
    article_id: str
    role: str  # "user" or "assistant"
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# ===================== REQUEST/RESPONSE MODELS =====================

class InterestsUpdate(BaseModel):
    interests: List[str]

class ArticleInteraction(BaseModel):
    action: str  # "like", "dislike", "view"

class PollVote(BaseModel):
    option: str

class CommentCreate(BaseModel):
    content: str
    stance: str

class AskAIRequest(BaseModel):
    message: str
    article_id: str

class RelevanceFeedback(BaseModel):
    article_id: str
    is_relevant: bool

# ===================== SAMPLE NEWS DATA =====================

SAMPLE_ARTICLES = [
    {
        "article_id": "article_india001",
        "title": "India's Chandrayaan-4 Mission Set to Launch in 2026, ISRO Announces Lunar Sample Return",
        "description": "ISRO confirms ambitious lunar sample return mission, positioning India as fourth nation to achieve this milestone",
        "content": "The Indian Space Research Organisation (ISRO) has officially announced that the Chandrayaan-4 mission is on track for a 2026 launch. This ambitious mission aims to bring back lunar soil samples to Earth, a feat only achieved by the USA, Russia, and China so far. The mission will involve multiple spacecraft working in tandem - an orbiter, lander, ascender, and a transfer module.",
        "what": "ISRO announces Chandrayaan-4 lunar sample return mission scheduled for 2026, involving four spacecraft modules working together.",
        "why": "India seeks to join elite club of nations that have returned lunar samples, advancing scientific research and demonstrating technological prowess.",
        "context": "Following the historic success of Chandrayaan-3's soft landing in 2023, India has accelerated its space ambitions. The global space race has intensified with China's Chang'e missions and NASA's Artemis program.",
        "impact": "Success would establish India as a major space power, boost domestic space industry, attract international collaborations, and provide valuable lunar samples for scientific research.",
        "category": "Science",
        "subcategory": "Space",
        "image_url": "https://images.unsplash.com/photo-1446776811953-b23d57bd21aa?w=800",
        "source": "ISRO Press Release",
        "author": "Science Desk",
        "is_developing": True,
        "is_breaking": False
    },
    {
        "article_id": "article_india002",
        "title": "Union Budget 2026: Finance Minister Proposes ₹15 Lakh Crore Infrastructure Push",
        "description": "Massive capital expenditure plan targets roads, railways, and digital infrastructure across tier-2 and tier-3 cities",
        "content": "In a significant boost to India's infrastructure development, the Finance Minister unveiled a ₹15 lakh crore capital expenditure plan for FY2026-27. The budget prioritizes connectivity in tier-2 and tier-3 cities, with major allocations for highways, dedicated freight corridors, and 5G expansion. The government also announced tax incentives for semiconductor manufacturing units.",
        "what": "Union Budget allocates record ₹15 lakh crore for infrastructure development, focusing on smaller cities and digital connectivity.",
        "why": "To accelerate economic growth, create employment, reduce urban-rural divide, and position India as a global manufacturing hub.",
        "context": "India aims to become a $5 trillion economy. Infrastructure development is crucial for attracting foreign investment and boosting domestic manufacturing under Make in India initiative.",
        "impact": "Expected to create 50 lakh jobs, boost GDP growth by 0.5%, improve logistics efficiency, and accelerate urbanization of tier-2/3 cities.",
        "category": "Business",
        "subcategory": "Economy",
        "image_url": "https://images.unsplash.com/photo-1526304640581-d334cdbbf45e?w=800",
        "source": "Ministry of Finance",
        "author": "Economy Bureau",
        "is_developing": False,
        "is_breaking": True
    },
    {
        "article_id": "article_india003",
        "title": "India vs Australia: Rohit Sharma's Men Eye Historic Series Win at Gabba",
        "description": "After dramatic Adelaide victory, Team India enters Brisbane Test with 2-1 series lead",
        "content": "The Indian cricket team arrives at the Gabba with momentum on their side following a thrilling 4-wicket victory in Adelaide. Captain Rohit Sharma's tactical acumen and Jasprit Bumrah's lethal bowling have been instrumental in the series lead. The Gabba, historically a fortress for Australia, witnessed India's breakthrough victory in 2021, and the team aims to recreate that magic.",
        "what": "India leads Border-Gavaskar Trophy 2-1 heading into the crucial Gabba Test, seeking to seal historic series victory.",
        "why": "A series win in Australia would cement India's dominance in Test cricket and continue their remarkable overseas success story.",
        "context": "India's 2021 Gabba triumph remains one of cricket's greatest upsets. Australia hasn't lost a Test series at home since that defeat, making this contest highly anticipated.",
        "impact": "Victory would secure World Test Championship final spot, boost Indian cricket's global standing, and continue Australia's home struggles against India.",
        "category": "Sports",
        "subcategory": "Cricket",
        "image_url": "https://images.unsplash.com/photo-1531415074968-036ba1b575da?w=800",
        "source": "Sports Correspondent",
        "author": "Cricket Desk",
        "is_developing": True,
        "is_breaking": False
    },
    {
        "article_id": "article_india004",
        "title": "Supreme Court Upholds Privacy Rights in Landmark Data Protection Ruling",
        "description": "Verdict strengthens individual rights under Digital Personal Data Protection Act",
        "content": "In a landmark judgment, the Supreme Court of India has reinforced the fundamental right to privacy in the digital age. The five-judge constitutional bench ruled that citizens have absolute right to know how their personal data is being used by both government and private entities. The ruling comes as the Digital Personal Data Protection Act enters its implementation phase.",
        "what": "Supreme Court delivers historic ruling strengthening data privacy rights, mandating transparency from data collectors.",
        "why": "To protect citizens from surveillance overreach and corporate data exploitation in an increasingly digital economy.",
        "context": "The judgment builds on the 2017 Puttaswamy case that recognized privacy as a fundamental right. India's digital population of 800 million makes data protection crucial.",
        "impact": "Tech companies must overhaul data practices, government surveillance faces new constraints, citizens gain stronger legal recourse against data misuse.",
        "category": "Politics",
        "subcategory": "Judiciary",
        "image_url": "https://images.unsplash.com/photo-1589829545856-d10d557cf95f?w=800",
        "source": "Legal Correspondent",
        "author": "Law Bureau",
        "is_developing": False,
        "is_breaking": True
    },
    {
        "article_id": "article_india005",
        "title": "Bengaluru Startup Develops Indigenous AI Chip, Challenges Global Giants",
        "description": "Homegrown semiconductor company secures $200M funding for AI accelerator manufacturing",
        "content": "A Bengaluru-based startup has achieved a significant breakthrough in developing an indigenous AI accelerator chip that promises to compete with offerings from NVIDIA and AMD. The company has secured $200 million in Series C funding led by global venture capital firms. The chip, designed specifically for edge AI applications, offers 40% better power efficiency than existing solutions.",
        "what": "Indian startup develops indigenous AI chip with superior power efficiency, raises $200M for manufacturing scale-up.",
        "why": "To reduce India's dependence on imported semiconductors and establish presence in the strategic AI hardware market.",
        "context": "Global chip shortage and geopolitical tensions have highlighted the need for semiconductor self-reliance. India's semiconductor mission aims to create a $55 billion industry by 2030.",
        "impact": "Could position India in global AI supply chain, create high-tech jobs, reduce import dependency, and boost national security in critical tech sectors.",
        "category": "Technology",
        "subcategory": "Startups",
        "image_url": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=800",
        "source": "Tech Reporter",
        "author": "Startup Desk",
        "is_developing": True,
        "is_breaking": False
    },
    {
        "article_id": "article_india006",
        "title": "Monsoon Session: Parliament Passes Women's Reservation Bill with 2/3 Majority",
        "description": "Historic legislation guarantees 33% seats for women in Lok Sabha and State Assemblies",
        "content": "In a historic moment for Indian democracy, Parliament has passed the Women's Reservation Bill with overwhelming support from across party lines. The constitutional amendment guarantees 33% reservation for women in the Lok Sabha and all State Legislative Assemblies. The bill, first introduced in 1996, finally becomes law after nearly three decades of debate and deliberation.",
        "what": "Parliament passes Women's Reservation Bill guaranteeing 33% seats for women in legislative bodies with over 2/3 majority.",
        "why": "To address chronic underrepresentation of women in Indian politics and ensure gender-balanced governance.",
        "context": "Women currently hold only 15% of Lok Sabha seats. The bill has been a pending demand since 1996, blocked repeatedly due to political disagreements.",
        "impact": "Will transform Indian political landscape, potentially adding 180+ women MPs, influence policy priorities toward education, health, and social welfare.",
        "category": "Politics",
        "subcategory": "Parliament",
        "image_url": "https://images.unsplash.com/photo-1529107386315-e1a2ed48a620?w=800",
        "source": "Parliamentary Bureau",
        "author": "Political Editor",
        "is_developing": False,
        "is_breaking": True
    },
    {
        "article_id": "article_india007",
        "title": "Mumbai Metro Phase 3 Opens: India's Longest Underground Corridor Transforms City Commute",
        "description": "33.5 km underground metro connects Colaba to SEEPZ, expected to serve 2 million daily",
        "content": "Mumbai has inaugurated India's longest underground metro corridor, stretching 33.5 kilometers from Colaba in the south to SEEPZ in the north. The ₹37,000 crore project features 27 stations, including the country's deepest at 32 meters below sea level. Advanced signaling technology allows trains every 3 minutes during peak hours.",
        "what": "Mumbai Metro Phase 3, India's longest underground corridor at 33.5 km with 27 stations, begins commercial operations.",
        "why": "To decongest Mumbai's overburdened suburban railways and roads, reducing commute times by up to 60%.",
        "context": "Mumbai's existing transport infrastructure serves 80 lakh daily commuters under extreme capacity stress. The city has long needed mass rapid transit alternatives.",
        "impact": "Will reduce commute times, decrease road accidents, lower carbon emissions, boost property values along corridor, and set precedent for other cities.",
        "category": "Technology",
        "subcategory": "Infrastructure",
        "image_url": "https://images.unsplash.com/photo-1544620347-c4fd4a3d5957?w=800",
        "source": "Metro Rail Corporation",
        "author": "Infrastructure Desk",
        "is_developing": False,
        "is_breaking": False
    },
    {
        "article_id": "article_india008",
        "title": "Reliance Jio and Starlink Partnership: Satellite Internet to Reach Remote India",
        "description": "Landmark deal aims to provide high-speed internet to 100,000 villages by 2027",
        "content": "Reliance Jio has announced a strategic partnership with SpaceX's Starlink to bring satellite-based internet connectivity to India's most remote regions. The collaboration will deploy low-earth orbit satellite internet in areas where traditional telecom infrastructure is unviable. The first phase targets 100,000 villages across Northeast India, Himachal Pradesh, and island territories.",
        "what": "Jio partners with Starlink to deploy satellite internet across 100,000 remote Indian villages lacking telecom infrastructure.",
        "why": "To bridge India's digital divide, bringing internet access to geographically challenging regions not covered by fiber or cellular networks.",
        "context": "Over 25,000 villages in India still lack any internet connectivity. Satellite internet has emerged as the only viable solution for extremely remote areas.",
        "impact": "Will enable e-governance, telemedicine, online education in remote areas; unlock economic opportunities; strengthen national integration of border regions.",
        "category": "Technology",
        "subcategory": "Telecom",
        "image_url": "https://images.unsplash.com/photo-1516849841032-87cbac4d88f7?w=800",
        "source": "Telecom Correspondent",
        "author": "Tech Bureau",
        "is_developing": True,
        "is_breaking": False
    },
    {
        "article_id": "article_india009",
        "title": "RBI Holds Rates Steady, Signals Cautious Approach Amid Global Uncertainty",
        "description": "Repo rate unchanged at 6.5% for eighth consecutive meeting as inflation concerns ease",
        "content": "The Reserve Bank of India has maintained the repo rate at 6.5% for the eighth consecutive monetary policy meeting. Governor Shaktikanta Das cited stable domestic inflation, which has returned within the 4% target, while highlighting global economic uncertainties including US tariff policies and geopolitical tensions. GDP growth forecast remains at 7.2% for FY26.",
        "what": "RBI keeps repo rate unchanged at 6.5%, maintains accommodative stance while monitoring global economic conditions.",
        "why": "Balanced approach to support growth while ensuring inflation remains within target range amid global uncertainties.",
        "context": "Indian economy shows resilient growth despite global slowdown. Inflation has moderated from peaks of 7%+ to current 4.2%, within RBI's comfort zone.",
        "impact": "Home loan EMIs remain stable, business borrowing costs unchanged, rupee stability supported, foreign investor confidence maintained.",
        "category": "Business",
        "subcategory": "Banking",
        "image_url": "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=800",
        "source": "RBI Press Release",
        "author": "Banking Editor",
        "is_developing": False,
        "is_breaking": False
    },
    {
        "article_id": "article_india010",
        "title": "Indian Cinema Sweeps International Film Festival: 'The Last Light' Wins Palme d'Or",
        "description": "Director Anurag Kashyap's meditation on partition makes history at Cannes",
        "content": "Indian cinema has achieved its highest international honor as 'The Last Light', directed by Anurag Kashyap, won the prestigious Palme d'Or at the Cannes Film Festival. The film, a poetic exploration of partition memories told through three generations, features breakthrough performances and stunning cinematography. This marks the first Palme d'Or for an Indian production.",
        "what": "Indian film 'The Last Light' wins Cannes Palme d'Or, becoming the first Indian production to receive cinema's highest honor.",
        "why": "Recognition of Indian cinema's artistic evolution and ability to tell universal stories with cultural authenticity.",
        "context": "Indian films have won awards at Cannes before, but never the top prize. This victory comes amid a renaissance in Indian independent cinema.",
        "impact": "Global spotlight on Indian cinema, increased international distribution opportunities, inspiration for independent filmmakers, cultural soft power boost.",
        "category": "Entertainment",
        "subcategory": "Cinema",
        "image_url": "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=800",
        "source": "Entertainment Correspondent",
        "author": "Film Desk",
        "is_developing": False,
        "is_breaking": True
    },
    {
        "article_id": "article_india011",
        "title": "Climate Alert: Northern India Faces Unprecedented Heat Wave, Delhi Crosses 48°C",
        "description": "IMD issues red alert across 12 states; schools closed, power grid under stress",
        "content": "Northern India is experiencing an unprecedented heat wave with temperatures breaching 48°C in Delhi NCR. The India Meteorological Department has issued red alerts across 12 states, advising residents to avoid outdoor activities. Power demand has surged 25% above normal, straining the grid. Hospitals report surge in heat stroke cases, prompting government to set up cooling centers.",
        "what": "Extreme heat wave grips North India with temperatures exceeding 48°C; IMD issues red alerts for 12 states.",
        "why": "Climate change-induced extreme weather events becoming more frequent and intense across the subcontinent.",
        "context": "India has witnessed increasingly severe summers over the past decade. Scientific studies link this to global warming and urban heat island effects.",
        "impact": "Public health emergency in affected regions, agricultural losses, power crisis, economic productivity decline, heightened focus on climate action.",
        "category": "Science",
        "subcategory": "Climate",
        "image_url": "https://images.unsplash.com/photo-1504701954957-2010ec3bcec1?w=800",
        "source": "IMD Bulletin",
        "author": "Environment Desk",
        "is_developing": True,
        "is_breaking": True
    },
    {
        "article_id": "article_india012",
        "title": "UPI Crosses 20 Billion Monthly Transactions, India Leads Global Digital Payments",
        "description": "NPCI reports record digital payment volumes as India's fintech ecosystem matures",
        "content": "India's Unified Payments Interface (UPI) has crossed a historic milestone of 20 billion monthly transactions, cementing the country's position as the global leader in real-time digital payments. The achievement represents a 40% year-on-year growth, with transaction value exceeding ₹20 lakh crore. International adoption has expanded with UPI now operational in 15 countries.",
        "what": "UPI achieves 20 billion monthly transactions milestone, with ₹20 lakh crore transaction value and expansion to 15 countries.",
        "why": "Result of India's digital payments infrastructure investment, smartphone penetration, and policy support for cashless economy.",
        "context": "UPI launched in 2016 and has since become the backbone of India's digital economy, far surpassing similar systems in developed nations.",
        "impact": "Financial inclusion for millions, reduced cash handling costs, model for other nations, boost to fintech startups, transparent economic tracking.",
        "category": "Technology",
        "subcategory": "Fintech",
        "image_url": "https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?w=800",
        "source": "NPCI Report",
        "author": "Fintech Correspondent",
        "is_developing": False,
        "is_breaking": False
    }
]

SAMPLE_POLLS = [
    {
        "poll_id": "poll_001",
        "article_id": "article_india001",
        "question": "Should India prioritize lunar exploration over Mars missions?",
        "options": ["Yes, Moon first", "No, Mars is the future", "Both equally", "Neither, focus on Earth"],
        "votes": {"Yes, Moon first": 234, "No, Mars is the future": 156, "Both equally": 312, "Neither, focus on Earth": 45}
    },
    {
        "poll_id": "poll_002",
        "article_id": "article_india002",
        "question": "What should be the top priority for infrastructure spending?",
        "options": ["Roads & Highways", "Railways", "Digital Infrastructure", "Urban Development"],
        "votes": {"Roads & Highways": 189, "Railways": 267, "Digital Infrastructure": 312, "Urban Development": 198}
    },
    {
        "poll_id": "poll_003",
        "article_id": "article_india003",
        "question": "Will India win the Border-Gavaskar Trophy 2024-25?",
        "options": ["Yes, 3-1 or better", "Yes, 2-1", "Draw 2-2", "No, Australia wins"],
        "votes": {"Yes, 3-1 or better": 445, "Yes, 2-1": 312, "Draw 2-2": 189, "No, Australia wins": 123}
    },
    {
        "poll_id": "poll_004",
        "article_id": "article_india006",
        "question": "Will Women's Reservation significantly improve governance?",
        "options": ["Yes, transformative change", "Somewhat helpful", "Too early to tell", "No significant impact"],
        "votes": {"Yes, transformative change": 534, "Somewhat helpful": 267, "Too early to tell": 189, "No significant impact": 78}
    }
]

INTEREST_CATEGORIES = {
    "Politics": ["Parliament", "Elections", "Judiciary", "International Relations", "State Politics"],
    "Technology": ["AI & ML", "Startups", "Gadgets", "Fintech", "Space Tech", "Telecom"],
    "Business": ["Markets", "Economy", "Startups", "Real Estate", "Banking", "Corporate"],
    "Sports": ["Cricket", "Football", "Tennis", "Olympics", "Kabaddi", "Motorsport"],
    "Entertainment": ["Bollywood", "OTT", "Music", "Television", "Regional Cinema"],
    "Science": ["Space", "Health", "Environment", "Research", "Climate"],
    "World": ["USA", "China", "Europe", "Middle East", "Southeast Asia"],
    "Lifestyle": ["Travel", "Food", "Fashion", "Wellness", "Automobiles"]
}

# ===================== AUTHENTICATION =====================

async def get_session_from_request(request: Request) -> Optional[dict]:
    """Extract and validate session from cookies or header"""
    session_token = request.cookies.get("session_token")
    if not session_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            session_token = auth_header.split(" ")[1]
    
    if not session_token:
        return None
    
    session_doc = await db.user_sessions.find_one(
        {"session_token": session_token},
        {"_id": 0}
    )
    
    if not session_doc:
        return None
    
    expires_at = session_doc["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        return None
    
    return session_doc

async def get_current_user(request: Request) -> Optional[dict]:
    """Get current user from session"""
    session = await get_session_from_request(request)
    if not session:
        return None
    
    user = await db.users.find_one(
        {"user_id": session["user_id"]},
        {"_id": 0}
    )
    return user

async def require_auth(request: Request) -> dict:
    """Dependency that requires authentication"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user

# ===================== AUTH ROUTES =====================

@api_router.post("/auth/google")
async def google_auth(request: Request, response: Response):
    """Exchange Google OAuth authorization code for a session token"""
    body = await request.json()
    code = body.get("code")
    redirect_uri = body.get("redirect_uri")

    if not code or not redirect_uri:
        raise HTTPException(status_code=400, detail="code and redirect_uri required")

    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")

    async with httpx.AsyncClient() as http:
        # Exchange authorization code for tokens
        token_resp = await http.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            logger.error(f"Google token exchange failed: {token_resp.text}")
            raise HTTPException(status_code=401, detail="Failed to exchange code with Google")

        tokens = token_resp.json()
        access_token = tokens.get("access_token")

        # Fetch user profile from Google
        userinfo_resp = await http.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_resp.status_code != 200:
            logger.error(f"Google userinfo failed: {userinfo_resp.text}")
            raise HTTPException(status_code=401, detail="Failed to fetch user info from Google")

        google_user = userinfo_resp.json()

    user_id = f"user_{uuid.uuid4().hex[:12]}"
    session_token = f"st_{uuid.uuid4().hex}"
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    # Upsert user — match on verified Google email
    existing_user = await db.users.find_one(
        {"email": google_user["email"]},
        {"_id": 0}
    )

    if existing_user:
        user_id = existing_user["user_id"]
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "name": google_user.get("name"),
                "picture": google_user.get("picture"),
            }}
        )
    else:
        new_user = {
            "user_id": user_id,
            "email": google_user["email"],
            "name": google_user.get("name"),
            "picture": google_user.get("picture"),
            "interests": [],
            "onboarding_completed": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(new_user)

    session_doc = {
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.user_sessions.insert_one(session_doc)

    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=7 * 24 * 60 * 60,
    )

    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return {"user": user, "session_token": session_token}

_NATIVE_REDIRECT_URI = "https://chintangithubio-production.up.railway.app/api/auth/native-callback"
_NATIVE_APP_SCHEME  = "com.chintan.app://auth/callback"
# In-memory cache: state → {session_token, expires_at}  (5-min TTL, cleared on retrieval)
_native_auth_cache: dict = {}

@api_router.get("/auth/native-callback")
async def google_native_callback(
    code: str = None,
    state: str = None,
    error: str = None,
):
    """
    Google OAuth relay for the Capacitor Android app.
    Google redirects here (https://), we exchange the code and redirect
    back to the app via the custom scheme com.chintan.app://auth/callback.
    Add this URL to Google Cloud Console → OAuth client → Authorised redirect URIs:
      https://chintangithubio-production.up.railway.app/api/auth/native-callback
    """
    try:
        if error or not code:
            logger.warning(f"native-callback: error={error} code_present={bool(code)}")
            return RedirectResponse(url=f"{_NATIVE_APP_SCHEME}?error=access_denied")

        if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
            logger.error("native-callback: GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET not set")
            return RedirectResponse(url=f"{_NATIVE_APP_SCHEME}?error=server_misconfigured")

        async with httpx.AsyncClient(timeout=15.0) as http:
            token_resp = await http.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": _NATIVE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )
            if token_resp.status_code != 200:
                logger.error(f"Native OAuth token exchange failed: {token_resp.text}")
                return RedirectResponse(url=f"{_NATIVE_APP_SCHEME}?error=token_exchange_failed")

            tokens = token_resp.json()
            access_token = tokens.get("access_token")
            if not access_token:
                logger.error(f"Native OAuth: no access_token in response: {tokens}")
                return RedirectResponse(url=f"{_NATIVE_APP_SCHEME}?error=no_access_token")

            userinfo_resp = await http.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if userinfo_resp.status_code != 200:
                logger.error(f"Native OAuth userinfo failed: {userinfo_resp.text}")
                return RedirectResponse(url=f"{_NATIVE_APP_SCHEME}?error=userinfo_failed")

            google_user = userinfo_resp.json()
            logger.info(f"Native OAuth userinfo keys: {list(google_user.keys())}")

        email = google_user.get("email")
        if not email:
            logger.error(f"Native OAuth: no email in userinfo: {google_user}")
            return RedirectResponse(url=f"{_NATIVE_APP_SCHEME}?error=no_email")

        user_id = f"user_{uuid.uuid4().hex[:12]}"
        session_token = f"st_{uuid.uuid4().hex}"
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)

        existing_user = await db.users.find_one({"email": email}, {"_id": 0})
        if existing_user:
            user_id = existing_user["user_id"]
            await db.users.update_one(
                {"user_id": user_id},
                {"$set": {"name": google_user.get("name"), "picture": google_user.get("picture")}},
            )
        else:
            await db.users.insert_one({
                "user_id": user_id,
                "email": email,
                "name": google_user.get("name"),
                "picture": google_user.get("picture"),
                "interests": [],
                "onboarding_completed": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

        await db.user_sessions.insert_one({
            "user_id": user_id,
            "session_token": session_token,
            "expires_at": expires_at.isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        # Store session_token in memory cache keyed by state so the app can poll for it.
        # This is the fallback path when the deep link redirect doesn't fire.
        if state:
            _native_auth_cache[state] = {
                "session_token": session_token,
                "expires_at": time.time() + 300,  # 5-minute TTL
            }

        logger.info(f"native-callback: success for {email}, redirecting to app scheme")
        # Pass state back so the app can verify the CSRF nonce it stored in sessionStorage
        state_param = f"&state={state}" if state else ""
        return RedirectResponse(
            url=f"{_NATIVE_APP_SCHEME}?session_token={session_token}{state_param}"
        )

    except Exception as e:
        logger.error(f"native-callback CRASH: {traceback.format_exc()}")
        return RedirectResponse(url=f"{_NATIVE_APP_SCHEME}?error=server_error")


@api_router.get("/auth/native-poll")
async def native_poll(state: str = None):
    """
    Polling endpoint for native OAuth fallback.
    The Android app polls this with the CSRF state every 2 s after opening the browser.
    Returns the session_token once the backend relay has processed the OAuth code.
    One-time use: the cache entry is deleted on successful retrieval.
    """
    if not state:
        raise HTTPException(status_code=400, detail="state required")
    # Purge expired entries
    now = time.time()
    expired = [k for k, v in list(_native_auth_cache.items()) if v["expires_at"] < now]
    for k in expired:
        _native_auth_cache.pop(k, None)
    entry = _native_auth_cache.get(state)
    if not entry:
        raise HTTPException(status_code=404, detail="not ready")
    _native_auth_cache.pop(state, None)  # one-time use
    return {"session_token": entry["session_token"]}


@api_router.get("/auth/me")
async def get_me(request: Request):
    """Get current authenticated user"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

@api_router.post("/auth/logout")
async def logout(request: Request, response: Response):
    """Logout user"""
    session = await get_session_from_request(request)
    if session:
        await db.user_sessions.delete_one({"session_token": session["session_token"]})
    
    response.delete_cookie(key="session_token", path="/")
    return {"message": "Logged out"}

# ===================== USER ROUTES =====================

@api_router.put("/users/interests")
async def update_interests(interests_update: InterestsUpdate, user: dict = Depends(require_auth)):
    """Update user interests"""
    # Check if this is the first time completing onboarding
    was_onboarding_completed = user.get("onboarding_completed", False)
    
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "interests": interests_update.interests,
            "onboarding_completed": True
        }}
    )
    
    updated_user = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return updated_user

@api_router.get("/users/stats")
async def get_user_stats(user: dict = Depends(require_auth)):
    """Get user reading stats"""
    # Get reading history
    history = await db.reading_history.find(
        {"user_id": user["user_id"]},
        {"_id": 0}
    ).to_list(1000)
    
    total_time = sum(h.get("time_spent", 0) for h in history)
    articles_read = len(history)
    completed = sum(1 for h in history if h.get("completed", False))
    
    # Get bookmarks count
    bookmarks_count = await db.bookmarks.count_documents({"user_id": user["user_id"]})
    
    # Get category breakdown
    category_counts = {}
    for h in history:
        article = await db.articles.find_one({"article_id": h["article_id"]}, {"_id": 0})
        if article:
            cat = article.get("category", "Other")
            category_counts[cat] = category_counts.get(cat, 0) + 1
    
    return {
        "total_reading_time": total_time,
        "articles_read": articles_read,
        "articles_completed": completed,
        "bookmarks_count": bookmarks_count,
        "category_breakdown": category_counts
    }

@api_router.get("/users/weekly-report")
async def get_weekly_report(user: dict = Depends(require_auth)):
    """Generate weekly reading report"""
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    # Get reading history for last 7 days only
    history = await db.reading_history.find(
        {"user_id": user["user_id"], "created_at": {"$gte": seven_days_ago.isoformat()}},
        {"_id": 0}
    ).to_list(1000)
    
    total_time = sum(h.get("time_spent", 0) for h in history)
    articles_read = len(history)
    completed = sum(1 for h in history if h.get("completed", False))
    
    # Get bookmarks count
    bookmarks_count = await db.bookmarks.count_documents({"user_id": user["user_id"]})
    
    # Get category breakdown
    category_counts = {}
    for h in history:
        article = await db.articles.find_one({"article_id": h["article_id"]}, {"_id": 0})
        if article:
            cat = article.get("category", "Other")
            category_counts[cat] = category_counts.get(cat, 0) + 1
    
    top_category = max(category_counts.items(), key=lambda x: x[1])[0] if category_counts else None
    total_minutes = total_time // 60
    completion_rate = round((completed / articles_read) * 100) if articles_read > 0 else 0
    
    # Generate personalized summary
    insights = []
    
    if articles_read > 0:
        insights.append(f"You've engaged with {articles_read} articles this week, showing a healthy appetite for staying informed.")
    
    if total_minutes > 30:
        insights.append(f"With {total_minutes} minutes of reading, you're investing quality time in understanding the world around you.")
    elif total_minutes > 0:
        insights.append(f"You've spent {total_minutes} minutes reading. Consider setting aside a few more minutes each day for deeper engagement.")
    
    if top_category:
        insights.append(f"{top_category} has captured most of your attention. This focus helps you build expertise in areas that matter to you.")
    
    if completion_rate > 70:
        insights.append(f"With a {completion_rate}% completion rate, you're reading articles thoroughly rather than just skimming headlines.")
    elif articles_read > 0:
        insights.append(f"Your {completion_rate}% completion rate suggests room for deeper engagement. Try the collapsible sections for better understanding.")
    
    if bookmarks_count > 0:
        insights.append(f"You've saved {bookmarks_count} articles for later, building a personal knowledge library.")
    
    return {
        "summary": "\n\n".join(insights) if insights else "Start reading articles to generate your personalized weekly insights.",
        "stats": {
            "articlesRead": articles_read,
            "minutesSpent": total_minutes,
            "topCategory": top_category or "Not enough data",
            "completionRate": completion_rate
        }
    }

@api_router.get("/interests/categories")
async def get_interest_categories():
    """Get all interest categories with subcategories"""
    return INTEREST_CATEGORIES

# ===================== NEWS API CONFIG =====================

# Category mapping based on keywords in title/body
def detect_category(title: str, body: str) -> tuple:
    """Detect category from article content"""
    text = (title + " " + body).lower()
    
    category_keywords = {
        "Technology": ["tech", "ai", "software", "app", "digital", "computer", "startup", "innovation", "gadget", "smartphone", "internet", "cyber", "data", "cloud", "robot"],
        "Business": ["market", "stock", "economy", "finance", "investment", "company", "trade", "business", "revenue", "profit", "bank", "startup", "corporate", "ceo"],
        "Politics": ["government", "election", "minister", "parliament", "policy", "vote", "political", "congress", "senate", "law", "legislation", "president", "prime minister"],
        "Sports": ["cricket", "football", "tennis", "match", "player", "tournament", "team", "score", "championship", "olympic", "sports", "game", "league"],
        "Entertainment": ["movie", "film", "actor", "actress", "music", "singer", "celebrity", "bollywood", "hollywood", "show", "concert", "album", "award"],
        "Science": ["research", "scientist", "study", "discovery", "space", "nasa", "climate", "environment", "health", "medical", "vaccine", "experiment"],
        "World": ["international", "global", "foreign", "country", "nation", "war", "diplomatic", "united nations", "europe", "asia", "america"],
        "Lifestyle": ["food", "travel", "fashion", "wellness", "fitness", "recipe", "restaurant", "vacation", "style", "beauty", "home"]
    }
    
    for category, keywords in category_keywords.items():
        if any(kw in text for kw in keywords):
            return category, None
    
    return "World", None  # Default fallback

def clean_newsapi_text(text: str) -> str:
    """Strip NewsAPI truncation artifacts like '[+1234 chars]' and anything after."""
    if not text:
        return text
    return re.sub(r'\s*\[\+\d+\s*chars?\].*', '', text, flags=re.IGNORECASE).strip()


# Domains that consistently produce off-topic / non-India content.
# Articles from these domains are dropped regardless of keyword matches.
_BLACKLISTED_DOMAINS = {
    "whyevolutionistrue.com",
    "kdnuggets.com",
    "spektrum.de",
    "financialpost.com",
    "abc.net.au",
    "linkedin.com",
    "globenewswire.com",
    "hurriyetdailynews.com",
    "oilprice.com",
    "scilogs.spektrum.de",
    "consent.yahoo.com",
}

# Keywords used to filter out off-topic articles returned by the broad q=India query.
# An article passes if its title OR description contains at least one of these (case-insensitive).
_INDIA_RELEVANCE_KEYWORDS = [
    "india", "indian", "delhi", "mumbai", "chennai", "kolkata", "bangalore",
    "bengaluru", "hyderabad", "pune", "ahmedabad", "jaipur", "lucknow",
    "chandigarh", "bhopal", "patna", "bhubaneswar", "guwahati", "srinagar",
    "kashmir", "northeast", "modi", "bjp", "congress", "aap", "kejriwal",
    "rahul gandhi", "amit shah", "yogi", "mamata", "rupee", "inr", "sebi",
    "rbi", "nse", "bse", "sensex", "nifty", "adani", "tata", "reliance",
    "infosys", "tcs", "wipro", "hcl", "flipkart", "zomato", "swiggy",
    "paytm", "phonepe", "isro", "chandrayaan", "gaganyaan", "ipl", "bcci",
    "virat", "rohit", "dhoni", "sachin", "bumrah", "shubman", "jadeja",
    "test cricket", "odi", "t20", "bollywood", "hindi film", "tollywood",
    "ott", "netflix india", "hotstar", "amazon prime india", "aadhaar", "upi",
    "digital india", "make in india", "startup india", "gst", "income tax",
    "budget", "finance minister", "nirmala", "supreme court india", "high court",
    "cbi", "ed", "lokpal", "army", "air force", "navy", "lac", "loc",
    "pakistan", "china", "bangladesh", "sri lanka", "nepal", "maldives",
    "brics", "g20", "sco", "farmer", "msp", "agriculture", "kisan",
    "monsoon", "imd", "cyclone", "flood", "earthquake", "heatwave",
    "pollution", "aqi", "iit", "iim", "neet", "jee", "cbse", "ugc",
    "narayana murthy", "ratan tata", "mukesh ambani", "gautam adani",
    "hospital", "aiims", "vaccine", "dengue", "malaria", "tuberculosis",
    "cancer india",
]

# ── Developing-story topics ──────────────────────────────────────────────────
# Upserted into the developing_stories collection on startup.
# The background ingestor matches new articles against these keyword lists.
WATCHED_TOPICS = [
    {
        "story_id": "iran-us-war-2026",
        "title": "Iran–US Military Tensions 2026",
        "theme": "war",
        "keywords": [
            "iran", "us strike", "trump iran", "tehran", "nuclear deal",
            "sanctions iran", "middle east conflict", "pentagon iran",
            "missile strike", "islamic republic",
        ],
    },
    {
        "story_id": "india-pakistan-tensions-2026",
        "title": "India–Pakistan Tensions 2026",
        "theme": "war",
        "keywords": [
            "india pakistan", "loc", "kashmir tension", "ceasefire",
            "surgical strike", "islamabad", "pak army", "imf pakistan",
            "pakistan india", "border tension",
        ],
    },
    {
        "story_id": "ipl-2026",
        "title": "IPL 2026",
        "theme": "cricket",
        "keywords": [
            "ipl", "ipl 2026", "indian premier league", "rcb", "csk",
            "kkr", "srh", "pbks", "ipl season", "ipl match",
        ],
    },
]


async def fetch_from_newsapi() -> list:
    """Fetch Indian news from NewsAPI.org (/v2/everything with fresh sortBy=publishedAt)."""
    if not NEWSAPI_KEY:
        logger.warning("NEWSAPI_KEY not set — skipping NewsAPI fetch")
        return []

    logger.info("NewsAPI: key present, starting fetch")
    seen: dict = {}  # url → raw NewsAPI article, for deduplication

    async with httpx.AsyncClient(timeout=15.0) as client:
        # 1. Everything about India (broad keyword query), sorted by newest first
        _q = (
            "India AND ("
            "politics OR cricket OR business OR Modi OR BJP OR Congress OR RBI OR SEBI OR "
            "Sensex OR Rupee OR ISRO OR IPL OR Bollywood OR Kashmir OR Pakistan OR "
            "Adani OR Tata OR Reliance OR startup OR budget"
            ")"
        )
        try:
            resp = await client.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": _q,
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": 100,
                    "apiKey": NEWSAPI_KEY,
                },
            )
            logger.info(f"NewsAPI everything?q=India status={resp.status_code}")
            if resp.status_code == 200:
                articles_returned = resp.json().get("articles", [])
                logger.info(f"NewsAPI everything?q=India returned {len(articles_returned)} articles")
                for a in articles_returned:
                    url = a.get("url") or ""
                    if url and url not in seen:
                        seen[url] = a
            else:
                logger.warning(f"NewsAPI everything?q=India {resp.status_code}: {resp.text[:300]}")
        except Exception as e:
            logger.error(f"NewsAPI everything?q=India error: {e}")

        # 2. Latest from major Indian news domains
        try:
            resp = await client.get(
                "https://newsapi.org/v2/everything",
                params={
                    "domains": "thehindu.com,livemint.com,indianexpress.com,ndtv.com,hindustantimes.com,timesofindia.indiatimes.com,business-standard.com,financialexpress.com,scroll.in,thewire.in,deccanherald.com,telegraphindia.com,theprint.in,firstpost.com,outlookindia.com",
                    "sortBy": "publishedAt",
                    "pageSize": 100,
                    "apiKey": NEWSAPI_KEY,
                },
            )
            logger.info(f"NewsAPI everything?domains=indian-press status={resp.status_code}")
            if resp.status_code == 200:
                articles_returned = resp.json().get("articles", [])
                logger.info(f"NewsAPI everything?domains returned {len(articles_returned)} articles")
                for a in articles_returned:
                    url = a.get("url") or ""
                    if url and url not in seen:
                        seen[url] = a
            else:
                logger.warning(f"NewsAPI everything?domains {resp.status_code}: {resp.text[:300]}")
        except Exception as e:
            logger.error(f"NewsAPI everything?domains error: {e}")

    results = []
    for url, a in list(seen.items())[:200]:
        title = clean_newsapi_text((a.get("title") or "").strip())
        description = clean_newsapi_text((a.get("description") or "").strip())
        raw_content = clean_newsapi_text((a.get("content") or description).strip())
        source_name = (a.get("source") or {}).get("name") or "News Feed"
        published_at = a.get("publishedAt") or datetime.now(timezone.utc).isoformat()
        image_url = a.get("urlToImage") or "https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=800"

        if not title or title == "[Removed]":
            continue

        # Domain blacklist: drop known non-India domains unconditionally
        try:
            _domain = url.split("//", 1)[1].split("/")[0].lower().removeprefix("www.")
        except Exception:
            _domain = ""
        if _domain in _BLACKLISTED_DOMAINS:
            logger.debug(f"NewsAPI: dropped blacklisted domain {_domain}: {title[:60]}")
            continue

        # Relevance filter: drop articles unrelated to India
        _haystack = (title + " " + description).lower()
        if not any(kw in _haystack for kw in _INDIA_RELEVANCE_KEYWORDS):
            logger.debug(f"NewsAPI: dropped off-topic article: {title[:80]}")
            continue

        article_id = "article_" + hashlib.md5(url.encode()).hexdigest()[:12]
        category, subcategory = detect_category(title, description + " " + raw_content)

        sentences = (description + " " + raw_content).split(". ")
        what = (sentences[0] + ".") if sentences else title
        why = (sentences[1] + ".") if len(sentences) > 1 else f"An important development in {category.lower()}."
        context = (sentences[2] + ".") if len(sentences) > 2 else "This story reflects recent trends in the sector."
        impact = (sentences[3] + ".") if len(sentences) > 3 else "The implications may affect stakeholders across multiple domains."

        content = raw_content[:1500] + "..." if len(raw_content) > 1500 else raw_content

        is_recent = False
        is_breaking = False
        try:
            published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            hours_ago = (datetime.now(timezone.utc) - published).total_seconds() / 3600
            is_recent = hours_ago < 24
            is_breaking = hours_ago < 6
        except Exception:
            pass

        results.append({
            "article_id": article_id,
            "title": title,
            "description": description[:300] + "..." if len(description) > 300 else description,
            "content": content,
            "what": what[:500],
            "why": why[:500],
            "context": context[:500],
            "impact": impact[:500],
            "category": category,
            "subcategory": subcategory,
            "source": source_name,
            "author": a.get("author"),
            "published_at": published_at,
            "image_url": image_url,
            "is_developing": is_recent,
            "is_breaking": is_breaking,
            "likes": 0,
            "dislikes": 0,
            "view_count": 0,
            "reading_time_sec": max(5, len(raw_content.split()) // 200 * 60),
            "url": url,
        })

    logger.info(f"NewsAPI: fetched {len(results)} articles")
    return results

# ===================== ARTICLES ROUTES =====================

@api_router.get("/articles")
async def get_articles(
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    developing: Optional[bool] = None,
    limit: int = 20,
    page: int = 1,
    request: Request = None,
    refresh: bool = False
):
    """Get articles from DB with personalised scoring."""

    skip = (page - 1) * limit

    # Explicit query-param filters (always applied at DB level)
    query: dict = {}
    if category:
        query["category"] = category
    if subcategory:
        query["subcategory"] = subcategory
    if developing is not None:
        query["is_developing"] = developing

    # Only return articles from the last 7 days
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    query["published_at"] = {"$gte": seven_days_ago.isoformat()}

    user = await get_current_user(request) if request else None
    user_interests: List[str] = user.get("interests", []) if user else []

    # ── Unauthenticated path: sort by freshness only ──────────────────────────
    if not user or not user_interests:
        return await db.articles.find(query, {"_id": 0}).sort(
            "published_at", -1
        ).skip(skip).limit(limit).to_list(limit)

    # ── Authenticated path: fetch candidates, score, paginate ─────────────────
    CANDIDATE_LIMIT = max(200, skip + limit + 50)
    candidates = await db.articles.find(query, {"_id": 0}).sort(
        "published_at", -1
    ).limit(CANDIDATE_LIMIT).to_list(CANDIDATE_LIMIT)

    if not candidates:
        return []

    # 1. Category affinity + engagement (cached 5 min)
    affinity = await _get_user_affinity_scores(user["user_id"])

    # 2. Relevance feedback — aggregate avg(is_relevant) per category
    relevance_docs = await db.relevance_feedback.find(
        {"user_id": user["user_id"]},
        {"_id": 0, "article_id": 1, "is_relevant": 1}
    ).to_list(5000)

    # Build article_id→category map from candidates + any extras
    cat_map: Dict[str, str] = {
        a["article_id"]: a["category"]
        for a in candidates if a.get("category")
    }
    missing_ids = {d["article_id"] for d in relevance_docs} - set(cat_map)
    if missing_ids:
        extras = await db.articles.find(
            {"article_id": {"$in": list(missing_ids)}},
            {"_id": 0, "article_id": 1, "category": 1}
        ).to_list(len(missing_ids))
        for a in extras:
            if a.get("category"):
                cat_map[a["article_id"]] = a["category"]

    rel_accum: Dict[str, dict] = {}
    for doc in relevance_docs:
        cat = cat_map.get(doc["article_id"])
        if not cat:
            continue
        if cat not in rel_accum:
            rel_accum[cat] = {"total": 0.0, "count": 0}
        rel_accum[cat]["total"] += 1.0 if doc["is_relevant"] else 0.0
        rel_accum[cat]["count"] += 1

    relevance_by_category: Dict[str, float] = {
        cat: s["total"] / s["count"]
        for cat, s in rel_accum.items() if s["count"] > 0
    }

    # 3. Score every candidate, sort, paginate
    now = datetime.now(timezone.utc)
    scored = [
        (_score_article(a, user_interests, affinity, relevance_by_category, now), a)
        for a in candidates
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [a for _, a in scored[skip:skip + limit]]

@api_router.get("/articles/developing")
async def get_developing_stories():
    """Get developing/breaking stories"""
    articles = await db.articles.find(
        {"$or": [{"is_developing": True}, {"is_breaking": True}]},
        {"_id": 0}
    ).sort("published_at", -1).limit(10).to_list(10)
    return articles

@api_router.get("/articles/{article_id}")
async def get_article(article_id: str):
    """Get single article"""
    article = await db.articles.find_one({"article_id": article_id}, {"_id": 0})
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article

@api_router.get("/articles/{article_id}/reaction")
async def get_article_reaction(article_id: str, user: dict = Depends(require_auth)):
    """Return the current user's like/dislike state for an article."""
    article = await db.articles.find_one({"article_id": article_id}, {"_id": 0, "likes": 1, "dislikes": 1})
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    uid = user["user_id"]
    liked    = await db.article_likes.find_one({"user_id": uid, "article_id": article_id}) is not None
    disliked = await db.article_dislikes.find_one({"user_id": uid, "article_id": article_id}) is not None
    return {
        "liked": liked,
        "disliked": disliked,
        "likes_count": max(0, article.get("likes", 0)),
        "dislikes_count": max(0, article.get("dislikes", 0)),
    }

@api_router.post("/articles/{article_id}/interact")
async def interact_with_article(
    article_id: str,
    interaction: ArticleInteraction,
    user: dict = Depends(require_auth)
):
    """Like, dislike, or track view on article"""
    article = await db.articles.find_one({"article_id": article_id}, {"_id": 0})
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    if interaction.action == "like":
        uid, aid = user["user_id"], article_id
        already_liked    = await db.article_likes.find_one({"user_id": uid, "article_id": aid})
        already_disliked = await db.article_dislikes.find_one({"user_id": uid, "article_id": aid})

        if already_liked:
            # Toggle off
            await db.article_likes.delete_one({"user_id": uid, "article_id": aid})
            await db.articles.update_one({"article_id": aid}, {"$inc": {"likes": -1}})
        else:
            # Add like; remove any existing dislike
            await db.article_likes.insert_one({
                "user_id": uid, "article_id": aid,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            await db.articles.update_one({"article_id": aid}, {"$inc": {"likes": 1}})
            if already_disliked:
                await db.article_dislikes.delete_one({"user_id": uid, "article_id": aid})
                await db.articles.update_one({"article_id": aid}, {"$inc": {"dislikes": -1}})

        updated = await db.articles.find_one({"article_id": aid}, {"_id": 0, "likes": 1, "dislikes": 1})
        is_liked    = await db.article_likes.find_one({"user_id": uid, "article_id": aid}) is not None
        is_disliked = await db.article_dislikes.find_one({"user_id": uid, "article_id": aid}) is not None
        return {
            "liked": is_liked, "disliked": is_disliked,
            "likes_count": max(0, updated.get("likes", 0)),
            "dislikes_count": max(0, updated.get("dislikes", 0)),
        }

    elif interaction.action == "dislike":
        uid, aid = user["user_id"], article_id
        already_disliked = await db.article_dislikes.find_one({"user_id": uid, "article_id": aid})
        already_liked    = await db.article_likes.find_one({"user_id": uid, "article_id": aid})

        if already_disliked:
            # Toggle off
            await db.article_dislikes.delete_one({"user_id": uid, "article_id": aid})
            await db.articles.update_one({"article_id": aid}, {"$inc": {"dislikes": -1}})
        else:
            # Add dislike; remove any existing like
            await db.article_dislikes.insert_one({
                "user_id": uid, "article_id": aid,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            await db.articles.update_one({"article_id": aid}, {"$inc": {"dislikes": 1}})
            if already_liked:
                await db.article_likes.delete_one({"user_id": uid, "article_id": aid})
                await db.articles.update_one({"article_id": aid}, {"$inc": {"likes": -1}})

        updated = await db.articles.find_one({"article_id": aid}, {"_id": 0, "likes": 1, "dislikes": 1})
        is_liked    = await db.article_likes.find_one({"user_id": uid, "article_id": aid}) is not None
        is_disliked = await db.article_dislikes.find_one({"user_id": uid, "article_id": aid}) is not None
        return {
            "liked": is_liked, "disliked": is_disliked,
            "likes_count": max(0, updated.get("likes", 0)),
            "dislikes_count": max(0, updated.get("dislikes", 0)),
        }

    elif interaction.action == "view":
        await db.articles.update_one(
            {"article_id": article_id},
            {"$inc": {"view_count": 1}}
        )
        # Track in reading history
        existing_history = await db.reading_history.find_one({
            "user_id": user["user_id"],
            "article_id": article_id
        })
        if not existing_history:
            history_doc = {
                "history_id": f"history_{uuid.uuid4().hex[:12]}",
                "user_id": user["user_id"],
                "article_id": article_id,
                "time_spent": 0,
                "completed": False,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db.reading_history.insert_one(history_doc)
    
    return {"success": True}

@api_router.post("/articles/{article_id}/reading-time")
async def update_reading_time(
    article_id: str,
    request: Request,
    user: dict = Depends(require_auth)
):
    """Update reading time for article"""
    body = await request.json()
    time_spent = body.get("time_spent", 0)
    completed = body.get("completed", False)
    
    await db.reading_history.update_one(
        {"user_id": user["user_id"], "article_id": article_id},
        {
            "$inc": {"time_spent": time_spent},
            "$set": {"completed": completed}
        },
        upsert=True
    )
    return {"success": True}

# ===================== BRIEFS ROUTES =====================

@api_router.get("/briefs/{brief_type}")
async def get_brief(brief_type: str, request: Request = None):
    """Get morning/midday/night brief with Claude-generated narrative."""
    if brief_type not in ["morning", "midday", "night"]:
        raise HTTPException(status_code=400, detail="Invalid brief type")

    user = await get_current_user(request) if request else None
    user_interests: List[str] = (user.get("interests") or []) if user else []
    raw_name: str = (user.get("name") or "") if user else ""
    user_name = raw_name.split()[0] if raw_name else "there"

    _greetings = {
        "morning": ("Good Morning",  "while you were sleeping, we curated your morning brief"),
        "midday":  ("Good Afternoon", "while you were working, we were curating your tailored afternoon brief"),
        "night":   ("Good Evening",  "while you wound down, here's what shaped your world today"),
    }
    greeting, subtitle = _greetings[brief_type]

    category_query: dict = {"category": {"$in": user_interests}} if user_interests else {}

    # ── 1. Cascade: 24 h → 72 h → no time filter → drop interest filter ──────
    fresh_articles: list = []
    for hours in (24, 72):
        cutoff_str = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        fresh_articles = await db.articles.find(
            {"published_at": {"$gte": cutoff_str}, **category_query},
            {"_id": 0},
        ).sort("published_at", -1).to_list(300)
        if len(fresh_articles) >= 3:
            break

    if len(fresh_articles) < 3:
        # Drop the time window entirely, keep interest filter
        fresh_articles = await db.articles.find(
            category_query if category_query else {},
            {"_id": 0},
        ).sort("published_at", -1).to_list(50)

    if len(fresh_articles) < 3 and user_interests:
        # Last resort: ignore interests too
        fresh_articles = await db.articles.find(
            {}, {"_id": 0}
        ).sort("published_at", -1).to_list(50)

    # ── 2. Group by category, no minimum threshold ───────────────────────────
    by_category: Dict[str, list] = {}
    for a in fresh_articles:
        cat = a.get("category")
        if cat:
            by_category.setdefault(cat, []).append(a)

    if user_interests:
        ordered = [c for c in user_interests if c in by_category]
        ordered += [c for c in sorted(by_category, key=lambda x: len(by_category[x]), reverse=True)
                    if c not in ordered]
    else:
        ordered = sorted(by_category, key=lambda c: len(by_category[c]), reverse=True)

    top_cats = ordered[:3]

    # ── 3. Hard fallback — only if DB is completely empty ────────────────────
    if not top_cats:
        any_articles = await db.articles.find({}, {"_id": 0}).sort(
            "published_at", -1).limit(3).to_list(3)
        return {
            "greeting": greeting,
            "subtitle": subtitle,
            "summary": "No stories are available right now. Check back soon.",
            "referenced_stories": [
                {"title": a.get("title", ""), "source": a.get("source", ""),
                 "article_id": a.get("article_id", "")}
                for a in any_articles
            ],
            "read_time": "1 min read",
        }

    # ── 4. Up to 3 articles per category for Claude context ──────────────────
    cat_articles: Dict[str, list] = {cat: by_category[cat][:3] for cat in top_cats}

    referenced_stories = [
        {
            "title":      cat_articles[cat][0].get("title", ""),
            "source":     cat_articles[cat][0].get("source", ""),
            "article_id": cat_articles[cat][0].get("article_id", ""),
        }
        for cat in top_cats
    ]

    # ── 5. Build Claude prompt ────────────────────────────────────────────────
    articles_text = ""
    for cat in top_cats:
        for a in cat_articles[cat]:
            articles_text += (
                f"Category: {cat}\n"
                f"Title: {a.get('title', '')}\n"
                f"Summary: {a.get('what') or a.get('description') or ''}\n\n"
            )

    prompt = (
        f"You are writing a personalized {brief_type} brief for {user_name}.\n"
        f"Their top interests are: {', '.join(top_cats)}.\n"
        f"Here are today's top stories:\n\n{articles_text}"
        f"Write EXACTLY 3 sentences total — one sentence per category in this order: {', '.join(top_cats)}.\n"
        f"Each sentence covers exactly ONE specific story from that category.\n"
        f"Be specific: use actual names, places, and numbers from the articles.\n"
        f"RULES: No markdown (no #, no **). Maximum 90 words total.\n"
        f"Do NOT start with the user's name or any title like 'Your Night Brief' or '{user_name}'s Night Brief'. Start directly with the news content.\n"
        f"Each sentence must end with a period. Output only the 3 sentences, nothing else."
    )

    summary = ""
    try:
        msg = await _anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        summary = msg.content[0].text.strip()
    except Exception as e:
        logger.error(f"Brief Claude call failed: {e}")
        fallback_parts = []
        for cat in top_cats:
            a = cat_articles[cat][0]
            text = (a.get("what") or a.get("description") or a.get("title") or "").strip()
            first = text.split(".")[0].strip()
            if first:
                fallback_parts.append(first + ".")
        summary = " ".join(fallback_parts)

    # Strip markdown artifacts
    summary = re.sub(r'^#+\s*', '', summary, flags=re.MULTILINE)
    summary = summary.replace('**', '')
    # Strip greeting/brief-name prefixes that Claude sometimes adds
    summary = re.sub(r'^(Your\s+\w+\s+Brief[,:\s]+)', '', summary, flags=re.IGNORECASE)
    summary = re.sub(r'^(Good\s+(Morning|Evening|Afternoon)[,:\s]+)', '', summary, flags=re.IGNORECASE)
    # Strip known generic sign-off phrases
    for phrase in (
        "Stay informed, stay ahead",
        "That's your midday update",
        "Here's how the day unfolded",
        "Before you rest, here's today's story",
    ):
        summary = summary.replace(phrase, "").strip().rstrip(".")

    read_time = f"{max(1, round(len(summary.split()) / 200))} min read"

    return {
        "greeting":           greeting,
        "subtitle":           subtitle,
        "summary":            summary,
        "categories":         top_cats,
        "referenced_stories": referenced_stories,
        "read_time":          read_time,
    }

# ===================== AI ROUTES =====================

@api_router.post("/ai/ask")
async def ask_ai(ask_request: AskAIRequest, user: dict = Depends(require_auth)):
    """Ask AI about an article"""
    article = await db.articles.find_one({"article_id": ask_request.article_id}, {"_id": 0})
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="AI service not configured")

    session_id = f"chat_{user['user_id']}_{ask_request.article_id}"

    # Build context
    context = (
        "You are a news analyst for Chintan app. Answer questions about news articles concisely. Rules:\n"
        "- Maximum 120 words\n"
        "- Always respond in 2-4 bullet points\n"
        "- No markdown symbols like ##, **, $ or headers\n"
        "- Each bullet point starts with a simple dash (-)\n"
        "- Be specific, well-researched and directly address the question asked\n"
        "- No fluff or generic statements\n\n"
        f"Article Title: {article['title']}\n"
        f"Article Content: {article.get('content', '')}\n"
        f"What happened: {article.get('what', '')}\n"
        f"Why it matters: {article.get('why', '')}\n"
        f"Context: {article.get('context', '')}\n"
        f"Impact: {article.get('impact', '')}"
    )

    try:
        # Reconstruct multi-turn history from DB for this session
        history = await db.chat_messages.find(
            {"session_id": session_id},
            {"_id": 0, "role": 1, "content": 1}
        ).sort("created_at", 1).to_list(50)

        api_messages = [{"role": h["role"], "content": h["content"]} for h in history]
        api_messages.append({"role": "user", "content": ask_request.message})

        msg = await _anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=context,
            messages=api_messages,
        )
        response = msg.content[0].text
        
        # Save messages to DB
        user_msg_doc = {
            "message_id": f"msg_{uuid.uuid4().hex[:12]}",
            "session_id": session_id,
            "user_id": user["user_id"],
            "article_id": ask_request.article_id,
            "role": "user",
            "content": ask_request.message,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.chat_messages.insert_one(user_msg_doc)
        
        ai_msg_doc = {
            "message_id": f"msg_{uuid.uuid4().hex[:12]}",
            "session_id": session_id,
            "user_id": user["user_id"],
            "article_id": ask_request.article_id,
            "role": "assistant",
            "content": response,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.chat_messages.insert_one(ai_msg_doc)
        
        return {"response": response, "session_id": session_id}
    
    except Exception as e:
        logger.error(f"AI error: {e}")
        raise HTTPException(status_code=500, detail="AI service error")

@api_router.get("/ai/chat-history/{article_id}")
async def get_chat_history(article_id: str, user: dict = Depends(require_auth)):
    """Get chat history for an article"""
    session_id = f"chat_{user['user_id']}_{article_id}"
    history = await db.chat_messages.find(
        {"session_id": session_id},
        {"_id": 0}
    ).sort("created_at", 1).to_list(50)
    return history

@api_router.get("/ai/other-side/{article_id}")
async def get_other_side(article_id: str, user: dict = Depends(require_auth)):
    """Get alternative perspective on article"""
    article = await db.articles.find_one({"article_id": article_id}, {"_id": 0})
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    # Check cache
    cached = await db.other_side_cache.find_one({"article_id": article_id}, {"_id": 0})
    if cached:
        return {"analysis": cached["analysis"]}
    
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="AI service not configured")

    try:
        prompt = (
            "Give exactly 3 contrasting perspectives on this news article. "
            'Return as a JSON object with key "points" containing an array of 3 strings. '
            "Each point must be ONE sentence only, maximum 20 words. "
            "Total response must be under 70 words. No paragraphs, no elaboration. "
            f'Format: {{"points": ["point 1", "point 2", "point 3"]}}\n\n'
            f"Title: {article['title']}\n"
            f"Story: {article.get('content', '')[:800]}"
        )

        response = await _llm(
            system="You generate contrasting perspectives on news articles. Return only valid JSON, nothing else.",
            user_content=prompt,
            max_tokens=200,
        )

        # Normalise: strip markdown fences, extract JSON object
        raw_s = response.strip()
        if raw_s.startswith("```"):
            raw_s = raw_s.split("```")[1]
            if raw_s.startswith("json"):
                raw_s = raw_s[4:]
            raw_s = raw_s.strip()
        start = raw_s.find("{")
        end = raw_s.rfind("}") + 1
        analysis = raw_s[start:end] if start >= 0 and end > start else response

        # Cache result
        cache_doc = {
            "article_id": article_id,
            "analysis": analysis,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.other_side_cache.insert_one(cache_doc)

        return {"analysis": analysis}

    except Exception as e:
        logger.error(f"AI error: {e}")
        raise HTTPException(status_code=500, detail="AI service error")

@api_router.get("/ai/questions/{article_id}")
async def get_ai_questions(article_id: str):
    """Get AI-generated questions for article"""
    article = await db.articles.find_one({"article_id": article_id}, {"_id": 0})
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    # Check cache
    cached = await db.ai_questions_cache.find_one({"article_id": article_id}, {"_id": 0})
    if cached:
        return {"questions": cached["questions"]}
    
    if not ANTHROPIC_API_KEY:
        # Return default questions
        return {"questions": [
            "What are the immediate implications of this?",
            "Who benefits and who loses from this development?",
        ]}

    try:
        prompt = f"""Generate exactly 2 smart questions for this article that encourage deep thinking. Each question must be 15 words or fewer.

Title: {article['title']}
Summary: {article['description']}
Impact: {article['impact']}

Return only 2 questions, one per line, no numbering or bullet points."""

        response = await _llm(
            system="Generate 2 thought-provoking questions that encourage critical thinking about news articles. Each question must be 15 words or fewer. No numbering or bullet points.",
            user_content=prompt,
            max_tokens=128,
        )

        questions = [q.strip().lstrip('0123456789.-) ') for q in response.strip().split('\n') if q.strip()][:2]

        # Cache result
        cache_doc = {
            "article_id": article_id,
            "questions": questions,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.ai_questions_cache.insert_one(cache_doc)

        return {"questions": questions}

    except Exception as e:
        logger.error(f"AI error: {e}")
        return {"questions": [
            "What are the key takeaways from this?",
            "How might this affect you personally?",
        ]}

# ===================== POLLS ROUTES =====================

@api_router.get("/polls/{article_id}")
async def get_poll(article_id: str):
    """Get poll for article, generating one on-demand if it doesn't exist yet."""
    # Check DB first
    poll = await db.polls.find_one({"article_id": article_id}, {"_id": 0})
    if poll:
        return poll

    # Check sample polls
    for sample_poll in SAMPLE_POLLS:
        if sample_poll["article_id"] == article_id:
            await db.polls.insert_one({**sample_poll})
            return sample_poll

    # On-demand generation: fetch article and generate poll synchronously
    article = await db.articles.find_one(
        {"article_id": article_id},
        {"_id": 0, "article_id": 1, "title": 1, "description": 1},
    )
    if not article:
        return None

    logger.info(f"On-demand poll generation starting for {article_id}")
    try:
        await asyncio.wait_for(_generate_poll_for_article(article), timeout=10.0)
    except asyncio.TimeoutError:
        logger.warning(f"On-demand poll generation timed out for {article_id}")
        raise HTTPException(status_code=404, detail="Poll generation failed")
    except Exception as e:
        logger.error(f"On-demand poll generation failed for {article_id}: {e}")
        raise HTTPException(status_code=404, detail="Poll generation failed")

    poll = await db.polls.find_one({"article_id": article_id}, {"_id": 0})
    return poll

@api_router.post("/polls/{poll_id}/vote")
async def vote_poll(poll_id: str, vote: PollVote, user: dict = Depends(require_auth)):
    """Vote on a poll"""
    poll = await db.polls.find_one({"poll_id": poll_id}, {"_id": 0})
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    
    # Check if poll is expired (7 days)
    if poll.get("created_at"):
        created = datetime.fromisoformat(poll["created_at"].replace('Z', '+00:00')) if isinstance(poll["created_at"], str) else poll["created_at"]
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        days_passed = (datetime.now(timezone.utc) - created).days
        if days_passed >= 7:
            raise HTTPException(status_code=400, detail="Poll has expired")
    
    if vote.option not in poll["options"]:
        raise HTTPException(status_code=400, detail="Invalid option")
    
    # Check if user already voted
    existing_vote = await db.poll_votes.find_one({
        "poll_id": poll_id,
        "user_id": user["user_id"]
    })
    
    if existing_vote:
        raise HTTPException(status_code=400, detail="Already voted")
    
    # Record vote
    vote_doc = {
        "vote_id": f"vote_{uuid.uuid4().hex[:12]}",
        "poll_id": poll_id,
        "user_id": user["user_id"],
        "option": vote.option,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.poll_votes.insert_one(vote_doc)
    
    # Update poll counts
    await db.polls.update_one(
        {"poll_id": poll_id},
        {"$inc": {f"votes.{vote.option}": 1}}
    )
    
    # Get updated poll
    updated_poll = await db.polls.find_one({"poll_id": poll_id}, {"_id": 0})
    return updated_poll

# ===================== COMMENTS ROUTES =====================

@api_router.get("/comments/{article_id}")
async def get_comments(article_id: str, limit: int = 20, skip: int = 0):
    """Get comments for article"""
    comments = await db.comments.find(
        {"article_id": article_id},
        {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return comments

@api_router.post("/comments/{article_id}")
async def create_comment(
    article_id: str,
    comment_data: CommentCreate,
    user: dict = Depends(require_auth)
):
    """Create a comment"""
    article = await db.articles.find_one({"article_id": article_id}, {"_id": 0})
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    comment_doc = {
        "comment_id": f"comment_{uuid.uuid4().hex[:12]}",
        "article_id": article_id,
        "user_id": user["user_id"],
        "user_name": user["name"],
        "user_picture": user.get("picture"),
        "content": comment_data.content,
        "stance": comment_data.stance,
        "likes": 0,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.comments.insert_one(comment_doc)
    
    return {k: v for k, v in comment_doc.items() if k != "_id"}

@api_router.post("/comments/{comment_id}/like")
async def like_comment(comment_id: str, user: dict = Depends(require_auth)):
    """Like a comment"""
    await db.comments.update_one(
        {"comment_id": comment_id},
        {"$inc": {"likes": 1}}
    )
    return {"success": True}

@api_router.post("/comments/{comment_id}/agree")
async def agree_comment(comment_id: str, user: dict = Depends(require_auth)):
    """Agree with a comment"""
    # Check if already reacted
    existing = await db.comment_reactions.find_one({
        "comment_id": comment_id,
        "user_id": user["user_id"]
    })
    if existing:
        raise HTTPException(status_code=400, detail="Already reacted")

    await db.comments.update_one(
        {"comment_id": comment_id},
        {"$inc": {"agrees": 1}}
    )
    await db.comment_reactions.insert_one({
        "comment_id": comment_id,
        "user_id": user["user_id"],
        "reaction": "agree",
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    return {"success": True}

@api_router.post("/comments/{comment_id}/disagree")
async def disagree_comment(comment_id: str, user: dict = Depends(require_auth)):
    """Disagree with a comment"""
    # Check if already reacted
    existing = await db.comment_reactions.find_one({
        "comment_id": comment_id,
        "user_id": user["user_id"]
    })
    if existing:
        raise HTTPException(status_code=400, detail="Already reacted")

    await db.comments.update_one(
        {"comment_id": comment_id},
        {"$inc": {"disagrees": 1}}
    )
    await db.comment_reactions.insert_one({
        "comment_id": comment_id,
        "user_id": user["user_id"],
        "reaction": "disagree",
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    return {"success": True}

# ===================== BOOKMARKS ROUTES =====================

@api_router.get("/bookmarks")
async def get_bookmarks(user: dict = Depends(require_auth)):
    """Get user bookmarks"""
    bookmarks = await db.bookmarks.find(
        {"user_id": user["user_id"]},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    
    # Get full article details
    article_ids = [b["article_id"] for b in bookmarks]
    articles = await db.articles.find(
        {"article_id": {"$in": article_ids}},
        {"_id": 0}
    ).to_list(100)
    
    return articles

@api_router.post("/bookmarks/{article_id}")
async def add_bookmark(article_id: str, user: dict = Depends(require_auth)):
    """Add bookmark"""
    article = await db.articles.find_one({"article_id": article_id}, {"_id": 0})
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    existing = await db.bookmarks.find_one({
        "user_id": user["user_id"],
        "article_id": article_id
    })
    
    if existing:
        raise HTTPException(status_code=400, detail="Already bookmarked")
    
    bookmark_doc = {
        "bookmark_id": f"bookmark_{uuid.uuid4().hex[:12]}",
        "user_id": user["user_id"],
        "article_id": article_id,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.bookmarks.insert_one(bookmark_doc)
    
    return {"success": True}

@api_router.delete("/bookmarks/{article_id}")
async def remove_bookmark(article_id: str, user: dict = Depends(require_auth)):
    """Remove bookmark"""
    result = await db.bookmarks.delete_one({
        "user_id": user["user_id"],
        "article_id": article_id
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Bookmark not found")
    
    return {"success": True}

@api_router.get("/bookmarks/check/{article_id}")
async def check_bookmark(article_id: str, user: dict = Depends(require_auth)):
    """Check if article is bookmarked"""
    existing = await db.bookmarks.find_one({
        "user_id": user["user_id"],
        "article_id": article_id
    })
    return {"bookmarked": existing is not None}

# ===================== RELEVANCE FEEDBACK =====================

@api_router.post("/feedback/relevance")
async def submit_relevance_feedback(
    feedback: RelevanceFeedback,
    user: dict = Depends(require_auth)
):
    """Submit relevance feedback for algorithm training"""
    feedback_doc = {
        "feedback_id": f"feedback_{uuid.uuid4().hex[:12]}",
        "user_id": user["user_id"],
        "article_id": feedback.article_id,
        "is_relevant": feedback.is_relevant,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.relevance_feedback.insert_one(feedback_doc)
    _affinity_cache.pop(user["user_id"], None)  # force recompute on next request
    return {"success": True}

# ===================== NOTIFICATIONS ROUTES =====================

@api_router.get("/notifications")
async def get_notifications(user: dict = Depends(require_auth)):
    """Get user notifications (reactions to their comments)"""
    # Get user's comments
    user_comments = await db.comments.find(
        {"user_id": user["user_id"]},
        {"_id": 0, "comment_id": 1, "content": 1}
    ).to_list(100)
    
    comment_ids = [c["comment_id"] for c in user_comments]
    comment_map = {c["comment_id"]: c["content"] for c in user_comments}
    
    # Get reactions to user's comments (excluding user's own reactions)
    reactions = await db.comment_reactions.find(
        {
            "comment_id": {"$in": comment_ids},
            "user_id": {"$ne": user["user_id"]}
        },
        {"_id": 0}
    ).sort("created_at", -1).limit(50).to_list(50)
    
    notifications = []
    for r in reactions:
        # Get reactor info
        reactor = await db.users.find_one({"user_id": r["user_id"]}, {"_id": 0, "name": 1})
        if reactor:
            created = datetime.fromisoformat(r["created_at"].replace('Z', '+00:00')) if isinstance(r["created_at"], str) else r["created_at"]
            now = datetime.now(timezone.utc)
            diff = now - created.replace(tzinfo=timezone.utc) if created.tzinfo is None else now - created
            
            if diff.days > 0:
                time_ago = f"{diff.days}d ago"
            elif diff.seconds > 3600:
                time_ago = f"{diff.seconds // 3600}h ago"
            else:
                time_ago = f"{diff.seconds // 60}m ago"
            
            notifications.append({
                "type": r["reaction"],
                "from_user": reactor["name"],
                "comment_preview": comment_map.get(r["comment_id"], "")[:50] + "...",
                "time_ago": time_ago,
                "read": r.get("read", False)
            })
    
    unread = sum(1 for n in notifications if not n["read"])
    
    return {
        "notifications": notifications,
        "unread_count": unread
    }

@api_router.post("/notifications/read")
async def mark_notifications_read(user: dict = Depends(require_auth)):
    """Mark all notifications as read"""
    # Get user's comments
    user_comments = await db.comments.find(
        {"user_id": user["user_id"]},
        {"_id": 0, "comment_id": 1}
    ).to_list(100)
    
    comment_ids = [c["comment_id"] for c in user_comments]
    
    await db.comment_reactions.update_many(
        {"comment_id": {"$in": comment_ids}},
        {"$set": {"read": True}}
    )
    
    return {"success": True}

# ===================== POLL HISTORY ROUTES =====================

@api_router.get("/users/voted-polls")
async def get_voted_polls(user: dict = Depends(require_auth)):
    """Get polls the user has voted in (last 7 days)"""
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    
    # Get user's votes
    votes = await db.poll_votes.find(
        {"user_id": user["user_id"]},
        {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    
    voted_polls = []
    for vote in votes:
        poll = await db.polls.find_one({"poll_id": vote["poll_id"]}, {"_id": 0})
        if poll:
            poll["user_vote"] = vote["option"]
            voted_polls.append(poll)
    
    return voted_polls

# ===================== ADMIN ROUTES =====================

@api_router.post("/admin/recategorize")
async def admin_recategorize():
    """One-time migration: run Claude categorization on all uncategorized articles."""
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="Anthropic API key not configured")

    _valid_cats = {"Technology", "Politics", "Business", "Sports", "Entertainment", "Health", "Science", "World"}
    total_updated = 0

    while True:
        batch = await db.articles.find(
            {"claude_categorized": {"$ne": True}},
            {"_id": 0, "article_id": 1, "title": 1},
        ).limit(10).to_list(10)

        if not batch:
            break

        for art in batch:
            try:
                raw = await _llm(
                    system="You categorize news articles. Return only the category name, nothing else.",
                    user_content=(
                        "Categorize this news article into exactly one of these categories: "
                        "Technology, Politics, Business, Sports, Entertainment, Health, Science, World. "
                        f"Article title: {art['title']}. Return only the category name, nothing else."
                    ),
                    max_tokens=20,
                )
                cat = raw.strip()
                if cat in _valid_cats:
                    await db.articles.update_one(
                        {"article_id": art["article_id"]},
                        {"$set": {"category": cat, "claude_categorized": True}},
                    )
                    total_updated += 1
                else:
                    # Mark as processed even if category was unrecognised so we don't loop forever
                    await db.articles.update_one(
                        {"article_id": art["article_id"]},
                        {"$set": {"claude_categorized": True}},
                    )
            except Exception as e:
                logger.error(f"Recategorize error for {art['article_id']}: {e}")

    return {"updated": total_updated}

@api_router.post("/admin/cleanup-truncated")
async def admin_cleanup_truncated():
    """Clean '[+N chars]' truncation from title/description/content on ALL articles."""
    all_articles = await db.articles.find(
        {}, {"_id": 0, "article_id": 1, "title": 1, "description": 1, "content": 1}
    ).to_list(10000)

    updated = 0
    for art in all_articles:
        new_title = clean_newsapi_text(art.get("title", ""))
        new_desc = clean_newsapi_text(art.get("description", ""))
        new_content = clean_newsapi_text(art.get("content", ""))
        changed = (
            new_title != art.get("title", "")
            or new_desc != art.get("description", "")
            or new_content != art.get("content", "")
        )
        if changed:
            patch = {"claude_summarized": False}
            if new_title != art.get("title", ""):
                patch["title"] = new_title
            if new_desc != art.get("description", ""):
                patch["description"] = new_desc
            if new_content != art.get("content", ""):
                patch["content"] = new_content
            await db.articles.update_one(
                {"article_id": art["article_id"]},
                {"$set": patch},
            )
            updated += 1

    return {"cleaned": updated}

@api_router.post("/admin/clear-other-side-cache")
async def admin_clear_other_side_cache():
    """One-time: clear cached other-side analyses so they regenerate with new prompt."""
    result = await db.other_side_cache.delete_many({})
    return {"deleted": result.deleted_count}

@api_router.delete("/admin/purge-blacklisted-domains")
async def admin_purge_blacklisted_domains():
    """One-shot: delete all articles whose URL domain is in _BLACKLISTED_DOMAINS."""
    all_articles = await db.articles.find(
        {"url": {"$exists": True}},
        {"_id": 0, "article_id": 1, "url": 1},
    ).to_list(100000)

    to_delete = []
    domain_counts: dict = {}
    for art in all_articles:
        url = art.get("url") or ""
        try:
            domain = url.split("//", 1)[1].split("/")[0].lower().removeprefix("www.")
        except Exception:
            continue
        if domain in _BLACKLISTED_DOMAINS:
            to_delete.append(art["article_id"])
            domain_counts[domain] = domain_counts.get(domain, 0) + 1

    if to_delete:
        result = await db.articles.delete_many({"article_id": {"$in": to_delete}})
        deleted = result.deleted_count
    else:
        deleted = 0

    return {"deleted": deleted, "domains": domain_counts}

@api_router.get("/admin/test-newsapi")
async def admin_test_newsapi():
    """Trigger fetch_from_newsapi() immediately and return diagnostic info."""
    if not NEWSAPI_KEY:
        return {"error": "NEWSAPI_KEY is not set in environment variables", "articles": []}

    articles = await fetch_from_newsapi()

    new_count = 0
    existing_count = 0
    for article in articles:
        exists = await db.articles.find_one({"article_id": article["article_id"]}, {"_id": 1})
        if exists:
            existing_count += 1
        else:
            new_count += 1

    return {
        "newsapi_key_present": True,
        "total_fetched": len(articles),
        "new_to_db": new_count,
        "already_in_db": existing_count,
        "articles": [
            {
                "title": a["title"],
                "source": a["source"],
                "published_at": a["published_at"],
                "article_id": a["article_id"],
                "url": a["url"],
            }
            for a in articles
        ],
    }

# ===================== DEVELOPING STORIES =====================

@api_router.get("/developing-stories")
async def get_developing_stories_list(user: dict = Depends(require_auth)):
    """Return all active watched topics with article count and latest article preview."""
    stories = await db.developing_stories.find(
        {"is_active": True}, {"_id": 0}
    ).to_list(100)

    result = []
    for story in stories:
        article_ids = story.get("article_ids", [])
        latest_article = None
        if article_ids:
            latest_article = await db.articles.find_one(
                {"article_id": {"$in": article_ids}},
                {"_id": 0, "article_id": 1, "title": 1, "image_url": 1, "published_at": 1, "source": 1},
                sort=[("published_at", -1)],
            )
        result.append({
            "story_id": story["story_id"],
            "title": story["title"],
            "theme": story["theme"],
            "article_count": len(article_ids),
            "last_updated": story.get("last_updated"),
            "latest_article": latest_article,
        })
    return result


@api_router.get("/developing-stories/{story_id}")
async def get_developing_story_detail(story_id: str, user: dict = Depends(require_auth)):
    """Return full topic detail with all matched articles sorted newest-first."""
    story = await db.developing_stories.find_one({"story_id": story_id}, {"_id": 0})
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    article_ids = story.get("article_ids", [])
    articles = []
    if article_ids:
        articles = await db.articles.find(
            {"article_id": {"$in": article_ids}},
            {"_id": 0, "article_id": 1, "title": 1, "description": 1, "source": 1,
             "published_at": 1, "image_url": 1, "url": 1, "is_breaking": 1},
        ).sort("published_at", -1).to_list(50)

    return {
        "story_id": story["story_id"],
        "title": story["title"],
        "theme": story["theme"],
        "articles": articles,
        "last_updated": story.get("last_updated"),
    }


# ===================== BASIC ROUTES =====================

@api_router.get("/")
async def root():
    return {"message": "Chintan API - Don't just consume. Contemplate."}

@api_router.get("/health")
async def health():
    return {"status": "healthy"}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


"""News sources: GNews (primary, real-time, licensed for production) and the
NewsAPI.org fallback. Pure rules only — no I/O — so filters, mapping, ranking
delay and the request budget are unit-testable. server.py does the fetching.

    GNews every 20 min (9 categories + an "India" search, country=in, lang=en)
      └─▶ to_article(): blocklist ─▶ trusted / India-relevance gate ─▶ Chintan article
            provider="gnews", rank_at = published_at (real time, delay 0)
    NewsAPI hourly, only while NEWSAPI_ENABLED (free tier: 24h late, not licensed
    for a live app) — its rank delay drops to 0 once GNews is live, so its day-old
    items rank by their real age instead of competing as fresh.

Labels: an API article is never "Breaking" (only a Desk Breaking story is), and
is "Developing" only when tagged into a live developing story — not merely
because it is recent (with real-time news, recency would label everything).
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Optional

GNEWS_CATEGORIES = ("general", "nation", "world", "business", "technology",
                    "entertainment", "sports", "science", "health")
# Every 20-min cycle: searches, which honour "from" (only stories since the last
# run). Each carries the GNews category we treat as its taxonomy prior.
# Measured 2026-10-04: top-headlines asked for "the last 20 minutes" returned
# NOTHING (234 of 260 requests that day) because top stories are older than
# the window; the "India" search returned 159 new stories from 26 requests.
GNEWS_SEARCHES = (
    ("India", None),
    ("Sensex OR Nifty OR RBI OR economy OR rupee OR inflation", "business"),
    ("cricket OR hockey OR football OR badminton OR tennis OR kabaddi", "sports"),
    ("ISRO OR startup OR smartphone OR \"artificial intelligence\" OR cyber", "technology"),
    ("Bollywood OR film OR actor OR OTT OR music", "entertainment"),
    ("hospital OR disease OR vaccine OR health OR doctors", "health"),
)
# Top headlines are a slow-moving list: ask every few hours over a wider window.
HEADLINES_EVERY_MIN = 180
HEADLINES_WINDOW_H = 6
GNEWS_MAX = 25                 # articles per request on Essential
INTERVAL_MIN = 20              # GNews cycle
STARTUP_MIN_GAP_MIN = 15       # a restart within this of the last run doesn't refetch
GNEWS_DAILY_CAP_DEFAULT = 900  # of Essential's 1,000/day: headroom for retries/admin tests
FIRST_RUN_LOOKBACK_H = 24

# Indian publishers: no India-keyword gate (their whole output is Indian news).
TRUSTED_INDIAN = {
    "thehindu.com", "thehindubusinessline.com", "indianexpress.com", "newindianexpress.com",
    "hindustantimes.com", "livemint.com", "timesofindia.indiatimes.com", "economictimes.indiatimes.com",
    "m.economictimes.com", "health.economictimes.indiatimes.com", "ndtv.com", "ndtvprofit.com",
    "business-standard.com", "financialexpress.com", "indiatoday.in", "news18.com", "theprint.in",
    "scroll.in", "thewire.in", "moneycontrol.com", "outlookindia.com", "telegraphindia.com",
    "tribuneindia.com", "deccanherald.com", "deccanchronicle.com", "firstpost.com", "freepressjournal.in",
    "timesnownews.com", "aninews.in", "ptinews.com", "lokmattimes.com", "thequint.com",
    "newslaundry.com", "cricbuzz.com", "espncricinfo.com", "cricinfo.com", "sportstar.thehindu.com",
    "businesstoday.in", "zeebiz.com", "wionews.com", "republicworld.com", "dnaindia.com",
    "mid-day.com", "nationalheraldindia.com", "frontline.thehindu.com", "etnownews.com",
}
# Serious international outlets: let world/science/tech/health in without an India angle.
TRUSTED_INTERNATIONAL = {
    "bbc.com", "bbc.co.uk", "aljazeera.com", "reuters.com", "apnews.com", "theguardian.com",
    "npr.org", "dw.com", "france24.com", "cnn.com", "nytimes.com", "washingtonpost.com",
    "bloomberg.com", "ft.com", "economist.com", "nature.com", "science.org", "scientificamerican.com",
    "newscientist.com", "phys.org", "eurekalert.org", "who.int", "arabnews.com", "scmp.com",
    "channelnewsasia.com", "abc.net.au", "theverge.com", "wired.com", "arstechnica.com",
    "techcrunch.com", "engadget.com",
}
INTERNATIONAL_OK_CATEGORIES = {"world", "science", "technology", "health"}

# Never: off-topic, shopping, downloads, gaming blogs, press-release mills.
BLOCKED = {
    "whyevolutionistrue.com", "kdnuggets.com", "spektrum.de", "scilogs.spektrum.de", "financialpost.com",
    "linkedin.com", "globenewswire.com", "hurriyetdailynews.com", "oilprice.com", "consent.yahoo.com",
    "finance.biggo.com", "biggo.com", "softonic.com", "en.softonic.com", "gamerant.com", "brainhealth.com",
    "prnewswire.com", "prnewswire.co.uk", "einpresswire.com", "openpr.com", "businesswire.com",
    "news.google.com",
}


def domain_of(url: str) -> str:
    try:
        host = url.split("//", 1)[1].split("/", 1)[0].lower()
    except IndexError:
        return ""
    host = host.split(":")[0]
    return host[4:] if host.startswith("www.") else host


def _matches(domain: str, pool: set) -> bool:
    return domain in pool or any(domain.endswith("." + d) for d in pool)


def india_relevant(text: str, keywords: Iterable[str]) -> bool:
    """Word-boundary match (the old substring check let 'ed', 'ott', 'odi'
    match almost any English sentence)."""
    low = (text or "").lower()
    return any(re.search(r"\b" + re.escape(k) + r"\b", low) for k in keywords)


def admit(url: str, title: str, description: str, gnews_category: Optional[str],
          india_keywords: Iterable[str]) -> tuple[bool, str]:
    """Should this article enter Chintan? Returns (ok, reason)."""
    d = domain_of(url)
    if not d or _matches(d, BLOCKED):
        return False, "blocked"
    if _matches(d, TRUSTED_INDIAN):
        return True, "trusted_indian"
    if _matches(d, TRUSTED_INTERNATIONAL) and (gnews_category in INTERNATIONAL_OK_CATEGORIES):
        return True, "trusted_international"
    if india_relevant(f"{title} {description}", india_keywords):
        return True, "india_relevant"
    return False, "off_topic"


def provider_delay_h(provider: str, gnews_live: bool, newsapi_delay_h: float) -> float:
    """Hours to add to published_at for rank_at. GNews is real time. NewsAPI is
    24h late: while it is the only source its items rank by arrival; once GNews
    is live they rank by their real age (so they can't pose as fresh)."""
    if provider == "newsapi" and not gnews_live:
        return newsapi_delay_h
    return 0.0


def article_id_for(url: str) -> str:
    return "article_" + hashlib.md5(url.encode()).hexdigest()[:12]


def build_article(*, url: str, title: str, description: str, raw_content: str, source_name: str,
                  published_at: str, image_url: Optional[str], author: Optional[str], provider: str,
                  rank_at: str, detect_category: Callable[[str, str], tuple], default_image: str) -> dict:
    """The one shape every API article is stored in (NewsAPI and GNews)."""
    category, subcategory = detect_category(title, description + " " + raw_content)
    summary = (description or raw_content[:400] or title).strip()
    content = raw_content[:1500] + "..." if len(raw_content) > 1500 else raw_content
    return {
        "article_id": article_id_for(url),
        "title": title,
        "description": description[:300] + "..." if len(description) > 300 else description,
        "content": content,
        "summary": summary[:600],
        "what": summary[:500],
        "why": "", "context": "", "impact": "",
        "category": category,
        "subcategory": subcategory,
        "source": source_name or "News Feed",
        "author": author,
        "published_at": published_at,
        "image_url": image_url or default_image,
        "rank_at": rank_at,
        # Labels come from the Desk / the developing-story tagger, never from age.
        "is_developing": False,
        "is_breaking": False,
        "likes": 0, "dislikes": 0, "view_count": 0,
        "reading_time_sec": max(5, len(raw_content.split()) // 200 * 60),
        "url": url,
        "provider": provider,
    }


def gnews_since(last_success: Optional[datetime], now: datetime) -> datetime:
    """Window start for the next GNews request: a little overlap with the last
    success (dedupe makes overlap free), at most FIRST_RUN_LOOKBACK_H back."""
    floor = now - timedelta(hours=FIRST_RUN_LOOKBACK_H)
    if not last_success:
        return floor
    return max(floor, last_success - timedelta(minutes=5))


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def summarize_quota(hourly_limit: int, interval_min: int) -> int:
    """Per-cycle summary cap that keeps the HOURLY Claude spend unchanged."""
    return max(1, round(hourly_limit * interval_min / 60))


def gnews_plan(now: datetime, since: datetime, last_headlines: Optional[datetime]) -> tuple[list, bool]:
    """This cycle's GNews requests: [(endpoint, params, category prior)], and
    whether top headlines are due (the caller records when they ran)."""
    plan = [("search", {"q": q, "sortby": "publishedAt", "from": iso_z(since)}, cat)
            for q, cat in GNEWS_SEARCHES]
    due = last_headlines is None or (now - last_headlines) >= timedelta(minutes=HEADLINES_EVERY_MIN)
    if due:
        hl_from = iso_z(min(since, now - timedelta(hours=HEADLINES_WINDOW_H)))
        plan += [("top-headlines", {"category": c, "from": hl_from}, c) for c in GNEWS_CATEGORIES]
    return plan, due


def query_key(endpoint: str, extra: dict) -> str:
    """Stable, Mongo-key-safe name for a GNews query ("top-headlines~nation",
    "search~India"), used for per-query yield counters."""
    which = extra.get("category") or extra.get("q") or "all"
    safe = "".join(ch if ch.isalnum() else "_" for ch in str(which))[:40]
    return f"{endpoint}~{safe}"

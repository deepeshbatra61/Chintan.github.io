"""GNews India coverage test — thorough, but cheap on a free key.

Uses about 25 requests (free plan: 100/day, max 10 articles each, ~12h delay).
Reads the key from the GNEWS_KEY environment variable; the key is never
printed or written to the output file.

Windows (Command Prompt), from the backend folder:
    set GNEWS_KEY=your_key_here
    python scripts\\gnews_probe.py

Writes everything it fetched to  Desktop\\gnews_probe.json  (no key inside),
so the analysis can be done without spending more requests.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

KEY = os.environ.get("GNEWS_KEY", "").strip().strip('"').strip("'").strip()
BASE = "https://gnews.io/api/v4"
OUT = Path.home() / "Desktop" / "gnews_probe.json"

CATEGORIES = ["general", "nation", "world", "business", "technology", "entertainment", "sports", "science", "health"]
# Topics Chintan readers care about: shows depth beyond the top headlines.
SEARCHES = ["India", "Modi", "RBI", "Sensex OR Nifty", "cricket", "Bollywood", "ISRO", "Supreme Court",
            "monsoon", "startup", "Parliament", "Kerala OR Tamil Nadu OR Karnataka", "Delhi OR Mumbai"]

calls = []


def get(endpoint: str, **params):
    params.update({"lang": "en", "country": "in", "max": 10, "apikey": KEY})
    url = f"{BASE}/{endpoint}?{urllib.parse.urlencode(params)}"
    shown = {k: v for k, v in params.items() if k != "apikey"}
    rec = {"endpoint": endpoint, "params": shown}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "chintan-probe"}),
                                    timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        rec["totalArticles"] = data.get("totalArticles")
        rec["articles"] = data.get("articles") or []
    except urllib.error.HTTPError as e:
        try:
            rec["error"] = f"HTTP {e.code}: {e.read().decode('utf-8')[:300]}"
        except Exception:
            rec["error"] = f"HTTP {e.code}"
    except Exception as e:
        rec["error"] = str(e)[:200]
    calls.append(rec)
    time.sleep(1.1)   # free plan allows about 1 request/second
    return rec


def main():
    if not KEY:
        print("GNEWS_KEY isn't set in this window. Run:  set GNEWS_KEY=your_key_here")
        sys.exit(1)
    print(f"Key in use: {len(KEY)} characters, starts '{KEY[:2]}', ends '{KEY[-2:]}'")
    started = datetime.now(timezone.utc)

    # 1. Top headlines per category (9 requests)
    for cat in CATEGORIES:
        r = get("top-headlines", category=cat)
        print(f"top-headlines {cat:13s} -> {len(r.get('articles', [])):2d} articles"
              + (f"  (total {r.get('totalArticles')})" if r.get("totalArticles") is not None else "")
              + (f"  ERROR {r['error']}" if r.get("error") else ""))
        if r.get("error") and "401" in r["error"] or (r.get("error") and "403" in r["error"]):
            print("Key rejected — stop here and paste this output.")
            break

    # 2. Topic searches over the last 2 days (13 requests): depth + daily volume via totalArticles
    since = (started - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for q in SEARCHES:
        r = get("search", q=q, sortby="publishedAt", **{"from": since})
        print(f"search {q[:32]:32s} -> {len(r.get('articles', [])):2d} shown, total {r.get('totalArticles')}"
              + (f"  ERROR {r['error']}" if r.get("error") else ""))

    # 3. Pagination check (1 request): can a plan page past the first 10?
    r = get("top-headlines", category="general", page=2)
    print(f"page 2 of general -> {len(r.get('articles', []))} articles"
          + (f"  ERROR {r['error']}" if r.get("error") else ""))

    OUT.write_text(json.dumps({"fetched_at": started.isoformat(), "calls": calls}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    n = sum(len(c.get("articles", [])) for c in calls)
    print(f"\nSaved {n} articles from {len(calls)} requests to {OUT}")
    print("Done. Tell Claude it's saved; no need to paste anything else.")


if __name__ == "__main__":
    main()

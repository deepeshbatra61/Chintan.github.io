"""Mediastack India coverage test — run BEFORE paying for a plan.

Uses at most 6 API requests (the free plan has 100/month). Reads the key from
the MEDIASTACK_KEY environment variable; it is never printed or saved.

Windows (Command Prompt), from the backend folder:
    set MEDIASTACK_KEY=your_key_here
    python scripts\\mediastack_probe.py

Then paste the printed report into the chat (it contains no key).

Answers: which Indian publishers Mediastack carries and how much of each, how
many India stories a day, how fresh they are, image/description quality,
category spread, and duplicates. Note: the FREE plan is delayed (~30 min), so
"newest story" will look older than it would on a paid plan.
"""

import collections
import json
import os
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

KEY = os.environ.get("MEDIASTACK_KEY", "").strip()
BASES = ("https://api.mediastack.com/v1", "http://api.mediastack.com/v1")  # free plans may be http-only
calls_used = 0

# Publishers Chintan cares about, matched loosely against source names/ids.
WANTED = {
    "The Hindu": ("hindu",), "Indian Express": ("indianexpress", "indian express"),
    "Hindustan Times": ("hindustantimes", "hindustan times"), "Times of India": ("timesofindia", "times of india"),
    "Mint": ("livemint", "mint"), "NDTV": ("ndtv",), "Business Standard": ("business-standard", "business standard"),
    "Economic Times": ("economictimes", "economic times"), "India Today": ("indiatoday", "india today"),
    "News18": ("news18",), "Deccan Herald": ("deccanherald", "deccan herald"), "Firstpost": ("firstpost",),
    "Scroll": ("scroll",), "ThePrint": ("theprint",), "The Wire": ("thewire",), "Moneycontrol": ("moneycontrol",),
    "BusinessLine": ("businessline", "thehindubusinessline"), "Financial Express": ("financialexpress",),
    "Outlook": ("outlook",), "The Telegraph India": ("telegraphindia",), "ESPNcricinfo": ("espncricinfo", "cricinfo"),
    "PTI / IANS": ("pti", "ians"),
}


def call(endpoint: str, **params):
    global calls_used
    params["access_key"] = KEY
    last_err = None
    for base in BASES:
        url = f"{base}/{endpoint}?{urllib.parse.urlencode(params)}"
        try:
            calls_used += 1
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "chintan-probe"}),
                                        timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
            if isinstance(data, dict) and data.get("error"):
                err = data["error"]
                last_err = f"{err.get('code')}: {err.get('message')}"
                if "https" in str(err).lower() and base.startswith("https"):
                    continue          # free plan without HTTPS -> retry over http
                return None, last_err
            return data, None
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read().decode("utf-8"))
                last_err = f"HTTP {e.code}: {body.get('error', body)}"
            except Exception:
                last_err = f"HTTP {e.code}"
            if base.startswith("https"):
                continue
        except Exception as e:
            last_err = str(e)[:120]
            if base.startswith("https"):
                continue
    return None, last_err


def parse_dt(s):
    try:
        d = datetime.fromisoformat((s or "").replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def main():
    if not KEY:
        print("MEDIASTACK_KEY isn't set in this window. Run:  set MEDIASTACK_KEY=your_key_here")
        sys.exit(1)
    now = datetime.now(timezone.utc)
    print("Mediastack India coverage test —", now.strftime("%Y-%m-%d %H:%M UTC"))
    print("=" * 70)

    # 1-3: newest India English news, 300 stories
    arts, total = [], None
    for offset in (0, 100, 200):
        data, err = call("news", countries="in", languages="en", sort="published_desc", limit=100, offset=offset)
        if err:
            print(f"news request failed (offset {offset}): {err}")
            break
        if total is None:
            total = (data.get("pagination") or {}).get("total")
        arts += data.get("data") or []
        if len(data.get("data") or []) < 100:
            break
    if not arts:
        print("No India articles returned — stop here and paste this output.")
        return

    times = sorted((t for t in (parse_dt(a.get("published_at")) for a in arts) if t), reverse=True)
    span_h = (times[0] - times[-1]).total_seconds() / 3600 if len(times) > 1 else 0
    per_day = len(times) / span_h * 24 if span_h else None
    print(f"India + English stories Mediastack holds in total: {total}")
    print(f"Sampled newest {len(arts)} stories, covering the last {span_h:.1f} hours"
          + (f"  ->  about {per_day:.0f} stories/day" if per_day else ""))
    if times:
        print(f"Newest story is {(now - times[0]).total_seconds() / 60:.0f} min old "
              "(free plan is delayed ~30 min; paid is live)")
    last24 = sum(1 for t in times if now - t <= timedelta(hours=24))
    print(f"Stories in the sample published in the last 24h: {last24}")

    # Sources
    src = collections.Counter((a.get("source") or "?").strip() for a in arts)
    print("\nSources in the sample (top 25):")
    for name, n in src.most_common(25):
        print(f"  {n:4d}  {name}")
    print(f"  ({len(src)} distinct sources; biggest single source = "
          f"{src.most_common(1)[0][1] / len(arts):.0%} of stories)")

    # Wanted publishers present?
    blob = " | ".join(f"{(a.get('source') or '').lower()} {(a.get('url') or '').lower()}" for a in arts)
    print("\nKey Indian publishers seen in the sample:")
    for name, needles in WANTED.items():
        n = sum(1 for a in arts if any(nd in f"{(a.get('source') or '').lower()} {(a.get('url') or '').lower()}"
                                        for nd in needles))
        print(f"  {'YES' if n else ' - '}  {name}" + (f"  ({n})" if n else ""))

    # Quality
    with_img = sum(1 for a in arts if (a.get("image") or "").startswith("http"))
    desc_lens = [len(a.get("description") or "") for a in arts]
    titles = collections.Counter((a.get("title") or "").strip().lower() for a in arts)
    dups = sum(c - 1 for c in titles.values() if c > 1)
    cats = collections.Counter(a.get("category") or "?" for a in arts)
    print(f"\nWith an image: {with_img}/{len(arts)} ({with_img / len(arts):.0%})")
    print(f"Description length: median {statistics.median(desc_lens):.0f} chars, "
          f"{sum(1 for x in desc_lens if x < 40)} stories with <40 chars")
    print(f"Duplicate titles in sample: {dups}")
    print("Categories:", ", ".join(f"{c} {n}" for c, n in cats.most_common()))

    # 4: Mediastack's own list of Indian sources
    data, err = call("sources", countries="in", languages="en", search="news", limit=100)
    if err:
        print(f"\nSources list request failed: {err}")
    else:
        rows = data.get("data") or []
        print(f"\nMediastack's Indian English sources matching 'news': "
              f"{(data.get('pagination') or {}).get('total')} (showing {len(rows)})")
        print("  " + ", ".join(sorted({r.get('name') or r.get('id') for r in rows})[:80]))

    # 5: sample story so we can see the shape
    a = arts[0]
    print("\nExample story:")
    print(json.dumps({k: a.get(k) for k in ("title", "description", "source", "category", "published_at",
                                             "image", "url")}, indent=2, ensure_ascii=False)[:1200])
    print("\n" + "=" * 70)
    print(f"API requests used: {calls_used}  (free plan: 100/month)")


if __name__ == "__main__":
    main()

"""Follow a story: pings when it moves (D8).

    rules   ─ quiet hours, 90-min gap, 2h per story, 3/story/day, 6/reader/day
    copy    ─ story as title, new headline + outlet as body, no emoji
    service ─ only followers, only when push is on, the 'follow' pref, caps
    trigger ─ a NEW independent outlet with a NEW headline on a DEVELOPING
              followed event → exactly one notify; copies / same outlet → none
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "t")
os.environ.setdefault("JWT_SECRET", "t")

import events_service as S  # noqa: E402
import push as P  # noqa: E402
from test_push_service import Env, run  # noqa: E402

IST = "Asia/Kolkata"
NOON_IST = datetime(2026, 10, 3, 6, 30, tzinfo=timezone.utc)    # 12:00 in India


def h(x):
    return NOON_IST + timedelta(hours=x)


# ── rules ─────────────────────────────────────────────────────────────────────

def test_follow_hold_rules():
    assert P.follow_hold(h(0), IST, None, [], []) is None
    assert P.follow_hold(datetime(2026, 10, 3, 17, 0, tzinfo=timezone.utc), IST, None, [], []) == "quiet"  # 22:30 IST
    assert P.follow_hold(h(0), IST, h(-1), [], []) == "gap"
    assert P.follow_hold(h(0), IST, h(-1.6), [h(-1.6)], [h(-1.6)]) == "story_gap"
    three = [h(-6), h(-4), h(-2.1)]
    assert P.follow_hold(h(0), IST, h(-2.1), three, three) == "story_day"
    six = [h(-x) for x in (5.5, 5, 4.5, 4, 3, 2)]
    assert P.follow_hold(h(0), IST, h(-2), [], six) == "reader_day"


def test_follow_copy():
    title, body = P.follow_copy("Pradhan resigns over exam paper leak 🚨",
                                "Congress demands judicial probe into leak!", "The Hindu")
    assert "🚨" not in title and title.startswith("Pradhan resigns")
    assert body == "Congress demands judicial probe into leak. (The Hindu)"
    assert len(body) <= P.BODY_MAX


# ── service ───────────────────────────────────────────────────────────────────

def make_env(live=True):
    env = Env(now=h(0), live=live)
    for uid in ("u1", "u2", "u3"):
        run(env.svc.register(token=f"tok-{uid}-" + "x" * 30, platform="android", tz=IST, user_id=uid))
    run(env.db.follows.insert_many([{"user_id": "u1", "story_id": "ev-1"}, {"user_id": "u2", "story_id": "ev-1"}]))
    return env


def send(env):
    return run(env.svc.send_follow_update(story_id="ev-1", story_title="Pradhan resigns",
                                          headline="Congress demands probe", outlet="The Hindu"))


def test_only_followers_get_it_with_the_story_route():
    env = make_env()
    r = send(env)
    assert r["ok"] and r["sent"] == 2
    tokens = {m["token"][:6] for m in env.fcm.sent}
    assert tokens == {"tok-u1", "tok-u2"}
    assert all(m["data"]["route"] == "/developing/ev-1" and m["data"]["kind"] == "follow" for m in env.fcm.sent)


def test_switched_off_sends_nothing():
    env = make_env(live=False)
    assert send(env)["ok"] is False and env.fcm.sent == []


def test_pref_off_and_story_gap():
    env = make_env()
    run(env.svc.set_prefs("u2", {"follow": False}))
    assert send(env)["held"]["off"] == 1
    env.clock.t = h(1)
    r = send(env)                                   # u1 pinged an hour ago
    assert r["sent"] == 0 and r["held"]["gap"] == 1


# ── trigger in the events cycle ──────────────────────────────────────────────

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)


def iso(x):
    return (NOW + timedelta(hours=x)).isoformat()


def art(aid, title, x, url):
    return {"article_id": aid, "title": title, "description": title, "content": "", "published_at": iso(x),
            "rank_at": iso(x), "url": url, "source": "", "category": "Politics"}


@pytest.fixture
async def db():
    S.reset_cache()
    d = mongomock_motor.AsyncMongoMockClient()["t"]
    await d.articles.insert_many([art(f"f{i}", t, -10 - i, f"https://example{i}.com/x") for i, t in enumerate([
        "RBI holds repo rate steady amid inflation worries", "Sensex closes higher on IT gains",
        "Monsoon rains lash Kerala coast", "Virat Kohli scores century in ODI",
        "ISRO schedules Gaganyaan test flight", "Apple launches new iPhone in India"])] + [
        art("p1", "Dharmendra Pradhan resigns as education minister over exam paper leak", 0, "https://www.thehindu.com/a"),
        art("p2", "Education minister Pradhan resigns amid exam leak protests", 2.5, "https://indianexpress.com/b"),
    ])
    await S.run_cycle(d, now=NOW + timedelta(hours=3), mode="shadow")
    eid = (await d.articles.find_one({"article_id": "p1"}))["event_id"]
    assert (await d.events.find_one({"event_id": eid}))["status"] == "developing"
    await d.follows.insert_one({"user_id": "u1", "story_id": eid})
    d.eid = eid
    return d


async def cycle(d, rows, at):
    calls = []

    async def notify(**kw):
        calls.append(kw)
    await d.articles.insert_many([art(*r) for r in rows])
    await S.run_cycle(d, now=NOW + timedelta(hours=at), mode="shadow", notify=notify)
    return calls


async def test_new_outlet_with_new_development_notifies(db):
    calls = await cycle(db, [("p3", "Pradhan resigns: exam leak probe ordered as students protest", 3.5,
                              "https://www.tribuneindia.com/c")], 4)
    assert len(calls) == 1 and calls[0]["story_id"] == db.eid and calls[0]["outlet"] == "The Tribune"


async def test_same_outlet_or_copy_does_not(db):
    calls = await cycle(db, [("p4", "Pradhan resigns over exam leak, students protest", 3.5, "https://www.thehindu.com/z")], 4)
    assert calls == []          # The Hindu already reported it
    calls = await cycle(db, [("p5", "Education minister Pradhan resigns amid exam leak protests", 4.5,
                              "https://www.ndtv.com/q")], 5)
    assert calls == []          # same headline as Indian Express: a copy, not a development


async def test_no_followers_no_notify(db):
    await db.follows.delete_many({})
    calls = await cycle(db, [("p3", "Pradhan resigns: exam leak probe ordered as students protest", 3.5,
                              "https://www.tribuneindia.com/c")], 4)
    assert calls == []


async def test_notify_failure_never_breaks_the_cycle(db):
    async def boom(**kw):
        raise RuntimeError("fcm down")
    await db.articles.insert_one(art("p3", "Pradhan resigns: exam leak probe ordered as students protest", 3.5,
                                     "https://www.tribuneindia.com/c"))
    m = await S.run_cycle(db, now=NOW + timedelta(hours=4), mode="shadow", notify=boom)
    assert m["assigned"] >= 1

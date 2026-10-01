"""push_service against an in-memory Mongo, a fake FCM and a fake clock.

    register ─▶ tick@prep (pin + copy) ─▶ tick@due (claim ─▶ send ─▶ log) ─▶ opened
    plus: switch/env off, read-today skip, 90-min gap, dead/auth/retry errors,
    two replicas racing, stale claims, Breaking reach/caps/guests, test push.
"""

import asyncio
import json
from datetime import date, datetime, timedelta, timezone

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")

import push as P  # noqa: E402
import push_service as PS  # noqa: E402

IST = "Asia/Kolkata"
SUNRISE = P.slot_instant("sunrise", date(2026, 10, 1), IST)      # 02:00 UTC
DUSK = P.slot_instant("dusk", date(2026, 10, 1), IST)


def run(coro):
    return asyncio.run(coro)


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


class FakeFCM:
    """Responds per token: a list of (status, body) consumed in order, else 200."""

    def __init__(self):
        self.sent, self.script = [], {}

    async def send(self, message):
        self.sent.append(message)
        queue = self.script.get(message["token"])
        if queue:
            return queue.pop(0)
        return 200, {"name": "projects/x/messages/1"}


GOOD_HOOK = json.dumps({"sensitive": False, "hook": "RBI holds rates, again", "title": "Rates stay put, again"})


class Env:
    def __init__(self, now=SUNRISE - timedelta(minutes=60), hook=GOOD_HOOK, live=True, env_on=True):
        self.db = mongomock_motor.AsyncMongoMockClient()["t"]
        self.clock = Clock(now)
        self.fcm = FakeFCM()
        self.emails = []
        self.hook = hook
        self.env_on = env_on
        self.llm_calls = []
        self.svc = self.make()
        run(self.svc.ensure_indexes())
        run(self.db.articles.insert_many([
            {"article_id": "a1", "title": "RBI holds repo rate for tenth time", "category": "Economy",
             "summary": "The MPC kept rates unchanged.", "image_url": "https://img.example/rbi.jpg",
             "published_at": (SUNRISE - timedelta(hours=3)).isoformat(), "source": "Mint"},
            {"article_id": "a2", "title": "India win the series", "category": "Sports",
             "summary": "A clean sweep.", "published_at": (SUNRISE - timedelta(hours=4)).isoformat(), "source": "ESPN"},
        ]))
        if live:
            run(self.svc.set_enabled(True, "owner@chintan.news"))

    def make(self):
        async def llm(prompt):
            self.llm_calls.append(prompt)
            if "push-notification copy" in prompt:
                if isinstance(self.hook, Exception):
                    raise self.hook
                return self.hook
            return "1. A take.\n2. Another take."

        async def email(to, subject, html):
            self.emails.append((to, subject))
            return True

        async def top(user):
            return (user.get("interests") or [])[:3]

        async def nosleep(_):
            return None

        return PS.PushService(db=self.db, sender=self.fcm, llm=llm, send_email=email,
                              alert_to=lambda: ["owner@chintan.news"], top_categories=top,
                              env_enabled=lambda: self.env_on, now=self.clock, sleep=nosleep)

    def user(self, uid, interests=("Economy",), name="Asha Rao", token=None, tz=IST, platform="android"):
        run(self.db.users.insert_one({"user_id": uid, "email": f"{uid}@x.in", "name": name,
                                      "interests": list(interests)}))
        run(self.svc.register(token=token or f"tok-{uid}", platform=platform, tz=tz, user_id=uid))

    def tick(self, at=None):
        if at:
            self.clock.t = at
        return run(self.svc.tick())

    def logs(self, **q):
        return run(self.db.push_log.find(q).to_list(100))


# ── switch ──────────────────────────────────────────────────────────────────

def test_switch_off_sends_nothing():
    e = Env(live=False)
    e.user("u1")
    e.tick()
    e.tick(SUNRISE)
    assert e.fcm.sent == [] and run(e.db.push_prep.count_documents({})) == 0


def test_env_hard_off_beats_desk_switch():
    e = Env(env_on=False)
    e.user("u1")
    e.tick()
    e.tick(SUNRISE)
    assert e.fcm.sent == []
    assert run(e.svc.state()) ["env_enabled"] is False


# ── devices ─────────────────────────────────────────────────────────────────

def test_guest_token_moves_to_account_on_sign_in():
    e = Env()
    run(e.svc.register(token="T", platform="android", tz=IST, user_id=None))
    run(e.svc.register(token="T", platform="android", tz=IST, user_id="u9"))
    devs = run(e.db.push_devices.find({}).to_list(10))
    assert len(devs) == 1 and devs[0]["user_id"] == "u9"


def test_device_cap_keeps_newest_ten():
    e = Env()
    for i in range(12):
        e.clock.t = SUNRISE + timedelta(minutes=i)
        run(e.svc.register(token=f"T{i}", platform="android", tz=IST, user_id="u1"))
    toks = {d["token"] for d in run(e.db.push_devices.find({"user_id": "u1"}).to_list(20))}
    assert toks == {f"T{i}" for i in range(2, 12)}


def test_unregister():
    e = Env()
    e.user("u1")
    assert run(e.svc.unregister("tok-u1")) is True
    assert run(e.svc.unregister("tok-u1")) is False


def test_prefs_user_and_guest():
    e = Env()
    assert run(e.svc.get_prefs("u1")) == P.DEFAULT_PREFS
    assert run(e.svc.set_prefs("u1", {"noon": True, "bogus": True, "dusk": "no"}))["noon"] is True
    assert run(e.svc.get_prefs("u1"))["dusk"] is True
    run(e.svc.register(token="G", platform="android", tz=IST, user_id=None))
    assert run(e.svc.set_prefs(None, {"breaking": False}, token="G")) == {"breaking": False}


# ── slots: happy path ───────────────────────────────────────────────────────

def test_prepare_then_send_once_with_pin_and_copy():
    e = Env()
    e.user("u1")
    summary = e.tick()                                   # 06:30 IST
    assert summary["prepared"] == 1
    prep = run(e.db.push_prep.find_one({}))
    assert prep["title"] == "Rates stay put, again" and prep["source"] == "ai"
    assert prep["image"] == "https://img.example/rbi.jpg"
    pin = run(e.db.push_briefs.find_one({"pin_id": prep["pin_id"]}))
    assert pin["slot_label"] == "07:30 Sunrise"

    assert e.tick(SUNRISE)["sent"] == 1
    msg = e.fcm.sent[-1]
    assert msg["notification"]["title"] == "Rates stay put, again"
    assert msg["data"]["route"] == f"/brief/morning?pin={prep['pin_id']}"
    assert msg["android"]["notification"]["channel_id"] == "daily"
    assert e.tick(SUNRISE + timedelta(minutes=1))["sent"] == 0           # claimed already
    assert len(e.fcm.sent) == 1
    claim = run(e.db.push_claims.find_one({}))
    assert claim["status"] == "sent"


def test_multiple_devices_all_receive():
    e = Env()
    e.user("u1")
    run(e.svc.register(token="ios-1", platform="ios", tz=IST, user_id="u1"))
    e.tick()
    e.tick(SUNRISE)
    plats = sorted("apns" in m for m in e.fcm.sent)
    assert plats == [False, True]
    ios = next(m for m in e.fcm.sent if "apns" in m)
    assert ios["apns"]["payload"]["aps"]["alert"]["subtitle"] == "Sunrise brief · 3 stories"


def test_two_replicas_race_one_send():
    e = Env()
    e.user("u1")
    e.tick()
    other = e.make()
    e.clock.t = SUNRISE

    async def both():
        return await asyncio.gather(e.svc.tick(), other.tick())
    run(both())
    assert len(e.fcm.sent) == 1


def test_unique_claim_blocks_second_sender_even_past_the_precheck():
    # Force the race: the pre-check sees no claim, so only the unique _id stops
    # the second send (what happens when two replicas interleave).
    e = Env()
    e.user("u1")
    e.tick()
    e.tick(SUNRISE)
    orig = e.db.push_claims.find_one

    async def blind(*a, **k):
        return None
    e.db.push_claims.find_one = blind
    try:
        assert e.tick(SUNRISE + timedelta(minutes=1)).get("noop") == 1
    finally:
        e.db.push_claims.find_one = orig
    assert len(e.fcm.sent) == 1


def test_missed_window_is_skipped_not_late():
    e = Env()
    e.user("u1")
    e.tick()
    e.tick(SUNRISE + timedelta(minutes=31))
    assert e.fcm.sent == []


def test_noon_only_when_opted_in():
    e = Env(now=P.slot_instant("noon", date(2026, 10, 1), IST) - timedelta(minutes=60))
    e.user("u1")
    assert e.tick()["prepared"] == 0
    run(e.svc.set_prefs("u1", {"noon": True}))
    assert e.tick()["prepared"] == 1


def test_guests_never_get_slot_pushes():
    e = Env()
    run(e.svc.register(token="G", platform="android", tz=IST, user_id=None))
    e.tick()
    e.tick(SUNRISE)
    assert e.fcm.sent == []


# ── slots: skips ────────────────────────────────────────────────────────────

def test_skip_when_brief_already_read_today():
    e = Env()
    e.user("u1")
    e.tick()
    run(e.db.brief_opens.insert_one({"user_id": "u1", "brief_type": "morning",
                                     "opened_at": SUNRISE - timedelta(minutes=20)}))
    assert e.tick(SUNRISE)["skipped"] == 1 and e.fcm.sent == []


def test_yesterdays_read_does_not_skip():
    e = Env()
    e.user("u1")
    e.tick()
    run(e.db.brief_opens.insert_one({"user_id": "u1", "brief_type": "morning",
                                     "opened_at": SUNRISE - timedelta(hours=20)}))
    assert e.tick(SUNRISE)["sent"] == 1


def test_gap_after_recent_push():
    e = Env()
    e.user("u1")
    e.tick()
    run(e.db.push_log.insert_one({"push_id": "x", "user_id": "u1", "status": "sent", "kind": "breaking",
                                  "sent_at": SUNRISE - timedelta(minutes=45), "opened_at": None}))
    assert e.tick(SUNRISE)["skipped"] == 1


def test_no_prep_fails_visibly():
    e = Env()
    e.user("u1")
    e.tick(SUNRISE)                  # never prepared: prep window opens and send is due in the same tick
    claim = run(e.db.push_claims.find_one({}))
    # prep ran in this tick, so it sends; now delete prep and check the next day's failure path
    assert claim["status"] == "sent"
    run(e.db.push_prep.delete_many({}))
    nxt = SUNRISE + timedelta(days=1)
    run(e.db.articles.update_many({}, {"$set": {"published_at": (nxt - timedelta(hours=2)).isoformat()}}))
    run(e.db.users.delete_one({"user_id": "u1"}))    # prep can't build → no prep
    e.tick(nxt)
    assert run(e.db.push_claims.find_one({"_id": "u1|sunrise|2026-10-02"}))["reason"] == "no_prep"


# ── copy decisions ──────────────────────────────────────────────────────────

def test_sensitive_hook_is_sober_and_photo_free():
    e = Env(hook=json.dumps({"sensitive": True, "hook": "x", "title": "Sunrise pun"}))
    e.user("u1")
    e.tick()
    prep = run(e.db.push_prep.find_one({}))
    assert prep["title"] == "Your morning brief" and prep["sober"] and prep["image"] is None


def test_llm_down_is_sober():
    e = Env(hook=RuntimeError("down"))
    e.user("u1")
    e.tick()
    assert run(e.db.push_prep.find_one({}))["source"] == "sober"


def test_desk_sensitive_article_forces_sober():
    e = Env()
    run(e.db.articles.update_many({}, {"$set": {"desk_sensitive": True}}))
    e.user("u1")
    e.tick()
    assert run(e.db.push_prep.find_one({}))["sober"] is True


def test_llm_daily_cap_falls_back():
    e = Env()
    e.svc.llm_daily_cap = 0
    e.user("u1")
    e.tick()
    assert run(e.db.push_prep.find_one({}))["source"] == "sober"


# ── delivery errors ─────────────────────────────────────────────────────────

def test_dead_token_deleted():
    e = Env()
    e.user("u1")
    e.fcm.script["tok-u1"] = [(404, {"error": {"details": [{"errorCode": "UNREGISTERED"}]}})]
    e.tick()
    e.tick(SUNRISE)
    assert run(e.db.push_devices.count_documents({})) == 0
    assert run(e.db.push_claims.find_one({}))["status"] == "failed"


def test_retry_then_success():
    e = Env()
    e.user("u1")
    e.fcm.script["tok-u1"] = [(503, {"error": {"details": [{"errorCode": "UNAVAILABLE"}]}})]
    e.tick()
    assert e.tick(SUNRISE)["sent"] == 1 and len(e.fcm.sent) == 2


def test_retries_exhausted():
    e = Env()
    e.user("u1")
    e.fcm.script["tok-u1"] = [(503, {})] * 3
    e.tick()
    assert e.tick(SUNRISE)["failed"] == 1 and len(e.fcm.sent) == 3
    assert run(e.db.push_devices.count_documents({})) == 1


def test_auth_error_keeps_tokens_and_alerts_once():
    e = Env()
    e.user("u1")
    e.user("u2")
    auth = (401, {"error": {"details": [{"errorCode": "THIRDPARTY_AUTH_ERROR"}], "message": "APNs"}})
    e.fcm.script = {"tok-u1": [auth], "tok-u2": [auth]}
    e.tick()
    e.tick(SUNRISE)
    assert run(e.db.push_devices.count_documents({})) == 2
    assert len([s for s in e.emails if "credentials" in s[1]]) == 1


def test_stale_claim_swept_and_alerted():
    e = Env()
    run(e.db.push_claims.insert_one({"_id": "u1|sunrise|2026-10-01", "status": "claimed", "slot": "sunrise",
                                     "window_end": SUNRISE + timedelta(minutes=30), "claimed_at": SUNRISE,
                                     "expires_at": SUNRISE + timedelta(days=14)}))
    e.tick(SUNRISE + timedelta(minutes=41))
    assert run(e.db.push_claims.find_one({}))["status"] == "stale"
    assert any("skipped" in s[1] for s in e.emails)


# ── opens ───────────────────────────────────────────────────────────────────

def test_opened_once_and_unknown_ignored():
    e = Env()
    e.user("u1")
    e.tick()
    e.tick(SUNRISE)
    pid = e.fcm.sent[0]["data"]["push_id"]
    assert run(e.svc.opened(pid)) is True
    assert run(e.svc.opened(pid)) is False
    assert run(e.svc.opened("nope")) is False
    assert run(e.svc.opened("x" * 100)) is False


# ── Breaking ────────────────────────────────────────────────────────────────

NOON = datetime(2026, 10, 1, 7, 0, tzinfo=timezone.utc)   # 12:30 IST


def breaking_env():
    e = Env(now=NOON)
    e.user("eco", interests=("Economy",))
    e.user("spo", interests=("Sports",))
    run(e.svc.register(token="G", platform="android", tz=IST, user_id=None))
    return e


def test_reach_topic_vs_national():
    e = breaking_env()
    r = run(e.svc.reach("a1", "Economy", national=False))
    assert (r["readers"], r["devices"]) == (1, 1)
    r = run(e.svc.reach("a1", "Economy", national=True))
    assert r["readers"] == 3                     # two users + the guest device


def test_send_breaking_receipt_and_caps():
    e = breaking_env()
    rec = run(e.svc.send_breaking(story_id="a1", text="Quake hits Uttarakhand!", category="Economy", national=True))
    assert rec["ok"] and rec["sent"] == 3 and rec["title"] == "Breaking" and "!" not in rec["body"]
    assert all(m["android"]["notification"]["channel_id"] == "breaking" for m in e.fcm.sent)
    assert all("image" not in m["notification"] for m in e.fcm.sent)
    e.clock.t = NOON + timedelta(hours=3)
    r = run(e.svc.reach("a2", "Sports", national=True))
    assert r["readers"] == 0 and r["held"]["cap_day"] == 3
    r = run(e.svc.reach("a1", "Economy", national=True))
    assert r["held"]["dup"] == 3


def test_breaking_quiet_hours_and_off():
    e = breaking_env()
    run(e.svc.set_prefs("spo", {"breaking": False}))
    e.clock.t = datetime(2026, 10, 1, 17, 0, tzinfo=timezone.utc)   # 22:30 IST
    r = run(e.svc.reach("a1", "Economy", national=True))
    assert r["held"]["quiet"] == 2 and r["held"]["off"] == 1


def test_breaking_blocked_when_switch_off():
    e = breaking_env()
    run(e.svc.set_enabled(False, "owner"))
    assert run(e.svc.send_breaking(story_id="a1", text="x", category="Economy", national=True))["ok"] is False
    assert e.fcm.sent == []


# ── test push, stats, preview ───────────────────────────────────────────────

def test_test_push_works_while_switch_off():
    e = Env(live=False)
    e.user("u1")
    res = run(e.svc.test_push("u1@x.in"))
    assert res["ok"] and res["devices"][0]["result"] == "delivered"
    assert run(e.svc.test_push("nobody@x.in"))["ok"] is False
    assert run(e.svc.test_push(""))["ok"] is False


def test_test_push_blocked_by_env():
    e = Env(env_on=False)
    e.user("u1")
    assert "PUSH_ENABLED" in run(e.svc.test_push("u1@x.in"))["error"]


def test_stats_and_next_slot_preview():
    e = Env()
    e.user("u1")
    prev = run(e.svc.next_slot_preview())
    assert prev == {"slot": "Sunrise", "local_time": "07:30", "tz": IST, "readers": 1}
    e.tick()
    e.tick(SUNRISE)
    run(e.svc.opened(e.fcm.sent[0]["data"]["push_id"]))
    s = run(e.svc.stats())
    assert s["rows"]["sunrise"] == {"sent": 1, "tapped": 1, "skipped": 0}
    assert s["readers"] == 1 and s["state"]["enabled"] is True


def test_alert_throttle():
    e = Env()
    assert run(e.svc.alert("x", "s", "t")) is True
    assert run(e.svc.alert("x", "s", "t")) is False
    e.clock.t += timedelta(hours=6, minutes=1)
    assert run(e.svc.alert("x", "s", "t")) is True



# ── 48h story repeat rule (owner saw Noon and Dusk both feature one article) ─

def test_next_slot_features_a_different_story():
    e = Env(now=P.slot_instant("noon", date(2026, 10, 1), IST) - timedelta(minutes=60))
    e.user("u1", interests=("Economy", "Sports"))
    run(e.svc.set_prefs("u1", {"noon": True}))
    noon = P.slot_instant("noon", date(2026, 10, 1), IST)
    e.tick()
    e.tick(noon)
    first = run(e.db.push_prep.find_one({"slot": "noon"}))["story_id"]
    e.tick(DUSK - timedelta(minutes=60))
    second = run(e.db.push_prep.find_one({"slot": "dusk"}))
    assert second["story_id"] and second["story_id"] != first


def test_slot_skipped_when_every_story_was_already_pushed():
    e = Env()
    e.user("u1", interests=("Economy", "Sports"))
    for i, aid in enumerate(("a1", "a2")):
        run(e.db.push_log.insert_one({"push_id": f"old{i}", "user_id": "u1", "status": "sent", "kind": "slot",
                                      "story_id": aid, "sent_at": SUNRISE - timedelta(hours=10), "opened_at": None}))
    e.tick()
    assert run(e.db.push_prep.find_one({}))["skip"] == "repeat"
    assert e.tick(SUNRISE)["skipped"] == 1 and e.fcm.sent == []
    assert run(e.db.push_claims.find_one({}))["reason"] == "repeat"

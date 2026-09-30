"""push.py: slot timing (incl. DST), quiet hours, gaps, Breaking caps, copy
rules, images, FCM message shapes and the FCM error table."""

from datetime import date, datetime, timedelta, timezone

import pytest

import push as P

UTC = timezone.utc
IST = "Asia/Kolkata"
SYD = "Australia/Sydney"


def utc(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=UTC)


# ── timing ──────────────────────────────────────────────────────────────────

def test_sunrise_ist_is_0200_utc():
    assert P.slot_instant("sunrise", date(2026, 10, 1), IST) == utc(2026, 10, 1, 2, 0)


def test_sydney_dst_keeps_local_0730():
    # Sydney moves to AEDT (UTC+11) on 2026-10-04.
    before = P.slot_instant("sunrise", date(2026, 10, 3), SYD)
    after = P.slot_instant("sunrise", date(2026, 10, 5), SYD)
    assert before == utc(2026, 10, 2, 21, 30)   # UTC+10
    assert after == utc(2026, 10, 4, 20, 30)    # UTC+11
    for d in (before, after):
        assert d.astimezone(P.zone(SYD)).strftime("%H:%M") == "07:30"


def test_unknown_tz_falls_back_to_ist():
    assert P.slot_instant("dusk", date(2026, 10, 1), "Mars/Olympus") == P.slot_instant("dusk", date(2026, 10, 1), IST)


@pytest.mark.parametrize("name,ok", [
    ("Asia/Kolkata", True), ("Australia/Sydney", True), ("America/Argentina/Buenos_Aires", True),
    ("", False), ("../etc/passwd", False), ("Mars/Olympus", False), ("A" * 80, False),
])
def test_valid_tz(name, ok):
    assert P.valid_tz(name) is ok


def test_due_window_30_min_then_skipped():
    at = utc(2026, 10, 1, 2, 0)
    assert [s[0] for s in P.due_slots(at, IST, None)] == ["sunrise"]
    assert [s[0] for s in P.due_slots(at + timedelta(minutes=29), IST, None)] == ["sunrise"]
    assert P.due_slots(at + timedelta(minutes=30), IST, None) == []
    assert P.due_slots(at - timedelta(minutes=1), IST, None) == []


def test_noon_off_by_default_on_when_opted_in():
    noon = P.slot_instant("noon", date(2026, 10, 1), IST)
    assert P.due_slots(noon, IST, None) == []
    assert [s[0] for s in P.due_slots(noon, IST, {"noon": True})] == ["noon"]


def test_toggle_off_dusk():
    dusk = P.slot_instant("dusk", date(2026, 10, 1), IST)
    assert P.due_slots(dusk, IST, {"dusk": False}) == []


def test_prep_starts_60_min_early():
    at = P.slot_instant("sunrise", date(2026, 10, 1), IST)
    assert P.prep_slots(at - timedelta(minutes=61), IST, None) == []
    assert [s[0] for s in P.prep_slots(at - timedelta(minutes=60), IST, None)] == ["sunrise"]
    assert [s[0] for s in P.prep_slots(at + timedelta(minutes=10), IST, None)] == ["sunrise"]


def test_first_brief_needs_prep_lead():
    # 19:00 IST: Dusk at 19:30 can't be prepared any more → tomorrow's Sunrise.
    now = utc(2026, 10, 1, 13, 30)
    key, day, _ = P.first_brief_slot(now, IST, None)
    assert (key, day) == ("sunrise", date(2026, 10, 2))
    # 18:00 IST: Dusk is still preparable.
    key, day, _ = P.first_brief_slot(utc(2026, 10, 1, 12, 30), IST, None)
    assert (key, day) == ("dusk", date(2026, 10, 1))


def test_pin_valid_until_next_slot_of_any_kind():
    sunrise = P.slot_instant("sunrise", date(2026, 10, 1), IST)
    assert P.pin_valid_until(sunrise, IST) == P.slot_instant("noon", date(2026, 10, 1), IST)
    dusk = P.slot_instant("dusk", date(2026, 10, 1), IST)
    assert P.pin_valid_until(dusk, IST) == P.slot_instant("sunrise", date(2026, 10, 2), IST)


@pytest.mark.parametrize("hhmm,quiet", [("21:59", False), ("22:00", True), ("03:00", True), ("06:59", True), ("07:00", False)])
def test_quiet_hours(hhmm, quiet):
    h, m = map(int, hhmm.split(":"))
    local = datetime(2026, 10, 1, h, m, tzinfo=P.zone(IST))
    assert P.in_quiet_hours(local) is quiet


def test_gap():
    now = utc(2026, 10, 1, 10)
    assert P.gap_ok(None, now)
    assert not P.gap_ok(now - timedelta(minutes=89), now)
    assert P.gap_ok(now - timedelta(minutes=90), now)


def test_breaking_caps_and_quiet():
    noon_ist = utc(2026, 10, 1, 7, 0)       # 12:30 IST
    assert P.breaking_hold(noon_ist, IST, None, []) is None
    assert P.breaking_hold(utc(2026, 10, 1, 17, 0), IST, None, []) == "quiet"          # 22:30 IST
    assert P.breaking_hold(noon_ist, IST, None, [noon_ist - timedelta(hours=3)]) == "cap_day"
    week = [noon_ist - timedelta(days=2), noon_ist - timedelta(days=4)]
    assert P.breaking_hold(noon_ist, IST, None, week) == "cap_week"
    assert P.breaking_hold(noon_ist, IST, noon_ist - timedelta(minutes=30), []) == "gap"
    assert P.breaking_hold(noon_ist, IST, None, [noon_ist - timedelta(days=8)] * 3) is None


# ── copy ────────────────────────────────────────────────────────────────────

def test_every_template_passes_its_own_rules():
    for slot, lines in P.TEMPLATES.items():
        for tid, title, body in lines:
            t = title.format(name="Asha")
            b = body.format(hook="x" * P.HOOK_MAX)
            assert P.copy_problem(t, b, slot, False, from_ai=False) is None, tid
    for slot, (tid, title, body) in P.SOBER_TEMPLATES.items():
        assert P.copy_problem(title, body.format(hook="x" * P.HOOK_MAX), slot, True, from_ai=False) is None, tid


def test_sun_emoji_only_in_templates():
    assert P.copy_problem("Rise and read ☀", "ok body", "sunrise", False, from_ai=False) is None
    assert P.copy_problem("Rise and read ☀", "ok body", "sunrise", False, from_ai=True) == "emoji"
    assert P.copy_problem("Rise and read 🚀", "ok body", "sunrise", False, from_ai=False) == "emoji"


@pytest.mark.parametrize("title,body,why", [
    ("x" * 33 + " sunrise", "b", "title_long"),
    ("Sunrise", "b" * 111, "body_long"),
    ("Sunrise!", "b", "exclamation"),
    ("Sunrise: just in", "b", "banned"),
    ("Good morning", "b", "no_sun_word"),
    ("", "b", "empty"),
])
def test_copy_problems(title, body, why):
    assert P.copy_problem(title, body, "sunrise", False, from_ai=True) == why


@pytest.mark.parametrize("name,out", [
    ("Deepesh Batra", "Deepesh"), ("  asha ", "asha"), ("Bartholomew-Jones", None),
    ("", None), (None, None), ("123", None), ("Dr. Rao", "Dr"),
])
def test_first_name(name, out):
    assert P.first_name(name) == out


def test_clip_words():
    assert P.clip_words("short", 10) == "short"
    out = P.clip_words("the monsoon leaves late for the fourth year running", 20)
    assert len(out) <= 20 and out.endswith("…") and " " not in out[-2:]


GOOD_AI = {"sensitive": False, "hook": "RBI holds rates, again", "title": "Surya's up, rates aren't"}


def test_compose_ai_path():
    c = P.compose_slot_copy("sunrise", "RBI holds repo rate", GOOD_AI, [], "Deepesh Batra", 0)
    assert (c.title, c.source, c.sober) == ("Surya's up, rates aren't", "ai", False)
    assert "RBI holds rates, again" in c.body


def test_compose_bad_ai_title_uses_template_title():
    ai = dict(GOOD_AI, title="Rates frozen!!")
    c = P.compose_slot_copy("sunrise", "RBI holds repo rate", ai, [], None, 0)
    assert c.title in {t[1] for t in P.TEMPLATES["sunrise"]}
    assert "RBI holds rates, again" in c.body and c.source == "ai"


def test_compose_bad_hook_uses_headline():
    ai = dict(GOOD_AI, hook="x" * 80, title=None)
    c = P.compose_slot_copy("dusk", "Monsoon exits late", ai, [], None, 0)
    assert "Monsoon exits late" in c.body and c.source == "template"


@pytest.mark.parametrize("ai", [None, {"sensitive": True, "hook": "h", "title": "Sunrise pun"}])
def test_sensitive_or_no_verdict_is_sober(ai):
    c = P.compose_slot_copy("sunrise", "Bus accident kills 12 in Himachal", ai, [], "Asha", 0)
    assert c.sober and c.title == "Your Sunrise brief" and c.source == "sober"
    assert not P.has_emoji(c.title + c.body)


def test_desk_sensitive_forces_sober():
    c = P.compose_slot_copy("dusk", "Headline", GOOD_AI, [], None, 0, force_sober=True)
    assert c.sober and c.title == "Your Dusk brief"


def test_rotation_avoids_recent_and_name_lines_without_name():
    ids = {P.pick_template("sunrise", ["sr1", "sr2"], None, s)[0] for s in range(10)}
    assert ids == {"sr4"}                       # sr3 needs a name
    ids = {P.pick_template("sunrise", ["sr1", "sr2", "sr3", "sr4"], "Asha", s)[0] for s in range(10)}
    assert ids == {"sr1", "sr2", "sr3", "sr4"}  # all recent → rotate through all


def test_every_composed_copy_is_sendable():
    heads = ["A", "x" * 200, "Crowds 🎉 cheer the win"]
    ais = [None, GOOD_AI, {"sensitive": False, "hook": "🚀" * 3, "title": "🚀"}]
    for slot in P.SLOT_ORDER:
        for h in heads:
            for ai in ais:
                for s in range(4):
                    c = P.compose_slot_copy(slot, h, ai, [], "Asha", s)
                    assert P.copy_problem(c.title, c.body, slot, c.sober, from_ai=False) is None, (slot, h, ai, c)


def test_breaking_copy():
    title, body = P.breaking_copy("Quake hits Uttarakhand! 🚨 " + "y" * 200)
    assert title == "Breaking" and "!" not in body and not P.has_emoji(body) and len(body) <= 110


def test_parse_hook():
    assert P.parse_hook('```json\n{"sensitive": false, "hook": "h", "title": null}\n```') == \
        {"sensitive": False, "hook": "h", "title": None}
    assert P.parse_hook('{"hook": "h"}')["sensitive"] is True      # missing = unsure = sober
    assert P.parse_hook("nope") is None and P.parse_hook(None) is None and P.parse_hook("{bad json}") is None


def test_hook_prompt_mentions_limits():
    p = P.hook_prompt("dusk", "Headline", "Summary")
    assert str(P.HOOK_MAX) in p and str(P.TITLE_MAX) in p and "Dusk" in p


# ── images ──────────────────────────────────────────────────────────────────

def test_image_rules():
    url = "https://img.example/a.jpg"
    assert P.push_image("sunrise", False, url) == url
    assert P.push_image("sunrise", True, url) is None                 # sober
    assert P.push_image("noon", False, url) is None                   # Sunrise/Dusk only
    assert P.push_image(None, False, url) is None                     # Breaking
    assert P.push_image("dusk", False, "http://img.example/a.jpg") is None
    assert P.push_image("dusk", False, url, 400, 300) is None         # too small
    assert P.push_image("dusk", False, url, 800, 1200) is None        # portrait
    assert P.push_image("dusk", False, url, 1200, 630) == url


# ── messages ────────────────────────────────────────────────────────────────

def test_android_message():
    m = P.build_message(token="t", platform="android", kind="slot", title="T", body="B",
                        data={"push_id": "p", "n": 1}, ttl_seconds=900, now_epoch=1000,
                        slot_key="sunrise", image="https://i/x.jpg")
    assert m["notification"] == {"title": "T", "body": "B", "image": "https://i/x.jpg"}
    assert m["android"]["notification"]["channel_id"] == "daily"
    assert m["android"]["notification"]["color"] == "#DC2626"
    assert m["android"]["ttl"] == "900s" and m["android"]["priority"] == "NORMAL"
    assert m["data"] == {"push_id": "p", "n": "1"} and "apns" not in m


def test_ios_breaking_message():
    m = P.build_message(token="t", platform="ios", kind="breaking", title="Breaking", body="B",
                        data={}, ttl_seconds=3600, now_epoch=1000)
    aps = m["apns"]["payload"]["aps"]
    assert aps["interruption-level"] == "active" and aps["thread-id"] == "breaking"
    assert m["apns"]["headers"] == {"apns-priority": "10", "apns-expiration": "4600"}
    assert "android" not in m


@pytest.mark.parametrize("status,body,out", [
    (404, {"error": {"status": "NOT_FOUND", "details": [{"errorCode": "UNREGISTERED"}]}}, "dead"),
    (403, {"error": {"details": [{"errorCode": "SENDER_ID_MISMATCH"}]}}, "dead"),
    (400, {"error": {"status": "INVALID_ARGUMENT", "message": "The registration token is not a valid FCM registration token",
                     "details": [{"errorCode": "INVALID_ARGUMENT"}]}}, "dead"),
    (400, {"error": {"status": "INVALID_ARGUMENT", "message": "Invalid value at 'message.android.ttl'"}}, "bad_request"),
    (503, {"error": {"details": [{"errorCode": "UNAVAILABLE"}]}}, "retry"),
    (429, {"error": {"details": [{"errorCode": "QUOTA_EXCEEDED"}]}}, "retry"),
    (500, None, "retry"),
    (401, {"error": {"details": [{"errorCode": "THIRDPARTY_AUTH_ERROR"}]}}, "auth"),
    (401, {}, "auth"),
    (403, {"error": {"status": "PERMISSION_DENIED"}}, "auth"),
    (418, {}, "other"),
])
def test_fcm_error_table(status, body, out):
    assert P.classify_fcm_error(status, body) == out

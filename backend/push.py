"""Push rules, copy and message builders. Pure: no I/O, no clock, no randomness
the caller doesn't pass in, so every rule is unit-testable.

Slots ("slots, not streams"): at most one push per slot per reader.

    local day  07:00 ────────────── 22:00   (quiet hours outside, absolute)
               │ SUNRISE 07:30 │ NOON 13:00 │ DUSK 19:30 │
               ├── prep at slot-60m ──┤ send in [slot, slot+30m) ── then skipped, never late
               └── never two pushes within 90 min (Breaking included)

Copy (v2, owner feedback 2026-10-01): the time of day is a subtle hint in the
BODY ("This morning:", "Lunch, with a side of context:", "Tonight:"), never forced
sun/Surya/Chintan wordplay in the title. The title is free to be a witty line about
the story itself. Title <= 32, body <= 110. AI copy is garnish: any failed check
falls back to a hand-written template (R9). Sober mode = no wit, no emoji, no photo.
A story is never pushed to the same reader twice within 48h (push_service).

FCM error table (eng review 6A): dead token -> delete; busy -> retry in window;
our key/auth broken -> keep tokens + alert owner.
"""

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# ── slots and timing ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Slot:
    key: str            # sunrise | noon | dusk
    brief_type: str     # morning | midday | night (brief_service types)
    at: time            # local time
    default_on: bool
    label: str          # reader-facing name
    time_words: Tuple[str, ...]  # a subtle time-of-day cue; one must appear in title or body


SLOTS: Dict[str, Slot] = {
    "sunrise": Slot("sunrise", "morning", time(7, 30), True, "Sunrise",
                    ("morning", "breakfast", "chai", "start the day", "the day gets", "wake")),
    "noon":    Slot("noon", "midday", time(13, 0), False, "High Noon",
                    ("lunch", "midday", "afternoon", "noon", "half the day", "since morning")),
    "dusk":    Slot("dusk", "night", time(19, 30), True, "Dusk",
                    ("evening", "tonight", "night", "the day", "call it a day", "dinner")),
}
SLOT_ORDER = ("sunrise", "noon", "dusk")

WINDOW = timedelta(minutes=30)        # a slot sends only inside [at, at+30m)
PREP_LEAD = timedelta(minutes=60)     # prepare brief + copy this far ahead
MIN_GAP = timedelta(minutes=90)       # never two pushes this close
STALE_CLAIM_GRACE = timedelta(minutes=10)
QUIET_START = time(22, 0)
QUIET_END = time(7, 0)
BREAKING_PER_DAY = 1
BREAKING_PER_WEEK = 2
DEFAULT_TZ = "Asia/Kolkata"

PREF_KEYS = ("sunrise", "noon", "dusk", "breaking")
DEFAULT_PREFS = {"sunrise": True, "noon": False, "dusk": True, "breaking": True}


def zone(name: Optional[str]) -> ZoneInfo:
    """An IANA zone (DST-safe). Unknown or empty names fall back to IST, the
    app's home zone, rather than failing a whole scheduling tick."""
    try:
        return ZoneInfo(name or DEFAULT_TZ)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TZ)


def valid_tz(name: str) -> bool:
    if not name or len(name) > 64 or not re.fullmatch(r"[A-Za-z_]+(/[A-Za-z0-9_+\-]+){0,2}", name):
        return False
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def prefs_with_defaults(prefs: Optional[dict]) -> dict:
    out = dict(DEFAULT_PREFS)
    for k in PREF_KEYS:
        if prefs and isinstance(prefs.get(k), bool):
            out[k] = prefs[k]
    return out


def slot_instant(slot_key: str, local_day: date, tz_name: Optional[str]) -> datetime:
    """The UTC instant of a slot on a local calendar day. zoneinfo resolves DST:
    07:30 stays 07:30 local on both sides of a clock change."""
    tz = zone(tz_name)
    local = datetime.combine(local_day, SLOTS[slot_key].at, tzinfo=tz)
    return local.astimezone(timezone.utc)


def local_now(now_utc: datetime, tz_name: Optional[str]) -> datetime:
    return now_utc.astimezone(zone(tz_name))


def in_quiet_hours(local_dt: datetime) -> bool:
    t = local_dt.timetz().replace(tzinfo=None)
    return t >= QUIET_START or t < QUIET_END


def _candidate_days(now_utc: datetime, tz_name: Optional[str]) -> List[date]:
    today = local_now(now_utc, tz_name).date()
    return [today - timedelta(days=1), today, today + timedelta(days=1)]


def enabled_slots(prefs: Optional[dict]) -> List[str]:
    p = prefs_with_defaults(prefs)
    return [k for k in SLOT_ORDER if p[k]]


def due_slots(now_utc: datetime, tz_name: Optional[str], prefs: Optional[dict]) -> List[Tuple[str, date, datetime]]:
    """Slots whose send window [at, at+WINDOW) contains now."""
    out = []
    for day in _candidate_days(now_utc, tz_name):
        for key in enabled_slots(prefs):
            at = slot_instant(key, day, tz_name)
            if at <= now_utc < at + WINDOW:
                out.append((key, day, at))
    return out


def prep_slots(now_utc: datetime, tz_name: Optional[str], prefs: Optional[dict]) -> List[Tuple[str, date, datetime]]:
    """Slots to prepare now: at - PREP_LEAD <= now < at + WINDOW. Preparation
    is idempotent (keyed per reader+slot+day), so the overlap with the send
    window just gives a late-registering reader a chance to still be prepared."""
    out = []
    for day in _candidate_days(now_utc, tz_name):
        for key in enabled_slots(prefs):
            at = slot_instant(key, day, tz_name)
            if at - PREP_LEAD <= now_utc < at + WINDOW:
                out.append((key, day, at))
    return out


def next_slot(now_utc: datetime, tz_name: Optional[str], prefs: Optional[dict],
              after: Optional[datetime] = None) -> Optional[Tuple[str, date, datetime]]:
    """The next enabled slot strictly after `after` (default now)."""
    after = after or now_utc
    best = None
    today = local_now(now_utc, tz_name).date()
    for offset in range(0, 3):
        day = today + timedelta(days=offset)
        for key in enabled_slots(prefs):
            at = slot_instant(key, day, tz_name)
            if at > after and (best is None or at < best[2]):
                best = (key, day, at)
    return best


def first_brief_slot(now_utc: datetime, tz_name: Optional[str], prefs: Optional[dict]) -> Optional[Tuple[str, date, datetime]]:
    """The first slot a reader who just opted in will actually receive: it
    must still be preparable, i.e. at least PREP_LEAD away (design review:
    "First brief: tomorrow, 07:30")."""
    return next_slot(now_utc, tz_name, prefs, after=now_utc + PREP_LEAD)


def pin_valid_until(slot_at: datetime, tz_name: Optional[str]) -> datetime:
    """A pin wins until the next slot of ANY kind (all three, regardless of
    prefs), so Briefs from the menu shows the pushed brief until a newer one
    could exist."""
    nxt = next_slot(slot_at, tz_name, {"sunrise": True, "noon": True, "dusk": True}, after=slot_at)
    return nxt[2] if nxt else slot_at + timedelta(hours=6)


def gap_ok(last_sent: Optional[datetime], now_utc: datetime) -> bool:
    return last_sent is None or now_utc - last_sent >= MIN_GAP


def breaking_hold(now_utc: datetime, tz_name: Optional[str], last_sent: Optional[datetime],
                  breaking_sent: Sequence[datetime]) -> Optional[str]:
    """Why a Breaking push must be held for this reader, or None to send.
    Reasons: quiet | cap_day | cap_week | gap."""
    local = local_now(now_utc, tz_name)
    if in_quiet_hours(local):
        return "quiet"
    today = local.date()
    same_day = [t for t in breaking_sent if local_now(t, tz_name).date() == today]
    if len(same_day) >= BREAKING_PER_DAY:
        return "cap_day"
    week = [t for t in breaking_sent if now_utc - t < timedelta(days=7)]
    if len(week) >= BREAKING_PER_WEEK:
        return "cap_week"
    if not gap_ok(last_sent, now_utc):
        return "gap"
    return None


# ── copy ─────────────────────────────────────────────────────────────────────

TITLE_MAX = 32
BODY_MAX = 110
HOOK_MAX = 45
NAME_MAX = 12

# Hand-written lines (the floor under the AI). Every BODY carries a subtle
# time-of-day cue, so any title (template or AI) can sit on top. No line claims
# the hook is the brief's first story ("opens with"/"leads"): after the 48h
# repeat rule the hook may be the 2nd or 3rd story. No emoji anywhere.
TEMPLATES: Dict[str, List[Tuple[str, str, str]]] = {
    # (template_id, title, body) - body contains {hook}; title may contain {name}
    "sunrise": [
        ("sr5", "Your morning three", "This morning: {hook}, and 2 more."),
        ("sr6", "Before the day gets loud", "Over chai: {hook}, and two more worth knowing."),
        ("sr7", "Morning, {name}", "This morning: {hook}. Three stories, two minutes."),
        ("sr8", "Three for your chai", "Before the day gets loud: {hook}, and 2 more."),
    ],
    "noon": [
        ("nn3", "Half the day, whole picture", "{hook}, plus what else moved since morning."),
        ("nn4", "Your lunchtime read", "Lunch, with a side of context: {hook}."),
    ],
    "dusk": [
        ("dk4", "The day, distilled", "Tonight: {hook}, and two more worth knowing."),
        ("dk5", "Tonight's three", "Before you scroll the night away: {hook}."),
        ("dk6", "Before you call it a day", "The day in three, including {hook}."),
    ],
}
SOBER_TEMPLATES: Dict[str, Tuple[str, str, str]] = {
    "sunrise": ("srS", "Your morning brief", "This morning: {hook}. And 2 more stories."),
    "noon":    ("nnS", "Your afternoon brief", "This afternoon: {hook}. And 2 more stories."),
    "dusk":    ("dkS", "Your evening brief", "This evening: {hook}. And 2 more stories."),
}
# Brand words an AI title may not lean on (unless the story itself is about them).
BRAND_WORDS = ("sun", "surya", "chintan", "sunrise", "sunset", "dusk")

_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\U00002B00-\U00002BFF️‍]"
)
BANNED = [
    r"\bjust in\b", r"\bright now\b", r"\bjust now\b", r"\bbreaking\b", r"\burgent\b",
    r"you won'?t believe", r"\bshocking\b", r"\bmust[- ]read\b", r"\bdon'?t miss\b",
    r"\bwe miss you\b", r"\bclick\b", r"\bexclusive\b",
]
_BANNED = re.compile("|".join(BANNED), re.IGNORECASE)


def has_emoji(text: str) -> bool:
    return bool(_EMOJI.search(text or ""))


def strip_emoji(text: str) -> str:
    return re.sub(r"\s{2,}", " ", _EMOJI.sub("", text or "")).strip()


def first_name(name: Optional[str]) -> Optional[str]:
    """First name only, <= 12 chars, letters only; else None (template without
    a name). Never prints a full Google display name (DR-11A)."""
    if not name:
        return None
    first = name.strip().split()[0] if name.strip() else ""
    first = first.strip(".,")
    if not first or len(first) > NAME_MAX or not re.fullmatch(r"[^\W\d_][^\W\d_'\-]*", first):
        return None
    return first


def clip_words(text: str, limit: int) -> str:
    """Trim at a word boundary to <= limit, with an ellipsis if cut."""
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:-—")
    return (cut or text[: limit - 1]) + "…"


def plain_hook(headline: str) -> str:
    """The sober/fallback hook: the lead headline, trimmed, no emoji."""
    return clip_words(strip_emoji(headline).rstrip("."), HOOK_MAX)


def copy_problem(title: str, body: str, slot_key: Optional[str], sober: bool,
                 from_ai: bool) -> Optional[str]:
    """Why this title/body can't be sent, or None. Used on AI output and as a
    last guard on templates."""
    if not title or not body:
        return "empty"
    if len(title) > TITLE_MAX:
        return "title_long"
    if len(body) > BODY_MAX:
        return "body_long"
    if "!" in title or "!" in body:
        return "exclamation"
    if (from_ai or sober) and (has_emoji(title) or has_emoji(body)):
        return "emoji"
    if has_emoji(title) or has_emoji(body):
        return "emoji"
    if slot_key and _BANNED.search(title + " " + body):
        return "banned"
    if slot_key and not any(w in (title + " " + body).lower() for w in SLOTS[slot_key].time_words):
        return "no_time_cue"
    return None


def leans_on_brand(title: str, headline: str) -> bool:
    """True if an AI title forces sun/Surya/Chintan wordplay the story doesn't
    contain (owner feedback: 'too much SUN SUN')."""
    t, h = title.lower(), (headline or "").lower()
    return any(re.search(rf"\b{w}\b", t) and not re.search(rf"\b{w}\b", h) for w in BRAND_WORDS)


def pick_template(slot_key: str, recent_ids: Iterable[str], name: Optional[str], salt: int) -> Tuple[str, str, str]:
    """Rotate so a reader never sees the same line twice in 7 days (the caller
    passes the ids sent in the last 7 days). `salt` (e.g. day number + user
    hash) keeps readers from all getting the same line on the same day."""
    options = [t for t in TEMPLATES[slot_key] if "{name}" not in t[1] or name]
    fresh = [t for t in options if t[0] not in set(recent_ids)] or options
    return fresh[salt % len(fresh)]


@dataclass
class SlotCopy:
    title: str
    body: str
    template_id: str
    source: str       # "ai" | "template" | "sober"
    sober: bool


def compose_slot_copy(slot_key: str, lead_headline: str, ai: Optional[dict], recent_ids: Iterable[str],
                      name: Optional[str], salt: int, force_sober: bool = False) -> SlotCopy:
    """Assemble the push text for one reader's slot. Never fails: every path
    ends in a checked template line.

      force_sober (Desk sensitive box), ai.sensitive, or no AI verdict ─▶ sober
      ai hook passes checks ─▶ ai title if it passes, else template title
      ai hook fails checks ─▶ template with the plain headline as hook

    No AI verdict (timeout, bad JSON) is "unsure", and unsure = sober: a witty
    template wrapped around an unchecked headline is the failure this avoids.
    """
    fname = first_name(name)
    sober = force_sober or ai is None or ai.get("sensitive") is not False
    if sober:
        tid, title, body = SOBER_TEMPLATES[slot_key]
        body = body.format(hook=plain_hook(lead_headline))
        return SlotCopy(title, clip_words(body, BODY_MAX), tid, "sober", True)

    tid, t_title, t_body = pick_template(slot_key, recent_ids, fname, salt)
    t_title = t_title.format(name=fname or "")

    hook = None
    if ai and isinstance(ai.get("hook"), str):
        cand = strip_emoji(ai["hook"]).rstrip(".")
        if cand and len(cand) <= HOOK_MAX and not _BANNED.search(cand) and "!" not in cand:
            hook = cand
    source = "ai" if hook else "template"
    hook = hook or plain_hook(lead_headline)
    body = t_body.format(hook=hook)
    if len(body) > BODY_MAX:
        body = t_body.format(hook=clip_words(hook, max(12, HOOK_MAX - (len(body) - BODY_MAX))))
    title = t_title
    ai_title = ai.get("title") if ai else None
    if isinstance(ai_title, str) and ai_title.strip():
        cand = ai_title.strip()
        if (copy_problem(cand, body, slot_key, False, from_ai=True) is None
                and not leans_on_brand(cand, lead_headline)):
            title, source = cand, "ai"
    if copy_problem(title, body, slot_key, False, from_ai=False):
        # Last guard: the plainest template line for this slot.
        tid, title, t_body = TEMPLATES[slot_key][0]
        body = clip_words(t_body.format(hook=plain_hook(lead_headline)), BODY_MAX)
        source = "template"
    return SlotCopy(title, body, tid, source, False)


def breaking_copy(text: str) -> Tuple[str, str]:
    """Breaking is sober by design: fixed title, the Desk's text, no emoji,
    no exclamation, <= 110 (DR-8A)."""
    body = clip_words(strip_emoji(text).replace("!", "."), BODY_MAX)
    return "Breaking", body


# ── the hook prompt (one short LLM call per prepared brief, eng 12A) ─────────

def hook_prompt(slot_key: str, headline: str, summary: str) -> str:
    slot = SLOTS[slot_key]
    when = {"sunrise": "morning", "noon": "lunchtime", "dusk": "evening"}[slot_key]
    return (
        "You write push-notification copy for Chintan, an Indian news app. "
        "Voice: warm, witty, Indian English, never clickbait. This is the reader's "
        f"{when} brief, and the push features this story:\n"
        f"HEADLINE: {headline[:300]}\nSUMMARY: {summary[:600]}\n\n"
        "Return ONLY a JSON object with keys:\n"
        '  "sensitive": true if the story involves death, disaster, violence, crime against people, '
        "communal or religious conflict, illness, or anything a reader could be grieving; also true if unsure.\n"
        f'  "hook": the story compressed to <= {HOOK_MAX} characters, factual, no emoji, no exclamation mark, '
        'no "just in"/"right now".\n'
        f'  "title": only if sensitive is false, a title of <= {TITLE_MAX} characters with light, kind wordplay '
        "drawn from THE STORY ITSELF (its people, place, numbers or stakes). Do NOT mention the sun, sunrise, "
        "sunset, dusk, Surya or Chintan, and do not force a time-of-day pun; a time hint is fine only if it "
        "comes naturally. No emoji, no exclamation mark. If you can't do it well, use null.\n"
    )


def parse_hook(raw: Optional[str]) -> Optional[dict]:
    """Parse the model's JSON. Anything malformed -> None (caller uses the
    template path, which is sober only if the Desk said so). An unparseable
    `sensitive` counts as sensitive: unsure = sober."""
    if not raw:
        return None
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    sensitive = data.get("sensitive")
    return {
        "sensitive": sensitive if isinstance(sensitive, bool) else True,
        "hook": data.get("hook") if isinstance(data.get("hook"), str) else None,
        "title": data.get("title") if isinstance(data.get("title"), str) else None,
    }


# ── images ───────────────────────────────────────────────────────────────────

def push_image(slot_key: Optional[str], sober: bool, image_url: Optional[str],
               width: Optional[int] = None, height: Optional[int] = None) -> Optional[str]:
    """Photo rules (DR-10A): never on Breaking or sober pushes; https only;
    landscape >= 600px when the size is known."""
    if not slot_key or slot_key not in ("sunrise", "dusk") or sober or not image_url:
        return None
    if not image_url.startswith("https://"):
        return None
    if width is not None and height is not None and (width < 600 or width < height):
        return None
    return image_url


# ── FCM HTTP v1 messages ─────────────────────────────────────────────────────

ANDROID_ICON = "ic_stat_surya"
ACCENT = "#DC2626"


def build_message(*, token: str, platform: str, kind: str, title: str, body: str,
                  data: Dict[str, str], ttl_seconds: int, now_epoch: int, slot_key: Optional[str] = None,
                  subtitle: Optional[str] = None, image: Optional[str] = None) -> dict:
    """One FCM v1 `message` for one device (eng 2A/11B). Android: a standard
    notification on channel "daily" or "breaking" with the Surya icon and red
    accent. iOS: an APNs alert with subtitle and a thread per slot. TTL keeps a
    push from arriving after its window (missed = skipped, never late)."""
    ttl = max(60, int(ttl_seconds))
    str_data = {k: str(v) for k, v in data.items() if v is not None}
    notification = {"title": title, "body": body}
    if image:
        notification["image"] = image
    msg = {"token": token, "notification": notification, "data": str_data}
    if platform == "ios":
        alert = {"title": title, "body": body}
        if subtitle:
            alert["subtitle"] = subtitle
        aps = {"alert": alert, "thread-id": slot_key or kind, "interruption-level": "active"}
        if kind == "breaking":
            aps["sound"] = "default"
        msg["apns"] = {
            "headers": {"apns-priority": "10" if kind == "breaking" else "5",
                        "apns-expiration": str(int(now_epoch) + ttl)},
            "payload": {"aps": aps},
        }
    else:
        msg["android"] = {
            "priority": "HIGH" if kind == "breaking" else "NORMAL",
            "ttl": f"{ttl}s",
            "notification": {
                "channel_id": "breaking" if kind == "breaking" else "daily",
                "icon": ANDROID_ICON,
                "color": ACCENT,
                "tag": slot_key or kind,
            },
        }
    return msg


FCM_DEAD = {"UNREGISTERED", "SENDER_ID_MISMATCH"}
FCM_RETRY = {"UNAVAILABLE", "INTERNAL", "QUOTA_EXCEEDED"}
FCM_AUTH = {"THIRDPARTY_AUTH_ERROR"}


def classify_fcm_error(http_status: int, body: Optional[dict]) -> str:
    """dead | retry | auth | bad_request | other (eng review 6A).
    dead -> delete the token. retry -> backoff within the window. auth -> our
    credentials or the APNs key are broken: keep every token, alert the owner."""
    err = (body or {}).get("error") or {}
    codes = {d.get("errorCode") for d in err.get("details") or [] if isinstance(d, dict)}
    status = err.get("status") or ""
    message = (err.get("message") or "").lower()
    codes.discard(None)
    if codes & FCM_AUTH:
        return "auth"
    if codes & FCM_DEAD or status == "NOT_FOUND" and "unregistered" in message:
        return "dead"
    if "INVALID_ARGUMENT" in codes or status == "INVALID_ARGUMENT":
        return "dead" if "token" in message else "bad_request"
    if http_status in (401, 403):
        return "auth"
    if codes & FCM_RETRY or http_status in (429, 500, 502, 503, 504):
        return "retry"
    if http_status == 404:
        return "dead"
    return "other"

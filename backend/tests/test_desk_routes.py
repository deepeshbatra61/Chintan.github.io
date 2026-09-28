"""HTTP-level tests for the Desk API (D6): real requests through FastAPI
against an in-memory MongoDB, so a route that forgets a gate fails here.

    every route  ── no/wrong proxy secret ─▶ 404
    session routes ─ no/expired/revoked session ─▶ 401
    mutating routes ─ missing/wrong CSRF ─▶ 403
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("fastapi")
mongomock_motor = pytest.importorskip("mongomock_motor")
pyotp = pytest.importorskip("pyotp")
import httpx  # noqa: E402
from cryptography.fernet import Fernet  # noqa: E402
from fastapi import FastAPI  # noqa: E402

import desk  # noqa: E402
import desk_auth as A  # noqa: E402
import desk_routes  # noqa: E402
import research  # noqa: E402

PROXY = "proxy-secret-for-tests"
KEY = Fernet.generate_key().decode()
SECRET = pyotp.random_base32()
EMAIL = "owner@chintan.news"
PASSWORD = "correct horse battery staple 42"
IP = "203.0.113.9"

GOOD_RESEARCH = {
    "ok": True, "headline": "Supreme Court strikes down electoral bond scheme",
    "summary": "The Supreme Court struck down the scheme and ordered disclosure.",
    "points": ["Unanimous five-judge bench.", "SBI to share donor data."],
    "keywords": ["electoral bonds", "supreme court", "sbi"],
    "citations": [{"url": "https://www.thehindu.com/a", "title": "a"},
                  {"url": "https://indianexpress.com/b", "title": "b"}],
    "domain_count": 2,
}


class Harness:
    def __init__(self):
        self.db = mongomock_motor.AsyncMongoMockClient()["t"]
        self.clock_offset = timedelta(0)
        self.emails = []
        self.email_ok = True
        self.research_result = dict(GOOD_RESEARCH)
        self.research_calls = 0
        self.research_gate = None
        self.research_args = []
        self.pages = {}          # url -> meta dict the fake fetcher returns
        self.auth = A.DeskAuth(self.db, KEY, now=self.now)
        app = FastAPI()
        app.include_router(desk_routes.build_desk_router(
            db=self.db, auth=self.auth, proxy_secret=lambda: PROXY,
            admin_emails=lambda: {EMAIL}, research=self._research, fetch_meta=self._fetch, send_email=self._email,
            registrable_domain=research._registrable_domain,
            suggest_category=lambda t: "Politics", default_image="https://img.example/x.jpg",
            logger=__import__("logging").getLogger("t"),
        ), prefix="/api")
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
        self.token = self.csrf = None

    def now(self):
        return datetime.now(timezone.utc) + self.clock_offset

    async def _fetch(self, url):
        page = self.pages.get(url)
        return dict(page) if page else None

    async def _research(self, topic, source=None):
        self.research_calls += 1
        self.research_args.append((topic, source))
        if self.research_gate:
            await self.research_gate.wait()
        return self.research_result

    async def _email(self, to, subject, text):
        self.emails.append((to, subject))
        return self.email_ok

    async def seed_admin(self):
        await self.db.desk_admins.insert_one({
            "admin_id": "adm_1", "email": EMAIL, "pw_hash": A.hash_password(PASSWORD),
            "totp_secret_enc": A.Crypto(KEY).encrypt(SECRET), "totp_last_step": 0})

    def headers(self, session=True, csrf=True, proxy=PROXY):
        h = {"x-desk-client-ip": IP, "user-agent": "pytest"}
        if proxy:
            h["x-desk-proxy"] = proxy
        if session and self.token:
            h["x-desk-session"] = self.token
        if csrf and self.csrf:
            h["x-desk-csrf"] = self.csrf
        return h

    async def login(self, password=PASSWORD, code=None, email=EMAIL):
        code = code or pyotp.TOTP(SECRET).at(int(self.now().timestamp()))
        r = await self.client.post("/api/desk/login", headers=self.headers(session=False, csrf=False),
                                   json={"email": email, "password": password, "code": code})
        if r.status_code == 200:
            self.token, self.csrf = r.json()["token"], r.json()["csrf"]
        return r

    async def settle(self):
        for _ in range(20):
            await asyncio.sleep(0)


@pytest.fixture
async def h():
    harness = Harness()
    await harness.seed_admin()
    yield harness
    await harness.client.aclose()


ROUTES = [
    ("post", "/api/desk/logout", None), ("post", "/api/desk/logout-all", None),
    ("get", "/api/desk/me", None), ("get", "/api/desk/items", None),
    ("post", "/api/desk/check", {"topic": "x y z", "category": "Politics", "news_type": "normal", "heat": 1}),
    ("post", "/api/desk/drafts", {"topic": "x y z", "category": "Politics", "news_type": "normal", "heat": 1}),
    ("get", "/api/desk/drafts/dft_x", None), ("patch", "/api/desk/drafts/dft_x", {}),
    ("post", "/api/desk/drafts/dft_x/publish", None), ("post", "/api/desk/drafts/dft_x/discard", None),
    ("post", "/api/desk/boost", {"type": "article", "id": "a", "heat": 2}),
    ("post", "/api/desk/stories/s/end", None), ("post", "/api/desk/stories/s/extend", None),
    ("post", "/api/desk/articles/a/unpublish", None), ("post", "/api/desk/articles/a/restore/b", None),
]


async def _call(h, method, path, body, headers):
    kw = {"headers": headers}
    if body is not None:
        kw["json"] = body
    return await getattr(h.client, method)(path, **kw)


# ─────────────────────── gates ───────────────────────

@pytest.mark.parametrize("method,path,body", ROUTES + [("post", "/api/desk/login", {"email": "a", "password": "b", "code": "1"})])
async def test_every_route_is_invisible_without_proxy_secret(h, method, path, body):
    await h.login()
    for proxy in (None, "wrong"):
        r = await _call(h, method, path, body, h.headers(proxy=proxy))
        assert r.status_code == 404, (path, proxy)


@pytest.mark.parametrize("method,path,body", ROUTES)
async def test_every_session_route_needs_a_session(h, method, path, body):
    r = await _call(h, method, path, body, h.headers(session=False))
    assert r.status_code == 401, path


@pytest.mark.parametrize("method,path,body", [r for r in ROUTES if r[0] != "get"])
async def test_every_mutating_route_needs_csrf(h, method, path, body):
    await h.login()
    r = await _call(h, method, path, body, h.headers(csrf=False))
    assert r.status_code == 403, path
    good_csrf = h.csrf
    h.csrf = "forged"
    r = await _call(h, method, path, body, h.headers())
    assert r.status_code == 403, path
    h.csrf = good_csrf


async def test_empty_configured_secret_keeps_desk_closed():
    harness = Harness()
    harness.client._transport.app.router.routes.clear()  # rebuild with an unset secret
    app = FastAPI()
    app.include_router(desk_routes.build_desk_router(
        db=harness.db, auth=harness.auth, proxy_secret=lambda: "", admin_emails=lambda: {EMAIL},
        research=harness._research, fetch_meta=harness._fetch, send_email=harness._email,
        registrable_domain=research._registrable_domain,
        suggest_category=lambda t: "Politics", default_image="x", logger=__import__("logging").getLogger("t")),
        prefix="/api")
    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    r = await c.post("/api/desk/login", headers={"x-desk-proxy": ""}, json={"email": EMAIL, "password": "x", "code": "1"})
    assert r.status_code == 404
    await c.aclose()


# ─────────────────────── login ───────────────────────

async def test_login_success_sets_session_and_alerts(h):
    r = await h.login()
    assert r.status_code == 200 and r.json()["alert_failed"] is False
    assert h.emails[-1] == (EMAIL, "New Chintan Desk sign-in")
    me = await h.client.get("/api/desk/me", headers=h.headers())
    assert me.json()["email"] == EMAIL and me.json()["csrf"] == h.csrf


async def test_login_failures_are_generic(h):
    wrong_pw = await h.login(password="nope nope nope nope")
    wrong_code = await h.login(code="000000")
    unknown = await h.login(email="stranger@x.com")
    assert {r.status_code for r in (wrong_pw, wrong_code, unknown)} == {401}
    assert len({r.json()["detail"] for r in (wrong_pw, wrong_code, unknown)}) == 1


async def test_email_not_in_admin_emails_cannot_log_in_even_with_right_secrets(h):
    await h.db.desk_admins.update_one({"admin_id": "adm_1"}, {"$set": {"email": "old@chintan.news"}})
    assert (await h.login(email="old@chintan.news")).status_code == 401


async def test_lockout_after_five_failures_blocks_correct_login_and_emails(h):
    for _ in range(5):
        await h.login(password="wrong wrong wrong wrong")
    assert any("locked" in s for _, s in h.emails)
    r = await h.login()
    assert r.status_code == 429
    h.clock_offset = timedelta(minutes=16)
    assert (await h.login()).status_code == 200


async def test_alert_failure_flags_the_session(h):
    h.email_ok = False
    r = await h.login()
    assert r.json()["alert_failed"] is True
    assert (await h.client.get("/api/desk/me", headers=h.headers())).json()["alert_failed"] is True


async def test_session_expires_when_idle(h):
    await h.login()
    h.clock_offset = timedelta(minutes=31)
    assert (await h.client.get("/api/desk/me", headers=h.headers())).status_code == 401


async def test_removed_from_admin_emails_kills_live_session(h):
    await h.login()
    await h.db.desk_sessions.update_many({}, {"$set": {"email": "gone@chintan.news"}})
    assert (await h.client.get("/api/desk/me", headers=h.headers())).status_code == 401


async def test_logout_and_logout_all(h):
    await h.login()
    first = (h.token, h.csrf)
    assert (await h.client.post("/api/desk/logout", headers=h.headers())).status_code == 200
    assert (await h.client.get("/api/desk/me", headers=h.headers())).status_code == 401
    h.clock_offset = timedelta(seconds=31)
    await h.login()
    assert (await h.client.post("/api/desk/logout-all", headers=h.headers())).json()["sessions"] >= 1
    assert (await h.client.get("/api/desk/me", headers=h.headers())).status_code == 401
    assert first[0] != h.token


# ─────────────────────── drafts ───────────────────────

BODY = {"topic": "Electoral bonds verdict", "category": "Politics", "news_type": "normal", "heat": 3}


async def _draft(h, body=BODY, force=True):
    r = await h.client.post("/api/desk/drafts", headers=h.headers(), json={**body, "force": force})
    assert r.status_code == 200, r.text
    return r.json()


async def test_submit_researches_in_background_then_ready(h):
    await h.login()
    out = await _draft(h)
    assert out["draft"]["status"] == "researching"
    await h.settle()
    d = (await h.client.get(f"/api/desk/drafts/{out['draft']['draft_id']}", headers=h.headers())).json()
    assert d["status"] == "ready" and d["headline"].startswith("Supreme Court")
    assert d["attribution"] == "Chintan Desk · via The Hindu, Indian Express"
    assert d["errors"] == []


async def test_double_submit_reuses_draft_and_pays_once(h):
    await h.login()
    h.research_gate = asyncio.Event()
    a = await _draft(h)
    b = await _draft(h)
    assert b.get("reused") and a["draft"]["draft_id"] == b["draft"]["draft_id"]
    h.research_gate.set()
    await h.settle()
    assert h.research_calls == 1


async def test_dedup_match_returned_before_any_spend(h):
    await h.login()
    await h.db.articles.insert_one({"article_id": "a1", "title": "SC verdict on electoral bonds",
                                    "description": "", "category": "Politics", "source": "TOI",
                                    "published_at": datetime.now(timezone.utc).isoformat()})
    out = await _draft(h, force=False)
    assert out["draft"] is None and out["matches"][0]["id"] == "a1"
    assert h.research_calls == 0


async def test_research_failure_is_explained(h):
    await h.login()
    h.research_result = {"ok": False, "reason": "no_sources"}
    out = await _draft(h)
    await h.settle()
    d = (await h.client.get(f"/api/desk/drafts/{out['draft']['draft_id']}", headers=h.headers())).json()
    assert d["status"] == "failed" and "No source" in d["fail_message"]


async def test_stale_research_is_marked_failed(h):
    await h.login()
    h.research_gate = asyncio.Event()      # never released: simulates a dead process
    out = await _draft(h)
    h.clock_offset = timedelta(minutes=6)
    # a fresh login is needed after 6 min idle? no: 6 < 30
    await h.db.desk_drafts.update_one({"draft_id": out["draft"]["draft_id"]}, {"$set": {
        "created_at": (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()}})
    d = (await h.client.get(f"/api/desk/drafts/{out['draft']['draft_id']}", headers=h.headers())).json()
    assert d["status"] == "failed" and d["fail_reason"] == "stale"
    h.research_gate.set()


async def _ready(h, body=BODY, **research_over):
    h.research_result = {**GOOD_RESEARCH, **research_over}
    out = await _draft(h, body)
    await h.settle()
    return out["draft"]["draft_id"]


async def test_publish_normal_creates_final_article(h):
    await h.login()
    did = await _ready(h)
    r = await h.client.post(f"/api/desk/drafts/{did}/publish", headers=h.headers())
    assert r.status_code == 200
    a = await h.db.articles.find_one({"origin": "desk"})
    assert a["claude_summarized"] and a["claude_categorized"]     # nothing rewrites it (D11f)
    assert a["rank_at"] == a["published_at"]                       # Desk has no delay (D8)
    assert a["source"] == "Chintan Desk · via The Hindu, Indian Express"
    assert a["url"] == "https://www.thehindu.com/a" and a["absorb_until"]
    assert [b["hook"] for b in a["beats"]] == GOOD_RESEARCH["points"]
    assert await h.db.desk_audit.find_one({"action": "publish"})


async def test_publish_twice_is_refused(h):
    await h.login()
    did = await _ready(h)
    r1, r2 = await asyncio.gather(
        h.client.post(f"/api/desk/drafts/{did}/publish", headers=h.headers()),
        h.client.post(f"/api/desk/drafts/{did}/publish", headers=h.headers()))
    assert sorted([r1.status_code, r2.status_code]) == [200, 409]
    assert await h.db.articles.count_documents({"origin": "desk"}) == 1


async def test_single_source_needs_reason_then_is_labelled(h):
    await h.login()
    did = await _ready(h, domain_count=1, citations=[{"url": "https://pib.gov.in/x", "title": "p"}])
    r = await h.client.post(f"/api/desk/drafts/{did}/publish", headers=h.headers())
    assert r.status_code == 422 and "one source" in r.json()["detail"]
    await h.client.patch(f"/api/desk/drafts/{did}", headers=h.headers(),
                         json={"single_source_reason": "Official PIB release, primary source"})
    assert (await h.client.post(f"/api/desk/drafts/{did}/publish", headers=h.headers())).status_code == 200
    a = await h.db.articles.find_one({"origin": "desk"})
    assert a["single_source"] and a["source"] == "Chintan Desk · single source: PIB"
    audit = await h.db.desk_audit.find_one({"action": "publish"})
    assert audit["detail"]["reason"].startswith("Official PIB")


async def test_publish_developing_creates_story_with_lifecycle(h):
    await h.login()
    did = await _ready(h, {**BODY, "news_type": "developing", "topic": "Bonds case live"})
    assert (await h.client.post(f"/api/desk/drafts/{did}/publish", headers=h.headers())).status_code == 200
    s = await h.db.developing_stories.find_one({"kind": "desk"})
    assert s["is_active"] and s["quiet_window_h"] == 36 and s["keywords"] == GOOD_RESEARCH["keywords"]
    assert s["state_summary"] == GOOD_RESEARCH["summary"]
    items = (await h.client.get("/api/desk/items", headers=h.headers())).json()
    assert items["published"][0]["story"]["active"] and items["published"][0]["story"]["closes_at"]


async def test_edit_is_validated_and_image_must_be_https(h):
    await h.login()
    did = await _ready(h)
    d = (await h.client.patch(f"/api/desk/drafts/{did}", headers=h.headers(),
                              json={"image_url": "javascript:alert(1)"})).json()
    assert any("https" in e for e in d["errors"])
    assert (await h.client.post(f"/api/desk/drafts/{did}/publish", headers=h.headers())).status_code == 422


# ─────────────────────── manage ───────────────────────

async def test_end_and_extend_story(h):
    await h.login()
    did = await _ready(h, {**BODY, "news_type": "developing", "topic": "Bonds case live"})
    ref = (await h.client.post(f"/api/desk/drafts/{did}/publish", headers=h.headers())).json()["ref"]
    assert (await h.client.post(f"/api/desk/stories/{ref['id']}/end", headers=h.headers())).status_code == 200
    assert not (await h.db.developing_stories.find_one({"story_id": ref["id"]}))["is_active"]
    r = await h.client.post(f"/api/desk/stories/{ref['id']}/extend", headers=h.headers())
    s = await h.db.developing_stories.find_one({"story_id": ref["id"]})
    assert r.status_code == 200 and s["is_active"] and s["extra_h"] >= 24


async def test_unpublish_hides_and_releases_absorbed(h):
    await h.login()
    did = await _ready(h)
    aid = (await h.client.post(f"/api/desk/drafts/{did}/publish", headers=h.headers())).json()["ref"]["id"]
    await h.db.articles.insert_one({"article_id": "api1", "title": "t", "merged_into": aid})
    await h.client.post(f"/api/desk/articles/{aid}/unpublish", headers=h.headers())
    assert (await h.db.articles.find_one({"article_id": aid}))["desk_hidden"]
    assert "merged_into" not in await h.db.articles.find_one({"article_id": "api1"})


async def test_restore_absorbed_article(h):
    await h.login()
    await h.db.articles.insert_one({"article_id": "api1", "title": "t", "merged_into": "desk_x"})
    r = await h.client.post("/api/desk/articles/desk_x/restore/api1", headers=h.headers())
    doc = await h.db.articles.find_one({"article_id": "api1"})
    assert r.status_code == 200 and "merged_into" not in doc and doc["absorb_exempt"]


async def test_boost_existing_article(h):
    await h.login()
    await h.db.articles.insert_one({"article_id": "api1", "title": "t", "published_at": "2026-09-27T00:00:00+00:00"})
    r = await h.client.post("/api/desk/boost", headers=h.headers(), json={"type": "article", "id": "api1", "heat": 3})
    a = await h.db.articles.find_one({"article_id": "api1"})
    assert r.status_code == 200 and a["boosted"] and a["heat"] == 3
    assert desk.heat_points(a, datetime.now(timezone.utc)) > 20
    missing = await h.client.post("/api/desk/boost", headers=h.headers(), json={"type": "article", "id": "nope", "heat": 3})
    assert missing.status_code == 404


# ─────────────────────── link or headline in ───────────────────────

LINK = "https://www.ndtv.com/india-news/sc-strikes-down-electoral-bonds-4321.html"
PAGE = {"title": "SC strikes down electoral bonds", "image": "https://c.ndtvimg.com/lead.jpg",
        "description": "The Supreme Court on Thursday struck down the scheme.", "site_name": "NDTV"}


async def test_link_already_in_chintan_is_an_exact_match(h):
    await h.login()
    await h.db.articles.insert_one({"article_id": "api9", "url": LINK, "title": "old", "source": "NDTV",
                                    "published_at": datetime.now(timezone.utc).isoformat()})
    out = await _draft(h, {**BODY, "topic": LINK}, force=False)
    assert out["draft"] is None and out["matches"][0]["detail"].startswith("Same link")
    assert h.research_calls == 0


async def test_link_anchors_research_and_supplies_image_and_lead_source(h):
    await h.login()
    h.pages[LINK] = PAGE
    out = await _draft(h, {**BODY, "topic": LINK})
    await h.settle()
    d = (await h.client.get(f"/api/desk/drafts/{out['draft']['draft_id']}", headers=h.headers())).json()
    topic, source = h.research_args[-1]
    assert topic == PAGE["title"] and source["url"] == LINK
    assert d["image_url"] == PAGE["image"] and d["source_url"] == LINK
    assert d["citations"][0]["url"] == LINK and d["domain_count"] == 3
    assert d["attribution"] == "Chintan Desk · via NDTV, The Hindu"


async def test_link_with_no_other_coverage_becomes_single_source_draft(h):
    await h.login()
    h.pages[LINK] = PAGE
    h.research_result = {"ok": False, "reason": "no_sources"}
    out = await _draft(h, {**BODY, "topic": LINK})
    await h.settle()
    d = (await h.client.get(f"/api/desk/drafts/{out['draft']['draft_id']}", headers=h.headers())).json()
    assert d["status"] == "ready" and d["domain_count"] == 1 and d["note"]
    assert any("one source" in e for e in d["errors"])          # needs a reason (D9)


async def test_unreadable_link_with_no_research_explains_itself(h):
    await h.login()
    h.research_result = {"ok": False, "reason": "no_sources"}
    out = await _draft(h, {**BODY, "topic": LINK})
    await h.settle()
    d = (await h.client.get(f"/api/desk/drafts/{out['draft']['draft_id']}", headers=h.headers())).json()
    assert d["status"] == "failed" and "Paste the headline" in d["fail_message"]


async def test_http_link_is_rejected_up_front(h):
    await h.login()
    r = await h.client.post("/api/desk/drafts", headers=h.headers(),
                            json={**BODY, "topic": "http://example.com/story", "force": True})
    assert r.status_code == 422 and "https" in r.json()["detail"]


async def test_headline_draft_gets_image_from_first_source_with_one(h):
    await h.login()
    h.pages["https://indianexpress.com/b"] = {"title": "x", "image": "https://ie.com/i.jpg", "description": ""}
    out = await _draft(h)
    await h.settle()
    d = (await h.client.get(f"/api/desk/drafts/{out['draft']['draft_id']}", headers=h.headers())).json()
    assert d["image_url"] == "https://ie.com/i.jpg" and d["source_url"] is None

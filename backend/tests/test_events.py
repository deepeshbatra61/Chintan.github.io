"""events.py: the pure News v2 engine (same story? which lead? what status?).

    vectors ─ DocFreq incremental == rebuilt; cosine bounds
    assign  ─ same event joins; different event founds; 36h-from-FIRST window;
              size guard; drift (founding) guard; Desk-blocked article
    voices  ─ wire copies count once; syndication detection
    lead    ─ Desk › earliest original › publisher share; 4h pin
    status  ─ every transition in the module docstring, incl. invalid ones
"""

from datetime import datetime, timedelta, timezone

import events as E

T0 = datetime(2026, 10, 3, 6, 0, tzinfo=timezone.utc)


def h(x):
    return T0 + timedelta(hours=x)


CORPUS = [
    ("Dharmendra Pradhan resigns as education minister over exam paper leak", "Pradhan quits after NEET leak row"),
    ("Pradhan resignation: Congress demands judicial probe into exam leak", "Opposition wants probe after Pradhan quits"),
    ("Education minister Pradhan steps down amid exam leak protests", "Students protest exam leak; Pradhan resigns"),
    ("RBI holds repo rate at 5.5% citing inflation risks", "Monetary policy committee keeps rates unchanged"),
    ("India beat Malaysia to win Asian Games hockey gold", "Harmanpreet corner seals final"),
    ("Kotak Mahindra Bank names Anup Saha as MD and CEO", "RBI approves appointment"),
    ("Farmers protest in Punjab over paddy procurement delays", "Punjab farmers block highways"),
    ("Teachers protest in Kerala over pay commission", "Kerala teachers strike over salaries"),
]


def df_for(texts):
    df = E.DocFreq()
    for t, d in texts:
        df.add(E.term_weights(t, d))
    return df


DF = df_for(CORPUS)


def vec(title, desc=""):
    return E.vectorize(E.term_weights(title, desc), DF)


def ev(event_id, title, desc="", first=None, size=1, **kw):
    v = vec(title, desc)
    return {"event_id": event_id, "centroid": v, "founding": [v], "size": size,
            "first_member_at": first or T0, **kw}


# ── vectors ───────────────────────────────────────────────────────────────────

def test_docfreq_incremental_equals_rebuilt():
    inc = E.DocFreq()
    for t, d in CORPUS + [("Extra story about trains", "")]:
        inc.add(E.term_weights(t, d))
    inc.remove(E.term_weights("Extra story about trains", ""))
    assert inc.n == DF.n and inc.df == DF.df


def test_cosine_bounds():
    a = vec(*CORPUS[0])
    assert abs(E.cosine(a, a) - 1.0) < 1e-9
    assert E.cosine(a, {}) == 0.0 and E.vectorize(E.term_weights(""), DF) == {}


# ── assignment ────────────────────────────────────────────────────────────────

def test_same_event_joins_and_different_event_founds():
    pradhan = ev("e1", *CORPUS[0])
    rbi = ev("e2", *CORPUS[3])
    assert E.choose_event(vec(*CORPUS[2]), "a3", h(2), [pradhan, rbi]) == "e1"
    assert E.choose_event(vec(*CORPUS[4]), "a5", h(2), [pradhan, rbi]) is None


def test_two_protests_in_different_states_stay_apart():
    punjab = ev("e7", *CORPUS[6])
    assert E.choose_event(vec(*CORPUS[7]), "a8", h(1), [punjab]) is None


def test_window_is_measured_from_the_first_article():
    pradhan = ev("e1", *CORPUS[0], first=h(0), last_member_at=h(35))
    assert E.choose_event(vec(*CORPUS[2]), "x", h(37), [pradhan]) is None
    assert E.choose_event(vec(*CORPUS[2]), "x", h(30), [pradhan]) == "e1"


def test_size_guard_blocked_and_closed():
    full = ev("e1", *CORPUS[0], size=E.MAX_MEMBERS)
    assert E.choose_event(vec(*CORPUS[2]), "x", h(1), [full]) is None
    blocked = ev("e1", *CORPUS[0], blocked={"x"})
    assert E.choose_event(vec(*CORPUS[2]), "x", h(1), [blocked]) is None
    closed = ev("e1", *CORPUS[0], closed=True)
    assert E.choose_event(vec(*CORPUS[2]), "x", h(1), [closed]) is None


def test_drift_guard_needs_a_founding_match():
    drifted = ev("e1", *CORPUS[0])
    drifted["founding"] = [vec(*CORPUS[3])]        # centroid says Pradhan, founders were RBI
    assert E.choose_event(vec(*CORPUS[2]), "x", h(1), [drifted]) is None


def test_merge_centroid_trims_and_normalises():
    c = E.merge_centroid(vec(*CORPUS[0]), 1, vec(*CORPUS[1]))
    assert len(c) <= E.CENTROID_TERMS
    assert abs(sum(x * x for x in c.values()) - 1.0) < 1e-9


# ── voices ────────────────────────────────────────────────────────────────────

def test_syndication():
    a = {"title": "RBI awaits Tata Sons’ formal response on Upper Layer NBFC compliance", "content": ""}
    b = {"title": "RBI awaits Tata Sons formal response on upper layer NBFC compliance", "content": ""}
    c = {"title": "Tata Trusts pitch Tata Sons restructuring as alternative to listing", "content": ""}
    assert E.is_syndicated(a, b) and not E.is_syndicated(a, c)
    body = "x " * 100
    assert E.is_syndicated({"title": "One", "content": body}, {"title": "Two", "content": body})


def m(aid, pub, at, **kw):
    return {"article_id": aid, "publisher": pub, "published_at": at, **kw}


def test_wire_copies_count_once():
    members = [m("a", "aninews.in", h(0)), m("b", "tribuneindia.com", h(1), syndicated_of="a",
                                                syndicated_publisher="aninews.in"),
               m("c", "thehindu.com", h(2))]
    assert E.independent_outlets(members) == ["aninews.in", "thehindu.com"]


# ── lead ──────────────────────────────────────────────────────────────────────

def test_lead_rule():
    members = [m("wire", "aninews.in", h(0)), m("copy", "devdiscourse.com", h(0.5), syndicated_of="wire"),
               m("toi", "timesofindia.indiatimes.com", h(1)), m("hindu", "thehindu.com", h(2))]
    assert E.pick_lead(members, h(3)) == "wire"
    # publisher over its share is skipped when another original exists
    assert E.pick_lead(members, h(3), overrepresented=frozenset({"aninews.in"})) == "toi"
    # pinned lead holds for 4h, then the rule applies again
    assert E.pick_lead(members, h(3), current="hindu", pinned_until=h(4)) == "hindu"
    assert E.pick_lead(members, h(5), current="hindu", pinned_until=h(4)) == "wire"
    # a pin on an article that left the event is ignored
    assert E.pick_lead(members, h(3), current="gone", pinned_until=h(9)) == "wire"
    # Desk always leads
    assert E.pick_lead(members + [m("desk1", "chintan", h(2.5), origin="desk")], h(3), current="hindu",
                       pinned_until=h(9)) == "desk1"
    assert E.pick_lead([], h(1)) is None


# ── status ────────────────────────────────────────────────────────────────────

def test_status_forming_to_developing_needs_spread():
    two_fast = [m("a", "p1", h(0)), m("b", "p2", h(0.5))]
    assert E.next_status("forming", two_fast, h(1)) == "forming"
    two_spread = [m("a", "p1", h(0)), m("b", "p2", h(2.5))]
    assert E.next_status("forming", two_spread, h(3)) == "developing"


def test_status_wire_copies_do_not_make_it_developing():
    copies = [m("a", "aninews.in", h(0)), m("b", "x", h(3), syndicated_publisher="aninews.in")]
    assert E.next_status("forming", copies, h(3.5)) == "forming"


def test_status_early_report_then_confirmed():
    one = [m("a", "p1", h(0))]
    assert E.next_status("forming", one, h(1), scout_flag=True) == "early_report"
    assert E.next_status("forming", one, h(1)) == "forming"
    two = one + [m("b", "p2", h(2.5))]
    assert E.next_status("early_report", two, h(3), scout_flag=True) == "developing"


def test_status_settles_after_quiet_and_desk_waits_longer():
    members = [m("a", "p1", h(0)), m("b", "p2", h(3))]
    assert E.next_status("developing", members, h(10)) == "developing"
    assert E.next_status("developing", members, h(11.5)) == "settled"
    assert E.next_status("developing", members, h(20), desk_event=True) == "developing"
    assert E.next_status("settled", members, h(12)) == "settled"


def test_status_desk_promote_and_container():
    one = [m("a", "p1", h(0))]
    assert E.next_status("forming", one, h(1), desk_promoted=True) == "developing"
    assert E.next_status("forming", one, h(30), in_container=True) == "developing"


def test_status_closed_is_terminal_and_hidden_frozen():
    members = [m("a", "p1", h(0))]
    assert E.next_status("developing", members, h(37)) == "closed"
    assert E.next_status("closed", members + [m("b", "p2", h(38))], h(38)) == "closed"
    assert E.next_status("developing", members, h(1), hidden=True) == "developing"
    assert E.next_status("forming", [], h(1)) == "closed"


def test_cap_ranking_and_alarm():
    members = [m("a", "p1", h(0)), m("b", "p2", h(4)), m("c", "p3", h(5))]
    assert E.updates_last_hours(members, h(6)) == 3 and E.updates_last_hours(members, h(9.5)) == 2
    assert E.alarm(0.31, 3) and E.alarm(0.1, 26) and not E.alarm(0.3, 25)

"""desk.py: the Desk's rules, tested without a database.

Grouped by the decision each rule implements (/plan-eng-review 2026-09-28).
"""

from datetime import datetime, timedelta, timezone

import desk
import research

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


def ago(hours):
    return (NOW - timedelta(hours=hours)).isoformat()


def later(hours):
    return (NOW + timedelta(hours=hours)).isoformat()


# ─────────────────────── rank_at (D8) ───────────────────────

def test_rank_at_shifts_by_source_delay():
    assert desk.rank_at("2026-09-27T12:00:00+00:00", 24) == "2026-09-28T12:00:00+00:00"
    assert desk.rank_at("2026-09-28T12:00:00Z", 0) == "2026-09-28T12:00:00+00:00"


def test_rank_at_preserves_order_within_a_source():
    times = ["2026-09-27T01:00:00Z", "2026-09-27T05:30:00Z", "2026-09-27T05:31:00Z"]
    shifted = [desk.rank_at(t, 24) for t in times]
    assert shifted == sorted(shifted)


def test_rank_at_bad_input():
    assert desk.rank_at("not a date", 24) is None
    assert desk.rank_at(None, 24) is None


# ─────────────────────── matching (D-2hit, D10) ───────────────────────

def test_two_hits_required():
    kws = ["electoral bonds", "sbi", "supreme court"]
    assert not desk.matches_story(kws, "SBI posts quarterly profit")
    assert desk.matches_story(kws, "Supreme Court tells SBI to disclose")


def test_word_boundaries_not_substrings():
    assert not desk.matches_story(["loc", "pok"], "Local spokesperson location")


def test_single_keyword_story_never_matches():
    assert not desk.matches_story(["asiad"], "Asiad Asiad Asiad")


# ─────────────────────── dedup ───────────────────────

ARTS = [
    {"article_id": "a1", "title": "SC strikes down electoral bonds scheme", "description": "", "category": "Politics", "source": "TOI"},
    {"article_id": "a2", "title": "India beat Pakistan in Asia Cup", "description": "", "category": "Sports", "source": "TOI"},
]
STORIES = [{"story_id": "asian-games-2026", "title": "Asian Games 2026", "keywords": ["asiad", "aichi"], "kind": "scheduled", "article_ids": ["x"] * 115}]


def test_dedup_finds_article_by_terms():
    m = desk.dedup_candidates("Electoral bonds struck down", ARTS, STORIES)
    assert m and m[0]["id"] == "a1"


def test_dedup_finds_story_by_keyword_and_prefers_story_on_tie():
    m = desk.dedup_candidates("Asiad", ARTS, STORIES)
    assert m[0]["type"] == "story" and "115 updates" in m[0]["detail"]


def test_one_shared_generic_word_is_not_a_duplicate():
    assert desk.dedup_candidates("India monsoon floods in Assam", ARTS, STORIES) == []


def test_empty_topic_has_no_candidates():
    assert desk.dedup_candidates("the of and", ARTS, STORIES) == []


# ─────────────────────── placement (D11b) ───────────────────────

def art(heat, published_hours_ago, origin="desk"):
    return {"origin": origin, "heat": heat, "published_at": ago(published_hours_ago)}


def test_api_articles_get_no_heat():
    assert desk.heat_points(art(3, 0, origin=None), NOW) == 0
    assert desk.heat_slots(art(3, 0, origin=None), NOW) == 0


def test_normal_gets_no_boost():
    assert desk.heat_points(art(1, 0), NOW) == 0


def test_boosts_fade_linearly_to_zero():
    assert desk.heat_points(art(3, 0), NOW) == 25
    assert desk.heat_points(art(3, 12), NOW) == 12.5
    assert desk.heat_points(art(3, 24), NOW) == 0
    assert desk.heat_slots(art(2, 6), NOW) == 1.5
    assert desk.heat_slots(art(2, 12), NOW) == 0


def test_breaking_pins_for_six_hours_then_acts_as_big():
    assert desk.article_is_pinned(art(4, 5.9), NOW)
    assert not desk.article_is_pinned(art(4, 6), NOW)
    assert desk.heat_points(art(4, 6), NOW) == desk.heat_points(art(3, 6), NOW)


def test_future_publish_time_does_not_overboost():
    assert desk.heat_points({"origin": "desk", "heat": 3, "published_at": later(2)}, NOW) == 25


# ─────────────────────── lifecycle ───────────────────────

def story(heat=3, created_h_ago=30, last_h_ago=1, long_running=False, **extra):
    created = NOW - timedelta(hours=created_h_ago)
    s = desk.lifecycle_fields(heat, created, long_running)
    s["last_updated"] = ago(last_h_ago)
    s.update(extra)
    return s


def test_minimum_run_holds_even_if_quiet():
    assert desk.lifecycle_decision(story(heat=3, created_h_ago=10, last_h_ago=10), NOW)[0] == "stay"


def test_quiet_window_by_heat():
    assert desk.lifecycle_decision(story(heat=3, last_h_ago=35), NOW)[0] == "stay"
    assert desk.lifecycle_decision(story(heat=3, last_h_ago=36), NOW)[:2] == ("end", "quiet")
    assert desk.lifecycle_decision(story(heat=2, created_h_ago=60, last_h_ago=47), NOW)[0] == "stay"
    assert desk.lifecycle_decision(story(heat=1, created_h_ago=80, last_h_ago=71), NOW)[0] == "stay"
    assert desk.lifecycle_decision(story(heat=1, created_h_ago=80, last_h_ago=72), NOW)[0] == "end"


def test_hard_cap_ends_even_if_busy():
    s = story(heat=3, created_h_ago=24 * 15, last_h_ago=0)
    assert desk.lifecycle_decision(s, NOW)[:2] == ("end", "cap")


def test_long_running_has_no_cap():
    s = story(heat=3, created_h_ago=24 * 30, last_h_ago=0, long_running=True)
    assert desk.lifecycle_decision(s, NOW)[0] == "stay"


def test_closes_at_reported_for_dashboard():
    _, _, closes = desk.lifecycle_decision(story(heat=3, last_h_ago=6), NOW)
    assert closes == later(30)


def test_extend_adds_a_day_without_touching_last_updated():
    s = story(heat=3, last_h_ago=30)
    f = desk.extended_fields(s, NOW)
    assert "last_updated" not in f
    _, _, closes = desk.lifecycle_decision({**s, **f}, NOW)
    assert closes == later(30)       # was 6h left, now 30h


def test_extend_revives_an_overdue_story_for_a_day():
    s = story(heat=3, last_h_ago=50)
    f = desk.extended_fields(s, NOW)
    decision, _, closes = desk.lifecycle_decision({**s, **f}, NOW)
    assert decision == "stay" and desk.parse_dt(closes) >= NOW + timedelta(hours=24)


def test_extend_moves_hard_cap_if_needed():
    s = story(heat=3, created_h_ago=24 * 14 - 2, last_h_ago=0)
    f = desk.extended_fields(s, NOW)
    # would have closed at the cap (2h from now); extend = 24h past that
    assert desk.parse_dt(f["hard_end"]) == NOW + timedelta(hours=26)


# ─────────────────────── validation (D9) ───────────────────────

def draft(**over):
    d = {"headline": "Supreme Court strikes down bonds", "summary": "A long enough summary of events.",
         "points": ["one"], "category": "Politics", "heat": 3, "news_type": "normal",
         "image_url": "", "citations": [{"url": "https://a.com"}, {"url": "https://b.com"}],
         "domain_count": 2, "keywords": []}
    d.update(over)
    return d


def test_valid_draft_passes():
    assert desk.validate_draft(draft()) == []


def test_single_source_needs_a_reason():
    assert any("one source" in e for e in desk.validate_draft(draft(domain_count=1)))
    assert desk.validate_draft(draft(domain_count=1, single_source_reason="PIB release, official")) == []


def test_zero_sources_never_publishes_even_with_reason():
    errs = desk.validate_draft(draft(citations=[], domain_count=0, single_source_reason="trust me please"))
    assert any("at least one real source" in e for e in errs)


def test_developing_needs_keywords():
    assert desk.validate_draft(draft(news_type="developing", keywords=["a", "b"]))
    assert desk.validate_draft(draft(news_type="developing", keywords=["a", "b", "c"])) == []


def test_image_url_rules():
    assert desk.validate_draft(draft(image_url="https://cdn.x.com/a.jpg")) == []
    for bad in ["http://x.com/a.jpg", "javascript:alert(1)", "https://x.com/a b.jpg", "https://localhost/a", "https://" + "a" * 700 + ".com"]:
        assert desk.validate_draft(draft(image_url=bad)), bad


def test_submit_validation():
    assert desk.validate_submit("Electoral bonds verdict", "Politics", "normal", 3) == []
    assert len(desk.validate_submit("x", "Nope", "other", 9)) == 4


# ─────────────────────── attribution (D11g) ───────────────────────

def test_attribution_names_outlets_in_order():
    cites = [{"url": "https://www.thehindu.com/a"}, {"url": "https://thehindu.com/b"},
             {"url": "https://www.ndtv.com/c"}, {"url": "https://reuters.com/d"}]
    assert desk.attribution(cites, research._registrable_domain) == "Chintan Desk · via The Hindu, NDTV"


def test_attribution_unknown_outlet_uses_domain():
    assert desk.attribution([{"url": "https://news.example.org/x"}], research._registrable_domain) == "Chintan Desk · via example.org"


def test_attribution_without_citations():
    assert desk.attribution([], research._registrable_domain) == "Chintan Desk"


def test_boosted_api_article_fades_from_boost_time_not_publish_time():
    a = {"origin": None, "boosted": True, "heat": 3,
         "published_at": ago(30), "heat_from": ago(0)}
    assert desk.heat_points(a, NOW) == 25
    assert desk.heat_slots({**a, "heat": 2}, NOW) == 3


def test_heat_without_boost_flag_is_ignored_on_api_articles():
    assert desk.heat_points({"heat": 3, "published_at": ago(0)}, NOW) == 0


def test_boosted_breaking_pins_from_boost_time():
    a = {"boosted": True, "heat": 4, "published_at": ago(30), "heat_from": ago(1)}
    assert desk.article_is_pinned(a, NOW)


# ─────────────────────── links as topics ───────────────────────

def test_topic_text_reads_article_slug_from_link():
    assert desk.topic_text("https://www.thehindu.com/news/national/sc-strikes-down-electoral-bonds-scheme/article67845.ece") \
        == "sc strikes down electoral bonds scheme"
    assert desk.topic_text("https://www.ndtv.com/india-news/asian-games-india-medal-tally-12345.html") \
        == "asian games india medal tally"
    assert desk.topic_text("Plain headline stays") == "Plain headline stays"


def test_link_topic_dedups_by_its_slug():
    m = desk.dedup_candidates("https://x.com/news/electoral-bonds-struck-down-123.html", ARTS, STORIES)
    assert m and m[0]["id"] == "a1"


# ── story matching on phrase WORDS (2026-10-01: FlyDubai duplicates outranked the Desk card) ──

FLY_KW = ["flydubai fz1073", "benjamin netanyahu", "tabuk saudi arabia", "dubai tel aviv flight",
          "cockpit stabbing september 2026"]


def test_phrase_words_match_real_coverage():
    a = ("Flydubai flight incident: What we know about the pilot under investigation. A flydubai "
         "flight from Dubai to Tel Aviv had to make an emergency landing in Saudi Arabia")
    assert desk.story_keyword_hits(FLY_KW, a) == 2 and desk.matches_story(FLY_KW, a)


def test_phrase_words_do_not_glue_unrelated_news():
    for t in ("Emirates launches a new Dubai to London service",
              "Netanyahu addresses the Knesset on the budget",
              "Saudi Arabia hosts a tech summit in Riyadh"):
        assert not desk.matches_story(FLY_KW, t), t


def test_codes_years_and_months_are_ignored():
    assert desk._phrase_tokens("cockpit stabbing september 2026") == ["cockpit", "stabbing"]
    assert desk._phrase_tokens("flydubai fz1073") == ["flydubai"]
    assert desk._phrase_tokens("2026") == []
    assert desk.story_keyword_hits(["2026", "september"], "anything 2026 september") == 0

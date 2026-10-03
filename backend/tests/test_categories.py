"""Category classifier tests, built from real headlines that were mis-tagged in
production on 2026-09-27. Most had zero keyword hits, so they fell through to
the Politics default: a squash semi-final and a marathon silver were showing
up under Politics, and Sports readers never saw them.
"""

import categories


def cat(title, body=""):
    return categories.detect_category(title, body)[0]


# ── Asian Games coverage that landed in Politics ──────────────────────────

def test_multi_sport_event_coverage_is_sports():
    for title in [
        "Asian Games 2026: Anahat and Abhay triumph to reach the squash finals after intense matches",
        "Asiad 2026: Sawan Barwal wins silver in men's marathon with national record",
        "Potential to podium: For Haryana duo, an Asiad shooting gold forged in pain",
        "Asiad 2026: Tough road for Lakshya, Sindhu; Satwik-Chirag eye another gold",
        "Asian Games 2026: India win team bronze medals in men's and women's skeet",
        "Jay Meena: Ball Boy To Asian Games Medallist",
        "What happened to Hardik Pandya? Latest on India all-rounder's return and why he's ruled out",
    ]:
        assert cat(title) == "Sports", title


def test_a_minister_praising_an_athlete_is_still_sports():
    # 'PM Modi' is a Politics keyword; the medal is what the story is about.
    assert cat("'India is Proud of Her...' PM Modi Hails Chanu's Asian Games Silver") == "Sports"


def test_sports_subcategory_for_multi_sport_events():
    _, sub = categories.detect_category("Asiad 2026: Joshna Chinappa, Velavan settle for squash mixed doubles bronze", "")
    assert sub == "Olympics"


# ── guard rails: new words must not drag unrelated stories into Sports ─────

def test_a_crime_shooting_is_not_sports():
    assert cat("Two dead in shooting outside Delhi mall, police say") != "Sports"


def test_gold_and_silver_prices_stay_business():
    assert cat("Gold price today: gold and silver rates fall as dollar strengthens") == "Business"


def test_politics_is_unchanged():
    assert cat("'EC lost its credibility': Pinarayi Vijayan says CEC turning 'personal views into decisions'") == "Politics"
    assert cat("BJP defends MMDR act amid opposition protests") == "Politics"


# ── business stories that had no signal ────────────────────────────────────

def test_business_gaps():
    for title in [
        "SAIL signs MoU with BCCL for joint development of coal blocks",
        "Mumbai property prices: Premium homes get 6.2% costlier in a year, eighth-highest globally",
        "India orders captive coal plants to maximise power output on surging demand",
    ]:
        assert cat(title) == "Business", title


def test_foreign_coal_policy_stays_world():
    # Only coal-as-industry phrases count for Business; China's overseas coal
    # funding is a foreign-policy story.
    assert cat(
        "China has kept its promise to stop funding overseas coal, but loopholes are helping",
        "Xi Jinping told the United Nations China would stop building coal plants abroad.",
    ) == "World"


def test_pre_113_account_state_pick_keeps_interests():
    """A pre-1.13 account has only legacy interests. The server derives
    interests_v2 for the app; the app's state pick sends that list plus the
    state, and the legacy list saved from it must be the reader's old one."""
    legacy = ["Sports", "Technology", "Business"]
    v2 = categories.interests_to_v2(legacy)
    saved = categories.interests_to_legacy(v2 + ["Kerala"])
    assert set(saved) == set(legacy)

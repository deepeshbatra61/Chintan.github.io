"""Taxonomy v2 (categories.py): Health top-level, richer subs, GNews prior,
1.12 legacy mapping, lossless interest round-trips, the States lens."""

import pytest

import categories as C


@pytest.mark.parametrize("title,body,gcat,cat,sub", [
    ("India beat Malaysia to win Asian Games hockey gold", "Harmanpreet scores late", "sports", "Sports", "Hockey"),
    ("Pranavi Urs wins historic Asian Games golf gold", "", "sports", "Sports", "Multi-sport events"),
    ("Gukesh draws with Carlsen in Norway rapid chess", "", None, "Sports", "Chess"),
    ("Dengue cases rise in Delhi hospitals", "AIIMS sees surge in patients", None, "Health", "Disease"),
    ("New study links sleep to mental health in teens", "", "health", "Health", "Mental Health"),
    ("Tata Motors launches new electric SUV", "car sales", "business", "Business", "Auto"),
    ("Ransomware attack hits AIIMS servers", "data breach feared", "technology", "Technology", "Cybersecurity"),
    ("Parliament passes data protection bill", "Lok Sabha", None, "Politics", "Parliament"),
])
def test_classify(title, body, gcat, cat, sub):
    assert C.classify(title, body, gcat) == (cat, sub)


def test_gnews_prior_breaks_ties_but_not_strong_signal():
    assert C.classify("Ministry announces new scheme", "", "business")[0] == "Business"
    assert C.classify("Kohli hits century as India win ODI series", "", "business")[0] == "Sports"
    assert C.classify("", "", None)[0] == "Politics"


def test_legacy_category_for_112_clients():
    assert C.legacy_category("Health", "Disease") == ("Science", "Health")
    assert C.legacy_category("Sports", "Hockey") == ("Sports", "Olympics")
    assert C.legacy_category("Sports", "Chess") == ("Sports", None)
    assert C.legacy_category("Business", "Banking & Finance") == ("Business", "Banking")
    assert C.legacy_category("Politics", "Parliament") == ("Politics", "Parliament")
    for cat in C.CATEGORIES_V2:
        assert C.legacy_category(cat)[0] in C.LEGACY_CATEGORIES


def test_every_v2_sub_has_a_home():
    for cat, subs in C.SUBCATEGORIES_V2.items():
        assert cat in C.CATEGORIES_V2 and len(subs) == len(set(subs))


def test_interest_mapping_both_ways():
    assert C.interests_to_v2(["Olympics", "Cricket", "Banking"]) == ["Multi-sport events", "Cricket", "Banking & Finance"]
    assert C.interests_to_legacy(["Hockey", "Mental Health", "Maharashtra", "Cricket"]) == ["Olympics", "Health", "Cricket"]


def test_112_save_is_lossless_for_v2_only_picks():
    v2 = ["Cricket", "Hockey", "Maharashtra", "Mental Health"]
    shown = C.interests_to_legacy(v2)                    # what 1.12 displays: Cricket, Olympics, Health
    assert C.merge_legacy_save(shown, v2) == v2          # unchanged save = no loss
    # 1.12 user deselects Health and adds Football
    after = C.merge_legacy_save(["Cricket", "Olympics", "Football"], v2)
    assert after == ["Cricket", "Hockey", "Maharashtra", "Football"]


@pytest.mark.parametrize("title,body,pub_state,state", [
    ("Mumbai rains disrupt local trains", "", None, "Maharashtra"),
    ("Bengaluru traffic: new metro line opens", "Karnataka government", None, "Karnataka"),
    ("PM addresses nation from Delhi", "", None, "Delhi"),
    ("Parliament passes bill", "The session in Delhi ended", None, None),
    ("Farmers block highway over procurement", "", "Punjab", "Punjab"),
    ("Kerala floods: rescue on in Kochi", "Tamil Nadu sends help", "Tamil Nadu", "Kerala"),
])
def test_detect_state(title, body, pub_state, state):
    assert C.detect_state(title, body, pub_state) == state


def test_states_and_regions_agree():
    flat = [s for ss in C.STATE_REGIONS.values() for s in ss]
    assert sorted(flat) == sorted(C.STATES)

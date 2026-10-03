"""textutil: the one home for matching helpers. These tests pin the stopword
lists, because a silently dropped word is how the 2026-10-03 flood happened."""

import categories
import desk
import textutil as T


def test_kw_pattern_word_boundary_and_phrase():
    assert T.kw_pattern("ai").search("AI rules") and not T.kw_pattern("ai").search("said again")
    assert T.kw_pattern("lok sabha").search("in the Lok Sabha today")


def test_modules_share_one_matcher_and_lists():
    assert categories._kw_pattern is T.kw_pattern and desk._kw_pattern is T.kw_pattern
    assert desk._STOP is T.STOP_TOPIC and desk._PHRASE_STOP is T.STOP_PHRASE


def test_stopword_lists_pinned():
    for w in ("india", "indian", "minister", "take", "government"):
        assert w in T.STOP_HEADLINE
    for w in ("live", "vs", "update", "latest"):
        assert w in T.STOP_TOPIC
    for w in ("live", "wins", "final", "protest", "versus"):
        assert w in T.SCOUT_GENERIC
    assert len(T.STOP_HEADLINE) >= 150 and len(T.STOP_TOPIC) >= 60 and len(T.STOP_PHRASE) == 23


def test_headline_terms():
    assert T.headline_terms("India crushes Pakistan in Asia Cup final") == ["crushes", "pakistan", "asia", "final"]
    assert T.headline_terms("India crushes Pakistan in Asia Cup final", T.SCOUT_GENERIC) == ["pakistan", "asia"]


def test_stem():
    assert T.stem("resigns") == T.stem("resigned") == T.stem("resigning") == "resign"
    assert T.stem("protests") == "protest" and T.stem("cities") == "city"
    assert T.stem("bus") == "bus"          # too short to stem


def test_tokens_mark_entities_and_drop_noise():
    toks = T.tokens("Pradhan resigns as Congress demands probe in 2026")
    words = [w for w, _ in toks]
    assert "2026" not in words and "as" not in words
    assert ("congress", True) in toks
    assert ("pradhan", False) in toks       # first word: capitalised by grammar, not a name signal
    assert ("demand", False) in toks

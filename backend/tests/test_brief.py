"""Tests for brief assembly.

The two invariants these exist to defend, both of which have failed in
production before:

  I1. stories[i]["take"] describes stories[i]["article_id"].
  I2. summary.split(/\\.\\s+/) round-trips back to exactly the takes, because
      app builds already in the field still derive card text that way.
"""

import re
from datetime import datetime, timedelta, timezone

import pytest

import brief

NOW = datetime(2026, 8, 7, 12, 0, 0, tzinfo=timezone.utc)


def article(article_id, category, **kw):
    """Minimal article doc; overrides win."""
    doc = {
        "article_id": article_id,
        "title": f"Title {article_id}",
        "category": category,
        "source": "Reuters",
        "what": "A reasonably detailed account of what happened, long enough to count.",
        "published_at": (NOW - timedelta(hours=12)).isoformat(),
        "view_count": 0,
        "likes": 0,
        "dislikes": 0,
    }
    doc.update(kw)
    return doc


def client_split(summary):
    """Exactly what BriefPage.js:38 does, so I2 is tested against the real rule."""
    parts = [p.strip() for p in re.split(r"\.\s+", summary)]
    parts = [p for p in parts if p][:3]
    return [p.rstrip(".") + "." for p in parts]


# ───────────────────────── I1: take matches its link ────────────────────────

def test_take_and_link_come_from_the_same_article():
    pairs = [("Politics", article("a1", "Politics")), ("Sports", article("b2", "Sports"))]
    out = brief.assemble(pairs, "1| Politics happened.\n2| Sports happened.")

    assert [s["article_id"] for s in out["referenced_stories"]] == ["a1", "b2"]
    assert out["referenced_stories"][0]["take"] == "Politics happened."
    assert out["referenced_stories"][1]["take"] == "Sports happened."
    assert out["categories"] == ["Politics", "Sports"]


def test_out_of_order_model_lines_still_bind_correctly():
    """The model numbering its lines 2,1 must not transpose the links."""
    pairs = [("Politics", article("a1", "Politics")), ("Sports", article("b2", "Sports"))]
    out = brief.assemble(pairs, "2| Sports happened.\n1| Politics happened.")

    stories = out["referenced_stories"]
    assert stories[0]["article_id"] == "a1" and stories[0]["take"] == "Politics happened."
    assert stories[1]["article_id"] == "b2" and stories[1]["take"] == "Sports happened."


def test_categories_stay_aligned_with_stories():
    pairs = [("P", article("a1", "P")), ("S", article("b2", "S")), ("T", article("c3", "T"))]
    out = brief.assemble(pairs, "1| One.\n2| Two.\n3| Three.")

    assert len(out["categories"]) == len(out["referenced_stories"])
    assert out["categories"] == ["P", "S", "T"]


# ───────────────────────── I2: old clients stay aligned ─────────────────────

def test_summary_round_trips_through_the_old_client_split():
    pairs = [("P", article("a1", "P")), ("S", article("b2", "S")), ("T", article("c3", "T"))]
    out = brief.assemble(pairs, "1| Alpha moved.\n2| Beta fell.\n3| Gamma rose.")

    takes = [s["take"] for s in out["referenced_stories"]]
    assert client_split(out["summary"]) == takes


def test_abbreviations_cannot_shift_the_old_client_split():
    """The exact failure the earlier fix attempt would have shipped.

    "The U.S. Fed cut rates." is ONE sentence, but the old regex sees a
    boundary after "U.S." — two real sentences then yield three fragments,
    which passes a naive count-to-three check while misaligning every card.
    """
    pairs = [("Fin", article("a1", "Fin")), ("Spo", article("b2", "Spo")), ("Wor", article("c3", "Wor"))]
    llm = (
        "1| The U.S. Fed cut rates by 0.25 points.\n"
        "2| Arsenal beat Spurs 2-0 at home.\n"
        "3| Dr. Rao met Mr. Chen in St. Louis.\n"
    )
    out = brief.assemble(pairs, llm)

    takes = [s["take"] for s in out["referenced_stories"]]
    assert len(takes) == 3
    assert client_split(out["summary"]) == takes
    # Abbreviations survive as readable text, minus the dots the old client
    # would have read as sentence boundaries.
    assert "US Fed" in takes[0]
    assert "0.25" in takes[0]                       # decimals must not be mangled
    assert "Dr Rao" in takes[2] and "St Louis" in takes[2]


def test_multi_sentence_take_does_not_break_the_split():
    pairs = [("P", article("a1", "P")), ("S", article("b2", "S"))]
    out = brief.assemble(pairs, "1| Rates fell. Markets rallied.\n2| Spurs lost.")

    takes = [s["take"] for s in out["referenced_stories"]]
    assert client_split(out["summary"]) == takes
    assert ". " not in takes[0]          # boundary removed, content kept
    assert "Markets rallied" in takes[0]


# ───────────────────────── model failure paths ──────────────────────────────

def test_llm_failure_still_produces_aligned_takes():
    pairs = [("P", article("a1", "P", what="US officials said the deal is done and dusted today.")),
             ("S", article("b2", "S"))]
    out = brief.assemble(pairs, None)

    stories = out["referenced_stories"]
    assert len(stories) == 2
    assert stories[0]["article_id"] == "a1"
    assert client_split(out["summary"]) == [s["take"] for s in stories]


def test_fallback_never_emits_a_single_letter_sentence():
    """Regression: the old fallback did text.split(".")[0] — on "U.S. officials
    said..." that produced "U", which shipped as an entire brief sentence."""
    pairs = [("P", article("a1", "P", what="U.S. officials said the ceasefire holds for now."))]
    out = brief.assemble(pairs, None)

    take = out["referenced_stories"][0]["take"]
    assert take not in ("U.", "U")
    assert len(take) > 10
    assert "officials said" in take


def test_missing_model_line_does_not_shift_other_takes():
    pairs = [("P", article("a1", "P")), ("S", article("b2", "S")), ("T", article("c3", "T"))]
    out = brief.assemble(pairs, "1| Alpha moved.\n3| Gamma rose.")

    stories = out["referenced_stories"]
    assert stories[0]["take"] == "Alpha moved."
    assert stories[2]["take"] == "Gamma rose."      # NOT shifted up into slot 2
    assert stories[1]["article_id"] == "b2"         # slot 2 fell back, kept its link


def test_garbage_model_output_falls_back_entirely():
    pairs = [("P", article("a1", "P")), ("S", article("b2", "S"))]
    out = brief.assemble(pairs, "I'm sorry, I can't help with that.")

    assert len(out["referenced_stories"]) == 2
    assert all(s["take"] for s in out["referenced_stories"])


def test_duplicate_model_line_numbers_do_not_overwrite():
    pairs = [("P", article("a1", "P")), ("S", article("b2", "S"))]
    out = brief.assemble(pairs, "1| First wins.\n1| Second should be ignored.\n2| Slot two.")

    assert out["referenced_stories"][0]["take"] == "First wins."
    assert out["referenced_stories"][1]["take"] == "Slot two."


# ───────────────────────── selection + ranking ──────────────────────────────

def test_ranking_prefers_substance_over_mere_recency():
    """The behaviour change: newest-published no longer wins automatically."""
    thin = article("thin", "P", published_at=(NOW - timedelta(minutes=20)).isoformat(),
                   what="", description="", view_count=0)
    rich = article("rich", "P", published_at=(NOW - timedelta(hours=10)).isoformat(),
                   why="Because of a long-running dispute that finally came to a head.",
                   context="Background detail that gives the story real shape and weight.",
                   impact="Consequences that matter to a lot of people in the region.",
                   view_count=60, likes=12, image_url="http://x/y.jpg")

    pairs = brief.select_stories(["P"], {"P": [thin, rich]}, [], NOW)
    assert pairs[0][1]["article_id"] == "rich"


def test_selection_is_deterministic():
    arts = [article(f"a{i}", "P", view_count=5) for i in range(5)]
    runs = {brief.select_stories(["P"], {"P": arts}, [], NOW)[0][1]["article_id"] for _ in range(25)}
    assert len(runs) == 1, "brief picks must be reproducible across runs"


def test_subcategory_interest_outranks_freshness():
    generic = article("gen", "Sports", published_at=NOW.isoformat())
    niche = article("niche", "Sports", subcategory="Formula 1",
                    published_at=(NOW - timedelta(hours=30)).isoformat())

    pairs = brief.select_stories(["Sports"], {"Sports": [generic, niche]}, ["Formula 1"], NOW)
    assert pairs[0][1]["article_id"] == "niche"


def test_category_with_no_articles_is_skipped_without_shifting_labels():
    pairs = brief.select_stories(
        ["P", "Empty", "S"],
        {"P": [article("a1", "P")], "Empty": [], "S": [article("b2", "S")]},
        [], NOW,
    )
    assert [(c, a["article_id"]) for c, a in pairs] == [("P", "a1"), ("S", "b2")]


def test_articles_without_ids_are_never_selected():
    pairs = brief.select_stories(["P"], {"P": [{"title": "no id"}, article("a1", "P")]}, [], NOW)
    assert [a["article_id"] for _, a in pairs] == ["a1"]


def test_fewer_than_three_categories_is_fine():
    out = brief.assemble([("P", article("a1", "P"))], "1| Only one story today.")

    assert len(out["referenced_stories"]) == 1
    assert client_split(out["summary"]) == ["Only one story today."]


def test_no_articles_at_all_yields_an_empty_but_valid_payload():
    out = brief.assemble([], None)
    assert out["referenced_stories"] == []
    assert out["categories"] == []
    assert out["summary"] == ""
    assert out["read_time"].endswith("min read")


def test_malformed_published_at_does_not_raise():
    pairs = brief.select_stories(["P"], {"P": [article("a1", "P", published_at="not-a-date")]}, [], NOW)
    assert pairs[0][1]["article_id"] == "a1"


def test_missing_category_key_in_by_category_is_safe():
    pairs = brief.select_stories(["Nope"], {}, [], NOW)
    assert pairs == []


# ───────────────────────── sanitiser units ──────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("**Bold** claim", "Bold claim."),
    ("### Heading style", "Heading style."),
    ("Trailing space   ", "Trailing space."),
    ("Already ends in period.", "Already ends in period."),
    ("Ellipsis... continues", "Ellipsis continues."),
    ("Priced at 1.5 billion", "Priced at 1.5 billion."),   # decimals must survive
    ("", ""),
])
def test_sanitise_take_shapes(raw, expected):
    assert brief.sanitise_take(raw) == expected


def test_sanitise_leaves_no_internal_sentence_boundary():
    messy = "The U.S. and U.K. met. Dr. Smith spoke. Prices rose 2.5 percent."
    cleaned = brief.sanitise_take(messy)
    assert not re.search(r"\.\s", cleaned)     # nothing the old client could split on
    assert cleaned.endswith(".")
    assert "2.5 percent" in cleaned            # decimal preserved

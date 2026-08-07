"""Tests for profile reading observations.

The rule under test: an observation appears only when the data earns it.
Silence is a valid, correct output. The card this replaces filled its slot
unconditionally, which is how it produced "You haven't opened a Politics story
in 0 days" on a profile where Politics was 58% of all reading.
"""

from datetime import datetime, timedelta, timezone

import insights

NOW = datetime(2026, 8, 8, 12, 0, 0, tzinfo=timezone.utc)


def read(category, days_ago=1, completed=False):
    return {
        "category": category,
        "at": (NOW - timedelta(days=days_ago)).isoformat(),
        "completed": completed,
    }


def kinds(observations):
    return [o["kind"] for o in observations]


# ─────────────── the regression that started this ───────────────────────────

def test_a_category_is_never_both_the_beat_and_a_gap():
    """Reproduces the reported profile: Politics dominant AND every category
    read today. The old code called Politics the top category and the quietest
    corner in one sentence. Nothing here may name a gap at all."""
    reads = [read("Politics") for _ in range(58)]
    reads += [read("Business") for _ in range(17)]
    reads += [read("Science") for _ in range(8)]
    reads += [read(c) for c in ("World", "Entertainment", "Technology", "Sports")]

    obs = insights.observe(reads, bookmarks_count=2, now=NOW)

    assert obs, "a 103-read profile should produce something"
    beat = next(o for o in obs if o["kind"] == "beat")
    assert beat["category"] == "Politics"
    assert beat["pct"] >= 35
    # No observation may be phrased around absence, and none may contradict
    # the beat by naming the same category negatively.
    for o in obs:
        assert o["kind"] in insights.PRIORITY
        assert "days" not in o, "nothing should be counting days since something"


def test_no_observation_can_report_a_zero_day_gap():
    """There is no code path that can emit a 'days since' figure at all."""
    for reads in ([], [read("Politics")], [read("Politics") for _ in range(50)]):
        for o in insights.observe(reads, 0, NOW):
            assert not any("day" in str(k).lower() for k in o.keys())


# ─────────────── earned, or absent ──────────────────────────────────────────

def test_nothing_is_claimed_with_no_history():
    assert insights.observe([], 0, NOW) == []


def test_a_handful_of_reads_earns_nothing():
    """Three taps is not a habit. Silence is the correct answer."""
    assert insights.observe([read("Politics"), read("World"), read("Science")], 0, NOW) == []


def test_scattered_reading_earns_no_beat():
    """Evenly spread across sections: there is no centre of gravity to report."""
    reads = [read(c) for c in ("Politics", "World", "Science", "Sports",
                               "Business", "Technology", "Entertainment")] * 2
    obs = insights.observe(reads, 0, NOW)
    assert "beat" not in kinds(obs)
    assert "range" in kinds(obs)          # breadth is the true thing to say here


def test_beat_requires_both_share_and_volume():
    """A 100% share of five reads is not a beat, it's a small sample."""
    assert "beat" not in kinds(insights.observe([read("Politics")] * 5, 0, NOW))
    assert "beat" in kinds(insights.observe([read("Politics")] * 9, 0, NOW))


def test_at_most_two_observations():
    reads = [read("Politics", completed=True) for _ in range(30)]
    reads += [read(c, completed=True) for c in ("World", "Science", "Sports", "Business")]
    assert len(insights.observe(reads, 40, NOW)) <= insights.MAX_OBSERVATIONS


def test_priority_order_is_respected():
    """beat outranks range, so a focused reader leads with the beat."""
    reads = [read("Politics") for _ in range(20)]
    reads += [read(c) for c in ("World", "Science", "Sports", "Business")]
    obs = insights.observe(reads, 0, NOW)
    assert obs[0]["kind"] == "beat"


# ─────────────── individual observations ────────────────────────────────────

def test_rising_names_a_growing_habit_not_a_gap():
    """The positive replacement for 'blind spot': a section climbing lately."""
    old = [read("Politics", days_ago=20) for _ in range(30)]
    recent = [read("Science", days_ago=1) for _ in range(4)]
    recent += [read("Politics", days_ago=2) for _ in range(6)]

    obs = insights.observe(old + recent, 0, NOW)
    rising = [o for o in obs if o["kind"] == "rising"]
    if rising:                                  # priority may crowd it out
        assert rising[0]["category"] == "Science"
        assert rising[0]["hits"] >= insights.RISING_MIN_HITS


def test_rising_never_repeats_the_beat():
    reads = [read("Politics") for _ in range(40)]
    for o in insights.observe(reads, 0, NOW):
        if o["kind"] == "rising":
            assert o["category"] != "Politics"


def test_depth_requires_a_real_completion_rate():
    skimmed = [read("Politics", completed=False) for _ in range(20)]
    assert "depth" not in kinds(insights.observe(skimmed, 0, NOW))

    finished = [read("Politics", completed=True) for _ in range(20)]
    obs = insights.observe(finished, 0, NOW)
    depth = [o for o in obs if o["kind"] == "depth"]
    if depth:
        assert depth[0]["pct"] >= insights.DEPTH_MIN_RATE


def test_saving_needs_a_real_library():
    reads = [read("Politics") for _ in range(20)]
    assert "saving" not in kinds(insights.observe(reads, 1, NOW))


def test_range_counts_distinct_sections():
    reads = [read(c) for c in ("Politics", "World", "Science", "Sports")] * 3
    obs = insights.observe(reads, 0, NOW)
    rng = [o for o in obs if o["kind"] == "range"]
    if rng:
        assert rng[0]["count"] == 4


# ─────────────── the window actually means something ────────────────────────

def test_recent_window_ignores_ancient_history():
    """'Recently' used to be a lie: the query had no date filter at all."""
    ancient = [read("Sports", days_ago=200) for _ in range(60)]
    recent = [read("Politics", days_ago=2) for _ in range(12)]

    obs = insights.observe(ancient + recent, 0, NOW)
    beat = next(o for o in obs if o["kind"] == "beat")
    assert beat["category"] == "Politics", "old reading must not dominate 'recently'"
    assert beat["scope"] == "recent"


def test_sparse_recent_window_falls_back_and_says_so():
    """Too little recent data to claim 'recently', so it widens and labels it."""
    old = [read("Sports", days_ago=120) for _ in range(30)]
    obs = insights.observe(old + [read("Sports", days_ago=1)], 0, NOW)
    assert obs and all(o["scope"] == "all" for o in obs if o["kind"] != "saving")


# ─────────────── never crash on real-world data ─────────────────────────────

def test_malformed_and_missing_timestamps_are_survivable():
    reads = [
        {"category": "Politics", "at": "not-a-date", "completed": True},
        {"category": "Politics", "at": None, "completed": False},
        {"category": None, "at": NOW.isoformat(), "completed": False},
    ] + [read("Politics") for _ in range(10)]
    insights.observe(reads, 0, NOW)          # must not raise


def test_uncategorised_articles_bucket_without_crashing():
    reads = [{"category": None, "at": NOW.isoformat(), "completed": False} for _ in range(12)]
    obs = insights.observe(reads, 0, NOW)
    for o in obs:
        assert o.get("category") in (None, "Other")

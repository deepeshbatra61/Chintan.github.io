"""Tests for feed diversification.

The reported symptom was concrete: "read a few business articles and the first
5-10 are all business." So the tests are concrete too -- the first one
reproduces exactly that input and asserts the outcome the reader actually
wanted, rather than testing that a knob has a value.
"""

import feed


def art(article_id, category):
    return {"article_id": article_id, "category": category}


def scored_run(pairs):
    """[(score, category)] -> [(score, article)], ids generated."""
    return [(s, art(f"a{i}", c)) for i, (s, c) in enumerate(pairs)]


# ───────────────────────── the actual complaint ─────────────────────────

def test_a_business_dominated_score_no_longer_produces_a_business_wall():
    """The bug, reproduced. Business scores far above everything else because
    every category-keyed signal piled onto it -- previously the top 10 came out
    as ten business stories."""
    items = scored_run(
        [(200 - i, "Business") for i in range(10)]
        + [(60 - i, "Politics") for i in range(6)]
        + [(50 - i, "Sports") for i in range(6)]
        + [(40 - i, "Technology") for i in range(6)]
    )
    out = feed.diversify(items, needed=10)

    assert len(out) == 10
    assert feed.max_consecutive_repeats(out) == 1
    # And the density complaint, not just adjacency: business must not own the
    # screen even though it wins on raw score by a mile.
    assert feed.category_counts(out)["Business"] <= 5


def test_no_two_consecutive_share_a_category():
    items = scored_run([(100 - i, c) for i, c in enumerate(
        ["Business", "Business", "Business", "Sports", "Sports", "Politics"]
    )])
    out = feed.diversify(items, needed=6)
    assert feed.max_consecutive_repeats(out) == 1


def test_relevance_order_survives_within_the_constraint():
    """Diversifying must not become shuffling -- the best story still leads."""
    items = scored_run([(100, "Business"), (90, "Sports"), (80, "Business"), (70, "Sports")])
    out = feed.diversify(items, needed=4)
    assert [a["article_id"] for a in out] == ["a0", "a1", "a2", "a3"]


def test_a_dominant_story_still_wins_its_slot():
    """The penalty nudges; it must not veto. A story scoring far above the
    field should still place ahead of a weak one from another category."""
    items = scored_run([(100, "Business"), (500, "Business"), (10, "Sports")])
    out = feed.diversify(items, needed=3)
    # Sports separates them, but the 500 outranks the 100.
    assert [a["article_id"] for a in out] == ["a1", "a2", "a0"]


# ───────────────────────── degenerate inputs ─────────────────────────

def test_single_category_catalogue_returns_everything_anyway():
    """A thin catalogue must yield a repetitive feed, never a truncated one.
    A missing story is a worse failure than a samey one."""
    items = scored_run([(100 - i, "Business") for i in range(5)])
    out = feed.diversify(items, needed=5)
    assert len(out) == 5
    assert [a["article_id"] for a in out] == ["a0", "a1", "a2", "a3", "a4"]


def test_uncategorised_articles_do_not_block_each_other():
    """Empty category is absence of a category, not a category called "". Two
    uncategorised stories in a row is not a repeat."""
    items = scored_run([(100, ""), (90, ""), (80, "")])
    out = feed.diversify(items, needed=3)
    assert len(out) == 3


def test_empty_input():
    assert feed.diversify([], needed=10) == []


def test_needed_larger_than_available():
    items = scored_run([(100, "Business"), (90, "Sports")])
    assert len(feed.diversify(items, needed=50)) == 2


def test_needed_zero():
    items = scored_run([(100, "Business")])
    assert feed.diversify(items, needed=0) == []


def test_no_article_is_dropped_or_duplicated():
    items = scored_run(
        [(100 - i, "Business") for i in range(4)]
        + [(50 - i, "Sports") for i in range(4)]
    )
    out = feed.diversify(items, needed=8)
    ids = [a["article_id"] for a in out]
    assert len(ids) == len(set(ids)) == 8


# ───────────────────────── guest / recency path ─────────────────────────

def _recency_ranked(categories):
    """What the unauthenticated feed builds: newest first, rank as score."""
    n = len(categories)
    return [(float(n - i), art(f"a{i}", c)) for i, c in enumerate(categories)]


def test_guest_feed_never_repeats_a_category_back_to_back():
    """Regression: the guest/interest-less path returned a raw date sort, so
    a fresh install opened Politics, Politics."""
    cats = ["Politics", "Politics", "Politics", "World", "Sports", "Politics", "Business", "World"]
    out = feed.diversify(_recency_ranked(cats), needed=8, penalty=6.0)
    assert feed.max_consecutive_repeats(out) == 1


def test_guest_feed_keeps_the_newest_story_first():
    """Diversifying must not demote the freshest story off the top slot."""
    cats = ["Politics", "Politics", "World", "Sports"]
    out = feed.diversify(_recency_ranked(cats), needed=4, penalty=6.0)
    assert out[0]["article_id"] == "a0"


def test_guest_penalty_does_not_bury_fresh_news_deep():
    """With rank-position scores one point apart, the personalised default
    penalty (22) would push a repeated category ~22 slots down. The guest
    path's smaller penalty must keep a fresh repeat within a few slots."""
    cats = ["Politics", "Politics"] + ["World", "Sports", "Business", "Technology"] * 5
    out = feed.diversify(_recency_ranked(cats), needed=len(cats), penalty=6.0)
    pos = [a["article_id"] for a in out].index("a1")  # the second-newest story
    assert pos <= 8, f"second-newest story pushed to slot {pos}"


def test_finds_a_clean_order_whenever_one_exists():
    """Property test. The greedy used to spend its separator categories early
    and then stack the dominant one at the end, even when a clean interleave
    existed -- example tests missed it because they always had plenty of
    separators. Across random catalogues: if a no-repeat order is possible
    (max category count <= ceil(n/2)), diversify must produce one."""
    import random
    rng = random.Random(1234)
    cats_pool = ["Politics", "World", "Sports", "Business", "Technology"]
    checked = 0
    for _ in range(500):
        n = rng.randint(2, 24)
        weights = [rng.random() ** 2 for _ in cats_pool]   # skewed, like real feeds
        cats = rng.choices(cats_pool, weights=weights, k=n)
        if max(cats.count(c) for c in set(cats)) > (n + 1) // 2:
            continue  # no clean order exists; nothing to assert
        scored = [(rng.uniform(0, 200), art(f"a{i}", c)) for i, c in enumerate(cats)]
        scored.sort(key=lambda x: x[0], reverse=True)
        out = feed.diversify(scored, needed=n)
        assert len(out) == n
        assert feed.max_consecutive_repeats(out) == 1, [a["category"] for a in out]
        checked += 1
    assert checked > 200  # make sure the property was actually exercised


# ───────────────────────── helpers ─────────────────────────

def test_max_consecutive_repeats_counts_runs():
    assert feed.max_consecutive_repeats([]) == 0
    assert feed.max_consecutive_repeats([art("a", "B")]) == 1
    assert feed.max_consecutive_repeats([art("a", "B"), art("b", "B"), art("c", "S")]) == 2
    assert feed.max_consecutive_repeats([art("a", "B"), art("b", "S"), art("c", "B")]) == 1

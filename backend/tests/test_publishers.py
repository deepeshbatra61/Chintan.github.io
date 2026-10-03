"""publishers.canonical: one identity per outlet, from the URL (live-data cases
from 2026-10-03)."""

import pytest

import publishers as P


@pytest.mark.parametrize("source,url,name,group", [
    ("The Times of India", "https://timesofindia.indiatimes.com/india/x.cms", "The Times of India", "national"),
    ("Times of India", "https://timesofindia.indiatimes.com/y", "The Times of India", "national"),
    ("timesofindia.indiatimes.com", "https://timesofindia.indiatimes.com/z", "The Times of India", "national"),
    # GNews labels ET as TOI; the URL decides
    ("The Times of India", "https://economictimes.indiatimes.com/markets/a", "The Economic Times", "national"),
    ("Economictimes.com", "https://m.economictimes.com/b", "The Economic Times", "national"),
    ("NDTV.com", "https://www.ndtv.com/india-news/c", "NDTV", "national"),
    ("NDTV Sports", "https://sports.ndtv.com/d", "NDTV Sports", "national"),
    ("Sportstar", "https://sportstar.thehindu.com/e", "Sportstar", "national"),
    ("The Tribune India", "https://www.tribuneindia.com/f", "The Tribune", "regional"),
    ("ANI News", "https://aninews.in/g", "ANI", "wire"),
    ("Al Jazeera English", "https://www.aljazeera.com/h", "Al Jazeera", "international"),
    ("BBC News", "https://www.bbc.co.uk/news/i", "BBC News", "international"),
])
def test_canonical_known(source, url, name, group):
    p = P.canonical(source, url)
    assert (p.name, p.group) == (name, group)


def test_regional_carries_home_state():
    assert P.canonical("Lokmat Times", "https://www.lokmattimes.com/x").state == "Maharashtra"
    assert P.canonical("x", "https://assamtribune.com/y").state == "Assam"


def test_unknown_outlet_keeps_a_readable_name():
    p = P.canonical("Khabarhub.com", "https://english.khabarhub.com/2026/x")
    assert p.key == "khabarhub.com" and p.name == "Khabarhub" and p.group == "other"
    q = P.canonical("The Punch", "https://punchng.com/x")
    assert q.name == "The Punch" and q.initials == "TP"
    r = P.canonical("", "https://news.bbc.co.uk.example.co.uk/x")
    assert r.key == "example.co.uk"


def test_bad_inputs_never_raise():
    assert P.canonical("", "").name
    assert P.canonical("Some Outlet", "not a url").name == "Some Outlet"
    assert P.canonical(None, None).group == "other"


def test_initials_and_mix():
    assert P.initials_for("Hindustan Times") == "HT" and P.initials_for("Cricbuzz") == "CR"
    pubs = [P.canonical("", u) for u in (
        "https://thehindu.com/a", "https://thehindu.com/b", "https://tribuneindia.com/c",
        "https://aninews.in/d", "https://bbc.com/e")]
    assert P.coverage_mix(pubs) == {"national": 1, "regional": 1, "wire": 1, "international": 1}


def test_every_registry_row_is_valid():
    for dom, (name, ini, typ, state) in P._REGISTRY.items():
        assert dom == dom.lower() and not dom.startswith("www.")
        assert name and len(ini) == 2 and typ in P._GROUP
        assert (state is None) == (typ != "regional"), dom

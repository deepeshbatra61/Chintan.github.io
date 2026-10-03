"""Text helpers shared by every "is this about the same thing?" matcher.

Pure, no I/O. Before this module the same pieces lived in four places
(categories._kw_pattern, desk._kw_pattern, server._DEV_STOPWORDS, desk._STOP /
_PHRASE_STOP) and drifted apart -- the 2026-10-03 Developing flood came from one
copy missing "india". Each stopword set keeps its own job; they just live here.

    kw_pattern(kw)     word-boundary regex (single word) / escaped phrase regex
    STOP_TOPIC         Desk topic words (desk.topic_terms)
    STOP_PHRASE        Desk keyword-phrase tokens (desk._phrase_tokens)
    STOP_HEADLINE      headline clustering / developing detection
    SCOUT_GENERIC      words describing HOW an event happened, not WHAT
    headline_terms()   content-bearing words of a headline
    tokens()           lowercase word tokens for similarity (with light stemming)
"""

import re
from functools import lru_cache


@lru_cache(maxsize=4096)
def kw_pattern(kw: str):
    """Word-boundary regex for single words; plain (escaped) regex for phrases.
    Word boundaries stop short keywords like 'ev' or 'app' from matching inside
    unrelated words (the old 'ai in text' bug matched said/again/main/campaign)."""
    if " " in kw:
        return re.compile(re.escape(kw), re.IGNORECASE)
    return re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)


STOP_TOPIC = frozenset("""
a an the and or of in on at to for from by with about into over after before
is are was were be been has have had will would can could should may might
this that these those it its as not no new says said live update updates
today latest news report reports amid vs than more most
""".split())

STOP_PHRASE = frozenset({
    "the", "and", "for", "with", "from", "into", "over", "after", "amid", "about", "says",
    "said", "new", "its", "his", "her", "their", "this", "that", "was", "are", "has", "had",
})

STOP_HEADLINE = frozenset(
    "the and for with that this from into over after before amid says said report reports "
    "will have has had not new latest their they what when where which more most about india "
    "indian government minister national country people first year years today week month "
    # Common English verbs/function words -- a single ordinary verb slipping
    # through becomes a clustering key that merges unrelated headlines
    # ("Zepto IPO... may TAKE 40-45%" + an NZ politics headline with "take off").
    "take takes taken taking make makes made making get gets got getting give "
    "gives given giving keep keeps kept keeping come comes came coming want "
    "wants wanted go goes went going look looks looked show shows showed "
    "shown tell tells told find finds found could would should still also "
    "just near likely expected reveals reveal visit visits dig digs off out "
    "back down up near seen amid within without amidst upon than then some "
    "such being been were does both each only every much many other another "
    "here there now while during since across against between among per set "
    "sets put puts turn turns move moves moved hold holds held bring brings "
    "brought call calls called leave leaves left let lets stay stays stayed "
    "way ways case cases part parts point points thing things time times".split()
)

# "India vs Zimbabwe 3rd T20I live" must not tag every live match (2026-10-03).
SCOUT_GENERIC = frozenset(
    "live ongoing underway result results match matches series final finals semi "
    "versus against wins win won beats beat defeats routs crushes sweeps reaches "
    "begins starts ends meeting talks protest protests day".split()
)

_WORD = re.compile(r"[A-Za-z][A-Za-z'&-]{3,}")


def headline_terms(title: str, extra_stop=frozenset()) -> list:
    """Content-bearing lowercased words of a headline (4+ letters, no
    STOP_HEADLINE / extra_stop), de-duplicated, in title order."""
    out = []
    for w in _WORD.findall(title or ""):
        lw = w.lower()
        if lw not in STOP_HEADLINE and lw not in extra_stop and lw not in out:
            out.append(lw)
    return out


def stem(word: str) -> str:
    """Very light English stemming so 'resigns'/'resigned'/'resigning' and
    'protests'/'protest' meet. Deliberately crude and predictable: it only has
    to make two headlines about one event share terms, not be linguistics."""
    w = word
    if w.endswith(("ss", "us", "is")):          # congress, campus, crisis
        return w
    for suf, keep, min_stem in (("ies", "y", 3), ("ing", "", 4), ("ed", "", 4), ("s", "", 4)):
        if w.endswith(suf) and len(w) - len(suf) >= min_stem:
            return w[: len(w) - len(suf)] + keep
    return w


_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9'&-]+|\d{2,}")
_YEAR = re.compile(r"(19|20)\d\d")   # "2026" is in half of all headlines; it's not a topic


def tokens(text: str, stop=STOP_HEADLINE) -> list:
    """(token, is_entity) pairs for similarity. Lowercased, stemmed, stopwords
    and 1-2 letter words dropped. is_entity = the word was Capitalised (a name,
    place or organisation) and not the first word of the text, which carries
    more weight when deciding two articles describe the same event."""
    out = []
    for i, m in enumerate(_TOKEN.finditer(text or "")):
        raw = m.group(0).strip("'-")
        low = raw.lower()
        if len(low) < 3 or low in stop or _YEAR.fullmatch(low):
            continue
        entity = i > 0 and raw[:1].isupper()
        out.append((stem(low), entity))
    return out

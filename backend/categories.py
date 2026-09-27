"""Article category classifier -- pure, no I/O, so it can be tested without
the server's dependencies (same reasoning as feed.py).

The keyword scorer here is the source of truth for every article's category;
see detect_category() for how ties and zero-signal articles are resolved.
"""

import re

_CATEGORY_KEYWORDS = {
    "Politics": [
        "election", "elections", "minister", "parliament", "lok sabha", "rajya sabha",
        "policy", "vote", "votes", "voter", "bjp", "congress", "aap", "modi",
        "rahul gandhi", "amit shah", "kejriwal", "mamata", "yogi", "government",
        "cabinet", "opposition", "coalition", "ordinance", "supreme court",
        "high court", "cbi", "governor", "chief minister", "prime minister",
        "manifesto", "poll", "assembly", "mla", "bypoll", "lokpal", "rally",
    ],
    "Business": [
        "market", "markets", "stock", "stocks", "sensex", "nifty", "economy",
        "economic", "gdp", "inflation", "rbi", "sebi", "rupee", "investment",
        "investor", "ipo", "revenue", "profit", "earnings", "merger", "fintech",
        "acquisition", "bank", "banking", "loan", "gst", "budget", "valuation",
        "adani", "ambani", "reliance", "infosys", "tcs", "wipro", "funding",
        "trade", "tariff", "export", "import", "shares", "mutual fund",
        "petrol", "diesel", "fuel price", "forex", "reserves", "trade deficit",
        "current account", "industrial policy", "manufacturing", "msme", "sme",
        "retail", "e-commerce", "company", "companies", "corporate", "ceo",
        "industry", "commerce ministry", "finance ministry", "customs duty",
        "commodity", "crude oil", "gold price", "quarterly results", "q1 results",
        "q2 results", "q3 results", "q4 results",
        "coal blocks", "coal plants", "coal india", "coal production", "coal mining",
        "power demand", "power output", "mou", "property prices",
        "real estate", "housing prices", "ecommerce", "steel", "psu",
    ],
    "Technology": [
        "artificial intelligence", "machine learning", "software", "smartphone",
        "gadget", "chip", "semiconductor", "cyber", "data breach", "cloud computing",
        "5g", "google", "apple", "microsoft", "openai", "chatgpt", "android",
        "ios", "app", "startup", "robotics", "electric vehicle",
        "coding", "developer", "hardware", "laptop", "processor", "gpu", "ai model",
    ],
    "Sports": [
        "cricket", "ipl", "bcci", "world cup", "football", "tennis", "hockey",
        "kabaddi", "olympic", "olympics", "match", "tournament", "wicket",
        "batsman", "bowler", "virat", "kohli", "rohit sharma", "dhoni", "bumrah",
        "medal", "championship", "league", "fifa", "odi", "t20", "test series",
        "stadium", "athlete", "innings", "captain",
        # Multi-sport events and the sports beyond cricket/football. Without
        # these, Asian Games coverage (squash, shooting, marathon, badminton)
        # scored zero and fell through to the Politics default. Deliberately
        # specific: bare "shooting" would pull in crime, bare "gold"/"silver"
        # would pull in commodity prices.
        "asian games", "asiad", "commonwealth games", "paralympic", "paralympics",
        "khelo india", "asia cup", "squash", "badminton", "table tennis",
        "athletics", "marathon", "javelin", "sprinter", "wrestling", "wrestler",
        "boxing", "boxer", "archery", "archer", "weightlifting", "weightlifter",
        "chess", "grandmaster", "skeet", "air rifle", "air pistol", "nrai",
        "shooting gold", "shooting silver", "shooting bronze", "golf", "nba",
        "medallist", "medalist", "medals", "silver medal", "gold medal",
        "bronze", "podium", "semifinal", "semi-final", "quarterfinal",
        "quarter-final", "all-rounder", "hardik pandya", "neeraj chopra",
        "sindhu", "lakshya sen", "mirabai", "chanu", "satwik", "sports",
    ],
    "Entertainment": [
        "bollywood", "film", "movie", "actor", "actress", "cinema", "box office",
        "ott", "netflix", "song", "music", "album", "concert", "celebrity",
        "trailer", "web series", "director", "shah rukh", "salman khan",
        "deepika", "singer", "tollywood", "teaser", "biopic", "filmmaker",
    ],
    "Science": [
        "isro", "chandrayaan", "gaganyaan", "satellite", "space", "nasa",
        "research", "scientist", "vaccine", "climate", "discovery", "experiment",
        "astronomy", "physics", "biology", "genome", "hospital", "aiims",
        "disease", "covid", "dengue", "cancer", "medicine", "health",
        "monsoon", "heatwave", "cyclone", "imd", "rainfall", "flood", "drought",
        "weather", "cold wave", "hailstorm", "landslide", "earthquake", "tremor",
        "air quality", "aqi", "pollution", "wildlife", "forest", "biodiversity",
    ],
    "World": [
        "united nations", "g20", "brics", "pakistan", "china", "russia",
        "ukraine", "united states", "europe", "ceasefire", "foreign",
        "embassy", "bilateral", "trump", "putin", "biden", "gaza", "israel",
        "diplomatic", "treaty", "summit",
    ],
}


# Niche keywords, scored WITHIN the winning category (names mirror
# INTEREST_CATEGORIES so a tagged article maps straight to a picked interest).
_SUBCATEGORY_KEYWORDS = {
    "Politics": {
        "Parliament": ["parliament", "lok sabha", "rajya sabha", "bill", "ordinance", "monsoon session", "speaker"],
        "Elections": ["election", "poll", "voter", "bypoll", "campaign", "manifesto", "constituency", "polling"],
        "Judiciary": ["supreme court", "high court", "verdict", "judge", "bench", "petition", "plea", "judgment"],
        "International Relations": ["bilateral", "diplomat", "treaty", "summit", "embassy", "external affairs"],
        "State Politics": ["chief minister", "assembly", "mla", "governor", "state government", "cabinet"],
    },
    "Technology": {
        "AI & ML": ["artificial intelligence", "machine learning", "openai", "chatgpt", "ai model", "llm", "generative ai"],
        "Startups": ["startup", "funding", "unicorn", "founder", "venture capital", "seed round"],
        "Gadgets": ["smartphone", "laptop", "gadget", "wearable", "processor", "gpu", "chip", "semiconductor"],
        "Fintech": ["fintech", "upi", "digital payment", "neobank", "paytm", "razorpay"],
        "Space Tech": ["satellite", "spacex", "rocket", "launch vehicle"],
        "Telecom": ["5g", "telecom", "spectrum", "jio", "airtel", "vodafone", "broadband"],
    },
    "Business": {
        "Markets": ["sensex", "nifty", "stock", "shares", "ipo", "mutual fund", "equities"],
        "Economy": ["gdp", "inflation", "rbi", "fiscal", "repo rate", "economic"],
        "Startups": ["startup", "funding", "unicorn", "venture", "founder"],
        "Real Estate": ["real estate", "property", "housing", "realty"],
        "Banking": ["bank", "loan", "npa", "sbi", "hdfc", "credit", "banking"],
        "Corporate": ["merger", "acquisition", "earnings", "revenue", "ceo", "corporate", "profit"],
    },
    "Sports": {
        "Cricket": ["cricket", "ipl", "bcci", "wicket", "batsman", "bowler", "virat", "kohli", "rohit", "dhoni", "odi", "t20", "test match", "innings"],
        "Football": ["football", "fifa", "isl", "messi", "ronaldo", "premier league"],
        "Tennis": ["tennis", "wimbledon", "grand slam", "djokovic"],
        "Olympics": ["olympic", "medal", "medals", "athlete", "asian games", "asiad",
                     "commonwealth games", "paralympic", "squash", "badminton",
                     "shooting", "skeet", "marathon", "athletics", "wrestling",
                     "boxing", "archery", "weightlifting", "bronze", "podium"],
        "Kabaddi": ["kabaddi", "pro kabaddi"],
        "Motorsport": ["formula 1", "f1", "motogp", "grand prix"],
    },
    "Entertainment": {
        "Bollywood": ["bollywood", "shah rukh", "salman khan", "deepika", "box office", "hindi film"],
        "OTT": ["ott", "netflix", "prime video", "web series", "hotstar", "streaming"],
        "Music": ["song", "music", "album", "concert", "singer"],
        "Television": ["television", "tv serial", "reality show"],
        "Regional Cinema": ["tollywood", "kollywood", "telugu film", "tamil film", "regional cinema"],
    },
    "Science": {
        "Space": ["isro", "chandrayaan", "gaganyaan", "satellite", "nasa", "astronomy"],
        "Health": ["hospital", "disease", "covid", "vaccine", "aiims", "medicine", "cancer", "dengue"],
        "Environment": ["environment", "pollution", "wildlife", "forest", "biodiversity"],
        "Research": ["research", "study", "scientist", "discovery", "experiment"],
        "Climate": ["climate", "global warming", "emissions", "monsoon", "heatwave"],
    },
    "World": {
        "USA": ["united states", "trump", "biden", "washington"],
        "China": ["china", "beijing", "xi jinping"],
        "Europe": ["european union", "uk", "france", "germany", "europe"],
        "Middle East": ["gaza", "israel", "iran", "saudi", "middle east", "palestine"],
        "Southeast Asia": ["pakistan", "bangladesh", "sri lanka", "nepal", "myanmar"],
    },
}


def _kw_pattern(kw: str):
    """Word-boundary regex for single words; plain (escaped) regex for phrases.
    Word boundaries stop short keywords like 'ev' or 'app' from matching inside
    unrelated words (the old 'ai in text' bug matched said/again/main/campaign)."""
    if " " in kw:
        return re.compile(re.escape(kw), re.IGNORECASE)
    return re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)


_CATEGORY_PATTERNS = {
    cat: [_kw_pattern(kw) for kw in kws] for cat, kws in _CATEGORY_KEYWORDS.items()
}

_SUBCATEGORY_PATTERNS = {
    cat: {sub: [_kw_pattern(kw) for kw in kws] for sub, kws in subs.items()}
    for cat, subs in _SUBCATEGORY_KEYWORDS.items()
}


def detect_category(title: str, body: str) -> tuple:
    """Score every category by weighted keyword matches (title hits count double)
    and return the highest scorer, plus the best niche WITHIN that category (or
    None). Beats the old first-match-wins + substring approach that dumped nearly
    everything into Technology.

    Default is "Politics" (general/national India news), NOT "World" — World's
    own keyword list is specifically foreign/international terms (China,
    Russia, Ukraine, Gaza...), so it must win on its own merits like every
    other category. Defaulting zero-signal articles to World was the actual
    bug behind Indian weather and business stories reading as World news:
    anything that failed to hit a keyword (which used to include most weather
    reports — "monsoon"/"heatwave"/"cyclone" lived only in a subcategory list,
    never in the list that decides the primary category) silently became
    "World" by fallback, not by any real signal that it was international."""
    title_s = title or ""
    body_s = body or ""
    best_cat, best_score = "Politics", 0
    for cat, patterns in _CATEGORY_PATTERNS.items():
        score = 0
        for pat in patterns:
            if pat.search(title_s):
                score += 2
            if pat.search(body_s):
                score += 1
        if score > best_score:
            best_cat, best_score = cat, score

    # Niche within the winning category
    subcategory = None
    if best_score > 0:
        best_sub, best_sub_score = None, 0
        for sub, pats in _SUBCATEGORY_PATTERNS.get(best_cat, {}).items():
            sub_score = 0
            for pat in pats:
                if pat.search(title_s):
                    sub_score += 2
                if pat.search(body_s):
                    sub_score += 1
            if sub_score > best_sub_score:
                best_sub, best_sub_score = sub, sub_score
        subcategory = best_sub

    return best_cat, subcategory

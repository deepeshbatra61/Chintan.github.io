"""Article category classifier -- pure, no I/O, so it can be tested without
the server's dependencies (same reasoning as feed.py).

The keyword scorer here is the source of truth for every article's category;
see detect_category() for how ties and zero-signal articles are resolved.
"""

from textutil import kw_pattern as _kw_pattern  # shared matcher (textutil.py)

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


# ══ Taxonomy v2 (News v2, app 1.13) ══════════════════════════════════════════
#
#   v2 top level : Politics Business Technology Sports Entertainment Science
#                  Health World            (+ the States LENS, see detect_state)
#   1.12 clients : keep seeing the 7 legacy categories (legacy_category) and
#                  legacy interest names (interests_to_legacy) -- eng review OV3.
#
# States is deliberately NOT a category: a Punjab farmers' story is still
# Politics or Business. It carries `state` (publisher home state or a mention
# in the text) and the States chip filters on that, so no story has to pick
# between its subject and its place.

CATEGORIES_V2 = ("Politics", "Business", "Technology", "Sports", "Entertainment",
                 "Science", "Health", "World")
LEGACY_CATEGORIES = ("Politics", "Technology", "Business", "Sports", "Entertainment", "Science", "World")

SUBCATEGORIES_V2 = {
    "Politics": ["Parliament", "Elections", "Judiciary", "International Relations", "State Politics"],
    "Business": ["Markets", "Economy", "Banking & Finance", "Startups", "Corporate", "Auto", "Energy",
                 "Real Estate"],
    "Technology": ["AI & ML", "Gadgets", "Fintech", "Space Tech", "Telecom", "Cybersecurity"],
    "Sports": ["Cricket", "Football", "Hockey", "Tennis", "Badminton", "Athletics", "Multi-sport events",
               "Motorsport", "Chess", "Kabaddi"],
    "Entertainment": ["Bollywood", "OTT", "Music", "Television", "Regional Cinema"],
    "Science": ["Space", "Environment", "Research", "Climate"],
    "Health": ["Public Health", "Medicine", "Disease", "Nutrition & Fitness", "Mental Health"],
    "World": ["USA", "China", "Europe", "Middle East", "South Asia"],
}

_SUB_V2_KEYWORDS = {
    "Business": {
        "Banking & Finance": ["bank", "loan", "npa", "sbi", "hdfc", "credit", "banking", "nbfc", "insurance"],
        "Auto": ["car", "cars", "suv", "automobile", "two-wheeler", "maruti", "tata motors", "mahindra", "ev sales"],
        "Energy": ["oil", "crude", "power", "electricity", "coal", "solar", "renewable", "petrol", "diesel", "lng"],
    },
    "Technology": {
        "Cybersecurity": ["cyber", "hack", "hacker", "ransomware", "data breach", "malware", "phishing"],
    },
    "Sports": {
        "Hockey": ["hockey", "harmanpreet", "sreejesh"],
        "Badminton": ["badminton", "sindhu", "lakshya sen", "satwik", "chirag"],
        "Athletics": ["athletics", "javelin", "neeraj chopra", "sprint", "marathon", "relay", "high jump"],
        "Multi-sport events": ["asian games", "asiad", "commonwealth games", "olympic", "olympics",
                               "paralympic", "khelo india", "medal tally"],
        "Chess": ["chess", "grandmaster", "gukesh", "praggnanandhaa", "carlsen", "fide"],
    },
    "Health": {
        "Public Health": ["outbreak", "vaccination", "icmr", "health ministry", "hospital", "aiims"],
        "Medicine": ["drug", "medicine", "surgery", "treatment", "clinical trial", "doctor", "doctors"],
        "Disease": ["dengue", "covid", "cancer", "tuberculosis", "malaria", "virus", "infection", "diabetes"],
        "Nutrition & Fitness": ["diet", "nutrition", "fitness", "obesity", "exercise", "yoga"],
        "Mental Health": ["mental health", "depression", "anxiety", "suicide", "stress"],
    },
    "World": {
        "South Asia": ["pakistan", "bangladesh", "sri lanka", "nepal", "myanmar", "afghanistan", "bhutan",
                       "maldives"],
    },
}

_HEALTH_KEYWORDS = ["health", "hospital", "aiims", "doctor", "doctors", "disease", "vaccine", "vaccination",
                    "covid", "dengue", "cancer", "medicine", "drug", "patients", "icmr", "outbreak", "virus",
                    "tuberculosis", "malaria", "diabetes", "mental health", "nutrition", "obesity", "surgery"]

# GNews' own category is a strong prior, not the answer ("nation" and
# "general" carry no subject, so they add nothing).
_GNEWS_PRIOR = {"business": "Business", "technology": "Technology", "sports": "Sports",
                "entertainment": "Entertainment", "science": "Science", "health": "Health", "world": "World"}
GNEWS_PRIOR_POINTS = 3

_HEALTH_PATTERNS = [_kw_pattern(k) for k in _HEALTH_KEYWORDS]
# v1 filed health under Science, so Science's list carries health words; in v2
# those words belong to Health alone, or every dengue story ties and Science wins.
_V2_PATTERNS = {
    **{cat: ([_kw_pattern(k) for k in kws if k not in _HEALTH_KEYWORDS] if cat == "Science"
             else _CATEGORY_PATTERNS[cat]) for cat, kws in _CATEGORY_KEYWORDS.items()},
    "Health": _HEALTH_PATTERNS,
}
_SUB_V2_PATTERNS = {cat: {sub: [_kw_pattern(k) for k in kws] for sub, kws in subs.items()}
                    for cat, subs in _SUB_V2_KEYWORDS.items()}


def _score(patterns, title, body):
    return sum((2 if p.search(title) else 0) + (1 if p.search(body) else 0) for p in patterns)


def classify(title: str, body: str, gnews_category: str = None) -> tuple:
    """(category_v2, subcategory_v2): the v1 keyword scores, a Health score of
    its own, and GNews' category as a prior worth GNEWS_PRIOR_POINTS."""
    title_s, body_s = title or "", body or ""
    scores = {cat: _score(pats, title_s, body_s) for cat, pats in _V2_PATTERNS.items()}
    prior = _GNEWS_PRIOR.get((gnews_category or "").lower())
    if prior:
        scores[prior] = scores.get(prior, 0) + GNEWS_PRIOR_POINTS
    best = max(CATEGORIES_V2, key=lambda c: (scores.get(c, 0), c == "Politics"))
    if scores.get(best, 0) == 0:
        best = "Politics"            # same zero-signal default as v1 (see detect_category)
    sub, sub_score = None, 0
    pools = [_SUB_V2_PATTERNS.get(best, {}),
             {s: p for s, p in _SUBCATEGORY_PATTERNS.get(best, {}).items() if s in SUBCATEGORIES_V2.get(best, [])}]
    for pool in pools:
        for name, pats in pool.items():
            sc = _score(pats, title_s, body_s)
            if sc > sub_score:
                sub, sub_score = name, sc
    return best, sub


_SUB_TO_LEGACY = {
    ("Sports", "Multi-sport events"): "Olympics", ("Sports", "Hockey"): "Olympics",
    ("Sports", "Badminton"): "Olympics", ("Sports", "Athletics"): "Olympics",
    ("Business", "Banking & Finance"): "Banking", ("World", "South Asia"): "Southeast Asia",
}


def legacy_category(category_v2: str, subcategory_v2: str = None) -> tuple:
    """What a 1.12 client sees: Health files under Science (as before v2) and
    v2 sub-categories map to the nearest 1.12 name, or None."""
    if category_v2 == "Health":
        return "Science", "Health"
    if category_v2 not in LEGACY_CATEGORIES:
        return "Politics", None
    sub = _SUB_TO_LEGACY.get((category_v2, subcategory_v2), subcategory_v2)
    return category_v2, (sub if sub in _SUBCATEGORY_KEYWORDS.get(category_v2, {}) else None)


# ── interests (eng review OV3: two fields, one mapping keeps them in step) ───

_INTEREST_V2_TO_LEGACY = {
    "Health": "Science", "Multi-sport events": "Olympics", "Hockey": "Olympics", "Badminton": "Olympics",
    "Athletics": "Olympics", "Banking & Finance": "Banking", "South Asia": "Southeast Asia",
    "Public Health": "Health", "Medicine": "Health", "Disease": "Health", "Nutrition & Fitness": "Health",
    "Mental Health": "Health",
}
_INTEREST_LEGACY_TO_V2 = {"Olympics": "Multi-sport events", "Banking": "Banking & Finance",
                          "Southeast Asia": "South Asia"}


def _legacy_interest_names() -> set:
    names = set(LEGACY_CATEGORIES)
    for subs in _SUBCATEGORY_KEYWORDS.values():
        names.update(subs)
    return names


_LEGACY_NAMES = _legacy_interest_names()


def _to_legacy(x: str):
    y = _INTEREST_V2_TO_LEGACY.get(x, x)
    return y if y in _LEGACY_NAMES else None


def interests_to_v2(legacy: list) -> list:
    out = []
    for x in legacy or []:
        y = _INTEREST_LEGACY_TO_V2.get(x, x)
        if y not in out:
            out.append(y)
    return out


def interests_to_legacy(v2: list) -> list:
    """The v2 picks a 1.12 app can show, as 1.12 names (states and v2-only
    names with no 1.12 equivalent are left out)."""
    out = []
    for x in v2 or []:
        y = _to_legacy(x)
        if y and y not in out:
            out.append(y)
    return out


def merge_legacy_save(legacy_saved: list, current_v2: list) -> list:
    """A 1.12 app saved `legacy_saved`. Lossless (OV3): v2 picks the 1.12 app
    can't show (states, ...) are kept; v2 picks it shows as some legacy name
    stay only if that name is still selected; new legacy picks are added."""
    saved = set(legacy_saved or [])
    out = [x for x in current_v2 or [] if _to_legacy(x) is None or _to_legacy(x) in saved]
    covered = {_to_legacy(x) for x in out}
    for x in legacy_saved or []:
        if x not in covered:
            y = _INTEREST_LEGACY_TO_V2.get(x, x)
            if y not in out:
                out.append(y)
    return out


# ── States lens ──────────────────────────────────────────────────────────────

STATES = (
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat", "Haryana",
    "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur",
    "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana",
    "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal", "Delhi", "Jammu and Kashmir", "Ladakh",
    "Puducherry", "Chandigarh", "Northeast",
)
STATE_REGIONS = {
    "North": ["Delhi", "Haryana", "Punjab", "Himachal Pradesh", "Jammu and Kashmir", "Ladakh", "Uttarakhand",
              "Uttar Pradesh", "Chandigarh", "Rajasthan"],
    "South": ["Tamil Nadu", "Kerala", "Karnataka", "Andhra Pradesh", "Telangana", "Puducherry"],
    "East": ["West Bengal", "Odisha", "Bihar", "Jharkhand"],
    "West": ["Maharashtra", "Gujarat", "Goa"],
    "Central": ["Madhya Pradesh", "Chhattisgarh"],
    "Northeast": ["Assam", "Arunachal Pradesh", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Sikkim",
                  "Tripura", "Northeast"],
}
# Names, capitals and big cities that place a story in a state.
_STATE_MENTIONS = {
    "Maharashtra": ["maharashtra", "mumbai", "pune", "nagpur", "nashik", "thane"],
    "Karnataka": ["karnataka", "bengaluru", "bangalore", "mysuru", "mangaluru"],
    "Tamil Nadu": ["tamil nadu", "chennai", "coimbatore", "madurai"],
    "Kerala": ["kerala", "thiruvananthapuram", "kochi", "kozhikode"],
    "Telangana": ["telangana", "hyderabad"],
    "Andhra Pradesh": ["andhra pradesh", "vijayawada", "visakhapatnam", "amaravati"],
    "West Bengal": ["west bengal", "kolkata"],
    "Delhi": ["delhi", "new delhi"],
    "Uttar Pradesh": ["uttar pradesh", "lucknow", "noida", "varanasi", "ayodhya", "kanpur", "prayagraj"],
    "Gujarat": ["gujarat", "ahmedabad", "surat", "vadodara", "gandhinagar"],
    "Rajasthan": ["rajasthan", "jaipur", "udaipur", "jodhpur"],
    "Punjab": ["punjab", "amritsar", "ludhiana"],
    "Haryana": ["haryana", "gurugram", "gurgaon", "faridabad"],
    "Bihar": ["bihar", "patna"],
    "Odisha": ["odisha", "bhubaneswar", "cuttack"],
    "Assam": ["assam", "guwahati"],
    "Madhya Pradesh": ["madhya pradesh", "bhopal", "indore"],
    "Jharkhand": ["jharkhand", "ranchi"],
    "Chhattisgarh": ["chhattisgarh", "raipur"],
    "Uttarakhand": ["uttarakhand", "dehradun"],
    "Himachal Pradesh": ["himachal pradesh", "shimla"],
    "Goa": ["goa", "panaji"],
    "Jammu and Kashmir": ["jammu and kashmir", "kashmir", "srinagar", "jammu"],
    "Ladakh": ["ladakh", "leh"],
    "Manipur": ["manipur", "imphal"],
    "Meghalaya": ["meghalaya", "shillong"],
    "Mizoram": ["mizoram", "aizawl"],
    "Nagaland": ["nagaland", "kohima"],
    "Tripura": ["tripura", "agartala"],
    "Sikkim": ["sikkim", "gangtok"],
    "Arunachal Pradesh": ["arunachal pradesh", "itanagar"],
    "Puducherry": ["puducherry", "pondicherry"],
    "Chandigarh": ["chandigarh"],
}
_STATE_PATTERNS = {st: [_kw_pattern(k) for k in kws] for st, kws in _STATE_MENTIONS.items()}


def detect_state(title: str, body: str, publisher_state: str = None):
    """The state a story is about: the strongest mention (title counts
    double), else a regional publisher's home state, else None. A bare
    "Delhi" only counts in the title -- national-capital stories mention it
    in passing all the time."""
    title_s, body_s = title or "", body or ""
    best, best_score = None, 0
    for st, pats in _STATE_PATTERNS.items():
        sc = _score(pats, title_s, body_s)
        if st == "Delhi" and not any(p.search(title_s) for p in pats):
            sc = 0
        if sc > best_score:
            best, best_score = st, sc
    return best or publisher_state

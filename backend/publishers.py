"""Publisher registry: who an article really comes from. Pure, no I/O.

Identity comes from the article URL's domain, never the provider's source name:
GNews files Economic Times stories (economictimes.indiatimes.com) under "The
Times of India", and one outlet arrives as "Times of India", "The Times of
India" and "timesofindia.indiatimes.com" (live data, 2026-10-03). Counting
voices, capping a publisher's share and the coverage mix all need one name.

    canonical(source_name, url) -> Publisher(key, name, initials, type, group, state)

    type  : national | regional | business | sports | entertainment | digital
            | magazine | wire | international | other
    group : the coverage-mix bucket shown to readers
            national (Indian national, business, sports, digital, magazine,
            entertainment) | regional | wire | international | other
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse


@dataclass(frozen=True)
class Publisher:
    key: str             # registrable domain, the stable id ("thehindu.com")
    name: str            # display name ("The Hindu")
    initials: str        # 2 letters for the coverage strip ("TH")
    type: str
    group: str
    state: Optional[str] = None   # home state for regional outlets


_GROUP = {
    "national": "national", "business": "national", "sports": "national",
    "entertainment": "national", "digital": "national", "magazine": "national",
    "regional": "regional", "wire": "wire", "international": "international", "other": "other",
}

# domain : (name, initials, type, home_state)
# Longest-suffix match, so "economictimes.indiatimes.com" wins over
# "indiatimes.com" and "sportstar.thehindu.com" over "thehindu.com".
_REGISTRY: dict[str, tuple] = {
    # ── Indian national ──────────────────────────────────────────────────────
    "timesofindia.indiatimes.com": ("The Times of India", "TI", "national", None),
    "indiatimes.com": ("Indiatimes", "IT", "digital", None),
    "thehindu.com": ("The Hindu", "TH", "national", None),
    "hindustantimes.com": ("Hindustan Times", "HT", "national", None),
    "indianexpress.com": ("The Indian Express", "IE", "national", None),
    "ndtv.com": ("NDTV", "ND", "national", None),
    "indiatoday.in": ("India Today", "IN", "national", None),
    "news18.com": ("News18", "N1", "national", None),
    "timesnownews.com": ("Times Now", "TN", "national", None),
    "theprint.in": ("ThePrint", "TP", "digital", None),
    "scroll.in": ("Scroll", "SC", "digital", None),
    "thewire.in": ("The Wire", "TW", "digital", None),
    "thequint.com": ("The Quint", "TQ", "digital", None),
    "newslaundry.com": ("Newslaundry", "NL", "digital", None),
    "firstpost.com": ("Firstpost", "FP", "digital", None),
    "wionews.com": ("WION", "WI", "national", None),
    "newsx.com": ("NewsX", "NX", "national", None),
    "news9live.com": ("News9", "N9", "national", None),
    "india.com": ("India.com", "IC", "digital", None),
    "rediff.com": ("Rediff", "RE", "digital", None),
    "dnaindia.com": ("DNA", "DN", "national", None),
    "zeenews.india.com": ("Zee News", "ZN", "national", None),
    "abplive.com": ("ABP Live", "AB", "national", None),
    "republicworld.com": ("Republic", "RW", "national", None),
    "outlookindia.com": ("Outlook", "OU", "magazine", None),
    "theweek.in": ("The Week", "WK", "magazine", None),
    "frontline.thehindu.com": ("Frontline", "FL", "magazine", None),
    "caravanmagazine.in": ("The Caravan", "CA", "magazine", None),
    "devdiscourse.com": ("Devdiscourse", "DD", "digital", None),
    "nationpress.com": ("Nation Press", "NP", "digital", None),
    "livelaw.in": ("Live Law", "LL", "digital", None),
    "barandbench.com": ("Bar and Bench", "BB", "digital", None),
    "downtoearth.org.in": ("Down To Earth", "DE", "magazine", None),
    # ── Indian business ──────────────────────────────────────────────────────
    "economictimes.indiatimes.com": ("The Economic Times", "ET", "business", None),
    "m.economictimes.com": ("The Economic Times", "ET", "business", None),
    "economictimes.com": ("The Economic Times", "ET", "business", None),
    "health.economictimes.indiatimes.com": ("ET HealthWorld", "EH", "business", None),
    "business-standard.com": ("Business Standard", "BS", "business", None),
    "thehindubusinessline.com": ("BusinessLine", "BL", "business", None),
    "livemint.com": ("Mint", "MI", "business", None),
    "moneycontrol.com": ("Moneycontrol", "MC", "business", None),
    "financialexpress.com": ("Financial Express", "FE", "business", None),
    "businesstoday.in": ("Business Today", "BT", "business", None),
    "cnbctv18.com": ("CNBC-TV18", "CN", "business", None),
    "ndtvprofit.com": ("NDTV Profit", "NP", "business", None),
    "outlookbusiness.com": ("Outlook Business", "OB", "business", None),
    "etnownews.com": ("ET Now", "EN", "business", None),
    "inc42.com": ("Inc42", "I4", "business", None),
    "yourstory.com": ("YourStory", "YS", "business", None),
    "entrackr.com": ("Entrackr", "EK", "business", None),
    "bwhealthcareworld.com": ("BW Healthcare", "BW", "business", None),
    "businessworld.in": ("BW Businessworld", "BW", "business", None),
    # ── Indian sports / entertainment / tech ─────────────────────────────────
    "sportstar.thehindu.com": ("Sportstar", "SS", "sports", None),
    "cricbuzz.com": ("Cricbuzz", "CB", "sports", None),
    "cricinfo.com": ("ESPNcricinfo", "EC", "sports", None),
    "espncricinfo.com": ("ESPNcricinfo", "EC", "sports", None),
    "sports.ndtv.com": ("NDTV Sports", "NS", "sports", None),
    "cricketnews.com": ("Cricketnews", "CK", "sports", None),
    "sportskeeda.com": ("Sportskeeda", "SK", "sports", None),
    "hockeyindia.org": ("Hockey India", "HI", "sports", None),
    "bollywoodhungama.com": ("Bollywood Hungama", "BH", "entertainment", None),
    "pinkvilla.com": ("Pinkvilla", "PV", "entertainment", None),
    "filmfare.com": ("Filmfare", "FF", "entertainment", None),
    "gadgets360.com": ("Gadgets 360", "G3", "digital", None),
    "telecomtalk.info": ("TelecomTalk", "TT", "digital", None),
    "carandbike.com": ("carandbike", "CR", "digital", None),
    "autocarindia.com": ("Autocar India", "AI", "magazine", None),
    # ── Indian regional ──────────────────────────────────────────────────────
    "tribuneindia.com": ("The Tribune", "TR", "regional", "Punjab"),
    "telegraphindia.com": ("The Telegraph", "TG", "regional", "West Bengal"),
    "thestatesman.com": ("The Statesman", "ST", "regional", "West Bengal"),
    "deccanchronicle.com": ("Deccan Chronicle", "DC", "regional", "Telangana"),
    "deccanherald.com": ("Deccan Herald", "DH", "regional", "Karnataka"),
    "newindianexpress.com": ("The New Indian Express", "NE", "regional", "Tamil Nadu"),
    "thehansindia.com": ("The Hans India", "HN", "regional", "Telangana"),
    "lokmattimes.com": ("Lokmat Times", "LT", "regional", "Maharashtra"),
    "freepressjournal.in": ("Free Press Journal", "FJ", "regional", "Maharashtra"),
    "mid-day.com": ("Mid-day", "MD", "regional", "Maharashtra"),
    "punemirror.com": ("Pune Mirror", "PM", "regional", "Maharashtra"),
    "thehitavada.com": ("The Hitavada", "HV", "regional", "Maharashtra"),
    "bangaloremirror.indiatimes.com": ("Bangalore Mirror", "BM", "regional", "Karnataka"),
    "onmanorama.com": ("Onmanorama", "OM", "regional", "Kerala"),
    "english.mathrubhumi.com": ("Mathrubhumi", "MB", "regional", "Kerala"),
    "dtnext.in": ("DT Next", "DT", "regional", "Tamil Nadu"),
    "orissapost.com": ("Orissa POST", "OP", "regional", "Odisha"),
    "navhindtimes.in": ("The Navhind Times", "NV", "regional", "Goa"),
    "heraldgoa.in": ("Herald Goa", "HG", "regional", "Goa"),
    "assamtribune.com": ("The Assam Tribune", "AT", "regional", "Assam"),
    "sentinelassam.com": ("The Sentinel", "SN", "regional", "Assam"),
    "eastmojo.com": ("EastMojo", "EM", "regional", "Northeast"),
    "nagalandpost.com": ("Nagaland Post", "NG", "regional", "Nagaland"),
    "theshillongtimes.com": ("The Shillong Times", "SH", "regional", "Meghalaya"),
    "arunachaltimes.in": ("The Arunachal Times", "AR", "regional", "Arunachal Pradesh"),
    "thesangaiexpress.com": ("The Sangai Express", "SE", "regional", "Manipur"),
    "greaterkashmir.com": ("Greater Kashmir", "GK", "regional", "Jammu and Kashmir"),
    "dailyexcelsior.com": ("Daily Excelsior", "DX", "regional", "Jammu and Kashmir"),
    "kashmirobserver.net": ("Kashmir Observer", "KO", "regional", "Jammu and Kashmir"),
    "kashmirnewsbureau.com": ("Kashmir News Bureau", "KB", "regional", "Jammu and Kashmir"),
    "theshillongtimes.in": ("The Shillong Times", "SH", "regional", "Meghalaya"),
    "babushahi.com": ("Babushahi", "BS", "regional", "Punjab"),
    "lokmat.com": ("Lokmat", "LK", "regional", "Maharashtra"),
    # ── Wires ────────────────────────────────────────────────────────────────
    "aninews.in": ("ANI", "AN", "wire", None),
    "ptinews.com": ("PTI", "PT", "wire", None),
    "ianslive.in": ("IANS", "IA", "wire", None),
    "uniindia.com": ("UNI", "UN", "wire", None),
    "reuters.com": ("Reuters", "RT", "wire", None),
    "apnews.com": ("AP", "AP", "wire", None),
    "afp.com": ("AFP", "AF", "wire", None),
    # ── International ────────────────────────────────────────────────────────
    "bbc.com": ("BBC News", "BB", "international", None),
    "bbc.co.uk": ("BBC News", "BB", "international", None),
    "aljazeera.com": ("Al Jazeera", "AJ", "international", None),
    "theguardian.com": ("The Guardian", "GU", "international", None),
    "nytimes.com": ("The New York Times", "NY", "international", None),
    "washingtonpost.com": ("The Washington Post", "WP", "international", None),
    "cnn.com": ("CNN", "CN", "international", None),
    "bloomberg.com": ("Bloomberg", "BG", "international", None),
    "ft.com": ("Financial Times", "FT", "international", None),
    "wsj.com": ("The Wall Street Journal", "WS", "international", None),
    "economist.com": ("The Economist", "EC", "international", None),
    "dw.com": ("DW", "DW", "international", None),
    "france24.com": ("France 24", "F2", "international", None),
    "channelnewsasia.com": ("CNA", "CA", "international", None),
    "straitstimes.com": ("The Straits Times", "SG", "international", None),
    "scmp.com": ("South China Morning Post", "SM", "international", None),
    "dawn.com": ("Dawn", "DA", "international", None),
    "thedailystar.net": ("The Daily Star", "DS", "international", None),
    "thediplomat.com": ("The Diplomat", "TD", "international", None),
    "foreignpolicy.com": ("Foreign Policy", "FO", "international", None),
    "arabnews.com": ("Arab News", "AR", "international", None),
    "cnbc.com": ("CNBC", "CB", "international", None),
    "npr.org": ("NPR", "NR", "international", None),
    "cbc.ca": ("CBC News", "CC", "international", None),
    "abc.net.au": ("ABC News (Australia)", "AU", "international", None),
    "techcrunch.com": ("TechCrunch", "TC", "international", None),
    "theverge.com": ("The Verge", "VG", "international", None),
    "variety.com": ("Variety", "VA", "international", None),
    "olympics.com": ("Olympics.com", "OL", "international", None),
    "espn.com": ("ESPN", "ES", "international", None),
    "nature.com": ("Nature", "NA", "international", None),
    "phys.org": ("Phys.org", "PH", "international", None),
}


def _host(url: str) -> str:
    try:
        host = urlparse(url or "").netloc.lower()
    except ValueError:
        return ""
    host = host.split("@")[-1].split(":")[0]
    return host[4:] if host.startswith("www.") else host


def _lookup(host: str) -> Optional[tuple[str, tuple]]:
    """Longest registered domain that host equals or ends with (on a dot).
    Walks the host's own suffixes, longest first: a.b.c.com, b.c.com, c.com."""
    parts = host.split(".")
    for i in range(len(parts) - 1):
        dom = ".".join(parts[i:])
        if dom in _REGISTRY:
            return dom, _REGISTRY[dom]
    return None


def _registrable(host: str) -> str:
    """Rough eTLD+1: last two labels, three for co.uk/com.au/co.in style."""
    parts = host.split(".")
    if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "net", "gov", "ac"):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def initials_for(name: str) -> str:
    words = [w for w in name.replace(".", " ").replace("-", " ").split() if w]
    if not words:
        return "??"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()


def _looks_like_domain(s: str) -> bool:
    s = (s or "").strip().lower()
    return " " not in s and "." in s


def canonical(source_name: str, url: str) -> Publisher:
    """The one identity for an article's outlet. Known domains map to the
    registry; unknown ones keep a readable name (the provider's, unless that
    is itself just a domain) with type and group "other"."""
    host = _host(url)
    hit = _lookup(host) if host else None
    if hit:
        dom, (name, ini, typ, state) = hit
        return Publisher(dom, name, ini, typ, _GROUP[typ], state)
    key = _registrable(host) if host else (source_name or "unknown").strip().lower()
    name = (source_name or "").strip()
    if not name or _looks_like_domain(name):
        base = key.split(".")[0] if key else "Unknown"
        name = base[:1].upper() + base[1:]
    return Publisher(key, name, initials_for(name), "other", "other", None)


def coverage_mix(publishers) -> dict:
    """{group: count} over distinct publishers, for the mix line/bar."""
    seen, mix = set(), {}
    for p in publishers:
        if p.key in seen:
            continue
        seen.add(p.key)
        mix[p.group] = mix.get(p.group, 0) + 1
    return mix

// Taxonomy v2 (app 1.13). Mirrors backend/categories.py (CATEGORIES_V2,
// SUBCATEGORIES_V2, STATES, STATE_REGIONS); a test pins the two together.
//
// A feed filter is one string key so the feed's existing plumbing (cache,
// paging, retry) carries it unchanged:
//   "Sports"          category=Sports
//   "Sports/Hockey"   category=Sports&subcategory=Hockey
//   "States/Kerala"   state=Kerala

export const TOP_CHIPS = ["All", "Politics", "Business", "Technology", "Sports", "Entertainment",
  "Science", "Health", "World", "States"];

export const SUBCATEGORIES = {
  Politics: ["Parliament", "Elections", "Judiciary", "International Relations", "State Politics"],
  Business: ["Markets", "Economy", "Banking & Finance", "Startups", "Corporate", "Auto", "Energy", "Real Estate"],
  Technology: ["AI & ML", "Gadgets", "Fintech", "Space Tech", "Telecom", "Cybersecurity"],
  Sports: ["Cricket", "Football", "Hockey", "Tennis", "Badminton", "Athletics", "Multi-sport events",
    "Motorsport", "Chess", "Kabaddi"],
  Entertainment: ["Bollywood", "OTT", "Music", "Television", "Regional Cinema"],
  Science: ["Space", "Environment", "Research", "Climate"],
  Health: ["Public Health", "Medicine", "Disease", "Nutrition & Fitness", "Mental Health"],
  World: ["USA", "China", "Europe", "Middle East", "South Asia"],
};

export const STATE_REGIONS = {
  North: ["Delhi", "Haryana", "Punjab", "Himachal Pradesh", "Jammu and Kashmir", "Ladakh", "Uttarakhand",
    "Uttar Pradesh", "Chandigarh", "Rajasthan"],
  South: ["Tamil Nadu", "Kerala", "Karnataka", "Andhra Pradesh", "Telangana", "Puducherry"],
  East: ["West Bengal", "Odisha", "Bihar", "Jharkhand"],
  West: ["Maharashtra", "Gujarat", "Goa"],
  Central: ["Madhya Pradesh", "Chhattisgarh"],
  Northeast: ["Assam", "Arunachal Pradesh", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Sikkim",
    "Tripura", "Northeast"],
};
export const STATES = Object.values(STATE_REGIONS).flat();

export function parseFilter(key) {
  if (!key || key === "All") return { top: "All", sub: null, state: null };
  const [top, rest] = key.split("/");
  if (top === "States") return { top, sub: null, state: rest || null };
  return { top, sub: rest || null, state: null };
}

export function filterKey(top, subOrState) {
  if (!top || top === "All") return null;
  return subOrState ? `${top}/${subOrState}` : top;
}

/** Query params for /articles from a filter key (server reads them only
 * from 1.13 clients; see X-Chintan-Client). */
export function filterParams(key, params) {
  const f = parseFilter(key);
  if (f.top === "All") return params;
  if (f.top === "States") {
    params.set("state", f.state || "*");      // "*": every state-tagged story
    return params;
  }
  params.set("category", f.top);
  if (f.sub) params.set("subcategory", f.sub);
  return params;
}

// ── home state: interests_v2 for signed-in readers, the device for guests ──
const HOME_KEY = "chintan.homeState";

export function homeStateOf(user) {
  const fromUser = (user?.interests_v2 || []).find((x) => STATES.includes(x));
  if (fromUser) return fromUser;
  try {
    const v = localStorage.getItem(HOME_KEY);
    return STATES.includes(v) ? v : null;
  } catch {
    return null;
  }
}

export function rememberGuestState(state) {
  try { localStorage.setItem(HOME_KEY, state); } catch { /* private mode */ }
}

export const ASKED_KEY = "chintan.homeStateAsked";

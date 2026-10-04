// The Bureau (app 1.14): official announcements, decoded.
//
// The server decides who sees it (GET /bureau/status): everyone once it is
// live; only Desk admins while it is in shadow ("preview"). The chip is drawn
// only when enabled, so this build can ship before the Desk quality gate passes.
//
// The feed filter key is "Bureau" or "Bureau/<lens>" (e.g. "Bureau/rbi"), so
// the feed page's cache and back-navigation carry it like any other filter.

import axios from "axios";

const API = "https://chintangithubio-production.up.railway.app/api";

export const BUREAU_KEY = "Bureau";
export const BUREAU_LABEL = "The Bureau";
export const BUREAU_TAGLINE = "Official announcements, decoded";

export const LENSES = [
  ["", "All"], ["cabinet", "Cabinet"], ["rbi", "RBI"], ["sebi", "SEBI"], ["ministries", "Ministries"],
  ["parliament", "Parliament"], ["trade", "Trade"], ["data", "Data"],
];

export const isBureauKey = (key) => key === BUREAU_KEY || (typeof key === "string" && key.startsWith(`${BUREAU_KEY}/`));
export const lensOf = (key) => (isBureauKey(key) && key.includes("/") ? key.split("/")[1] : "");
export const bureauKey = (lens) => (lens ? `${BUREAU_KEY}/${lens}` : BUREAU_KEY);

// ── network ──────────────────────────────────────────────────────────────────
let statusCache = null;   // one check per app session; the chip never flickers

export async function getBureauStatus() {
  if (statusCache) return statusCache;
  try {
    const r = await axios.get(`${API}/bureau/status`, { withCredentials: true });
    statusCache = { enabled: !!r.data?.enabled, preview: !!r.data?.preview };
  } catch {
    return { enabled: false, preview: false };       // retried next time; no chip meanwhile
  }
  return statusCache;
}

export const resetBureauStatus = () => { statusCache = null; };

export async function getBureauFeed({ lens = "", before = null, limit = 20 } = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (lens) params.set("lens", lens);
  if (before) params.set("before", before);
  const r = await axios.get(`${API}/bureau?${params}`, { withCredentials: true });
  return r.data;
}

export async function getBureauItem(id) {
  const r = await axios.get(`${API}/bureau/items/${encodeURIComponent(id)}`, { withCredentials: true });
  return r.data;
}

// ── words ────────────────────────────────────────────────────────────────────
export const KIND_LABEL = {
  cabinet_decision: "Cabinet decision", policy: "Policy", circular: "Circular", notification: "Notification",
  scheme: "Scheme", consultation: "Consultation", appointment: "Appointment", data_release: "Data",
  mou: "Agreement", statement: "Statement", event: "Event", bill: "Bill",
};

/** "5.25%", "₹12,000 crore", "25 bps"; the unit is whatever the source used. */
export function formatNumber(kn) {
  if (!kn || kn.value === undefined || kn.value === null || String(kn.value).trim() === "") return "";
  const v = String(kn.value).trim();
  const u = String(kn.unit || "").trim();
  if (!u) return v;
  if (u === "%") return `${v}%`;
  if (/^(₹|rs\.?|inr|rupees?)$/i.test(u)) return v.startsWith("₹") ? v : `₹${v}`;
  const money = u.match(/^(?:₹|rs\.?|inr)\s*(crore|lakh|cr)\b/i);
  if (money) return `${v.startsWith("₹") ? v : `₹${v}`} ${money[1].toLowerCase() === "cr" ? "crore" : money[1].toLowerCase()}`;
  if (/^(bps|basis points?)$/i.test(u)) return `${v} bps`;
  return `${v} ${u}`;
}

/** { arrow, text, spoken } for a delta such as "-0.25"; null when there is none.
 * Neutral on purpose: a rate cut is good for borrowers and bad for savers. */
export function formatDelta(kn) {
  const raw = String(kn?.delta ?? "").trim();
  const m = raw.match(/^([+\-−])?\s*(\d[\d,]*(?:\.\d+)?)/);
  if (!m || Number(m[2].replace(/,/g, "")) === 0) return null;
  const down = m[1] === "-" || m[1] === "−";
  const unit = kn.unit === "%" ? "%" : /bps|basis/i.test(kn.unit || "") ? " bps" : "";
  return { arrow: down ? "▼" : "▲", text: `${m[2]}${unit}`, spoken: `${down ? "down" : "up"} ${m[2]}${unit === "%" ? " percent" : unit}` };
}

export function spokenNumber(kn) {
  const n = formatNumber(kn);
  if (!n) return "";
  const d = formatDelta(kn);
  return [kn.label, n.replace("%", " percent").replace("₹", "rupees "), d?.spoken].filter(Boolean).join(", ");
}

// ── drawn visual per kind (design review: line SVG, aria-hidden) ─────────────
export function visualFor(item) {
  const kind = item?.kind;
  if (kind === "bill" || item?.issuer_key === "parliament") return "pillar";
  if (kind === "data_release") return "bars";
  if (kind === "scheme") return "crate";
  if (kind === "consultation") return "calendar";
  if (item?.key_number?.unit === "%" && (item?.issuer_key === "rbi" || kind === "policy")) return "dial";
  if (["policy", "circular", "cabinet_decision"].includes(kind)) return "scales";
  return "document";
}

// ── time, in India ───────────────────────────────────────────────────────────
const IST_MS = 330 * 60 * 1000;
const istDate = (iso) => new Date(new Date(iso).getTime() + IST_MS);
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export const istDayKey = (iso) => istDate(iso).toISOString().slice(0, 10);

export function istTime(iso) {
  const d = istDate(iso);
  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
}

export function istDateLabel(iso) {
  const d = istDate(iso);
  return `${d.getUTCDate()} ${MON[d.getUTCMonth()]}`;
}

/** "Today", "Yesterday", or "Mon 5 Oct". */
export function dayLabel(iso, now = Date.now()) {
  const key = istDayKey(iso);
  const today = istDayKey(new Date(now).toISOString());
  const yesterday = istDayKey(new Date(now - 86400000).toISOString());
  if (key === today) return "Today";
  if (key === yesterday) return "Yesterday";
  const d = istDate(iso);
  return `${DOW[d.getUTCDay()]} ${d.getUTCDate()} ${MON[d.getUTCMonth()]}`;
}

export function isWeekendIST(now = Date.now()) {
  const dow = istDate(new Date(now).toISOString()).getUTCDay();
  return dow === 0 || dow === 6;
}

/** Items grouped into [label, items] by day in India, newest first. */
export function groupByDay(items, now = Date.now()) {
  const out = [];
  for (const it of items) {
    const label = dayLabel(it.published_at, now);
    if (!out.length || out[out.length - 1][0] !== label) out.push([label, []]);
    out[out.length - 1][1].push(it);
  }
  return out;
}

export function domainOf(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return ""; }
}

/** Card faces: what changed, then who it hits, then the analogy; only the
 * ones with something to say. */
export function facesOf(item) {
  const faces = ["what"];
  if ((item.who || []).length || (item.sectors || []).length) faces.push("who");
  if ((item.analogy || "").trim()) faces.push("like");
  return faces;
}

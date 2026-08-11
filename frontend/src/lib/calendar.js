// Shared Chintan Calendar presentation bits.
//
// Lives here rather than in DevelopingPage.js because the list card and the
// detail page are peers -- both need the same icon per category and the same
// date format, and having one page import from the other would make an
// arbitrary one of them the owner.
//
// The category keys must stay in sync with CALENDAR_EVENTS' `category` field
// in backend/server.py. An unknown category is not an error: it falls back to
// the generic calendar icon, so adding a category server-side degrades to a
// plain icon instead of crashing the page.
import {
  Flag, Trophy, Sparkles, Rocket, CalendarDays,
  ScrollText, Globe, HeartPulse, Landmark, Palette, Users, Leaf, Wheat,
} from "lucide-react";

export const CALENDAR_ICONS = {
  national: Flag,
  sports: Trophy,
  festival: Sparkles,
  science: Rocket,
  history: ScrollText,
  global: Globe,
  health: HeartPulse,
  politics: Landmark,
  culture: Palette,
  social: Users,
  environment: Leaf,
  economy: Wheat,
};

export const calendarIcon = (category) => CALENDAR_ICONS[category] || CalendarDays;

// "2026-08-11" -> "AUG 11". Parsed with an explicit T00:00:00 so the browser
// treats it as local time; a bare "2026-08-11" is parsed as UTC midnight and
// renders as the PREVIOUS day for anyone west of Greenwich.
export function formatCalendarDate(isoDate) {
  if (!isoDate) return "";
  const d = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" }).toUpperCase();
}

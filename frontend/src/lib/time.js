// Relative time for news ("12m ago"). Stays in hours out to 72h: developing
// stories' updates are often 1-2 days old, and "1d ago" at 24h flattened
// almost everything to the same label.
export function formatRelativeTime(isoString) {
  if (!isoString) return "";
  const diff = (Date.now() - new Date(isoString).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400 * 3) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

/** "Since you looked" for a newest-first timeline: which items are new, and
 * whether to draw the divider (only when some are new AND some are not; no
 * divider on a first visit or when nothing changed). */
export function sinceLooked(articles, prevSeen) {
  const seenAt = prevSeen ? new Date(prevSeen).getTime() : null;
  const isNew = (a) => seenAt !== null && !!a?.published_at && new Date(a.published_at).getTime() > seenAt;
  const newCount = (articles || []).filter(isNew).length;
  return { isNew, newCount, showDivider: newCount > 0 && newCount < (articles || []).length };
}

// "9:40 AM" in the reader's locale, for "SINCE YOU LOOKED · 9:40 AM".
export function clockTime(isoString) {
  if (!isoString) return "";
  return new Date(isoString).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

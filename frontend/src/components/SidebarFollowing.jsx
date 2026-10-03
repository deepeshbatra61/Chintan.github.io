import React, { useEffect, useState } from "react";
import axios from "axios";
import { BellRing } from "lucide-react";
import { formatRelativeTime } from "../lib/time";

const API = "https://chintangithubio-production.up.railway.app/api";
const SHOWN = 2;

// Sidebar "Following" (design review 2026-10-03: the owner keeps the home feed
// uncluttered, so followed stories live here, not on the feed). Renders
// nothing until the reader follows something; the two most recently updated
// stories show, the rest expand inline.
export default function SidebarFollowing({ open, user, onOpenStory }) {
  const [data, setData] = useState(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!open || !user) return;
    let alive = true;
    axios.get(`${API}/follows`, { withCredentials: true })
      .then((r) => { if (alive) setData(r.data); })
      .catch(() => { /* hidden on error; next open retries */ });
    return () => { alive = false; };
  }, [open, user]);

  const follows = data?.follows || [];
  if (!user || follows.length === 0) return null;
  const shown = expanded ? follows : follows.slice(0, SHOWN);

  return (
    <div data-testid="sidebar-following" style={{ marginTop: 6 }}>
      <div className="w-full flex items-center gap-3 px-3 py-3" style={{ minHeight: 48 }}>
        <BellRing className="w-[18px] h-[18px]" style={{ color: "var(--c-faint)", flexShrink: 0 }} aria-hidden="true" />
        <span style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontSize: "15px", fontWeight: 500, color: "var(--c-sub)" }}>
          Following
        </span>
        {data.new_total > 0 && (
          <span style={{ marginLeft: "auto", fontFamily: "'JetBrains Mono', monospace", fontSize: "10.5px", letterSpacing: "0.06em", color: "var(--c-accent-ink)" }}>
            {data.new_total} NEW
          </span>
        )}
      </div>
      <ul style={{ listStyle: "none", margin: "-2px 0 4px 42px", padding: "0 0 0 12px", borderLeft: "1px solid rgb(var(--c-fg-rgb) / 0.08)" }}>
        {shown.map((f) => (
          <li key={f.story_id}>
            <button
              type="button"
              onClick={() => onOpenStory(f.story_id)}
              style={{ display: "block", width: "100%", textAlign: "left", background: "none", border: "none", cursor: "pointer", padding: "8px 0", minHeight: 44 }}
              data-testid={`following-${f.story_id}`}
            >
              <span style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden", color: "var(--c-ink2)", fontSize: "13px", lineHeight: 1.3 }}>
                {f.title}
              </span>
              <span style={{ display: "block", marginTop: 2, fontFamily: "'JetBrains Mono', monospace", fontSize: "10px", color: f.new_count > 0 ? "var(--c-accent-ink)" : "var(--c-muted)" }}>
                {f.new_count > 0 ? `${f.new_count} new · ` : "updated "}{f.last_updated ? formatRelativeTime(f.last_updated) : ""}
              </span>
            </button>
          </li>
        ))}
        {follows.length > SHOWN && (
          <li>
            <button
              type="button"
              onClick={() => setExpanded(!expanded)}
              aria-expanded={expanded}
              style={{ background: "none", border: "none", cursor: "pointer", padding: "8px 0", minHeight: 44, color: "var(--c-muted)", fontSize: "12.5px" }}
            >
              {expanded ? "Show fewer" : `See all ${follows.length} ›`}
            </button>
          </li>
        )}
      </ul>
    </div>
  );
}

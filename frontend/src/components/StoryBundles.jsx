import React, { useState } from "react";
import { ChevronDown } from "lucide-react";
import { formatRelativeTime } from "../lib/time";

/** The rest of a Developing story's coverage, folded away (owner, 2026-10-09):
 * the timeline above is developments only; tributes, reactions, explainers
 * and analysis sit here, one tap each. Shown only when the server sends them. */
export default function StoryBundles({ bundles, onOpen }) {
  const [open, setOpen] = useState(null);
  if (!bundles || bundles.length === 0) return null;
  return (
    <section aria-label="More coverage" style={{ marginTop: 8 }} data-testid="story-bundles">
      {bundles.map((b) => {
        const isOpen = open === b.kind;
        return (
          <div key={b.kind} style={{ marginBottom: 10, borderRadius: 14, background: "var(--c-surface)",
            border: "1px solid rgb(var(--c-fg-rgb) / 0.06)", overflow: "hidden" }}>
            <button type="button" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : b.kind)}
              data-testid={`bundle-${b.kind}`}
              style={{ width: "100%", minHeight: 52, display: "flex", alignItems: "center", justifyContent: "space-between",
                gap: 10, padding: "12px 14px", background: "none", border: "none", cursor: "pointer", textAlign: "left" }}>
              <span>
                <span style={{ display: "block", fontSize: 14, fontWeight: 500, color: "var(--c-ink2)" }}>{b.label}</span>
                <span style={{ display: "block", fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: "var(--c-faint)", marginTop: 2 }}>
                  {b.count} {b.count === 1 ? "story" : "stories"}
                </span>
              </span>
              <ChevronDown className="w-4 h-4" aria-hidden="true"
                style={{ color: "var(--c-muted)", transform: isOpen ? "rotate(180deg)" : "none", transition: "transform .2s" }} />
            </button>
            {isOpen && (
              <ul style={{ listStyle: "none", margin: 0, padding: "0 14px 6px" }}>
                {b.items.map((a) => (
                  <li key={a.article_id}>
                    <button type="button" onClick={() => onOpen(a)} data-testid={`bundle-item-${a.article_id}`}
                      style={{ width: "100%", textAlign: "left", background: "none", border: "none", cursor: "pointer",
                        padding: "10px 0", borderTop: "1px solid rgb(var(--c-fg-rgb) / 0.06)" }}>
                      <span style={{ display: "block", fontSize: 13.5, lineHeight: 1.36, color: "var(--c-sub)" }}>{a.title}</span>
                      <span style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontFamily: "'JetBrains Mono', monospace",
                        fontSize: 10, color: "var(--c-faint)" }}>
                        <span>{a.source}</span><span>{formatRelativeTime(a.published_at)}</span>
                      </span>
                    </button>
                  </li>
                ))}
                {b.count > b.items.length && (
                  <li style={{ fontSize: 12, color: "var(--c-faint)", padding: "6px 0 8px" }}>
                    Showing the latest {b.items.length}.
                  </li>
                )}
              </ul>
            )}
          </div>
        );
      })}
    </section>
  );
}

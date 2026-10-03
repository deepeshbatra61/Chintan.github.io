import React, { useEffect, useState } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "./ui/sheet";
import { formatRelativeTime } from "../lib/time";

const API = "https://chintangithubio-production.up.railway.app/api";

// News v2 coverage (design review 2026-10-03, direction B). Outlet circles and
// the mix bar are tinted by outlet TYPE, never by brand, and never logos (5A).
// Text colour per tint is picked for contrast in both themes.
export const GROUPS = ["national", "regional", "wire", "international", "other"];
export const GROUP_LABEL = { national: "National", regional: "Regional", wire: "Wire", international: "International", other: "Other" };
const TINT = {
  national: { bg: "var(--c-ink)", fg: "var(--c-bg)" },
  regional: { bg: "var(--c-accent-soft)", fg: "var(--c-bg)" },
  wire: { bg: "var(--c-dim)", fg: "var(--c-ink)" },
  international: { bg: "var(--c-muted)", fg: "var(--c-bg)" },
  other: { bg: "var(--c-faint)", fg: "var(--c-bg)" },
};

export function OutletDot({ initials, group, size = 18, ring = "var(--c-surface)" }) {
  const t = TINT[group] || TINT.other;
  return (
    <span aria-hidden="true" style={{
      width: size, height: size, borderRadius: "50%", display: "inline-grid", placeItems: "center",
      background: t.bg, color: t.fg, border: `2px solid ${ring}`, fontFamily: "'Manrope', sans-serif",
      fontWeight: 600, fontSize: size <= 18 ? 7.5 : 10, letterSpacing: "0.02em", flexShrink: 0,
    }}>{initials}</span>
  );
}

export function mixSentence(count, mix) {
  const parts = GROUPS.filter((g) => mix?.[g]).map((g) => `${mix[g]} ${g}`);
  return `${count} outlets${parts.length ? `: ${parts.join(", ")}` : ""}`;
}

function MixBar({ mix }) {
  const total = GROUPS.reduce((n, g) => n + (mix?.[g] || 0), 0);
  if (!total) return null;
  return (
    <span aria-hidden="true" style={{ display: "flex", gap: 2, width: 64, height: 4, flexShrink: 0 }}>
      {GROUPS.filter((g) => mix[g]).map((g) => (
        <span key={g} style={{ flex: mix[g], background: (TINT[g] || TINT.other).bg, borderRadius: 1 }} />
      ))}
    </span>
  );
}

/** Card footer for an event card. Falls back to today's footer when the
 * server sends no coverage (events not live yet, or an old server). */
export function CoverageStrip({ article, onOpen }) {
  const count = article.outlets_count || 0;
  const strip = article.outlet_strip || [];
  if (count < 2 || strip.length === 0) {
    return count === 1
      ? <span className="font-mono">{article.source} · 1 outlet</span>
      : <span className="font-mono">{article.source}</span>;
  }
  const label = `${mixSentence(count, article.coverage_mix)}. Show coverage`;
  return (
    <button
      type="button"
      aria-label={label}
      onClick={(e) => { e.stopPropagation(); onOpen(article); }}
      onPointerDown={(e) => e.stopPropagation()}
      onTouchStart={(e) => e.stopPropagation()}
      onMouseDown={(e) => e.stopPropagation()}
      data-testid={`coverage-strip-${article.article_id}`}
      style={{
        display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", minHeight: 44, margin: "-10px 0",
        padding: "10px 0", background: "none", border: "none", cursor: "pointer", color: "var(--c-sub)", textAlign: "left",
      }}
    >
      <span style={{ display: "flex" }}>
        {strip.map((o, i) => (
          <span key={i} style={{ marginLeft: i ? -6 : 0 }}><OutletDot initials={o.i} group={o.g} /></span>
        ))}
      </span>
      <span className="font-mono" style={{ fontSize: 11 }}>{strip[0].n} +{count - 1}</span>
      <MixBar mix={article.coverage_mix} />
    </button>
  );
}

/** Bottom sheet listing every outlet covering an event, grouped by type. */
export function CoverageSheet({ article, onClose }) {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const eventId = article?.event_id;

  const load = React.useCallback(() => {
    if (!eventId) return;
    setFailed(false); setData(null);
    axios.get(`${API}/events/${eventId}/coverage`)
      .then((r) => setData(r.data))
      .catch(() => setFailed(true));
  }, [eventId]);
  useEffect(() => { load(); }, [load]);

  const go = (path) => { onClose(); navigate(path); };
  const row = { display: "flex", alignItems: "center", gap: 12, width: "100%", minHeight: 56, padding: "10px 0",
    background: "none", border: "none", textAlign: "left", cursor: "pointer" };

  return (
    <Sheet open={!!article} onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent side="bottom" className="max-h-[80vh] overflow-y-auto" style={{ background: "var(--c-surface)", borderTopLeftRadius: 20, borderTopRightRadius: 20 }}>
        <SheetTitle style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontSize: 18, lineHeight: 1.3, color: "var(--c-ink)", paddingRight: 24 }}>
          {article?.title}
        </SheetTitle>
        <SheetDescription style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: "var(--c-muted)" }}>
          {data ? mixSentence(data.outlets_count, Object.fromEntries(data.groups.map((g) => [g.group, g.outlets.length])))
            : article ? mixSentence(article.outlets_count || 0, article.coverage_mix) : ""}
        </SheetDescription>

        {data?.developing && (
          <button type="button" style={{ ...row, borderBottom: "1px solid rgb(var(--c-fg-rgb) / 0.08)" }}
            onClick={() => go(`/developing/${eventId}`)} data-testid="coverage-open-story">
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#DC2626", flexShrink: 0, marginLeft: 6 }} />
            <span style={{ flex: 1, color: "var(--c-ink2)", fontSize: 14, fontWeight: 500 }}>Open the story</span>
            <ChevronRight className="w-4 h-4" style={{ color: "var(--c-muted)" }} aria-hidden="true" />
          </button>
        )}

        {failed ? (
          <button type="button" onClick={load} style={{ ...row, justifyContent: "center", color: "var(--c-muted)", fontSize: 14 }}>
            Couldn&rsquo;t load outlets · <span style={{ textDecoration: "underline", marginLeft: 4 }}>Retry</span>
          </button>
        ) : !data ? (
          <div aria-busy="true" style={{ padding: "8px 0" }}>
            {[0, 1, 2].map((i) => <div key={i} style={{ height: 44, margin: "8px 0", borderRadius: 10, background: "rgb(var(--c-fg-rgb) / 0.05)" }} />)}
          </div>
        ) : data.outlets_count <= 1 ? (
          <p style={{ color: "var(--c-muted)", fontSize: 14, padding: "12px 0" }}>
            Only {data.groups[0]?.outlets[0]?.outlet || "one outlet"} so far.
          </p>
        ) : data.groups.map((g) => (
          <section key={g.group} aria-label={GROUP_LABEL[g.group]} style={{ marginTop: 12 }}>
            <h3 style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--c-faint)", margin: "0 0 2px" }}>
              {GROUP_LABEL[g.group]}
            </h3>
            {g.outlets.map((o) => (
              <button key={o.article_id} type="button" style={row} onClick={() => go(`/article/${o.article_id}`)}>
                <OutletDot initials={o.initials || (o.outlet || "?").slice(0, 2).toUpperCase()} group={g.group} size={28} ring="transparent" />
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ display: "block", fontFamily: "'JetBrains Mono', monospace", fontSize: 10.5, color: "var(--c-muted)" }}>
                    {o.outlet} · {formatRelativeTime(o.published_at)}
                  </span>
                  <span style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden", color: "var(--c-ink2)", fontSize: 14, lineHeight: 1.35 }}>
                    {o.title}
                  </span>
                </span>
              </button>
            ))}
          </section>
        ))}
      </SheetContent>
    </Sheet>
  );
}

import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { motion, useReducedMotion } from "framer-motion";
import { ChevronLeft, ExternalLink, Share2 } from "lucide-react";
import { Browser } from "@capacitor/browser";
import { Share } from "@capacitor/share";
import { Seal, KindVisual } from "../components/bureau/BureauArt";
import {
  BUREAU_LABEL, getBureauItem, KIND_LABEL, formatNumber, formatDelta, spokenNumber, visualFor,
  istTime, istDateLabel, domainOf,
} from "../lib/bureau";

const MONO = "'JetBrains Mono', monospace";
const SERIF = "'Playfair Display', 'Georgia', serif";

async function openSource(url) {
  if (!url) return;
  if (window.Capacitor?.isNativePlatform()) {
    try { await Browser.open({ url }); return; } catch { /* fall through */ }
  }
  window.open(url, "_blank", "noopener,noreferrer");
}

function Section({ title, children }) {
  return (
    <section style={{ marginTop: 26 }}>
      <h2 style={{ fontFamily: MONO, fontWeight: 500, fontSize: 10.5, letterSpacing: "0.14em", textTransform: "uppercase",
        color: "var(--c-muted)", margin: "0 0 10px" }}>{title}</h2>
      {children}
    </section>
  );
}

function Tile({ big, small }) {
  return (
    <div style={{ background: "var(--c-surface)", border: "1px solid rgb(var(--c-fg-rgb) / 0.08)", borderRadius: 12, padding: "10px 11px",
      overflowWrap: "anywhere" }}>
      <b style={{ display: "block", fontFamily: SERIF, fontWeight: 700, fontSize: 17, color: "var(--c-ink)", lineHeight: 1.2 }}>{big}</b>
      <span style={{ fontSize: 11.5, color: "var(--c-muted)" }}>{small}</span>
    </div>
  );
}

/** Direction A: the number, one plain line, tiles, the comparison, who it
 * hits, earlier steps, then the official text. Original + Share pinned below. */
export default function BureauItemPage() {
  const { officialId } = useParams();
  const navigate = useNavigate();
  const R = useReducedMotion();
  const [item, setItem] = useState(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let alive = true;
    setError(false);
    getBureauItem(officialId)
      .then((d) => { if (alive) setItem(d); })
      .catch(() => { if (alive) setError(true); });
    return () => { alive = false; };
  }, [officialId, attempt]);

  const back = () => (window.history.length > 1 ? navigate(-1) : navigate("/feed"));

  const share = async () => {
    if (!item) return;
    try {
      await Share.share({
        title: item.what_changed,
        text: `${item.issuer}: ${item.what_changed}\n\nOfficial text: ${item.source_url}\n\nvia Chintan · ${BUREAU_LABEL}`,
        dialogTitle: "Share this announcement",
      });
    } catch { /* dismissed */ }
  };

  const header = (
    <header style={{ position: "sticky", top: 0, zIndex: 40, paddingTop: "var(--sat)", paddingBottom: 8, paddingLeft: 8,
      paddingRight: 16, background: "rgb(var(--c-chrome-rgb) / 0.6)", backdropFilter: "blur(12px)", display: "flex",
      alignItems: "center" }}>
      <button type="button" onClick={back} data-testid="bureau-back"
        style={{ display: "inline-flex", alignItems: "center", gap: 2, minHeight: 44, padding: "0 8px", background: "none",
          border: "none", color: "var(--c-muted)", fontSize: 14, cursor: "pointer" }}>
        <ChevronLeft className="w-5 h-5" aria-hidden="true" />{BUREAU_LABEL}
      </button>
    </header>
  );

  if (error && !item) {
    return (
      <div style={{ minHeight: "100vh", background: "var(--c-bg)" }} data-testid="bureau-item-error">
        {header}
        <div style={{ padding: "64px 24px", textAlign: "center" }}>
          <p style={{ fontFamily: SERIF, fontSize: 18, color: "var(--c-ink2)", margin: "0 0 14px" }}>Couldn&rsquo;t load this announcement.</p>
          <button type="button" onClick={() => setAttempt((n) => n + 1)}
            style={{ minHeight: 44, padding: "0 18px", borderRadius: 999, border: "1px solid rgb(var(--c-fg-rgb) / 0.14)",
              background: "none", color: "var(--c-sub)", cursor: "pointer" }}>Try again</button>
        </div>
      </div>
    );
  }

  if (!item) {
    return (
      <div style={{ minHeight: "100vh", background: "var(--c-bg)" }} data-testid="bureau-item-loading">
        {header}
        <div className="animate-pulse" aria-hidden="true" style={{ padding: "20px 16px", maxWidth: 640, margin: "0 auto" }}>
          <div style={{ width: "40%", height: 10, borderRadius: 4, background: "rgb(var(--c-fg-rgb) / 0.08)" }} />
          <div style={{ width: "35%", height: 40, borderRadius: 8, background: "rgb(var(--c-fg-rgb) / 0.08)", marginTop: 20 }} />
          <div style={{ width: "92%", height: 22, borderRadius: 6, background: "rgb(var(--c-fg-rgb) / 0.08)", marginTop: 16 }} />
          <div style={{ width: "75%", height: 22, borderRadius: 6, background: "rgb(var(--c-fg-rgb) / 0.08)", marginTop: 8 }} />
        </div>
      </div>
    );
  }

  const number = formatNumber(item.key_number);
  const delta = formatDelta(item.key_number);
  const dates = (item.dates || []).filter((d) => d && d.date);
  const tiles = [
    ...(number ? [{ big: number, small: item.key_number?.label || "key number" }] : []),
    ...dates.map((d) => ({ big: d.date, small: d.label || "date" })),
  ].slice(0, 3);
  const useTiles = tiles.length > 1;          // otherwise dates get their own list
  const issuer = item.issuer_key === "pib" && item.ministry ? item.ministry : item.issuer;
  const domain = domainOf(item.source_url);
  const timeline = [{ official_id: item.official_id, what_changed: item.what_changed, published_at: item.published_at, now: true },
    ...(item.earlier || [])];

  return (
    <div style={{ minHeight: "100vh", background: "var(--c-bg)" }} data-testid="bureau-item">
      {header}
      <motion.main
        initial={R ? false : { opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
        style={{ maxWidth: 640, margin: "0 auto", padding: "10px 16px calc(110px + var(--sab))" }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
          <p style={{ display: "inline-flex", alignItems: "center", gap: 6, margin: 0, fontSize: 12, fontWeight: 600,
            letterSpacing: "0.03em", color: "var(--c-accent-ink)" }}>
            <Seal size={12} />
            {[issuer, KIND_LABEL[item.kind] || item.kind, `${istDateLabel(item.published_at)}, ${istTime(item.published_at)}`].filter(Boolean).join(" · ")}
          </p>
          <KindVisual kind={visualFor(item)} width={64} />
        </div>

        {number && (
          <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap", marginTop: 10 }}
            role="text" aria-label={spokenNumber(item.key_number)} data-testid="bureau-number">
            <b style={{ fontFamily: SERIF, fontWeight: 700, fontSize: number.length > 9 ? 36 : 46, lineHeight: 1,
              letterSpacing: "-0.02em", color: "var(--c-ink)" }}>{number}</b>
            {delta && <span style={{ fontSize: 14, fontWeight: 600, color: "var(--c-sub)" }}>{delta.arrow} {delta.text}</span>}
          </div>
        )}

        <h1 style={{ fontFamily: SERIF, fontWeight: 700, fontSize: 24, lineHeight: 1.22, color: "var(--c-ink)",
          margin: "12px 0 12px", textWrap: "balance" }}>{item.what_changed}</h1>

        {(item.facts || []).length > 0 && (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 6 }}>
            {item.facts.slice(0, 3).map((f) => (
              <span key={f} style={{ fontSize: 12.5, color: "var(--c-ink2)", background: "rgb(var(--c-fg-rgb) / 0.06)",
                borderRadius: 8, padding: "5px 9px" }}>{f}</span>
            ))}
          </div>
        )}

        {item.title_only ? (
          <p style={{ fontSize: 16, lineHeight: 1.6, color: "var(--c-sub)", margin: "14px 0 0" }} data-testid="bureau-title-only">
            Summary coming soon. This one came as a scanned document, so for now the details are in the official text below.
          </p>
        ) : item.summary ? (
          <p style={{ fontSize: 16, lineHeight: 1.65, color: "var(--c-ink2)", margin: "14px 0 0", maxWidth: "68ch", textWrap: "pretty" }}>
            {item.summary}
          </p>
        ) : null}

        {useTiles && (
          <div style={{ display: "grid", gridTemplateColumns: `repeat(${tiles.length}, minmax(0, 1fr))`, gap: 8, marginTop: 18 }}>
            {tiles.map((t) => <Tile key={`${t.big}-${t.small}`} {...t} />)}
          </div>
        )}

        {(item.analogy || "").trim() && (
          <Section title="Think of it like">
            <p style={{ margin: 0, padding: "13px 14px", borderRadius: 14, background: "rgba(220,38,38,0.07)",
              border: "1px solid rgba(220,38,38,0.22)", fontFamily: SERIF, fontStyle: "italic", fontSize: 17, lineHeight: 1.5,
              color: "var(--c-ink2)" }}>{item.analogy}</p>
          </Section>
        )}

        {((item.who || []).length > 0 || (item.sectors || []).length > 0) && (
          <Section title="Who it affects">
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {[...(item.who || []), ...(item.sectors || [])].filter((v, i, a) => a.indexOf(v) === i).map((w) => (
                <span key={w} style={{ fontSize: 13, padding: "7px 11px", borderRadius: 999, border: "1px solid rgb(var(--c-fg-rgb) / 0.10)",
                  color: "var(--c-ink2)" }}>{w}</span>
              ))}
            </div>
          </Section>
        )}

        {!useTiles && dates.length > 0 && (
          <Section title="Key dates">
            {dates.map((d) => (
              <div key={`${d.label}-${d.date}`} style={{ display: "flex", justifyContent: "space-between", gap: 12, padding: "11px 12px",
                marginBottom: 6, borderRadius: 12, background: "var(--c-surface)", border: "1px solid rgb(var(--c-fg-rgb) / 0.08)",
                fontSize: 14 }}>
                <span style={{ color: "var(--c-muted)", textTransform: "capitalize" }}>{d.label || "Date"}</span>
                <b style={{ color: "var(--c-ink)", fontWeight: 600 }}>{d.date}</b>
              </div>
            ))}
          </Section>
        )}

        {timeline.length > 1 && (
          <Section title="Earlier on this">
            <ol style={{ listStyle: "none", margin: 0, padding: "0 0 0 18px", position: "relative" }} data-testid="bureau-earlier">
              <span aria-hidden="true" style={{ position: "absolute", left: 4, top: 8, bottom: 8, width: 1, background: "rgba(220,38,38,0.35)" }} />
              {timeline.map((t) => (
                <li key={t.official_id} style={{ position: "relative", marginBottom: 12 }}>
                  <span aria-hidden="true" style={{ position: "absolute", left: -18, top: 5, width: 9, height: 9, borderRadius: "50%",
                    border: "1.5px solid var(--c-accent-ink)", background: t.now ? "var(--c-accent-ink)" : "var(--c-bg)" }} />
                  {t.now ? (
                    <p style={{ margin: 0, fontSize: 14, color: "var(--c-ink)", lineHeight: 1.4 }}>{t.what_changed}</p>
                  ) : (
                    <button type="button" onClick={() => navigate(`/bureau/${encodeURIComponent(t.official_id)}`)}
                      style={{ background: "none", border: "none", padding: 0, textAlign: "left", cursor: "pointer", fontSize: 14,
                        color: "var(--c-sub)", lineHeight: 1.4, minHeight: 24 }}>
                      {t.what_changed || t.title}
                    </button>
                  )}
                  <small style={{ display: "block", fontFamily: MONO, fontSize: 10.5, color: "var(--c-muted)", marginTop: 2 }}>
                    {t.now ? "This announcement" : istDateLabel(t.published_at)}
                  </small>
                </li>
              ))}
            </ol>
          </Section>
        )}

        <Section title="The official text">
          <p style={{ margin: 0, fontSize: 14, lineHeight: 1.5, color: "var(--c-sub)" }}>{item.title}</p>
          <p style={{ margin: "6px 0 0", fontSize: 12.5, color: "var(--c-muted)" }}>
            Summarised by Chintan from {item.source_name || item.issuer}. Chintan is not a government body; the original is the final word.
          </p>
        </Section>
      </motion.main>

      <div style={{ position: "fixed", left: 0, right: 0, bottom: 0, zIndex: 40, padding: "14px 16px calc(14px + var(--sab))",
        background: "linear-gradient(to top, var(--c-bg) 72%, transparent)" }}>
        <div style={{ maxWidth: 640, margin: "0 auto", display: "flex", gap: 8 }}>
          <button type="button" onClick={() => openSource(item.source_url)} data-testid="bureau-original"
            style={{ flex: 1, minHeight: 48, borderRadius: 999, border: "none", cursor: "pointer", fontWeight: 600, fontSize: 14,
              color: "#fff", background: "linear-gradient(180deg, #DC2626, #B91C1C)", display: "inline-flex", alignItems: "center",
              justifyContent: "center", gap: 6 }}>
            Original{domain ? ` · ${domain}` : ""} <ExternalLink className="w-4 h-4" aria-hidden="true" />
          </button>
          <button type="button" onClick={share} aria-label="Share" data-testid="bureau-share"
            style={{ width: 48, minHeight: 48, borderRadius: 999, border: "1px solid rgb(var(--c-fg-rgb) / 0.14)", background: "var(--c-surface)",
              color: "var(--c-ink2)", cursor: "pointer", display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
            <Share2 className="w-[18px] h-[18px]" aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>
  );
}

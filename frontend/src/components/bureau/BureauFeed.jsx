import React, { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { Pill } from "../SubFilters";
import { Seal, KindVisual } from "./BureauArt";
import {
  LENSES, BUREAU_TAGLINE, lensOf, bureauKey, getBureauFeed, groupByDay, istTime, isWeekendIST,
  KIND_LABEL, formatNumber, formatDelta, spokenNumber, visualFor, facesOf,
} from "../../lib/bureau";

const MONO = "'JetBrains Mono', monospace";
const SERIF = "'Playfair Display', 'Georgia', serif";
const PAGE = 20;

// Per-lens memory for this app session: coming back from an item restores the
// same cards and scroll instead of reloading (same rule as the main feed).
const memo = {};
export const clearBureauMemo = () => { for (const k of Object.keys(memo)) delete memo[k]; };

const FACE_NAME = { what: "What changed", who: "What it means for you", like: "Think of it like" };

function issuerLine(item) {
  const who = item.issuer_key === "pib" && item.ministry ? item.ministry.replace(/^Ministry of /, "") : item.issuer;
  return [who, KIND_LABEL[item.kind] || item.kind, istTime(item.published_at)].filter(Boolean).join(" · ");
}

function Kicker({ children, style }) {
  return (
    <p style={{ fontFamily: MONO, fontSize: 10, letterSpacing: "0.14em", textTransform: "uppercase",
      color: "var(--c-accent-ink)", margin: 0, ...style }}>{children}</p>
  );
}

function Chips({ items }) {
  if (!items.length) return null;
  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
      {items.map((t) => (
        <span key={t} style={{ fontSize: 12, color: "var(--c-ink2)", background: "rgb(var(--c-fg-rgb) / 0.06)",
          borderRadius: 8, padding: "4px 8px", lineHeight: 1.35 }}>{t}</span>
      ))}
    </div>
  );
}

/** Direction C, "The Flashcard": a big card per announcement. Swipe (or tap
 * the bars) for what it means for you and an everyday comparison; tap the
 * card to open the full page. */
export function Flashcard({ item, showHint, onOpen }) {
  const R = useReducedMotion();
  const faces = facesOf(item);
  const [face, setFace] = useState(0);
  const dragged = useRef(false);
  const number = formatNumber(item.key_number);
  const delta = formatDelta(item.key_number);
  const go = (i) => setFace(Math.max(0, Math.min(faces.length - 1, i)));
  const current = faces[face];

  return (
    <motion.article
      role="link" tabIndex={0}
      layout={R ? false : "size"}
      aria-label={`${item.issuer}: ${item.what_changed}`}
      onClick={() => { if (!dragged.current) onOpen(item); }}
      onKeyDown={(e) => { if (e.key === "Enter") onOpen(item); }}
      initial={R ? false : { opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1], layout: { duration: 0.25, ease: [0.16, 1, 0.3, 1] } }}
      whileTap={R ? undefined : { scale: 0.985 }}
      data-testid={`bureau-card-${item.official_id}`}
      style={{
        position: "relative", overflow: "hidden", cursor: "pointer", borderRadius: 22, padding: "18px 18px 12px",
        background: "radial-gradient(120% 90% at 100% 0%, rgba(220,38,38,0.13), transparent 55%), var(--c-surface)",
        border: "1px solid rgba(220,38,38,0.22)",
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontFamily: "'Manrope', sans-serif",
          fontSize: 11, fontWeight: 600, letterSpacing: "0.04em", color: "var(--c-accent-ink)", textTransform: "uppercase",
          paddingTop: 2 }}>
          <Seal size={11} />{issuerLine(item)}
        </span>
        <KindVisual kind={visualFor(item)} width={number ? 58 : 74} />
      </div>
      {item.needs_desk && (
        <span data-testid="desk-flag" style={{ display: "inline-block", marginTop: 6, fontFamily: MONO, fontSize: 9.5,
          letterSpacing: "0.12em", color: "var(--c-warn-ink)", border: "1px solid currentColor", borderRadius: 6,
          padding: "1px 6px" }}>DESK CHECK</span>
      )}

      <motion.div
        drag={faces.length > 1 ? "x" : false} dragDirectionLock dragConstraints={{ left: 0, right: 0 }} dragElastic={0.18}
        onDragStart={() => { dragged.current = true; }}
        onDragEnd={(e, info) => {
          if (info.offset.x < -45) go(face + 1);
          else if (info.offset.x > 45) go(face - 1);
          setTimeout(() => { dragged.current = false; }, 0);
        }}
        style={{ touchAction: "pan-y" }}
      >
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={current}
            initial={R ? { opacity: 0 } : { opacity: 0, x: 18 }} animate={{ opacity: 1, x: 0 }}
            exit={R ? { opacity: 0 } : { opacity: 0, x: -18 }} transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
            aria-live="polite"
          >
            {current === "what" && (
              <>
                {number && (
                  <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap", margin: "8px 0 2px" }}
                    aria-label={spokenNumber(item.key_number)} role="text">
                    <b style={{ fontFamily: SERIF, fontWeight: 700, fontSize: number.length > 9 ? 30 : 38, lineHeight: 1,
                      letterSpacing: "-0.02em", color: "var(--c-ink)" }}>{number}</b>
                    {delta && <span style={{ fontSize: 13, fontWeight: 600, color: "var(--c-sub)" }}>{delta.arrow} {delta.text}</span>}
                    {item.key_number?.label && <span style={{ fontSize: 12.5, color: "var(--c-muted)" }}>{item.key_number.label}</span>}
                  </div>
                )}
                <p style={{ fontFamily: SERIF, fontWeight: 600, fontSize: 20, lineHeight: 1.25, color: "var(--c-ink)",
                  margin: "10px 0 12px", textWrap: "pretty" }}>{item.what_changed}</p>
                {item.title_only
                  ? <p style={{ fontSize: 12.5, color: "var(--c-muted)", margin: 0 }}>Summary coming soon. The official text is one tap away.</p>
                  : <Chips items={(item.facts || []).slice(0, 3)} />}
              </>
            )}
            {current === "who" && (
              <div style={{ paddingTop: 12 }}>
                <Kicker style={{ marginBottom: 10 }}>What it means for you</Kicker>
                <Chips items={item.who || []} />
                {(item.sectors || []).length > 0 && (
                  <p style={{ fontSize: 13, color: "var(--c-sub)", margin: "12px 0 0" }}>
                    Sectors: {item.sectors.join(", ")}
                  </p>
                )}
              </div>
            )}
            {current === "like" && (
              <div style={{ paddingTop: 12 }}>
                <Kicker style={{ marginBottom: 8 }}>Think of it like</Kicker>
                <p style={{ fontFamily: SERIF, fontStyle: "italic", fontSize: 18, lineHeight: 1.45, color: "var(--c-ink2)",
                  margin: 0 }}>{item.analogy}</p>
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </motion.div>

      {faces.length > 1 && (
        <div style={{ display: "flex", gap: 4, marginTop: 6 }} role="group" aria-label="Card pages">
          {faces.map((f, i) => (
            <button key={f} type="button" aria-label={`${i + 1} of ${faces.length}: ${FACE_NAME[f]}`} aria-pressed={i === face}
              onClick={(e) => { e.stopPropagation(); go(i); }}
              style={{ flex: 1, minHeight: 24, padding: "10px 0", background: "none", border: "none", cursor: "pointer" }}>
              <span style={{ display: "block", height: 3, borderRadius: 2,
                background: i === face ? "var(--c-accent-ink)" : "rgb(var(--c-fg-rgb) / 0.14)", transition: "background .2s" }} />
            </button>
          ))}
        </div>
      )}
      {showHint && faces.length > 1 && face === 0 && (
        <p style={{ fontSize: 11.5, color: "var(--c-muted)", margin: "0 0 2px" }}>Swipe → what it means for you</p>
      )}
    </motion.article>
  );
}

function Shimmer() {
  return (
    <div aria-hidden="true" className="animate-pulse" style={{ borderRadius: 22, padding: 18, background: "var(--c-surface)",
      border: "1px solid rgb(var(--c-fg-rgb) / 0.06)" }}>
      <div style={{ width: "45%", height: 10, borderRadius: 4, background: "rgb(var(--c-fg-rgb) / 0.08)" }} />
      <div style={{ width: "90%", height: 18, borderRadius: 6, background: "rgb(var(--c-fg-rgb) / 0.08)", marginTop: 22 }} />
      <div style={{ width: "70%", height: 18, borderRadius: 6, background: "rgb(var(--c-fg-rgb) / 0.08)", marginTop: 8 }} />
      <div style={{ width: "55%", height: 12, borderRadius: 6, background: "rgb(var(--c-fg-rgb) / 0.06)", marginTop: 18 }} />
    </div>
  );
}

function DayDivider({ label, count }) {
  return (
    <h2 style={{ display: "flex", alignItems: "center", gap: 8, fontFamily: MONO, fontWeight: 500, fontSize: 10.5,
      letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--c-muted)", margin: "6px 0 10px" }}>
      {label} · {count} announcement{count === 1 ? "" : "s"}
      <span aria-hidden="true" style={{ flex: 1, height: 1, background: "rgb(var(--c-fg-rgb) / 0.08)" }} />
    </h2>
  );
}

/** Everything under the chip: tagline, issuer pills, cards by day. */
export default function BureauFeed({ filterKey, onFilterChange, refreshTick = 0 }) {
  const navigate = useNavigate();
  const lens = lensOf(filterKey);
  const [state, setState] = useState(() => memo[lens] || null);
  const [loading, setLoading] = useState(!memo[lens]);
  const [error, setError] = useState(false);
  const [more, setMore] = useState(false);
  const sentinel = useRef(null);
  const seq = useRef(0);

  const load = useCallback(async (append = false) => {
    const mine = append ? seq.current : ++seq.current;
    const before = append ? state?.items?.[state.items.length - 1]?.published_at : null;
    if (append) setMore(true); else if (!memo[lens]) setLoading(true);
    try {
      const data = await getBureauFeed({ lens, before, limit: PAGE });
      if (mine !== seq.current) return;
      const next = append ? { ...data, items: [...(state?.items || []), ...data.items], today_count: state.today_count } : data;
      memo[lens] = next;
      setState(next);
      setError(false);
    } catch {
      if (mine === seq.current) setError(true);
    } finally {
      if (mine === seq.current) { setLoading(false); setMore(false); }
    }
  }, [lens, state]);

  // A new lens (or first open) loads; coming back uses the memo.
  useEffect(() => {
    if (memo[lens]) { setState(memo[lens]); setLoading(false); return; }
    setState(null);
    load(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lens]);

  // Pull-to-refresh / Feed tab on the feed page.
  useEffect(() => {
    if (!refreshTick) return;
    delete memo[lens];
    load(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshTick]);

  useEffect(() => {
    const el = sentinel.current;
    if (!el || !state?.has_more || error) return undefined;
    const io = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting && !more) load(true);
    }, { rootMargin: "300px" });
    io.observe(el);
    return () => io.disconnect();
  }, [state, more, error, load]);

  const open = (item) => navigate(`/bureau/${encodeURIComponent(item.official_id)}`);
  const items = state?.items || [];
  const groups = groupByDay(items);
  const nothingToday = state && state.today_count === 0;
  const lensName = (LENSES.find(([k]) => k === lens) || [null, "All"])[1];

  return (
    <section aria-label="The Bureau" data-testid="bureau-feed">
      <p style={{ fontFamily: SERIF, fontStyle: "italic", fontSize: 14, color: "var(--c-sub)", margin: "-10px 0 4px" }}>
        {BUREAU_TAGLINE}
      </p>

      <div className="overflow-x-auto hide-scrollbar" style={{ margin: "0 0 8px" }}>
        <div role="list" aria-label="Who announced it" style={{ display: "flex", gap: 6 }}>
          {LENSES.map(([key, label]) => (
            <span role="listitem" key={key || "all"}>
              <Pill label={label} active={lens === key} onClick={() => onFilterChange(bureauKey(key))} testid={`bureau-lens-${key || "all"}`} />
            </span>
          ))}
        </div>
      </div>

      {state?.preview && (
        <p data-testid="bureau-preview" style={{ fontFamily: MONO, fontSize: 10.5, color: "var(--c-warn-ink)", margin: "0 0 12px",
          letterSpacing: "0.04em" }}>
          Preview · only Desk admins see The Bureau until it goes live
        </p>
      )}
      {(state?.delayed || []).length > 0 && (
        <p data-testid="bureau-delayed" style={{ fontSize: 13, color: "var(--c-muted)", margin: "0 0 12px" }}>
          {state.delayed.join(", ")} updates delayed. We&rsquo;re retrying.
        </p>
      )}

      {loading && !items.length && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="bureau-loading"><Shimmer /><Shimmer /><Shimmer /></div>
      )}

      {!loading && error && !items.length && (
        <div className="text-center py-16">
          <button type="button" onClick={() => load(false)} data-testid="bureau-retry"
            style={{ minHeight: 44, background: "none", border: "none", color: "var(--c-muted)", fontSize: 14, cursor: "pointer" }}>
            Couldn&rsquo;t load The Bureau. <span style={{ textDecoration: "underline", textUnderlineOffset: 2 }}>Try again</span>
          </button>
        </div>
      )}

      {!loading && !error && state && !items.length && (
        <p data-testid="bureau-empty" style={{ fontFamily: SERIF, fontSize: 18, color: "var(--c-ink2)", textAlign: "center", padding: "48px 12px" }}>
          {lens ? `Nothing from ${lensName} in the last three weeks.` : "No announcements in the last three weeks."}
        </p>
      )}

      {items.length > 0 && nothingToday && (
        <p data-testid="bureau-quiet" style={{ fontSize: 14, color: "var(--c-sub)", margin: "2px 0 14px", lineHeight: 1.5 }}>
          {isWeekendIST()
            ? "Government’s off for the weekend. Here’s what came before."
            : "No announcements yet today. Most land between 10 and 6."}
        </p>
      )}

      {groups.map(([label, dayItems], gi) => (
        <div key={label} style={{ marginBottom: 14 }}>
          <DayDivider label={label} count={label === "Today" ? state.today_count : dayItems.length} />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {dayItems.map((it, i) => (
              <Flashcard key={it.official_id} item={it} onOpen={open} showHint={gi === 0 && i === 0} />
            ))}
          </div>
        </div>
      ))}

      <div ref={sentinel} className="h-1" />
      {error && items.length > 0 && (
        <div className="flex justify-center py-6">
          <button type="button" onClick={() => load(true)}
            style={{ minHeight: 44, background: "none", border: "none", color: "var(--c-muted)", fontSize: 14, cursor: "pointer" }}>
            Couldn&rsquo;t load more. <span style={{ textDecoration: "underline" }}>Try again</span>
          </button>
        </div>
      )}
    </section>
  );
}

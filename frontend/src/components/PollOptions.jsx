import React, { useEffect, useState } from "react";
import { motion, useReducedMotion, animate } from "framer-motion";

const EASE = [0.16, 1, 0.3, 1]; // ease-out-expo, as the feed cards use

// Counts 0 → value when `play`, otherwise shows the value as is.
function CountUp({ value, play }) {
  const [n, setN] = useState(play ? 0 : value);
  useEffect(() => {
    if (!play) { setN(value); return undefined; }
    const c = animate(0, value, { duration: 0.7, ease: EASE, onUpdate: (v) => setN(Math.round(v)) });
    return () => c.stop();
  }, [value, play]);
  return <>{n}%</>;
}

// A check that draws itself in.
function Check({ play }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" style={{ flexShrink: 0 }}>
      <motion.circle cx="8" cy="8" r="7" fill="#DC2626"
        initial={play ? { scale: 0 } : false} animate={{ scale: 1 }}
        transition={{ type: "spring", stiffness: 500, damping: 22 }} style={{ originX: "50%", originY: "50%" }} />
      <motion.path d="M4.6 8.3 7 10.6l4.4-4.9" fill="none" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
        initial={play ? { pathLength: 0 } : false} animate={{ pathLength: 1 }}
        transition={{ delay: play ? 0.12 : 0, duration: 0.32, ease: EASE }} />
    </svg>
  );
}

/** Poll options. Before a vote: plain choices. The moment a vote lands
 * (`justVoted`): the chosen row pulses a soft ring, every result bar sweeps
 * in (staggered), percentages count up and a check draws in on your pick.
 * Reopening a poll you already voted in shows the same result, at rest. */
export default function PollOptions({ options, votes, myVote, justVoted, onVote }) {
  const R = useReducedMotion();
  const voted = !!myVote;
  const total = Object.values(votes || {}).reduce((a, b) => a + b, 0);
  const pct = (o) => (total ? Math.round(((votes || {})[o] || 0) / total * 100) : 0);
  const play = justVoted && !R;

  return (
    <div className="space-y-2" role={voted ? "list" : undefined}>
      {options.map((option, i) => {
        const mine = myVote === option;
        const p = pct(option);
        return (
          <motion.button
            key={option}
            type="button"
            onClick={() => onVote(option)}
            disabled={voted}
            aria-pressed={mine}
            whileTap={voted || R ? undefined : { scale: 0.97 }}
            className={`poll-option w-full text-left ${voted ? "cursor-default" : "hover:border-red-500"}`}
            style={mine ? { borderColor: "#DC2626", overflow: "hidden" } : { overflow: "hidden" }}
            data-testid={`poll-option-${option}`}
          >
            {voted && (
              <motion.div
                className="poll-bar"
                initial={play ? { width: 0 } : false}
                animate={{ width: `${p}%` }}
                transition={{ delay: play ? 0.08 + i * 0.07 : 0, duration: 0.8, ease: EASE }}
                style={{ background: mine ? "rgba(220,38,38,0.26)" : "rgb(var(--c-fg-rgb) / 0.08)", transition: "none" }}
              />
            )}
            {play && mine && (
              <motion.span
                aria-hidden="true"
                initial={{ opacity: 0.55, scale: 1 }}
                animate={{ opacity: 0, scale: 1.08 }}
                transition={{ duration: 0.7, ease: EASE }}
                style={{ position: "absolute", inset: -1, borderRadius: "0.75rem", border: "2px solid #DC2626", pointerEvents: "none" }}
              />
            )}
            <div className="relative flex items-center justify-between gap-3">
              <span className="flex items-center gap-2" style={{ color: mine ? "var(--c-ink)" : "var(--c-sub)", fontWeight: mine ? 600 : 400 }}>
                {mine && <Check play={play} />}
                {option}
              </span>
              {voted && (
                <span className="font-mono text-sm" style={{ color: mine ? "var(--c-accent-ink)" : "var(--c-muted)" }}>
                  <CountUp value={p} play={play} />
                </span>
              )}
            </div>
          </motion.button>
        );
      })}
      {voted ? (
        <motion.p
          className="text-xs text-center"
          style={{ color: "var(--c-muted)", paddingTop: 4 }}
          initial={play ? { opacity: 0, y: 4 } : false}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: play ? 0.45 : 0, duration: 0.35, ease: EASE }}
          data-testid="poll-voted-note"
        >
          {justVoted ? "Vote counted" : "You voted"} · {total} vote{total === 1 ? "" : "s"}
        </motion.p>
      ) : (
        <p className="text-xs text-center" style={{ color: "var(--c-muted)", paddingTop: 4 }}>
          Tap an option to vote · {total} vote{total === 1 ? "" : "s"} so far
        </p>
      )}
    </div>
  );
}

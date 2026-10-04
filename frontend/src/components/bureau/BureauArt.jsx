import React from "react";

/** The Bureau's seal: a ring and a dot. Deliberately NOT the national emblem,
 * so nothing here can be read as Chintan being a government body. */
export function Seal({ size = 12, style }) {
  return (
    <svg width={size} height={size} viewBox="0 0 12 12" aria-hidden="true" style={{ flexShrink: 0, ...style }}>
      <circle cx="6" cy="6" r="5" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="6" cy="6" r="2.2" fill="currentColor" />
    </svg>
  );
}

// One small line drawing per kind (design review): decoration only, so
// aria-hidden; the card's text carries the meaning.
const DRAWINGS = {
  dial: (
    <>
      <path d="M6 36a31 31 0 0 1 62 0" stroke="rgb(var(--c-fg-rgb) / 0.14)" strokeWidth="6" />
      <path d="M6 36a31 31 0 0 1 40-29" strokeWidth="6" />
      <line x1="37" y1="36" x2="46" y2="12" stroke="var(--c-ink)" strokeWidth="2.5" />
    </>
  ),
  crate: (
    <>
      <rect x="20" y="9" width="34" height="27" rx="4" strokeWidth="3" />
      <line x1="20" y1="19" x2="54" y2="19" strokeWidth="2" />
      <line x1="37" y1="9" x2="37" y2="36" strokeWidth="2" />
    </>
  ),
  scales: (
    <>
      <line x1="37" y1="6" x2="37" y2="35" strokeWidth="2.5" />
      <line x1="17" y1="12" x2="57" y2="12" strokeWidth="2.5" />
      <path d="M11 26l6-14 6 14z" strokeWidth="2" />
      <path d="M51 26l6-14 6 14z" strokeWidth="2" />
      <line x1="28" y1="35" x2="46" y2="35" strokeWidth="3" />
    </>
  ),
  calendar: (
    <>
      <rect x="21" y="9" width="32" height="27" rx="4" strokeWidth="2.5" />
      <line x1="21" y1="17" x2="53" y2="17" strokeWidth="2.5" />
      <line x1="29" y1="5" x2="29" y2="12" strokeWidth="2.5" />
      <line x1="45" y1="5" x2="45" y2="12" strokeWidth="2.5" />
      <circle cx="44" cy="27" r="2.4" fill="currentColor" stroke="none" />
    </>
  ),
  document: (
    <>
      <path d="M25 5h17l9 9v22H25z" strokeWidth="2.5" />
      <path d="M42 5v9h9" strokeWidth="2" />
      <line x1="30" y1="21" x2="46" y2="21" strokeWidth="2" />
      <line x1="30" y1="27" x2="42" y2="27" strokeWidth="2" />
    </>
  ),
  pillar: (
    <>
      <path d="M17 13l20-8 20 8z" strokeWidth="2.5" />
      <line x1="24" y1="16" x2="24" y2="31" strokeWidth="3" />
      <line x1="33" y1="16" x2="33" y2="31" strokeWidth="3" />
      <line x1="41" y1="16" x2="41" y2="31" strokeWidth="3" />
      <line x1="50" y1="16" x2="50" y2="31" strokeWidth="3" />
      <line x1="16" y1="35" x2="58" y2="35" strokeWidth="3" />
    </>
  ),
  bars: (
    <>
      <line x1="16" y1="36" x2="58" y2="36" stroke="rgb(var(--c-fg-rgb) / 0.2)" strokeWidth="2" />
      <line x1="23" y1="32" x2="23" y2="23" strokeWidth="6" />
      <line x1="33" y1="32" x2="33" y2="16" strokeWidth="6" />
      <line x1="43" y1="32" x2="43" y2="20" strokeWidth="6" />
      <line x1="53" y1="32" x2="53" y2="8" strokeWidth="6" />
    </>
  ),
};

export function KindVisual({ kind = "document", width = 74, style }) {
  return (
    <svg
      viewBox="0 0 74 40" width={width} height={(width * 40) / 74} aria-hidden="true" data-visual={kind}
      fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round"
      style={{ color: "var(--c-accent-ink)", flexShrink: 0, ...style }}
    >
      {DRAWINGS[kind] || DRAWINGS.document}
    </svg>
  );
}

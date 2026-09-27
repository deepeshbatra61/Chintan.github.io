import React from "react";
import { Monitor, Sun, Moon } from "lucide-react";
import { useTheme, setThemePref } from "../lib/theme";

const OPTIONS = [
  { value: "system", label: "System", Icon: Monitor },
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
];

// Segmented System / Light / Dark switch for the side nav. A radiogroup, not
// three buttons, so a screen reader announces it as one choice with a
// selected value.
export default function AppearanceControl() {
  const { pref } = useTheme();

  const onKeyDown = (e) => {
    const i = OPTIONS.findIndex((o) => o.value === pref);
    const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1
      : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = OPTIONS[(i + step + OPTIONS.length) % OPTIONS.length];
    setThemePref(next.value);
    e.currentTarget.querySelector(`[data-value="${next.value}"]`)?.focus();
  };

  return (
    <div>
      <p
        id="appearance-label"
        style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "9px", letterSpacing: "0.16em", textTransform: "uppercase", color: "var(--c-faint2)", margin: "0 0 8px 2px" }}
      >
        Appearance
      </p>
      <div
        role="radiogroup"
        aria-labelledby="appearance-label"
        onKeyDown={onKeyDown}
        style={{ display: "flex", gap: "2px", padding: "3px", borderRadius: "11px", background: "var(--c-surface2)", border: "1px solid rgb(var(--c-fg-rgb) / 0.06)" }}
      >
        {OPTIONS.map(({ value, label, Icon }) => {
          const on = pref === value;
          return (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={on}
              tabIndex={on ? 0 : -1}
              data-value={value}
              data-testid={`appearance-${value}`}
              onClick={() => setThemePref(value)}
              style={{
                flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: "6px",
                minHeight: "36px", padding: "0 6px", borderRadius: "8px", border: "none", cursor: "pointer",
                fontSize: "12.5px", fontWeight: 500,
                background: on ? "var(--c-seg-on)" : "transparent",
                color: on ? "var(--c-ink)" : "var(--c-muted)",
                boxShadow: on ? "0 1px 3px rgb(0 0 0 / 0.18)" : "none",
                transition: "background-color .2s, color .2s",
              }}
            >
              <Icon className="w-[14px] h-[14px]" strokeWidth={2} aria-hidden="true" />
              {label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

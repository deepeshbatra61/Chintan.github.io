import React from "react";
import { Moon, Sun } from "lucide-react";
import { useTheme, setThemePref } from "../lib/theme";

// One Light/Dark switch, a sidebar row like Notifications and Contact us: the
// switch sits in the icon slot, then the label (design review 2026-10-03, the
// owner dropped the state word). Untouched, the app follows the phone; the
// first flip pins the reader's choice (lib/theme.js).
export default function AppearanceControl() {
  const { resolved } = useTheme();
  const dark = resolved === "dark";
  const toggle = () => setThemePref(dark ? "light" : "dark");

  return (
    <button
      type="button"
      role="switch"
      aria-checked={dark}
      aria-label="Dark appearance"
      onClick={toggle}
      className="w-full flex items-center gap-3 px-3 py-3 rounded-lg hover:bg-fg/5 transition-colors text-left"
      style={{ minHeight: 48, background: "none", border: "none", cursor: "pointer" }}
      data-testid="appearance-switch"
    >
      <span
        aria-hidden="true"
        style={{
          position: "relative", width: 30, height: 18, borderRadius: 999, flexShrink: 0, marginLeft: -4, marginRight: -8,
          background: dark ? "var(--c-seg-on)" : "rgb(var(--c-fg-rgb) / 0.12)",
          border: "1px solid rgb(var(--c-fg-rgb) / 0.10)", transition: "background-color .2s",
        }}
      >
        <span
          style={{
            position: "absolute", top: 1, left: dark ? 13 : 1, width: 14, height: 14, borderRadius: "50%",
            background: dark ? "var(--c-ink)" : "#fff", boxShadow: "0 1px 3px rgb(0 0 0 / 0.25)",
            display: "grid", placeItems: "center", transition: "left .2s ease-out",
          }}
        >
          {dark
            ? <Moon className="w-[9px] h-[9px]" strokeWidth={2.4} style={{ color: "#111" }} />
            : <Sun className="w-[9px] h-[9px]" strokeWidth={2.4} style={{ color: "#B42318" }} />}
        </span>
      </span>
      <span style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontSize: "15px", fontWeight: 500, color: "var(--c-sub)" }}>
        Appearance
      </span>
    </button>
  );
}

import React, { useEffect, useRef, useState } from "react";
import { Copy, Check } from "lucide-react";

// Clipboard API first (Android WebView and WKWebView both allow it on a tap);
// the hidden-textarea fallback covers older WebViews.
async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch {
      return false;
    }
  }
}

/** Small "Copy" under an AI answer, like a chat app's: the icon turns into a
 * check and says "Copied" for a moment. */
export default function CopyButton({ text }) {
  const [state, setState] = useState("idle"); // idle | copied | failed
  const timer = useRef(null);
  useEffect(() => () => clearTimeout(timer.current), []);

  const onClick = async () => {
    const ok = await copyText(text || "");
    setState(ok ? "copied" : "failed");
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setState("idle"), 1600);
  };

  const Icon = state === "copied" ? Check : Copy;
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={state === "copied" ? "Copied" : "Copy answer"}
      data-testid="copy-answer"
      style={{
        display: "inline-flex", alignItems: "center", gap: 5, minHeight: 32, padding: "0 8px", marginLeft: -8,
        background: "none", border: "none", borderRadius: 8, cursor: "pointer",
        color: state === "copied" ? "var(--c-accent-ink)" : "var(--c-faint)", fontSize: 11.5,
      }}
    >
      <Icon className="w-3.5 h-3.5" aria-hidden="true" />
      <span aria-live="polite">{state === "copied" ? "Copied" : state === "failed" ? "Couldn’t copy" : "Copy"}</span>
    </button>
  );
}

import React, { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { App as CapApp } from "@capacitor/app";
import { useAuth } from "../App";
import { initPush, isPushSupported, onBreakingBanner, refreshRegistration, reportOpened } from "../lib/push";

// Mounted once inside the router. Installs push listeners, re-registers on
// resume and on sign-in (so a guest token moves to the account, R8), and shows
// the foreground Breaking banner (design review DR-12A):
//   top-centre toast, 8s, one at a time (same id replaces), tap opens the
//   story, skipped if the reader is already on it. No shadow, red hairline.

function BreakingBanner({ title, body, onOpen }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      data-testid="breaking-banner"
      style={{
        display: "flex", gap: "10px", width: "min(420px, calc(100vw - 32px))", textAlign: "left",
        background: "var(--c-surface)", border: "1px solid rgba(220,38,38,0.5)", borderRadius: "14px",
        padding: "12px 14px", cursor: "pointer", fontFamily: "'Manrope', sans-serif", boxShadow: "none",
      }}>
      <span aria-hidden="true" style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#DC2626", marginTop: "5px", flexShrink: 0 }} />
      <span style={{ flex: 1, minWidth: 0 }}>
        <span style={{ display: "block", fontFamily: "'JetBrains Mono', monospace", fontSize: "9px", letterSpacing: "0.2em",
                       textTransform: "uppercase", color: "var(--c-accent-ink)" }}>{title || "Breaking"}</span>
        <span style={{ display: "block", fontSize: "14px", fontWeight: 600, lineHeight: 1.35, color: "var(--c-ink)", marginTop: "4px" }}>{body}</span>
        <span style={{ display: "block", fontSize: "12px", color: "var(--c-muted)", marginTop: "6px" }}>Tap to read</span>
      </span>
    </button>
  );
}

export default function PushController() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();
  const pathRef = useRef(location.pathname);
  pathRef.current = location.pathname;

  useEffect(() => {
    if (!isPushSupported()) return;
    initPush({
      navigate,
      addResumeListener: (fn) => CapApp.addListener("appStateChange", ({ isActive }) => { if (isActive) fn(); }),
    });
    const off = onBreakingBanner(({ title, body, route, pushId }) => {
      if (route && pathRef.current === route.split("?")[0]) return; // already reading it
      toast.custom((id) => (
        <BreakingBanner title={title} body={body} onOpen={() => {
          toast.dismiss(id);
          reportOpened(pushId);
          if (route) navigate(route);
        }} />
      ), { id: "breaking", duration: 8000, unstyled: true });
    });
    return off;
  }, [navigate]);

  // Sign-in moves this device's token to the account.
  useEffect(() => {
    if (user) refreshRegistration();
  }, [user]);

  return null;
}

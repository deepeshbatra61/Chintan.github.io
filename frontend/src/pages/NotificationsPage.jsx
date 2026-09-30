import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { toast } from "sonner";
import { App as CapApp } from "@capacitor/app";
import { Switch } from "../components/ui/switch";
import { useAuth } from "../App";
import { enablePush, getPrefs, isPushSupported, permissionState, setPrefs } from "../lib/push";

// Profile › Notifications (design review DR-15A, DR-13A, state table).
//   states: loading · web (no push) · never asked · blocked by the phone ·
//           allowed · guest (briefs locked, Breaking only) · save failed (revert)
// Times are fixed labels in phase 1 (learned hour comes later), not buttons.

const kicker = {
  fontFamily: "'JetBrains Mono', monospace", fontSize: "9px", letterSpacing: "0.2em",
  textTransform: "uppercase", color: "var(--c-faint)", margin: "0 0 8px 2px",
};
const group = {
  background: "var(--c-surface)", borderRadius: "16px", border: "1px solid rgb(var(--c-fg-rgb) / 0.08)",
  marginBottom: "18px", overflow: "hidden",
};
const row = (first) => ({
  display: "flex", alignItems: "center", gap: "12px", padding: "12px 14px", minHeight: "56px",
  borderTop: first ? "none" : "1px solid rgb(var(--c-fg-rgb) / 0.08)",
});
const nameStyle = { fontWeight: 600, fontSize: "14px", color: "var(--c-ink)" };
const subStyle = { fontSize: "12px", color: "var(--c-muted)", marginTop: "2px" };
const timeStyle = {
  fontFamily: "'JetBrains Mono', monospace", fontSize: "10px", letterSpacing: "0.08em",
  textTransform: "uppercase", color: "var(--c-muted)", textAlign: "right", lineHeight: 1.3,
};
const linkBtn = {
  background: "none", border: "none", color: "var(--c-accent-ink)", fontWeight: 600, fontSize: "13px",
  cursor: "pointer", minHeight: "44px", padding: "0 4px", whiteSpace: "nowrap",
};

const SLOTS = [
  { key: "sunrise", name: "Sunrise", sub: "Three stories to start the day", time: "07:30" },
  { key: "noon", name: "High Noon", sub: "What moved since morning", time: "13:00" },
  { key: "dusk", name: "Dusk", sub: "The day, distilled", time: "19:30" },
];

function Toggle({ id, checked, disabled, onChange }) {
  const labelId = `${id}-label`;
  const descId = `${id}-desc`;
  return (
    <Switch
      checked={checked}
      disabled={disabled}
      onCheckedChange={onChange}
      aria-labelledby={labelId}
      aria-describedby={descId}
      data-testid={`notif-${id}`}
      className="data-[state=checked]:bg-[#DC2626]"
    />
  );
}

export default function NotificationsPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [perm, setPerm] = useState("loading");
  const [prefs, setPrefsState] = useState(null);
  const [loadError, setLoadError] = useState(false);
  const native = isPushSupported();

  const load = useCallback(async () => {
    setLoadError(false);
    setPerm(await permissionState());
    if (!isPushSupported()) return; // web: push lives in the app only
    try {
      const data = await getPrefs();
      setPrefsState(data.prefs);
    } catch {
      setLoadError(true);
    }
  }, []);

  useEffect(() => {
    load();
    if (!native) return undefined;
    // Coming back from the phone's settings: re-read the permission.
    const sub = CapApp.addListener("appStateChange", ({ isActive }) => { if (isActive) load(); });
    return () => { sub.then((h) => h.remove()); };
  }, [load, native]);

  const change = async (key, value) => {
    const before = prefs;
    setPrefsState({ ...prefs, [key]: value });           // optimistic
    try {
      const data = await setPrefs({ [key]: value });
      setPrefsState(data.prefs);
    } catch {
      setPrefsState(before);                               // snap back
      toast("Couldn't save that. Try again.");
    }
  };

  const turnOn = async () => {
    const { permission, registration } = await enablePush();
    setPerm(await permissionState());
    if (permission === "granted") {
      const fb = registration?.first_brief;
      toast(fb ? `You're set. First brief: ${fb.day}, ${fb.local_time}.` : "You're set.");
    } else {
      toast("Your phone is blocking notifications for Chintan. You can allow them in its settings.");
    }
  };

  const openSettings = () => {
    toast("Open your phone's Settings › Apps › Chintan › Notifications.");
  };

  const blocked = perm === "denied";
  const neverAsked = perm === "prompt";
  const disabled = blocked || !native;

  return (
    <div style={{ minHeight: "100vh", background: "var(--c-bg)" }} data-testid="notifications-page">
      <header className="sticky z-40 px-4" style={{ top: 0, paddingTop: "var(--sat)", paddingBottom: "12px", background: "rgb(var(--c-bg-rgb) / 0.72)", backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)" }}>
        <div style={{ maxWidth: "640px", margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <button onClick={() => navigate(-1)} aria-label="Back" style={{ padding: "8px", minWidth: "44px", minHeight: "44px", background: "none", border: "none", cursor: "pointer" }}>
            <ArrowLeft className="w-5 h-5" style={{ color: "var(--c-muted2)" }} />
          </button>
          <span style={{ color: "var(--c-muted)", fontFamily: "'JetBrains Mono', monospace", fontSize: "11px", letterSpacing: "0.12em", textTransform: "uppercase" }}>Notifications</span>
          <div style={{ width: "44px" }} />
        </div>
      </header>

      <main style={{ padding: "12px 22px 96px", maxWidth: "640px", margin: "0 auto" }}>
        <h1 style={{ fontFamily: "'Playfair Display', Georgia, serif", fontWeight: 600, fontSize: "24px", color: "var(--c-ink)", margin: "0 0 18px" }}>
          Notifications
        </h1>

        {!native && (
          <p style={{ fontSize: "14px", color: "var(--c-muted)", lineHeight: 1.5 }}>
            Notifications arrive in the Chintan app for Android and iPhone.
          </p>
        )}

        {native && perm === "loading" && (
          <div aria-busy="true" style={{ ...group, height: "170px", opacity: 0.5 }} />
        )}

        {native && blocked && (
          <div style={group}>
            <div style={{ ...row(true), gap: "10px" }}>
              <span aria-hidden="true" style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#DC2626", flexShrink: 0 }} />
              <div style={{ flex: 1, fontSize: "13px", color: "var(--c-ink)" }}>Blocked in your phone's settings</div>
              <button style={linkBtn} onClick={openSettings}>Open settings</button>
            </div>
          </div>
        )}

        {native && neverAsked && (
          <button onClick={turnOn} data-testid="notif-turn-on"
            style={{ width: "100%", minHeight: "48px", marginBottom: "18px", background: "linear-gradient(180deg, #DC2626, #B91C1C)", color: "#fff", border: "none", borderRadius: "12px", fontSize: "15px", fontWeight: 600, cursor: "pointer" }}>
            Turn on notifications
          </button>
        )}

        {loadError && (
          <div style={{ ...group, padding: "16px", textAlign: "center" }}>
            <p style={{ margin: "0 0 10px", fontSize: "14px", color: "var(--c-ink)" }}>Couldn't load your settings.</p>
            <button onClick={load} style={{ ...linkBtn, border: "1px solid rgb(var(--c-fg-rgb) / 0.12)", borderRadius: "10px", padding: "0 16px" }}>Try again</button>
          </div>
        )}

        {native && prefs && perm !== "loading" && (
          <>
            <p style={kicker}>Your briefs</p>
            <div style={group}>
              {user ? SLOTS.map((s, i) => (
                <div key={s.key} style={row(i === 0)}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div id={`${s.key}-label`} style={nameStyle}>{s.name}</div>
                    <div id={`${s.key}-desc`} style={subStyle}>{s.sub}</div>
                  </div>
                  <span style={timeStyle} aria-label={`${s.time} your time`}>{s.time}<br />your time</span>
                  <Toggle id={s.key} checked={!!prefs[s.key]} disabled={disabled || neverAsked}
                    onChange={(v) => change(s.key, v)} />
                </div>
              )) : (
                <div style={row(true)}>
                  <div style={{ flex: 1 }}>
                    <div style={nameStyle}>Sunrise &amp; Dusk</div>
                    <div style={subStyle}>Made for you, so they need an account</div>
                  </div>
                  <button style={linkBtn} onClick={() => navigate("/login")}>Sign in</button>
                </div>
              )}
            </div>

            <p style={kicker}>When it truly matters</p>
            <div style={group}>
              <div style={row(true)}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div id="breaking-label" style={nameStyle}>Breaking</div>
                  <div id="breaking-desc" style={subStyle}>{user ? "Rare. At most once a day." : "National stories only"}</div>
                </div>
                <Toggle id="breaking" checked={prefs.breaking !== false} disabled={disabled || neverAsked}
                  onChange={(v) => change("breaking", v)} />
              </div>
            </div>
            <p style={{ fontSize: "12px", color: "var(--c-muted)", margin: 0 }}>Quiet hours 22:00–07:00. Nothing arrives then.</p>
          </>
        )}
      </main>
    </div>
  );
}

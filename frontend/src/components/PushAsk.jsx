import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Drawer, DrawerContent, DrawerTitle, DrawerDescription } from "./ui/drawer";
import { useAuth } from "../App";
import { askStage, enablePush, getAsk, markAsk } from "../lib/push";

// The soft permission ask (design review DR-6A / 9C). Never on launch: it
// opens after the reader FINISHES their first article (ArticlePage fires
// "chintan:article-finished"), once more >= 7 days after "Not now", then only
// from Profile › Notifications. Guests are sent to sign in first, then see
// the reader sheet (their briefs need an account).

const kicker = {
  fontFamily: "'JetBrains Mono', monospace", fontSize: "9px", letterSpacing: "0.2em",
  textTransform: "uppercase", color: "var(--c-faint)",
};
const primary = {
  width: "100%", minHeight: "48px", background: "linear-gradient(180deg, #DC2626, #B91C1C)", color: "#fff",
  border: "none", borderRadius: "12px", padding: "13px", fontSize: "15px", fontWeight: 600,
  cursor: "pointer", fontFamily: "'Manrope', sans-serif",
};
const ghost = {
  width: "100%", minHeight: "44px", background: "none", border: "none", color: "var(--c-muted)",
  cursor: "pointer", fontSize: "14px", fontFamily: "'Manrope', sans-serif", padding: "10px",
};

function SunArc() {
  return (
    <svg viewBox="0 0 300 78" role="img" aria-label="Sunrise at 07:30 and Dusk at 19:30, your time"
      style={{ width: "100%", height: "78px", margin: "8px 0 4px", color: "var(--c-muted)" }}>
      <path d="M14 66 Q150 -18 286 66" fill="none" stroke="#DC2626" strokeWidth="1.5" strokeDasharray="3 4" />
      <circle cx="58" cy="38" r="6" fill="#F59E0B" />
      <circle cx="242" cy="38" r="6" fill="#DC2626" />
      <text x="28" y="74" fill="currentColor" fontSize="10" fontFamily="JetBrains Mono">SUNRISE 07:30</text>
      <text x="206" y="74" fill="currentColor" fontSize="10" fontFamily="JetBrains Mono">DUSK 19:30</text>
      <text x="150" y="74" fill="currentColor" opacity=".7" fontSize="9" fontFamily="JetBrains Mono" textAnchor="middle">YOUR TIME</text>
    </svg>
  );
}

function firstBriefLine(reg) {
  const fb = reg?.first_brief;
  if (!fb) return "You're set. Your briefs will arrive at 07:30 and 19:30.";
  const when = fb.day === "today" ? "today" : fb.day === "tomorrow" ? "tomorrow" : fb.day;
  return `You're set. First brief: ${when}, ${fb.local_time}.`;
}

export default function PushAsk() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [stage, setStage] = useState(null); // "first" | "again"
  const [busy, setBusy] = useState(false);

  // Trigger: first finished article.
  useEffect(() => {
    let timer;
    const onFinished = async () => {
      const s = await askStage();
      if (!s) return;
      setStage(s);
      timer = setTimeout(() => setOpen(true), 900); // let the last line land first
    };
    window.addEventListener("chintan:article-finished", onFinished);
    return () => { window.removeEventListener("chintan:article-finished", onFinished); clearTimeout(timer); };
  }, []);

  // A guest who said yes and then signed in gets the reader sheet right away.
  useEffect(() => {
    if (!user) return;
    (async () => {
      const a = await getAsk();
      if (a.afterLogin && !a.optedIn) {
        await markAsk({ afterLogin: false });
        setStage("first");
        setOpen(true);
      }
    })();
  }, [user]);

  const notNow = async () => {
    const a = await getAsk();
    await markAsk({ count: a.count + 1, lastAt: Date.now() });
    setOpen(false);
  };

  const onOpenChange = (next) => {
    if (!next && open) notNow(); // swipe down / Esc / back = "Not now"
    else setOpen(next);
  };

  const yes = async () => {
    if (!user) {
      await markAsk({ afterLogin: true });
      setOpen(false);
      navigate("/login");
      return;
    }
    setBusy(true);
    try {
      const { permission, registration } = await enablePush();
      setOpen(false);
      if (permission === "granted") toast(firstBriefLine(registration));
      else {
        const a = await getAsk();
        await markAsk({ count: Math.max(2, a.count + 1), lastAt: Date.now() });
        toast("No problem. Turn it on anytime in Profile › Notifications.");
      }
    } finally {
      setBusy(false);
    }
  };

  const guest = !user;
  const again = stage === "again";

  return (
    <Drawer open={open} onOpenChange={onOpenChange} shouldScaleBackground={false}>
      <DrawerContent
        data-testid="push-ask"
        style={{ background: "var(--c-surface)", borderColor: "rgb(var(--c-fg-rgb) / 0.08)", paddingBottom: "calc(16px + var(--sab, 0px))" }}>
        <div style={{ maxWidth: "440px", width: "100%", margin: "0 auto", padding: "18px 22px 0" }}>
          <div style={kicker}>{again ? "A week of reading" : "You finished your first story"}</div>
          <DrawerTitle
            style={{ fontFamily: "'Playfair Display', Georgia, serif", fontSize: "22px", fontWeight: 600,
                     lineHeight: 1.2, color: "var(--c-ink)", margin: "8px 0 2px", textWrap: "balance" }}>
            {again ? "Still want the morning brief?" : "Want the day, delivered at sunrise?"}
          </DrawerTitle>
          {!guest && !again && <SunArc />}
          <DrawerDescription
            style={{ fontSize: "14px", color: "var(--c-muted)", lineHeight: 1.5, margin: guest || again ? "8px 0 16px" : "0 0 16px",
                     textAlign: guest || again ? "left" : "center" }}>
            {guest
              ? "Briefs are made for you, so they need an account. It takes a few seconds."
              : again
                ? "07:30, three stories, two minutes. We'll only ask this once more."
                : "Two briefs a day. Breaking only when it truly matters."}
          </DrawerDescription>
          <button style={primary} onClick={yes} disabled={busy} data-testid="push-ask-yes">
            {guest ? "Sign in for my briefs" : again ? "Yes, send it" : "Yes, send my briefs"}
          </button>
          <button style={ghost} onClick={notNow} data-testid="push-ask-no">
            {again ? "No thanks" : "Not now"}
          </button>
          {!guest && (
            <p style={{ fontSize: "12px", color: "var(--c-muted)", textAlign: "center", margin: "2px 0 0" }}>
              Change anytime in Profile › Notifications
            </p>
          )}
        </div>
      </DrawerContent>
    </Drawer>
  );
}

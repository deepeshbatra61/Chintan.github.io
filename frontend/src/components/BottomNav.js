import React from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Home, Bookmark, User, Sun, CloudSun, Moon } from "lucide-react";
import { Haptics, ImpactStyle } from "@capacitor/haptics";

const tapHaptic = async () => {
  if (window.Capacitor?.isNativePlatform()) {
    try { await Haptics.impact({ style: ImpactStyle.Light }); } catch {}
  } else if ("vibrate" in navigator) {
    navigator.vibrate(15);
  }
};

// The app's single, persistent top-level navigation. Shown on the four
// destinations (Feed, Briefs, Saved, Profile) and nowhere else — drill-down
// screens (Article, Developing) use back navigation, per platform convention.
const currentBriefType = () => {
  const h = new Date().getHours();
  return h >= 5 && h < 12 ? "morning" : h >= 12 && h < 18 ? "midday" : "night";
};

const BottomNav = () => {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const h = new Date().getHours();
  const BriefIcon = h < 12 ? Sun : h < 18 ? CloudSun : Moon;

  const tabs = [
    { key: "feed", label: "Feed", Icon: Home, to: "/feed", active: pathname === "/feed" },
    { key: "brief", label: "Briefs", Icon: BriefIcon, to: `/brief/${currentBriefType()}`, active: pathname.startsWith("/brief") },
    { key: "saved", label: "Saved", Icon: Bookmark, to: "/bookmarks", active: pathname.startsWith("/bookmarks") },
    { key: "profile", label: "Profile", Icon: User, to: "/profile", active: pathname.startsWith("/profile") },
  ];

  return (
    <nav
      style={{
        position: "fixed", bottom: 0, left: 0, right: 0, zIndex: 50,
        background: "rgba(10,10,10,0.82)", backdropFilter: "blur(14px)", WebkitBackdropFilter: "blur(14px)",
        borderTop: "1px solid rgba(255,255,255,0.06)",
        paddingTop: "8px", paddingBottom: "calc(6px + var(--sab, 8px))",
      }}
      data-testid="bottom-nav"
    >
      <div style={{ maxWidth: "640px", margin: "0 auto", display: "flex", justifyContent: "space-around" }}>
        {tabs.map(({ key, label, Icon, to, active }) => (
          <button
            key={key}
            onClick={() => { tapHaptic(); navigate(to); }}
            data-testid={`nav-${key}`}
            style={{
              display: "flex", flexDirection: "column", alignItems: "center", gap: "3px",
              background: "none", border: "none", cursor: "pointer", flex: 1, padding: "4px 0",
              color: active ? "#DC2626" : "#6E6862", transition: "color .2s",
            }}
          >
            <Icon className="w-[22px] h-[22px]" style={{ width: "22px", height: "22px" }} />
            <span style={{ fontSize: "10.5px", fontWeight: active ? 600 : 400 }}>{label}</span>
          </button>
        ))}
      </div>
    </nav>
  );
};

export default BottomNav;

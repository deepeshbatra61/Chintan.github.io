import React, { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Home, Bookmark, User, Sun, CloudSun, Moon } from "lucide-react";
import { Haptics, ImpactStyle } from "@capacitor/haptics";
import axios from "axios";
import { getLatestSeenArticleId, getNewArticlesAvailable, setNewArticlesAvailable } from "../lib/feedCache";

const BACKEND_URL = "https://chintangithubio-production.up.railway.app";
const API = `${BACKEND_URL}/api`;

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

// Lightweight poll for "is there something new at the top of the feed" — just
// the newest article's id, compared against what FeedPage last loaded. Cheap
// today; worth revisiting (e.g. a dedicated /articles/latest-id endpoint) once
// the feed is pulling in a lot more volume per cycle.
const NEW_ARTICLES_POLL_MS = 60000;

const BottomNav = () => {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const h = new Date().getHours();
  const BriefIcon = h < 12 ? Sun : h < 18 ? CloudSun : Moon;
  const [hasNewArticles, setHasNewArticles] = useState(() => getNewArticlesAvailable());

  useEffect(() => {
    let cancelled = false;
    const checkForNewArticles = async () => {
      const seenId = getLatestSeenArticleId();
      if (!seenId) return; // feed hasn't loaded this session yet — nothing to compare against
      try {
        const r = await axios.get(`${API}/articles?page=1&limit=1`, { withCredentials: true });
        const topId = r.data?.[0]?.article_id;
        if (!cancelled && topId && topId !== seenId) {
          setNewArticlesAvailable(true);
          setHasNewArticles(true);
        }
      } catch {
        // silent — this is a background nicety, not core functionality
      }
    };
    checkForNewArticles();
    const id = setInterval(checkForNewArticles, NEW_ARTICLES_POLL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  const handleTabPress = (key, to) => {
    tapHaptic();
    if (key === "feed" && pathname === "/feed") {
      // Already here — nowhere to navigate to, so this doubles as a refresh.
      setNewArticlesAvailable(false);
      setHasNewArticles(false);
      window.dispatchEvent(new CustomEvent("chintan:feed-refresh"));
      return;
    }
    navigate(to);
  };

  const tabs = [
    { key: "feed", label: "Feed", Icon: Home, to: "/feed", active: pathname === "/feed", dot: hasNewArticles },
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
        {tabs.map(({ key, label, Icon, to, active, dot }) => (
          <button
            key={key}
            onClick={() => handleTabPress(key, to)}
            data-testid={`nav-${key}`}
            style={{
              position: "relative",
              display: "flex", flexDirection: "column", alignItems: "center", gap: "3px",
              background: "none", border: "none", cursor: "pointer", flex: 1, padding: "4px 0",
              color: active ? "#DC2626" : "#6E6862", transition: "color .2s",
            }}
          >
            <span style={{ position: "relative", display: "inline-flex" }}>
              <Icon className="w-[22px] h-[22px]" style={{ width: "22px", height: "22px" }} />
              {dot && (
                <span
                  className="animate-pulse"
                  style={{ position: "absolute", top: "-2px", right: "-3px", width: "8px", height: "8px", borderRadius: "50%", background: "#DC2626", border: "1.5px solid #0A0A0A" }}
                  data-testid="feed-new-articles-dot"
                />
              )}
            </span>
            <span style={{ fontSize: "10.5px", fontWeight: active ? 600 : 400 }}>{label}</span>
          </button>
        ))}
      </div>
    </nav>
  );
};

export default BottomNav;

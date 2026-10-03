import React, { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import axios from "axios";
import {
  Bell, User, Menu, Sun, CloudSun, Moon, Eye, Radio,
  Bookmark, Share2, ThumbsUp, ThumbsDown, Sunrise, Mail
} from "lucide-react";
import { Haptics, ImpactStyle } from "@capacitor/haptics";
import { Share } from "@capacitor/share";
import { toast } from "sonner";
import { useAuth, SuryaLogo } from "../App";
import { Sheet, SheetContent, SheetTrigger, SheetTitle, SheetDescription } from "../components/ui/sheet";
import { ScrollArea } from "../components/ui/scroll-area";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog";
import BottomNav from "../components/BottomNav";
import SignInPrompt from "../components/SignInPrompt";
import AppearanceControl from "../components/AppearanceControl";
import SidebarFollowing from "../components/SidebarFollowing";
import { CoverageStrip, CoverageSheet } from "../components/Coverage";
import Age from "../components/Age";
import { SubPills, StateSheet } from "../components/SubFilters";
import { TOP_CHIPS, parseFilter, filterKey, filterParams, homeStateOf, rememberGuestState, STATES, ASKED_KEY } from "../lib/taxonomy";
import {
  getFeedCache, setFeedCache,
  setLatestSeenArticleId, setNewArticlesAvailable,
} from "../lib/feedCache";
import { formatCalendarDate } from "../lib/calendar";

// www, not the apex: chintan.news 308-redirects to www, and Android does NOT
// follow redirects when fetching /.well-known/assetlinks.json -- pointing
// shares at the apex would fail App Link verification and the app would
// never intercept a shared story, however correct everything else looked.
const SHARE_BASE = "https://www.chintan.news";

const triggerHaptic = async (style = ImpactStyle.Light) => {
  if (window.Capacitor?.isNativePlatform()) {
    try { await Haptics.impact({ style }); } catch {}
  }
};

// Long-press (mobile) / long-mousedown (desktop preview) detector. Cancels on
// meaningful finger/cursor movement so it never fires mid-scroll, and never
// fires twice for the same press.
function useLongPress(onLongPress, threshold = 500, moveThreshold = 10) {
  const timerRef = useRef(null);
  const startPos = useRef({ x: 0, y: 0 });
  const firedRef = useRef(false);

  const clear = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
  };

  const start = (e, payload) => {
    firedRef.current = false;
    const point = e.touches ? e.touches[0] : e;
    startPos.current = { x: point.clientX, y: point.clientY };
    timerRef.current = setTimeout(() => {
      firedRef.current = true;
      onLongPress(payload);
    }, threshold);
  };

  const move = (e) => {
    if (!timerRef.current) return;
    const point = e.touches ? e.touches[0] : e;
    const dx = Math.abs(point.clientX - startPos.current.x);
    const dy = Math.abs(point.clientY - startPos.current.y);
    if (dx > moveThreshold || dy > moveThreshold) clear();
  };

  const bind = (payload) => ({
    onTouchStart: (e) => start(e, payload),
    onTouchMove: move,
    onTouchEnd: clear,
    onMouseDown: (e) => start(e, payload),
    onMouseMove: move,
    onMouseUp: clear,
    onMouseLeave: clear,
    // The OS/WebView's own long-press (text-selection callout, context menu)
    // fires its own haptic tick a beat after ours, which read as a "double
    // nudge" -- suppressing it here leaves just the one, deliberate buzz.
    onContextMenu: (e) => e.preventDefault(),
    style: { WebkitTouchCallout: "none", WebkitUserSelect: "none", userSelect: "none" },
  });

  return { bind, didFire: () => firedRef.current };
}

const BACKEND_URL = "https://chintangithubio-production.up.railway.app";
const API = `${BACKEND_URL}/api`;

// Time-aware sidebar crown: the header tint shifts with the hour (device clock).
const SIDEBAR_PHASES = {
  dawn:  "linear-gradient(135deg, rgba(245,158,11,0.26), rgba(220,38,38,0.06))",
  day:   "linear-gradient(135deg, rgba(220,38,38,0.20), rgba(220,38,38,0.03))",
  dusk:  "linear-gradient(135deg, rgba(234,88,12,0.24), rgba(124,58,237,0.14))",
  night: "linear-gradient(135deg, rgba(99,102,241,0.22), rgb(var(--c-bg-rgb) / 0.3))",
};
const sidebarPhase = (h) => (h < 5 ? "night" : h < 11 ? "dawn" : h < 17 ? "day" : h < 21 ? "dusk" : "night");
const sidebarGreeting = (h) => (h < 5 ? "Late night" : h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : h < 21 ? "Good evening" : "Good night");

// Wave-story intensity indicator ("Direction 2: Heartbeat" — approved design).
// Reuses the pulsing-dot language already used everywhere else in the app;
// only the pulse SPEED and color change with intensity, so a long-running
// conflict reads as "surging/simmering/watching" at a glance without any
// new visual vocabulary. "Watching" gets no pulse at all — a quiet stretch
// is expected behavior for these stories, not a decayed/dead state.
const WAVE_INTENSITY_COLOR = { surging: '#DC2626', simmering: 'var(--c-warn-ink)', watching: 'var(--c-dim)' };
const WAVE_INTENSITY_LABEL = { surging: 'Surging', simmering: 'Simmering', watching: 'Watching' };
const WaveHeartbeat = ({ intensity, reduced }) => {
  const state = intensity?.state || 'watching';
  const color = WAVE_INTENSITY_COLOR[state];
  const label = WAVE_INTENSITY_LABEL[state];
  const sub = state === 'watching'
    ? (intensity?.quiet_days ? `quiet ${intensity.quiet_days}d` : 'quiet')
    : `${intensity?.updates_today || 0} update${intensity?.updates_today === 1 ? '' : 's'} today`;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '5px' }}>
      <span style={{ position: 'relative', width: '10px', height: '10px', flexShrink: 0 }}>
        {!reduced && state !== 'watching' && (
          <motion.span
            animate={{ scale: [1, 1.9, 1], opacity: [0.7, 0, 0.7] }}
            transition={{ duration: state === 'surging' ? 1.1 : 3.4, repeat: Infinity, ease: 'easeOut' }}
            style={{ position: 'absolute', inset: 0, borderRadius: '50%', border: `1.5px solid ${color}` }}
          />
        )}
        <span style={{ position: 'absolute', inset: '2.5px', borderRadius: '50%', background: color }} />
      </span>
      <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '10px', color, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
        {label} · {sub}
      </span>
    </div>
  );
};

const FeedPage = () => {
  const navigate = useNavigate();
  const { user, logout, isGuest, checkAuth } = useAuth();
  const R = useReducedMotion();
  const [signInPromptOpen, setSignInPromptOpen] = useState(false);
  const [signInPromptReason, setSignInPromptReason] = useState("action");

  const promptSignIn = (reason = "action") => {
    setSignInPromptReason(reason);
    setSignInPromptOpen(true);
    closeActionSheet();
  };

  // One nudge per guest session, shown a beat after the feed settles rather
  // than the instant it mounts.
  useEffect(() => {
    if (!isGuest) return;
    const t = setTimeout(() => promptSignIn("personalize"), 2500);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isGuest]);
  const cached = getFeedCache();
  const [articles, setArticles] = useState(() => cached?.articles ?? []);
  const [developingStories, setDevelopingStories] = useState(() => cached?.developingStories ?? []);
  const [loading, setLoading] = useState(() => !cached);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [activeCategory, setActiveCategory] = useState(() => cached?.activeCategory ?? null);
  const [showNotifications, setShowNotifications] = useState(false);
  const [notifications, setNotifications] = useState(() => cached?.notifications ?? []);
  const [unreadCount, setUnreadCount] = useState(() => cached?.unreadCount ?? 0);
  const [page, setPage] = useState(() => cached?.page ?? 1);
  const [hasMore, setHasMore] = useState(() => cached?.hasMore ?? true);
  const [loadingMore, setLoadingMore] = useState(false);
  // The page load that last failed ({ pageNum, append }), or null. While set,
  // infinite scroll is paused -- otherwise a dead connection makes the
  // sentinel fire page after page -- and the retry control re-requests
  // exactly this page.
  const [loadError, setLoadError] = useState(null);
  const [actionSheetArticle, setActionSheetArticle] = useState(null);
  const [coverageArticle, setCoverageArticle] = useState(null);
  const sentinelRef = useRef(null);
  const mainRef = useRef(null);
  const [pullDistance, setPullDistance] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const pulling = useRef(false);
  const pullStartY = useRef(0);
  const PULL_THRESHOLD = 64;

  const PAGE_LIMIT = 20;
  // News v2 (1.13): 10 chips; Health and the States lens are new. A selection
  // is one filter key ("Sports/Hockey", "States/Kerala"), see lib/taxonomy.
  const categories = TOP_CHIPS;
  const [stateSheet, setStateSheet] = useState(null);   // null | "pick" | "first"

  const longPress = useLongPress((article) => {
    triggerHaptic(ImpactStyle.Light);
    setActionSheetArticle(article);
  });

  const closeActionSheet = () => setActionSheetArticle(null);

  const handleBookmark = async (article) => {
    if (!user) return promptSignIn("action");
    try {
      await axios.post(`${API}/bookmarks/${article.article_id}`, {}, { withCredentials: true });
      toast.success("Saved to bookmarks");
    } catch (error) {
      if (error?.response?.status === 400) {
        toast.info("Already in your bookmarks");
      } else {
        console.error("Bookmark error:", error);
        toast.error("Couldn't save — try again");
      }
    }
    closeActionSheet();
  };

  const handleShare = async (article) => {
    const category = article.category ? `${article.category} · ` : "";
    try {
      await Share.share({
        title: article.title,
        text: `${article.title}\n\n${category}${(article.what || "").slice(0, 180)}`,
        url: `${SHARE_BASE}/article/${article.article_id}`,
        dialogTitle: "Share this story",
      });
    } catch {
      // user dismissed or share not available — no feedback needed
    }
    closeActionSheet();
  };

  // "More/less like this" reuses the same like/dislike endpoint and scoring
  // that already powers feed personalization -- a deliberate, subtle nudge to
  // ranking (never a hard filter), consistent with how likes/dislikes already
  // behave everywhere else in the app.
  const handleMoreLikeThis = async (article) => {
    if (!user) return promptSignIn("action");
    try {
      await axios.post(`${API}/articles/${article.article_id}/interact`, { action: "like" }, { withCredentials: true });
      toast.success(`Showing more ${article.category || "stories like this"}`);
    } catch (error) {
      console.error("More-like-this error:", error);
    }
    closeActionSheet();
  };

  const handleLessLikeThis = async (article) => {
    if (!user) return promptSignIn("action");
    try {
      await axios.post(`${API}/articles/${article.article_id}/interact`, { action: "dislike" }, { withCredentials: true });
      toast.success(`Showing less ${article.category || "stories like this"}`);
    } catch (error) {
      console.error("Less-like-this error:", error);
    }
    closeActionSheet();
  };

  const handleSaveForBrief = async (article) => {
    if (!user) return promptSignIn("action");
    try {
      await axios.post(`${API}/articles/${article.article_id}/interact`, { action: "save_for_brief" }, { withCredentials: true });
      toast.success("We'll bring this back in your next Brief");
    } catch (error) {
      console.error("Save-for-brief error:", error);
    }
    closeActionSheet();
  };

  // Every full (page 1) load bumps this; a response from an older load is
  // dropped. Tapping Health then Startups quickly used to let the slower
  // Health reply land last and paint Health cards under Startups.
  const loadSeq = useRef(0);

  const fetchArticles = useCallback(async (category = null, pageNum = 1, append = false) => {
    const seq = append ? loadSeq.current : ++loadSeq.current;
    try {
      const params = filterParams(category, new URLSearchParams({ page: pageNum, limit: PAGE_LIMIT }));
      const response = await axios.get(`${API}/articles?${params}`, { withCredentials: true });
      if (seq !== loadSeq.current) return false;
      const data = response.data;
      if (append) {
        setArticles(prev => {
          const next = [...prev, ...data];
          setFeedCache({ articles: next, page: pageNum });
          return next;
        });
      } else {
        setArticles(data);
        setFeedCache({ articles: data, page: pageNum, activeCategory: category ?? null });
        // A full (non-append) load reflects everything currently at the top
        // of the feed -- record it so BottomNav's poll knows what "new"
        // means, and clear any dot from before this load.
        if (data.length > 0) {
          setLatestSeenArticleId(data[0].article_id);
          setNewArticlesAvailable(false);
        }
      }
      const more = data.length === PAGE_LIMIT;
      setHasMore(more);
      setFeedCache({ hasMore: more });
      setLoadError(null);
      return true;
    } catch (error) {
      if (seq !== loadSeq.current) return false;
      console.error("Error fetching articles:", error);
      setLoadError({ pageNum, append });
      return false;
    }
  }, []);

  const fetchDevelopingStories = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/developing-stories?feed_bar=true`, { withCredentials: true });
      setDevelopingStories(response.data);
      setFeedCache({ developingStories: response.data });
      // An empty array here is a legitimate state (no cluster currently clears
      // the auto-detection bar) — log it distinctly from a fetch failure so an
      // empty banner is never mistaken for a broken one.
      if (response.data.length === 0) {
        console.info("Developing stories: 0 active (server-side auto-detection found no qualifying cluster, or the recurring ingest cycle is paused — check INGEST_SCHEDULE_ENABLED on the backend).");
      }
    } catch (error) {
      console.error("Error fetching developing stories:", error?.response?.status, error?.response?.data || error.message);
    }
  }, []);

  const fetchNotifications = useCallback(async () => {
    if (!user) return;
    try {
      const response = await axios.get(`${API}/notifications`, { withCredentials: true });
      const notifs = response.data.notifications || [];
      const unread = response.data.unread_count || 0;
      setNotifications(notifs);
      setUnreadCount(unread);
      setFeedCache({ notifications: notifs, unreadCount: unread });
    } catch (error) {
      console.error("Error fetching notifications:", error);
    }
  }, [user]);

  useEffect(() => {
    // Already have a cached feed from a prior mount this session (e.g.
    // returning from an article) — show it as-is instead of refetching, so
    // navigating back never reshuffles or reloads what the user was reading.
    if (getFeedCache()) {
      setLoading(false);
      return;
    }
    const loadData = async () => {
      setLoading(true);
      await Promise.all([fetchArticles(), fetchDevelopingStories(), fetchNotifications()]);
      setLoading(false);
    };
    loadData();
  }, [fetchArticles, fetchDevelopingStories, fetchNotifications]);

  // Shared by pull-to-refresh and the bottom-nav Feed tab (tapped while
  // already on the feed) -- both just want a full, fresh reload.
  const doRefresh = useCallback(async () => {
    if (refreshing) return;
    setRefreshing(true);
    triggerHaptic(ImpactStyle.Light);
    setPage(1);
    setHasMore(true);
    setLoadError(null);
    await Promise.all([
      fetchArticles(activeCategory, 1, false),
      fetchDevelopingStories(),
      fetchNotifications(),
    ]);
    setRefreshing(false);
    setPullDistance(0);
  }, [refreshing, activeCategory, fetchArticles, fetchDevelopingStories, fetchNotifications]);

  // Tapping "Feed" in the bottom nav while already on the feed page has
  // nowhere to navigate to, so it refreshes instead -- BottomNav dispatches
  // this event since it has no direct reference to this page's fetch logic.
  // It also takes the reader back to the top, however far down they were.
  useEffect(() => {
    const handler = () => {
      mainRef.current?.scrollTo({ top: 0, behavior: R ? "auto" : "smooth" });
      doRefresh();
    };
    window.addEventListener("chintan:feed-refresh", handler);
    return () => window.removeEventListener("chintan:feed-refresh", handler);
  }, [doRefresh, R]);

  const handlePullStart = (e) => {
    if (!refreshing && mainRef.current && mainRef.current.scrollTop <= 0) {
      pulling.current = true;
      pullStartY.current = e.touches[0].clientY;
    }
  };

  const handlePullMove = (e) => {
    if (!pulling.current || refreshing) return;
    const dy = e.touches[0].clientY - pullStartY.current;
    if (dy > 0 && mainRef.current && mainRef.current.scrollTop <= 0) {
      setPullDistance(Math.min(dy * 0.45, 88));
    } else {
      pulling.current = false;
      setPullDistance(0);
    }
  };

  const handlePullEnd = () => {
    if (!pulling.current) return;
    pulling.current = false;
    if (pullDistance > PULL_THRESHOLD) {
      doRefresh();
    } else {
      setPullDistance(0);
    }
  };

  // Warm the AI content for the articles most likely to be opened next: hitting
  // GET /articles/:id triggers (and caches) the contemplation beats server-side,
  // so by the time the reader taps in, there's no generation wait. Bounded to the
  // top few, once each, and staggered so it never bursts.
  const prefetchedRef = useRef(new Set());
  useEffect(() => {
    if (!articles.length) return;
    const targets = articles
      .filter((a) => !prefetchedRef.current.has(a.article_id) && !(a.beats && a.beats.length))
      .slice(0, 6);
    targets.forEach((a, i) => {
      prefetchedRef.current.add(a.article_id);
      setTimeout(() => {
        axios.get(`${API}/articles/${a.article_id}`, { withCredentials: true }).catch(() => {});
      }, i * 500);
    });
  }, [articles]);

  const handleCategoryChange = (category) => {
    let cat = category === "All" ? null : category;
    if (cat === "States") {
      // Your state first; the first time with none set, ask (Skip always shown).
      const home = homeStateOf(user);
      if (home) {
        cat = filterKey("States", home);
      } else {
        let asked = false;
        try { asked = localStorage.getItem(ASKED_KEY) === "1"; } catch { /* private mode */ }
        if (!asked) setStateSheet("first");
      }
    }
    setActiveCategory(cat);
    setPage(1);
    setHasMore(true);
    setLoadError(null);
    fetchArticles(cat, 1, false);
  };

  // Infinite scroll: load next page when sentinel enters viewport
  useEffect(() => {
    if (!sentinelRef.current) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !loadingMore && !loading && !loadError) {
          const nextPage = page + 1;
          setLoadingMore(true);
          // Only advance the page counter once the page actually arrived, so a
          // failure leaves us pointed at the last page we really have.
          fetchArticles(activeCategory, nextPage, true)
            .then((ok) => { if (ok) setPage(nextPage); })
            .finally(() => setLoadingMore(false));
        }
      },
      { rootMargin: "200px" }
    );
    observer.observe(sentinelRef.current);
    return () => observer.disconnect();
  }, [hasMore, loadingMore, loading, loadError, page, activeCategory, fetchArticles]);

  const retryFailedLoad = () => {
    if (!loadError || loadingMore) return;
    const { pageNum, append } = loadError;
    setLoadingMore(true);
    fetchArticles(activeCategory, pageNum, append)
      .then((ok) => { if (ok) setPage(pageNum); })
      .finally(() => setLoadingMore(false));
  };

  const pickState = async (st) => {
    try { localStorage.setItem(ASKED_KEY, "1"); } catch { /* private mode */ }
    setStateSheet(null);
    if (user) {
      const keep = (user.interests_v2 || []).filter((x) => !STATES.includes(x));
      try {
        await axios.put(`${API}/users/interests`, { interests: [...keep, st] }, { withCredentials: true });
        await checkAuth();
      } catch { toast.error("Couldn\u2019t save your state. It\u2019s set for now."); }
    } else {
      rememberGuestState(st);
    }
    handleCategoryChange(filterKey("States", st));
  };

  const closeStateSheet = () => {
    try { localStorage.setItem(ASKED_KEY, "1"); } catch { /* private mode */ }
    setStateSheet(null);
  };

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  const markNotificationsRead = async () => {
    try {
      await axios.post(`${API}/notifications/read`, {}, { withCredentials: true });
      setUnreadCount(0);
      setFeedCache({ unreadCount: 0 });
    } catch (error) {
      console.error("Error marking notifications read:", error);
    }
  };

  const openNotifications = () => {
    setShowNotifications(true);
    if (unreadCount > 0) {
      markNotificationsRead();
    }
  };

  // Sidebar crown + quick-jump (computed when the feed renders / drawer opens)
  const _now = new Date();
  const _hour = _now.getHours();
  const _greeting = sidebarGreeting(_hour);
  const _firstName = user?.name?.split(" ")[0] || "";
  const _timeStr = _now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  // Same morning/midday/night split BottomNav uses for its single Briefs tab —
  // here there are three links at once, so only the one matching the phone's
  // current local time stays fully lit; the other two are dimmed instead of
  // all three competing for attention around the clock.
  const _currentBrief = _hour >= 5 && _hour < 12 ? "morning" : _hour >= 12 && _hour < 18 ? "midday" : "night";

  if (loading) {
    return (
      <div className="min-h-screen bg-page flex items-center justify-center">
        <SuryaLogo className="w-16 h-16 animate-spin-slow" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-page" data-testid="feed-page">
      {/* Header */}
      <header className="glass-nav sticky z-40 px-4" style={{ top: 0, paddingTop: 'var(--sat)', paddingBottom: '12px' }}>
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
              <SheetTrigger asChild>
                <button className="p-2 hover:bg-fg/5 rounded-lg transition-colors" data-testid="menu-btn">
                  <Menu className="w-5 h-5 text-gray-400" />
                </button>
              </SheetTrigger>
              <SheetContent side="left" className="w-80 bg-page border-r border-fg/10 p-0" style={{ display: 'flex', flexDirection: 'column', height: '100dvh' }}>
                {/* Time-aware crown */}
                <div style={{ flexShrink: 0, background: SIDEBAR_PHASES[sidebarPhase(_hour)], paddingTop: 'calc(var(--sat) + 22px)', paddingLeft: '20px', paddingRight: '20px', paddingBottom: '20px' }}>
                  <SuryaLogo className="w-11 h-11 animate-spin-slow" />
                  <h2 style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontWeight: 600, fontSize: '22px', color: 'var(--c-ink)', margin: '14px 0 0' }}>
                    {_greeting}{_firstName ? `, ${_firstName}` : ''}
                  </h2>
                  <p style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '11px', color: 'rgb(var(--c-fg-rgb) / 0.55)', margin: '5px 0 0', letterSpacing: '0.04em' }}>
                    {_timeStr} · Contemplate.
                  </p>
                </div>

                {/* Stylish divider — a red-glow hairline with a lit center */}
                <div style={{ flexShrink: 0, position: 'relative', height: '1px', background: 'linear-gradient(90deg, transparent, rgba(220,38,38,0.55) 50%, transparent)' }}>
                  <div style={{ position: 'absolute', top: '-2px', left: '50%', transform: 'translateX(-50%)', width: '5px', height: '5px', borderRadius: '50%', background: '#DC2626', boxShadow: '0 0 9px rgba(220,38,38,0.8)' }} />
                </div>

                {/* Scrollable nav — Direction A: quiet monochrome icons, serif
                    labels carry the hierarchy instead of per-item icon colors */}
                <div style={{ flex: 1, overflowY: 'auto' }} className="hide-scrollbar">
                  <div className="p-4 space-y-1">
                    <p style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '9px', letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--c-faint2)' }} className="px-3 py-2">Briefs</p>
                    {[
                      { key: "morning", label: "Morning Brief", Icon: Sun },
                      { key: "midday", label: "Midday Update", Icon: CloudSun },
                      { key: "night", label: "Night Summary", Icon: Moon },
                    ].map(({ key, label, Icon }) => {
                      const isNow = key === _currentBrief;
                      return (
                        <button
                          key={key}
                          onClick={() => { navigate(`/brief/${key}`); setSidebarOpen(false); }}
                          className="w-full flex items-center gap-3 px-3 py-3 rounded-lg hover:bg-fg/5 transition-colors text-left"
                          data-testid={`${key}-brief-nav`}
                          style={{ opacity: isNow ? 1 : 0.42 }}
                        >
                          <Icon className="w-[18px] h-[18px]" style={{ color: isNow ? 'var(--c-accent-ink)' : 'var(--c-faint)', flexShrink: 0 }} />
                          <span style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontSize: '15px', fontWeight: 500, color: isNow ? 'var(--c-ink)' : 'var(--c-sub)', flex: 1 }}>{label}</span>
                          {isNow && (
                            <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '9px', letterSpacing: '0.1em', color: 'var(--c-accent-ink)', textTransform: 'uppercase' }}>Now</span>
                          )}
                        </button>
                      );
                    })}

                    <div className="h-px bg-fg/10 my-4" />
                    {developingStories.length > 0 ? (
                      <button
                        onClick={() => { navigate("/developing"); setSidebarOpen(false); }}
                        className="w-full"
                        data-testid="developing-stories-nav"
                        style={{ padding: '12px 13px', borderRadius: '12px', background: 'rgba(220,38,38,0.06)', border: '1px solid rgba(220,38,38,0.22)', display: 'flex', alignItems: 'center', gap: '11px', textAlign: 'left' }}
                      >
                        <span className="animate-pulse" style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#DC2626', flexShrink: 0 }} />
                        <div>
                          <div style={{ fontSize: '13.5px', color: 'var(--c-ink2)', fontWeight: 500 }}>Developing Stories</div>
                          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '10px', color: 'var(--c-muted2)', marginTop: '2px' }}>{developingStories.length} topic{developingStories.length !== 1 ? "s" : ""}</div>
                        </div>
                      </button>
                    ) : (
                      <div
                        className="w-full flex items-center gap-3 px-3 py-3 rounded-lg"
                        data-testid="developing-stories-empty"
                      >
                        <Radio className="w-[18px] h-[18px]" style={{ color: "var(--c-faint2)", flexShrink: 0 }} />
                        <span style={{ color: "var(--c-faint)", fontSize: "14px" }}>No developing story right now</span>
                      </div>
                    )}

                    <SidebarFollowing open={sidebarOpen} user={user}
                      onOpenStory={(id) => { navigate(`/developing/${id}`); setSidebarOpen(false); }} />

                    <div className="h-px bg-fg/10 my-4" />
                    <button
                      onClick={() => { navigate("/notifications"); setSidebarOpen(false); }}
                      className="w-full flex items-center gap-3 px-3 py-3 rounded-lg hover:bg-fg/5 transition-colors text-left"
                      data-testid="notifications-sidebar-nav"
                    >
                      <Bell className="w-[18px] h-[18px]" style={{ color: 'var(--c-faint)', flexShrink: 0 }} />
                      <span style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontSize: '15px', fontWeight: 500, color: 'var(--c-sub)' }}>Notifications</span>
                    </button>
                    <AppearanceControl />
                    <button
                      onClick={() => { navigate("/contact"); setSidebarOpen(false); }}
                      className="w-full flex items-center gap-3 px-3 py-3 rounded-lg hover:bg-fg/5 transition-colors text-left"
                      data-testid="contact-sidebar-nav"
                    >
                      <Mail className="w-[18px] h-[18px]" style={{ color: 'var(--c-faint)', flexShrink: 0 }} />
                      <span style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontSize: '15px', fontWeight: 500, color: 'var(--c-sub)' }}>Contact us</span>
                    </button>
                  </div>
                </div>

                {/* Sign out — pinned footer, so it never overlaps the list */}
                <div style={{ flexShrink: 0, borderTop: '1px solid rgb(var(--c-fg-rgb) / 0.1)', padding: '14px 16px 12px', paddingBottom: 'calc(12px + var(--sab))' }}>
                  <button
                    onClick={user ? handleLogout : () => navigate("/login")}
                    className="w-full rounded-lg transition-colors hover:bg-red-500/10"
                    style={{ padding: '11px', color: 'var(--c-accent-ink)', background: 'none', border: 'none', cursor: 'pointer', fontSize: '14px', fontWeight: 500 }}
                    data-testid="logout-btn"
                  >
                    {user ? "Sign Out" : "Sign in"}
                  </button>
                </div>
              </SheetContent>
            </Sheet>

            <div className="flex items-center gap-2">
              <SuryaLogo className="w-8 h-8" />
              <span className="font-serif text-xl text-fg hidden sm:block">Chintan</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={openNotifications}
              className="p-2 hover:bg-fg/5 rounded-lg transition-colors relative"
              data-testid="notifications-btn"
            >
              <Bell className="w-5 h-5 text-gray-400" />
              {unreadCount > 0 && (
                <span className="absolute top-1 right-1 w-2.5 h-2.5 bg-red-600 rounded-full animate-pulse" />
              )}
            </button>
            <button 
              onClick={() => navigate("/profile")}
              className="w-8 h-8 rounded-full bg-fg/10 overflow-hidden"
              data-testid="profile-btn"
            >
              {user?.picture ? (
                <img src={user.picture} alt={user.name} className="w-full h-full object-cover" />
              ) : (
                <User className="w-5 h-5 text-gray-400 m-auto mt-1.5" />
              )}
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main
        ref={mainRef}
        className="pb-24 px-4"
        style={{ paddingTop: '14px', height: '100vh', overflowY: 'auto' }}
        onTouchStart={handlePullStart}
        onTouchMove={handlePullMove}
        onTouchEnd={handlePullEnd}
      >
        {(pullDistance > 0 || refreshing) && (
          <div
            style={{
              display: 'flex', justifyContent: 'center', alignItems: 'center',
              height: refreshing ? '52px' : `${pullDistance}px`,
              transition: refreshing ? 'height .2s ease' : 'none',
              overflow: 'hidden',
            }}
            data-testid="pull-to-refresh-indicator"
          >
            <SuryaLogo className="w-8 h-8 animate-spin-slow" />
          </div>
        )}
        <div className="max-w-6xl mx-auto">
          {/* Developing Stories Banner — always present: active state or a
              calm "nothing right now" state, never silently absent */}
          <motion.div
            className="mb-5"
            initial={R ? false : { opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
          >
            {developingStories.length > 0 ? (
              <motion.div
                animate={{ boxShadow: ['0 0 0px rgba(220,38,38,0)', '0 0 18px rgba(220,38,38,0.12)', '0 0 0px rgba(220,38,38,0)'] }}
                transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
                style={{ background: 'var(--c-surface)', border: '1px solid rgba(220,38,38,0.28)', borderRadius: '16px', padding: '14px 16px' }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '7px', marginBottom: '12px' }}>
                  <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#DC2626' }} className="animate-pulse" />
                  <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '10px', letterSpacing: '0.16em', color: 'var(--c-accent-ink)', textTransform: 'uppercase' }}>Developing</span>
                </div>
                <div className="overflow-x-auto hide-scrollbar">
                  <div style={{ display: 'flex', alignItems: 'stretch' }}>
                    {developingStories.slice(0, 4).map((story, i) => (
                      <React.Fragment key={story.story_id}>
                        {i > 0 && <div style={{ width: '1px', alignSelf: 'stretch', background: 'rgb(var(--c-fg-rgb) / 0.09)', margin: '2px 15px', flexShrink: 0 }} />}
                        <button
                          onClick={() => navigate(`/developing/${story.story_id}`)}
                          className="group"
                          style={{ flexShrink: 0, maxWidth: '210px', textAlign: 'left', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
                          data-testid={`developing-${story.story_id}`}
                        >
                          <p className="group-hover:text-red-400 transition-colors" style={{ color: 'var(--c-ink2)', fontSize: '13.5px', fontWeight: 500, lineHeight: 1.32, margin: 0, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                            {story.title}
                          </p>
                          {story.kind === 'wave' ? (
                            <WaveHeartbeat intensity={story.intensity} reduced={R} />
                          ) : story.kind === 'calendar' ? (
                            // Calendar entries have no articles by definition, so an
                            // update count is both meaningless and (with no
                            // article_count in the payload) literally "undefined".
                            <p style={{ color: 'var(--c-muted)', fontSize: '11px', marginTop: '5px', fontFamily: "'JetBrains Mono', monospace" }}>{formatCalendarDate(story.calendar_date)}</p>
                          ) : (
                            <p style={{ color: 'var(--c-muted)', fontSize: '11px', marginTop: '5px', fontFamily: "'JetBrains Mono', monospace" }}>{story.article_count} update{story.article_count !== 1 ? "s" : ""}</p>
                          )}
                        </button>
                      </React.Fragment>
                    ))}
                  </div>
                </div>
              </motion.div>
            ) : (
              <div
                style={{ background: 'var(--c-surface)', border: '1px solid rgb(var(--c-fg-rgb) / 0.08)', borderRadius: '16px', padding: '14px 16px', display: 'flex', alignItems: 'center', gap: '10px' }}
                data-testid="developing-banner-empty"
              >
                <motion.span
                  animate={R ? {} : { opacity: [0.35, 0.75, 0.35] }}
                  transition={R ? {} : { duration: 2.6, repeat: Infinity, ease: 'easeInOut' }}
                  style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--c-faint2)', flexShrink: 0 }}
                />
                <div>
                  <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '10px', letterSpacing: '0.16em', color: 'var(--c-faint)', textTransform: 'uppercase', marginBottom: '2px' }}>Developing</div>
                  <p style={{ fontFamily: "'Manrope', sans-serif", fontSize: '13px', color: 'var(--c-muted)', margin: 0 }}>Nothing developing right now — we're watching.</p>
                </div>
              </div>
            )}
          </motion.div>

          {/* Categories — active pill glides between chips */}
          <div className="mb-6 overflow-x-auto hide-scrollbar">
            <div className="flex gap-2">
              {categories.map((cat) => {
                const active = (cat === "All" && !activeCategory) || parseFilter(activeCategory).top === cat;
                return (
                  <button
                    key={cat}
                    onClick={() => handleCategoryChange(cat)}
                    className="relative rounded-full text-sm whitespace-nowrap"
                    style={{ flexShrink: 0, padding: "8px 16px", border: "none", cursor: "pointer", background: active ? "transparent" : "rgb(var(--c-fg-rgb) / 0.05)", color: active ? "#fff" : "var(--c-muted2)", transition: "color .3s ease" }}
                    data-testid={`category-filter-${cat.toLowerCase()}`}
                  >
                    {active && (
                      <motion.span
                        layoutId="catPill"
                        transition={{ type: "spring", stiffness: 400, damping: 34 }}
                        style={{ position: "absolute", inset: 0, borderRadius: "9999px", background: "linear-gradient(180deg, #DC2626, #B91C1C)", zIndex: 0 }}
                      />
                    )}
                    <span style={{ position: "relative", zIndex: 1 }}>{cat}</span>
                  </button>
                );
              })}
            </div>
          </div>

          <SubPills filter={activeCategory} onChange={(key) => handleCategoryChange(key || "All")}
            homeState={homeStateOf(user)} onPickState={() => setStateSheet("pick")} />
          {(() => {
            // A narrow filter with nothing from today shows the week, and says so.
            const f = parseFilter(activeCategory);
            const narrow = f.sub || f.state;
            const newest = articles[0]?.published_at;
            if (!narrow || !newest || Date.now() - new Date(newest).getTime() < 86400000) return null;
            return (
              <p style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: "var(--c-muted)", margin: "-4px 0 14px" }} data-testid="filter-week-note">
                Nothing new in {f.sub || f.state} today · from this week
              </p>
            );
          })()}

          {/* Articles Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <AnimatePresence>
              {articles.map((article, index) => (
                <motion.article
                  key={article.article_id}
                  className="news-card cursor-pointer"
                  onClick={() => {
                    if (longPress.didFire()) return; // long-press opened the action sheet, not navigation
                    navigate(`/article/${article.article_id}`);
                  }}
                  {...longPress.bind(article)}
                  initial={{ opacity: 0, y: 18 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(index, 8) * 0.05, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                  whileTap={{ scale: 0.98 }}
                  data-testid={`article-card-${article.article_id}`}
                >
                  <div className="relative h-48 overflow-hidden bg-surface2">
                    <img 
                      src={article.image_url} 
                      alt={article.title}
                      className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
                    />
                    <div className="img-fade absolute inset-0 bg-gradient-to-t from-page to-transparent" />
                    
                    <div className="absolute top-3 left-3 flex gap-2">
                      {article.is_breaking && (
                        <span className="live-indicator bg-black/60 backdrop-blur-sm px-2 py-1 rounded">
                          <span className="live-dot" />
                          Breaking
                        </span>
                      )}
                      {article.is_developing && !article.is_breaking && (
                        <span className="text-xs text-amber-500 bg-black/60 backdrop-blur-sm px-2 py-1 rounded">
                          Developing
                        </span>
                      )}
                      {article.event_status === "early_report" && !article.is_developing && !article.is_breaking && (
                        <span className="text-xs bg-black/60 backdrop-blur-sm px-2 py-1 rounded"
                          style={{ fontFamily: "'JetBrains Mono', monospace", letterSpacing: "0.12em", fontSize: 10, color: "var(--c-warn-ink)" }}
                          data-testid="early-report-flag">
                          EARLY REPORT
                        </span>
                      )}
                    </div>
                    
                    <div className="absolute bottom-3 left-3">
                      <span className="category-badge text-xs">
                        {article.category_v2 || article.category}{(article.subcategory_v2) ? ` · ${article.subcategory_v2}` : ""}
                      </span>
                    </div>
                  </div>

                  <div className="p-4">
                    <h3 className="font-serif text-lg text-fg mb-2 line-clamp-2 leading-tight">
                      {article.title}
                    </h3>
                    <p className="text-gray-500 text-sm line-clamp-2 mb-4">
                      {article.description}
                    </p>
                    
                    <div className="flex items-center justify-between text-xs text-gray-600">
                      <CoverageStrip article={article} onOpen={setCoverageArticle} />
                      <div className="flex items-center gap-3">
                        <span className="flex items-center gap-1">
                          <Eye className="w-3 h-3" />
                          {article.view_count || 0}
                        </span>
                        <Age iso={article.published_at} />
                      </div>
                    </div>
                  </div>
                </motion.article>
              ))}
            </AnimatePresence>
          </div>

          {articles.length === 0 && !loadError && !loading && (() => {
            const f = parseFilter(activeCategory);
            const name = f.sub || f.state;
            if (!name) {
              return <div className="text-center py-20"><p className="text-gray-500">No articles found</p></div>;
            }
            const parent = f.state ? "States" : f.top;
            const already = (user?.interests_v2 || []).includes(name);
            return (
              <div className="text-center py-16 px-6" data-testid="filter-empty">
                <p style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontSize: 18, color: "var(--c-ink2)", margin: "0 0 14px" }}>
                  {name} is quiet this week.
                </p>
                <div style={{ display: "flex", gap: 8, justifyContent: "center", flexWrap: "wrap" }}>
                  <button type="button" onClick={() => handleCategoryChange(f.state ? "States" : parent)}
                    style={{ minHeight: 44, padding: "0 16px", borderRadius: 999, border: "1px solid rgb(var(--c-fg-rgb) / 0.12)", background: "none", color: "var(--c-sub)", cursor: "pointer" }}>
                    {f.state ? "All states" : `All ${parent}`} ›
                  </button>
                  {user && !already && (
                    <button type="button"
                      onClick={async () => {
                        try {
                          await axios.put(`${API}/users/interests`, { interests: [...(user.interests_v2 || []), name] }, { withCredentials: true });
                          await checkAuth();
                          toast.success(`We\u2019ll bring you ${name} stories first.`);
                        } catch { toast.error("Couldn\u2019t save that. Try again."); }
                      }}
                      style={{ minHeight: 44, padding: "0 16px", borderRadius: 999, border: "1px solid rgba(220,38,38,0.5)", background: "rgba(220,38,38,0.10)", color: "var(--c-ink)", cursor: "pointer" }}>
                      Add {name} to your interests
                    </button>
                  )}
                </div>
              </div>
            );
          })()}

          {/* Infinite scroll sentinel */}
          <div ref={sentinelRef} className="h-1" />

          {loadingMore && (
            <div className="flex justify-center py-6">
              <SuryaLogo className="w-8 h-8 animate-spin-slow" />
            </div>
          )}

          {loadError && !loadingMore && (
            <div className={`flex justify-center ${articles.length === 0 ? "py-20" : "py-6"}`}>
              <button
                type="button"
                onClick={retryFailedLoad}
                className="text-sm text-gray-500 hover:text-fg transition-colors"
                data-testid="feed-load-retry"
              >
                {articles.length === 0 ? "Couldn't load stories." : "Couldn't load more."}{" "}
                <span className="underline underline-offset-2">Try again</span>
              </button>
            </div>
          )}
        </div>
      </main>

      {coverageArticle && <CoverageSheet article={coverageArticle} onClose={() => setCoverageArticle(null)} />}
      <StateSheet open={!!stateSheet} firstTime={stateSheet === "first"} onPick={pickState} onClose={closeStateSheet} />
      <BottomNav />

      {/* Long-press quick actions — headline + photo is enough signal to
          decide these, no need to open the article first. */}
      <Sheet open={!!actionSheetArticle} onOpenChange={(open) => !open && closeActionSheet()}>
        <SheetContent side="bottom" className="bg-page border-fg/10 rounded-t-2xl">
          {actionSheetArticle && (
            <div className="pt-2 pb-2">
              <SheetTitle className="sr-only">{actionSheetArticle.title}</SheetTitle>
              <SheetDescription className="sr-only">Quick actions for this article</SheetDescription>
              <p className="font-serif text-sm text-fg/90 line-clamp-2 mb-5 pr-8">
                {actionSheetArticle.title}
              </p>
              <div className="flex flex-col gap-1">
                <button
                  className="flex items-center gap-3 py-3 px-2 text-left text-fg hover:bg-fg/5 rounded-lg transition-colors"
                  onClick={() => handleBookmark(actionSheetArticle)}
                >
                  <Bookmark className="w-5 h-5 text-gray-400" />
                  <span>Add to bookmarks</span>
                </button>
                <button
                  className="flex items-center gap-3 py-3 px-2 text-left text-fg hover:bg-fg/5 rounded-lg transition-colors"
                  onClick={() => handleShare(actionSheetArticle)}
                >
                  <Share2 className="w-5 h-5 text-gray-400" />
                  <span>Share</span>
                </button>
                <button
                  className="flex items-center gap-3 py-3 px-2 text-left text-fg hover:bg-fg/5 rounded-lg transition-colors"
                  onClick={() => handleSaveForBrief(actionSheetArticle)}
                >
                  <Sunrise className="w-5 h-5 text-gray-400" />
                  <span>Save for my next Brief</span>
                </button>
                <div className="h-px bg-fg/10 my-1" />
                <button
                  className="flex items-center gap-3 py-3 px-2 text-left text-fg hover:bg-fg/5 rounded-lg transition-colors"
                  onClick={() => handleMoreLikeThis(actionSheetArticle)}
                >
                  <ThumbsUp className="w-5 h-5 text-gray-400" />
                  <span>Show more like this</span>
                </button>
                <button
                  className="flex items-center gap-3 py-3 px-2 text-left text-fg hover:bg-fg/5 rounded-lg transition-colors"
                  onClick={() => handleLessLikeThis(actionSheetArticle)}
                >
                  <ThumbsDown className="w-5 h-5 text-gray-400" />
                  <span>Show less like this</span>
                </button>
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>

      {/* Notifications Dialog */}
      <Dialog open={showNotifications} onOpenChange={setShowNotifications}>
        <DialogContent className="bg-page border-fg/10 max-w-md max-h-[70vh]">
          <DialogHeader>
            <DialogTitle className="text-fg flex items-center gap-2">
              <Bell className="w-5 h-5 text-red-500" />
              Notifications
            </DialogTitle>
          </DialogHeader>
          
          <ScrollArea className="h-[400px]">
            {notifications.length > 0 ? (
              <div className="space-y-3">
                {notifications.map((notif, idx) => (
                  <div 
                    key={idx} 
                    className={`p-4 rounded-lg ${notif.read ? 'bg-fg/5' : 'bg-red-950/30 border border-red-900/30'}`}
                  >
                    <div className="flex items-start gap-3">
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                        notif.type === 'agree' ? 'bg-green-500/20' : 'bg-red-500/20'
                      }`}>
                        {notif.type === 'agree' ? (
                          <span className="text-green-400 text-lg">👍</span>
                        ) : (
                          <span className="text-red-400 text-lg">👎</span>
                        )}
                      </div>
                      <div className="flex-1">
                        <p className="text-fg text-sm">
                          <span className="font-medium">{notif.from_user}</span>
                          {notif.type === 'agree' ? ' agreed with' : ' disagreed with'} your comment
                        </p>
                        <p className="text-gray-500 text-xs mt-1 line-clamp-2">
                          "{notif.comment_preview}"
                        </p>
                        <p className="text-gray-600 text-xs mt-2">{notif.time_ago}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-12">
                <Bell className="w-12 h-12 text-gray-700 mx-auto mb-4" />
                <p className="text-gray-500">No notifications yet</p>
                <p className="text-gray-600 text-sm mt-1">
                  You'll see reactions to your comments here
                </p>
              </div>
            )}
          </ScrollArea>
        </DialogContent>
      </Dialog>

      <SignInPrompt open={signInPromptOpen} onOpenChange={setSignInPromptOpen} reason={signInPromptReason} />
    </div>
  );
};

export default FeedPage;

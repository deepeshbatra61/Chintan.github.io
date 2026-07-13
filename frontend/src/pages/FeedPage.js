import React, { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import axios from "axios";
import {
  Bell, User, Menu, Sun, CloudSun, Moon, Eye, Radio
} from "lucide-react";
import { useAuth, SuryaLogo } from "../App";
import { Sheet, SheetContent, SheetTrigger } from "../components/ui/sheet";
import { ScrollArea } from "../components/ui/scroll-area";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog";
import BottomNav from "../components/BottomNav";

const BACKEND_URL = "https://chintangithubio-production.up.railway.app";
const API = `${BACKEND_URL}/api`;

// Time-aware sidebar crown: the header tint shifts with the hour (device clock).
const SIDEBAR_PHASES = {
  dawn:  "linear-gradient(135deg, rgba(245,158,11,0.26), rgba(220,38,38,0.06))",
  day:   "linear-gradient(135deg, rgba(220,38,38,0.20), rgba(220,38,38,0.03))",
  dusk:  "linear-gradient(135deg, rgba(234,88,12,0.24), rgba(124,58,237,0.14))",
  night: "linear-gradient(135deg, rgba(99,102,241,0.22), rgba(10,10,10,0.3))",
};
const sidebarPhase = (h) => (h < 5 ? "night" : h < 11 ? "dawn" : h < 17 ? "day" : h < 21 ? "dusk" : "night");
const sidebarGreeting = (h) => (h < 5 ? "Late night" : h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : h < 21 ? "Good evening" : "Good night");

const FeedPage = () => {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [articles, setArticles] = useState([]);
  const [developingStories, setDevelopingStories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [activeCategory, setActiveCategory] = useState(null);
  const [showNotifications, setShowNotifications] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const sentinelRef = useRef(null);

  const PAGE_LIMIT = 20;
  const categories = ["All", "Politics", "Technology", "Business", "Sports", "Entertainment", "Science", "World"];

  const fetchArticles = useCallback(async (category = null, pageNum = 1, append = false) => {
    try {
      const params = new URLSearchParams({ page: pageNum, limit: PAGE_LIMIT });
      if (category && category !== "All") params.set("category", category);
      const response = await axios.get(`${API}/articles?${params}`, { withCredentials: true });
      const data = response.data;
      if (append) {
        setArticles(prev => [...prev, ...data]);
      } else {
        setArticles(data);
      }
      setHasMore(data.length === PAGE_LIMIT);
    } catch (error) {
      console.error("Error fetching articles:", error);
    }
  }, []);

  const fetchDevelopingStories = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/developing-stories`, { withCredentials: true });
      setDevelopingStories(response.data);
    } catch (error) {
      console.error("Error fetching developing stories:", error);
    }
  }, []);

  const fetchNotifications = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/notifications`, { withCredentials: true });
      setNotifications(response.data.notifications || []);
      setUnreadCount(response.data.unread_count || 0);
    } catch (error) {
      console.error("Error fetching notifications:", error);
    }
  }, []);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([fetchArticles(), fetchDevelopingStories(), fetchNotifications()]);
      setLoading(false);
    };
    loadData();
  }, [fetchArticles, fetchDevelopingStories, fetchNotifications]);

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
    const cat = category === "All" ? null : category;
    setActiveCategory(cat);
    setPage(1);
    setHasMore(true);
    fetchArticles(cat, 1, false);
  };

  // Infinite scroll: load next page when sentinel enters viewport
  useEffect(() => {
    if (!sentinelRef.current) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !loadingMore && !loading) {
          const nextPage = page + 1;
          setPage(nextPage);
          setLoadingMore(true);
          fetchArticles(activeCategory, nextPage, true).finally(() => setLoadingMore(false));
        }
      },
      { rootMargin: "200px" }
    );
    observer.observe(sentinelRef.current);
    return () => observer.disconnect();
  }, [hasMore, loadingMore, loading, page, activeCategory, fetchArticles]);

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  const markNotificationsRead = async () => {
    try {
      await axios.post(`${API}/notifications/read`, {}, { withCredentials: true });
      setUnreadCount(0);
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

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center">
        <SuryaLogo className="w-16 h-16 animate-spin-slow" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0A0A0A]" data-testid="feed-page">
      {/* Header */}
      <header className="glass-nav sticky z-40 px-4" style={{ top: 0, paddingTop: 'var(--sat, 44px)', paddingBottom: '12px' }}>
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
              <SheetTrigger asChild>
                <button className="p-2 hover:bg-white/5 rounded-lg transition-colors" data-testid="menu-btn">
                  <Menu className="w-5 h-5 text-gray-400" />
                </button>
              </SheetTrigger>
              <SheetContent side="left" className="w-80 bg-[#0A0A0A] border-r border-white/10 p-0" style={{ display: 'flex', flexDirection: 'column', height: '100dvh' }}>
                {/* Time-aware crown */}
                <div style={{ flexShrink: 0, background: SIDEBAR_PHASES[sidebarPhase(_hour)], paddingTop: 'calc(var(--sat, 44px) + 22px)', paddingLeft: '20px', paddingRight: '20px', paddingBottom: '20px' }}>
                  <SuryaLogo className="w-11 h-11 animate-spin-slow" />
                  <h2 style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontWeight: 600, fontSize: '22px', color: '#F2EEE9', margin: '14px 0 0' }}>
                    {_greeting}{_firstName ? `, ${_firstName}` : ''}
                  </h2>
                  <p style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '11px', color: 'rgba(255,255,255,0.55)', margin: '5px 0 0', letterSpacing: '0.04em' }}>
                    {_timeStr} · Contemplate.
                  </p>
                </div>

                {/* Stylish divider — a red-glow hairline with a lit center */}
                <div style={{ flexShrink: 0, position: 'relative', height: '1px', background: 'linear-gradient(90deg, transparent, rgba(220,38,38,0.55) 50%, transparent)' }}>
                  <div style={{ position: 'absolute', top: '-2px', left: '50%', transform: 'translateX(-50%)', width: '5px', height: '5px', borderRadius: '50%', background: '#DC2626', boxShadow: '0 0 9px rgba(220,38,38,0.8)' }} />
                </div>

                {/* Scrollable nav */}
                <div style={{ flex: 1, overflowY: 'auto' }} className="hide-scrollbar">
                  <div className="p-4 space-y-2">
                    <p className="text-xs text-gray-500 uppercase tracking-wider px-3 py-2">Briefs</p>
                    <button
                      onClick={() => { navigate("/brief/morning"); setSidebarOpen(false); }}
                      className="w-full flex items-center gap-3 px-3 py-3 rounded-lg hover:bg-white/5 transition-colors text-left"
                      data-testid="morning-brief-nav"
                    >
                      <Sun className="w-5 h-5 text-amber-500" />
                      <span className="text-gray-300">Morning Brief</span>
                    </button>
                    <button
                      onClick={() => { navigate("/brief/midday"); setSidebarOpen(false); }}
                      className="w-full flex items-center gap-3 px-3 py-3 rounded-lg hover:bg-white/5 transition-colors text-left"
                      data-testid="midday-brief-nav"
                    >
                      <CloudSun className="w-5 h-5 text-orange-500" />
                      <span className="text-gray-300">Midday Update</span>
                    </button>
                    <button
                      onClick={() => { navigate("/brief/night"); setSidebarOpen(false); }}
                      className="w-full flex items-center gap-3 px-3 py-3 rounded-lg hover:bg-white/5 transition-colors text-left"
                      data-testid="night-brief-nav"
                    >
                      <Moon className="w-5 h-5 text-indigo-400" />
                      <span className="text-gray-300">Night Summary</span>
                    </button>

                    {developingStories.length > 0 && (
                      <>
                        <div className="h-px bg-white/10 my-4" />
                        <button
                          onClick={() => { navigate("/developing"); setSidebarOpen(false); }}
                          className="w-full relative overflow-hidden"
                          data-testid="developing-stories-nav"
                        >
                          <div className="flex items-center gap-3 px-3 py-3 rounded-lg bg-red-950/30 border border-red-900/50 relative z-10">
                            <div className="relative">
                              <Radio className="w-5 h-5 text-red-500" />
                              <div className="absolute inset-0 animate-pulse">
                                <div className="w-5 h-5 bg-red-500/30 rounded-full blur-sm" />
                              </div>
                            </div>
                            <div className="flex-1 text-left">
                              <span className="text-red-400 font-medium">Developing Stories</span>
                              <span className="text-red-500/60 text-xs ml-2">({developingStories.length} topic{developingStories.length !== 1 ? "s" : ""})</span>
                            </div>
                          </div>
                          <div className="absolute inset-0 bg-red-500/5 animate-pulse rounded-lg" />
                        </button>
                      </>
                    )}
                  </div>
                </div>

                {/* Sign out — a flex row, so it never overlaps the list */}
                <div style={{ flexShrink: 0, borderTop: '1px solid rgba(255,255,255,0.1)', padding: '12px 16px', paddingBottom: 'calc(12px + var(--sab, 8px))' }}>
                  <button
                    onClick={handleLogout}
                    className="w-full rounded-lg transition-colors hover:bg-red-500/10"
                    style={{ padding: '11px', color: '#DC6B5A', background: 'none', border: 'none', cursor: 'pointer', fontSize: '14px', fontWeight: 500 }}
                    data-testid="logout-btn"
                  >
                    Sign Out
                  </button>
                </div>
              </SheetContent>
            </Sheet>

            <div className="flex items-center gap-2">
              <SuryaLogo className="w-8 h-8" />
              <span className="font-serif text-xl text-white hidden sm:block">Chintan</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={openNotifications}
              className="p-2 hover:bg-white/5 rounded-lg transition-colors relative"
              data-testid="notifications-btn"
            >
              <Bell className="w-5 h-5 text-gray-400" />
              {unreadCount > 0 && (
                <span className="absolute top-1 right-1 w-2.5 h-2.5 bg-red-600 rounded-full animate-pulse" />
              )}
            </button>
            <button 
              onClick={() => navigate("/profile")}
              className="w-8 h-8 rounded-full bg-white/10 overflow-hidden"
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
      <main className="pb-24 px-4" style={{ paddingTop: '14px', height: '100vh', overflowY: 'auto' }}>
        <div className="max-w-6xl mx-auto">
          {/* Developing Stories Banner */}
          {developingStories.length > 0 && (
            <motion.div
              className="mb-5"
              initial={{ opacity: 0, y: -12 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <motion.div
                animate={{ boxShadow: ['0 0 0px rgba(220,38,38,0)', '0 0 18px rgba(220,38,38,0.12)', '0 0 0px rgba(220,38,38,0)'] }}
                transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
                style={{ background: '#131211', border: '1px solid rgba(220,38,38,0.28)', borderRadius: '16px', padding: '14px 16px' }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '7px', marginBottom: '12px' }}>
                  <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#DC2626' }} className="animate-pulse" />
                  <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '10px', letterSpacing: '0.16em', color: '#DC6B5A', textTransform: 'uppercase' }}>Developing</span>
                </div>
                <div className="overflow-x-auto hide-scrollbar">
                  <div style={{ display: 'flex', alignItems: 'stretch' }}>
                    {developingStories.slice(0, 4).map((story, i) => (
                      <React.Fragment key={story.story_id}>
                        {i > 0 && <div style={{ width: '1px', alignSelf: 'stretch', background: 'rgba(255,255,255,0.09)', margin: '2px 15px', flexShrink: 0 }} />}
                        <button
                          onClick={() => navigate(`/developing/${story.story_id}`)}
                          className="group"
                          style={{ flexShrink: 0, maxWidth: '210px', textAlign: 'left', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
                          data-testid={`developing-${story.story_id}`}
                        >
                          <p className="group-hover:text-red-400 transition-colors" style={{ color: '#ECE7E1', fontSize: '13.5px', fontWeight: 500, lineHeight: 1.32, margin: 0, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                            {story.title}
                          </p>
                          <p style={{ color: '#8A847C', fontSize: '11px', marginTop: '5px', fontFamily: "'JetBrains Mono', monospace" }}>{story.article_count} update{story.article_count !== 1 ? "s" : ""}</p>
                        </button>
                      </React.Fragment>
                    ))}
                  </div>
                </div>
              </motion.div>
            </motion.div>
          )}

          {/* Categories — active pill glides between chips */}
          <div className="mb-6 overflow-x-auto hide-scrollbar">
            <div className="flex gap-2">
              {categories.map((cat) => {
                const active = (cat === "All" && !activeCategory) || activeCategory === cat;
                return (
                  <button
                    key={cat}
                    onClick={() => handleCategoryChange(cat)}
                    className="relative rounded-full text-sm whitespace-nowrap"
                    style={{ flexShrink: 0, padding: "8px 16px", border: "none", cursor: "pointer", background: active ? "transparent" : "rgba(255,255,255,0.05)", color: active ? "#fff" : "#9ca3af", transition: "color .3s ease" }}
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

          {/* Articles Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <AnimatePresence>
              {articles.map((article, index) => (
                <motion.article
                  key={article.article_id}
                  className="news-card cursor-pointer"
                  onClick={() => navigate(`/article/${article.article_id}`)}
                  initial={{ opacity: 0, y: 18 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(index, 8) * 0.05, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                  whileTap={{ scale: 0.98 }}
                  data-testid={`article-card-${article.article_id}`}
                >
                  <div className="relative h-48 overflow-hidden">
                    <img 
                      src={article.image_url} 
                      alt={article.title}
                      className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-[#0A0A0A] to-transparent" />
                    
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
                    </div>
                    
                    <div className="absolute bottom-3 left-3">
                      <span className="category-badge text-xs">
                        {article.category}
                      </span>
                    </div>
                  </div>

                  <div className="p-4">
                    <h3 className="font-serif text-lg text-white mb-2 line-clamp-2 leading-tight">
                      {article.title}
                    </h3>
                    <p className="text-gray-500 text-sm line-clamp-2 mb-4">
                      {article.description}
                    </p>
                    
                    <div className="flex items-center justify-between text-xs text-gray-600">
                      <span className="font-mono">{article.source}</span>
                      <div className="flex items-center gap-3">
                        <span className="flex items-center gap-1">
                          <Eye className="w-3 h-3" />
                          {article.view_count || 0}
                        </span>
                      </div>
                    </div>
                  </div>
                </motion.article>
              ))}
            </AnimatePresence>
          </div>

          {articles.length === 0 && (
            <div className="text-center py-20">
              <p className="text-gray-500">No articles found</p>
            </div>
          )}

          {/* Infinite scroll sentinel */}
          <div ref={sentinelRef} className="h-1" />

          {loadingMore && (
            <div className="flex justify-center py-6">
              <SuryaLogo className="w-8 h-8 animate-spin-slow" />
            </div>
          )}
        </div>
      </main>

      <BottomNav />

      {/* Notifications Dialog */}
      <Dialog open={showNotifications} onOpenChange={setShowNotifications}>
        <DialogContent className="bg-[#0A0A0A] border-white/10 max-w-md max-h-[70vh]">
          <DialogHeader>
            <DialogTitle className="text-white flex items-center gap-2">
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
                    className={`p-4 rounded-lg ${notif.read ? 'bg-white/5' : 'bg-red-950/30 border border-red-900/30'}`}
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
                        <p className="text-white text-sm">
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
    </div>
  );
};

export default FeedPage;

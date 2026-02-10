import React, { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import axios from "axios";
import { 
  Search, Bell, User, Menu, Sun, CloudSun, Moon, 
  Bookmark, TrendingUp, ChevronRight, Clock, Eye, Radio, X
} from "lucide-react";
import { useAuth, SuryaLogo } from "../App";
import { Sheet, SheetContent, SheetTrigger } from "../components/ui/sheet";
import { ScrollArea } from "../components/ui/scroll-area";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

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

  const categories = ["All", "Politics", "Technology", "Business", "Sports", "Entertainment", "Science", "World"];

  const fetchArticles = useCallback(async (category = null) => {
    try {
      const params = category && category !== "All" ? `?category=${category}` : "";
      const response = await axios.get(`${API}/articles${params}`, { withCredentials: true });
      setArticles(response.data);
    } catch (error) {
      console.error("Error fetching articles:", error);
    }
  }, []);

  const fetchDevelopingStories = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/articles/developing`, { withCredentials: true });
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

  const handleCategoryChange = (category) => {
    setActiveCategory(category === "All" ? null : category);
    fetchArticles(category);
  };

  const getCurrentBrief = () => {
    const hour = new Date().getHours();
    if (hour >= 5 && hour < 12) return { type: "morning", icon: Sun, label: "Morning Brief" };
    if (hour >= 12 && hour < 18) return { type: "midday", icon: CloudSun, label: "Midday Update" };
    return { type: "night", icon: Moon, label: "Night Summary" };
  };

  const currentBrief = getCurrentBrief();

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
      <header className="glass-nav fixed top-0 left-0 right-0 z-40 px-4 py-3">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
              <SheetTrigger asChild>
                <button className="p-2 hover:bg-white/5 rounded-lg transition-colors" data-testid="menu-btn">
                  <Menu className="w-5 h-5 text-gray-400" />
                </button>
              </SheetTrigger>
              <SheetContent side="left" className="w-80 bg-[#0A0A0A] border-r border-white/10 p-0">
                <div className="p-6 border-b border-white/10">
                  <div className="flex items-center gap-3">
                    <SuryaLogo className="w-10 h-10" />
                    <div>
                      <h2 className="font-serif text-xl text-white">Chintan</h2>
                      <p className="text-xs text-gray-500">Contemplate.</p>
                    </div>
                  </div>
                </div>
                <ScrollArea className="h-[calc(100vh-180px)]">
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

                    <div className="h-px bg-white/10 my-4" />

                    {/* Developing Stories - Single Breathing Button */}
                    {developingStories.length > 0 && (
                      <button 
                        onClick={() => { navigate("/developing"); setSidebarOpen(false); }}
                        className="w-full relative overflow-hidden"
                        data-testid="developing-stories-nav"
                      >
                        <div className="flex items-center gap-3 px-3 py-3 rounded-lg bg-red-950/30 border border-red-900/50 relative z-10">
                          <div className="relative">
                            <Radio className="w-5 h-5 text-red-500" />
                            {/* Breathing glow effect */}
                            <div className="absolute inset-0 animate-pulse">
                              <div className="w-5 h-5 bg-red-500/30 rounded-full blur-sm" />
                            </div>
                          </div>
                          <div className="flex-1">
                            <span className="text-red-400 font-medium">Developing Stories</span>
                            <span className="text-red-500/60 text-xs ml-2">({developingStories.length} live)</span>
                          </div>
                        </div>
                        {/* Subtle breathing background glow */}
                        <div className="absolute inset-0 bg-red-500/5 animate-pulse rounded-lg" />
                      </button>
                    )}

                    <div className="h-px bg-white/10 my-4" />

                    <p className="text-xs text-gray-500 uppercase tracking-wider px-3 py-2">Menu</p>
                    <button 
                      onClick={() => { navigate("/bookmarks"); setSidebarOpen(false); }}
                      className="w-full flex items-center gap-3 px-3 py-3 rounded-lg hover:bg-white/5 transition-colors text-left"
                      data-testid="bookmarks-nav"
                    >
                      <Bookmark className="w-5 h-5 text-gray-400" />
                      <span className="text-gray-300">Bookmarks</span>
                    </button>
                    <button 
                      onClick={() => { navigate("/profile"); setSidebarOpen(false); }}
                      className="w-full flex items-center gap-3 px-3 py-3 rounded-lg hover:bg-white/5 transition-colors text-left"
                      data-testid="profile-nav"
                    >
                      <User className="w-5 h-5 text-gray-400" />
                      <span className="text-gray-300">Profile</span>
                    </button>
                  </div>
                </ScrollArea>
                <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-white/10">
                  <button 
                    onClick={handleLogout}
                    className="w-full py-2 text-red-500 hover:bg-red-500/10 rounded-lg transition-colors"
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
            <button className="p-2 hover:bg-white/5 rounded-lg transition-colors">
              <Search className="w-5 h-5 text-gray-400" />
            </button>
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
      <main className="pt-20 pb-24 px-4">
        <div className="max-w-6xl mx-auto">
          {/* Developing Stories Banner */}
          {developingStories.length > 0 && (
            <motion.div 
              className="mb-6"
              initial={{ opacity: 0, y: -20 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <div className="glass-card rounded-xl p-4 border-red-600/30">
                <div className="flex items-center gap-2 mb-3">
                  <span className="live-indicator">
                    <span className="live-dot" />
                    Developing
                  </span>
                </div>
                <div className="overflow-x-auto hide-scrollbar">
                  <div className="flex gap-4">
                    {developingStories.slice(0, 3).map((story) => (
                      <button
                        key={story.article_id}
                        onClick={() => navigate(`/article/${story.article_id}`)}
                        className="flex-shrink-0 text-left group"
                        data-testid={`developing-${story.article_id}`}
                      >
                        <p className="text-white text-sm font-medium group-hover:text-red-400 transition-colors line-clamp-2 max-w-[200px]">
                          {story.title}
                        </p>
                        <p className="text-gray-500 text-xs mt-1">{story.source}</p>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </motion.div>
          )}

          {/* Brief Button */}
          <motion.button
            onClick={() => navigate(`/brief/${currentBrief.type}`)}
            className="w-full glass-card rounded-xl p-4 mb-6 flex items-center justify-between group hover:border-red-600/30 transition-colors"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            data-testid="current-brief-btn"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-red-600/20 flex items-center justify-center">
                <currentBrief.icon className="w-5 h-5 text-red-500" />
              </div>
              <div className="text-left">
                <p className="text-white font-medium">{currentBrief.label}</p>
                <p className="text-gray-500 text-sm">Your personalized digest</p>
              </div>
            </div>
            <ChevronRight className="w-5 h-5 text-gray-500 group-hover:text-red-500 transition-colors" />
          </motion.button>

          {/* Categories */}
          <div className="mb-6 overflow-x-auto hide-scrollbar">
            <div className="flex gap-2">
              {categories.map((cat) => (
                <button
                  key={cat}
                  onClick={() => handleCategoryChange(cat)}
                  className={`px-4 py-2 rounded-full text-sm whitespace-nowrap transition-colors ${
                    (cat === "All" && !activeCategory) || activeCategory === cat
                      ? "bg-red-600 text-white"
                      : "bg-white/5 text-gray-400 hover:bg-white/10"
                  }`}
                  data-testid={`category-filter-${cat.toLowerCase()}`}
                >
                  {cat}
                </button>
              ))}
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
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.05 }}
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
        </div>
      </main>

      {/* Bottom Navigation (Mobile) */}
      <nav className="fixed bottom-0 left-0 right-0 glass-nav py-3 px-6 md:hidden">
        <div className="flex items-center justify-around">
          <button className="flex flex-col items-center gap-1 text-red-500">
            <TrendingUp className="w-5 h-5" />
            <span className="text-xs">Feed</span>
          </button>
          <button 
            onClick={() => navigate(`/brief/${currentBrief.type}`)}
            className="flex flex-col items-center gap-1 text-gray-500"
          >
            <currentBrief.icon className="w-5 h-5" />
            <span className="text-xs">Brief</span>
          </button>
          <button 
            onClick={() => navigate("/bookmarks")}
            className="flex flex-col items-center gap-1 text-gray-500"
          >
            <Bookmark className="w-5 h-5" />
            <span className="text-xs">Saved</span>
          </button>
          <button 
            onClick={() => navigate("/profile")}
            className="flex flex-col items-center gap-1 text-gray-500"
          >
            <User className="w-5 h-5" />
            <span className="text-xs">Profile</span>
          </button>
        </div>
      </nav>

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

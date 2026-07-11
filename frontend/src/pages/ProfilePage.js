import React, { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import axios from "axios";
import { toast } from "sonner";
import {
  ArrowLeft, User, Bookmark, BarChart2, LogOut, ChevronRight, ChevronDown,
  Edit3, Check, Loader2, Sparkles, Flame, BookOpen
} from "lucide-react";
import { useAuth, SuryaLogo } from "../App";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { ScrollArea } from "../components/ui/scroll-area";

const BACKEND_URL = "https://chintangithubio-production.up.railway.app";
const API = `${BACKEND_URL}/api`;

const MAX_NICHES_PER_CATEGORY = 3;

// Fallback taxonomy if /interests/categories can't be fetched (mirrors backend).
const FALLBACK_TAXONOMY = {
  Politics: ["Parliament", "Elections", "Judiciary", "International Relations", "State Politics"],
  Technology: ["AI & ML", "Startups", "Gadgets", "Fintech", "Space Tech", "Telecom"],
  Business: ["Markets", "Economy", "Startups", "Real Estate", "Banking", "Corporate"],
  Sports: ["Cricket", "Football", "Tennis", "Olympics", "Kabaddi", "Motorsport"],
  Entertainment: ["Bollywood", "OTT", "Music", "Television", "Regional Cinema"],
  Science: ["Space", "Health", "Environment", "Research", "Climate"],
  World: ["USA", "China", "Europe", "Middle East", "Southeast Asia"],
};

const ProfilePage = () => {
  const navigate = useNavigate();
  const { user, logout, checkAuth } = useAuth();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showEditInterests, setShowEditInterests] = useState(false);
  const [selectedInterests, setSelectedInterests] = useState([]);
  const [savingInterests, setSavingInterests] = useState(false);
  const [taxonomy, setTaxonomy] = useState(FALLBACK_TAXONOMY);
  const [expandedCats, setExpandedCats] = useState({});
  const [showPolls, setShowPolls] = useState(false);
  const [votedPolls, setVotedPolls] = useState([]);
  const [loadingPolls, setLoadingPolls] = useState(false);
  const [selectedPoll, setSelectedPoll] = useState(null);

  const fetchStats = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/users/stats`, { withCredentials: true });
      setStats(response.data);
    } catch (error) {
      console.error("Error fetching stats:", error);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchVotedPolls = useCallback(async () => {
    setLoadingPolls(true);
    try {
      const response = await axios.get(`${API}/users/voted-polls`, { withCredentials: true });
      setVotedPolls(response.data || []);
    } catch (error) {
      console.error("Error fetching voted polls:", error);
    } finally {
      setLoadingPolls(false);
    }
  }, []);

  useEffect(() => {
    fetchStats();
    if (user?.interests) setSelectedInterests(user.interests);
  }, [fetchStats, user]);

  // Pull the category → niches taxonomy from the backend (single source of truth).
  useEffect(() => {
    axios.get(`${API}/interests/categories`, { withCredentials: true })
      .then((r) => { if (r.data && typeof r.data === "object" && !Array.isArray(r.data)) setTaxonomy(r.data); })
      .catch(() => {});
  }, []);

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  const nicheCount = (cat) => (taxonomy[cat] || []).filter((n) => selectedInterests.includes(n)).length;

  const toggleCategory = (cat) => {
    setSelectedInterests((prev) => (prev.includes(cat) ? prev.filter((i) => i !== cat) : [...prev, cat]));
  };

  const toggleNiche = (cat, niche) => {
    setSelectedInterests((prev) => {
      if (prev.includes(niche)) return prev.filter((i) => i !== niche);
      if (nicheCount(cat) >= MAX_NICHES_PER_CATEGORY) {
        toast.error(`Up to ${MAX_NICHES_PER_CATEGORY} niches per category`);
        return prev;
      }
      return [...prev, niche];
    });
  };

  const saveInterests = async () => {
    if (selectedInterests.length < 3) {
      toast.error("Pick at least 3 interests");
      return;
    }
    setSavingInterests(true);
    try {
      await axios.put(`${API}/users/interests`, { interests: selectedInterests }, { withCredentials: true });
      await checkAuth();
      toast.success("Interests updated");
      setShowEditInterests(false);
    } catch (error) {
      toast.error("Couldn't update interests");
    } finally {
      setSavingInterests(false);
    }
  };

  const openPollsHistory = () => {
    setShowPolls(true);
    fetchVotedPolls();
  };

  const getPollStatus = (poll) => {
    if (!poll.created_at) return { active: true, daysLeft: 7 };
    const daysPassed = Math.floor((new Date() - new Date(poll.created_at)) / (1000 * 60 * 60 * 24));
    const daysLeft = 7 - daysPassed;
    return { active: daysLeft > 0, daysLeft: Math.max(0, daysLeft) };
  };

  const getTotalVotes = (poll) => (poll?.votes ? Object.values(poll.votes).reduce((a, b) => a + b, 0) : 0);
  const getVotePercentage = (poll, option) => {
    const total = getTotalVotes(poll);
    return total === 0 ? 0 : Math.round(((poll.votes[option] || 0) / total) * 100);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center">
        <SuryaLogo className="w-14 h-14 animate-spin-slow" />
      </div>
    );
  }

  const breakdown = stats?.category_breakdown ? Object.entries(stats.category_breakdown).sort(([, a], [, b]) => b - a) : [];
  const breakdownTotal = breakdown.reduce((sum, [, c]) => sum + c, 0);
  const hasInsight = stats && stats.articles_read > 0 && (stats.top_category || stats.blind_spot);

  const statTile = (num, label, Icon, onClick) => (
    <button
      onClick={onClick}
      style={{
        background: "#131211", borderRadius: "14px", padding: "14px 8px", textAlign: "center",
        border: onClick ? "1px solid rgba(220,38,38,0.25)" : "1px solid rgba(255,255,255,0.06)",
        cursor: onClick ? "pointer" : "default",
      }}
    >
      <div style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontWeight: 600, fontSize: "24px", color: "#F2EEE9", lineHeight: 1 }}>{num}</div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "4px", fontSize: "10.5px", color: onClick ? "#DC6B5A" : "#82828A", marginTop: "5px" }}>
        {Icon && <Icon className="w-3 h-3" />}{label}
      </div>
    </button>
  );

  return (
    <div style={{ minHeight: "100vh", background: "#0A0A0A" }} data-testid="profile-page">
      {/* Header */}
      <header className="sticky z-40 px-4" style={{ top: 0, paddingTop: "var(--sat, 44px)", paddingBottom: "12px", background: "rgba(10,10,10,0.72)", backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)" }}>
        <div style={{ maxWidth: "640px", margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <button onClick={() => navigate(-1)} style={{ padding: "8px", background: "none", border: "none", cursor: "pointer" }} data-testid="back-btn">
            <ArrowLeft className="w-5 h-5" style={{ color: "#9A938A" }} />
          </button>
          <span style={{ color: "#82828A", fontFamily: "'JetBrains Mono', monospace", fontSize: "11px", letterSpacing: "0.12em", textTransform: "uppercase" }}>Profile</span>
          <div style={{ width: "36px" }} />
        </div>
      </header>

      {/* Content */}
      <main style={{ padding: "20px 22px 48px", maxWidth: "640px", margin: "0 auto" }}>
        {/* Identity */}
        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} style={{ display: "flex", alignItems: "center", gap: "14px", marginBottom: "22px" }}>
          <div style={{ width: "60px", height: "60px", borderRadius: "50%", overflow: "hidden", flexShrink: 0, background: "#1a1917", border: "1px solid rgba(255,255,255,0.08)", display: "flex", alignItems: "center", justifyContent: "center" }}>
            {user?.picture ? <img src={user.picture} alt={user.name} style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : <User className="w-7 h-7" style={{ color: "#6E6862" }} />}
          </div>
          <div style={{ minWidth: 0, flex: 1 }}>
            <h1 style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontWeight: 600, fontSize: "22px", color: "#F2EEE9", margin: "0 0 2px" }}>{user?.name}</h1>
            <div style={{ wordBreak: "break-all", overflowWrap: "anywhere", fontSize: "12px", color: "#6E6862" }}>{user?.email}</div>
          </div>
        </motion.div>

        {/* Stat tiles */}
        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 }} style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "9px", marginBottom: "16px" }}>
          {statTile(stats?.articles_read || 0, "Read", BookOpen, null)}
          {statTile(stats?.bookmarks_count || 0, "Saved", Bookmark, () => navigate("/bookmarks"))}
          {statTile(stats?.streak_days || 0, "Day streak", Flame, null)}
        </motion.div>

        {/* Insight card — the intelligent moment */}
        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.14 }}
          style={{ background: "linear-gradient(135deg, rgba(220,38,38,0.09), #131211 62%)", border: "1px solid rgba(220,38,38,0.22)", borderRadius: "16px", padding: "16px", marginBottom: "24px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "6px", fontFamily: "'JetBrains Mono', monospace", fontSize: "9px", letterSpacing: "0.18em", color: "#DC6B5A", textTransform: "uppercase", marginBottom: "9px" }}>
            <Sparkles className="w-3 h-3" /> What Chintan noticed
          </div>
          <p style={{ margin: 0, fontFamily: "'Playfair Display', 'Georgia', serif", fontSize: "15.5px", lineHeight: 1.46, color: "#ECE7E1" }}>
            {hasInsight ? (
              <>
                {stats.top_category && (stats.top_pct >= 30
                  ? <>You leaned <b style={{ color: "#F0A090", fontWeight: 600 }}>{stats.top_pct}% into {stats.top_category}</b> recently. </>
                  : <><b style={{ color: "#F0A090", fontWeight: 600 }}>{stats.top_category}</b> led your reading recently. </>)}
                {stats.blind_spot && (stats.blind_spot_days == null
                  ? <>You haven't opened a <b style={{ color: "#F0A090", fontWeight: 600 }}>{stats.blind_spot}</b> story yet — your quietest corner.</>
                  : <>You haven't opened a <b style={{ color: "#F0A090", fontWeight: 600 }}>{stats.blind_spot}</b> story in {stats.blind_spot_days} days — your quietest corner.</>)}
              </>
            ) : (
              <>Read a few stories and Chintan will start spotting your patterns here.</>
            )}
          </p>
        </motion.div>

        {/* Reading breakdown */}
        {breakdown.length > 0 && (
          <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} style={{ marginBottom: "24px" }}>
            <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "9px", letterSpacing: "0.2em", color: "#5A544D", textTransform: "uppercase", marginBottom: "13px" }}>Reading breakdown</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "11px" }}>
              {breakdown.map(([category, count], idx) => {
                const percentage = Math.round((count / breakdownTotal) * 100);
                return (
                  <div key={category}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "5px" }}>
                      <span style={{ color: "#B6AFA6", fontSize: "13px" }}>{category}</span>
                      <span style={{ color: "#6E6862", fontSize: "11px", fontFamily: "'JetBrains Mono', monospace" }}>{percentage}%</span>
                    </div>
                    <div style={{ height: "6px", background: "rgba(255,255,255,0.05)", borderRadius: "3px", overflow: "hidden" }}>
                      <motion.div initial={{ width: 0 }} animate={{ width: `${percentage}%` }} transition={{ duration: 0.5, delay: 0.3 }}
                        style={{ height: "100%", borderRadius: "3px", background: idx === 0 ? "#DC2626" : "#5A544D" }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </motion.div>
        )}

        {/* Interests */}
        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.26 }} style={{ marginBottom: "24px" }}>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "9px", letterSpacing: "0.2em", color: "#5A544D", textTransform: "uppercase", marginBottom: "13px" }}>Your interests</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "7px" }}>
            {user?.interests?.map((interest) => (
              <span key={interest} style={{ padding: "6px 12px", background: "rgba(220,38,38,0.12)", color: "#E88A7C", borderRadius: "20px", fontSize: "12.5px" }}>{interest}</span>
            ))}
            <button onClick={() => setShowEditInterests(true)} data-testid="edit-interests-btn"
              style={{ display: "flex", alignItems: "center", gap: "5px", padding: "6px 12px", background: "#151412", border: "1px solid rgba(255,255,255,0.08)", color: "#8A847C", borderRadius: "20px", fontSize: "12.5px", cursor: "pointer" }}>
              <Edit3 className="w-3.5 h-3.5" /> Edit
            </button>
          </div>
        </motion.div>

        {/* Actions */}
        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.32 }} style={{ display: "flex", flexDirection: "column", gap: "9px" }}>
          <button onClick={openPollsHistory} data-testid="poll-history-btn" style={actionStyle}>
            <BarChart2 className="w-5 h-5" style={{ color: "#9A938A", flexShrink: 0 }} />
            <div style={{ flex: 1, textAlign: "left" }}>
              <div style={{ color: "#ECE7E1", fontSize: "14px" }}>Poll history</div>
              <div style={{ color: "#6E6862", fontSize: "11.5px" }}>Where you stood</div>
            </div>
            <ChevronRight className="w-4 h-4" style={{ color: "#4A453F" }} />
          </button>
          <button onClick={handleLogout} data-testid="logout-btn"
            style={{ ...actionStyle, justifyContent: "center", gap: "8px", color: "#DC6B5A", border: "1px solid rgba(220,38,38,0.2)" }}>
            <LogOut className="w-5 h-5" /> Sign out
          </button>
        </motion.div>

        {/* Footer */}
        <div style={{ textAlign: "center", marginTop: "40px" }}>
          <SuryaLogo className="w-7 h-7 mx-auto mb-2" style={{ opacity: 0.4 }} />
          <p style={{ color: "#4A453F", fontSize: "11px" }}>Chintan · Don't just consume. Contemplate.</p>
        </div>
      </main>

      {/* Edit Interests Dialog */}
      <Dialog open={showEditInterests} onOpenChange={setShowEditInterests}>
        <DialogContent className="bg-[#0A0A0A] border-white/10 max-w-md">
          <DialogHeader>
            <DialogTitle className="text-white">Edit interests</DialogTitle>
          </DialogHeader>
          <p className="text-gray-500 text-sm" style={{ marginTop: "2px" }}>
            Pick your topics — expand any for niches (up to {MAX_NICHES_PER_CATEGORY} each).
          </p>
          <ScrollArea className="max-h-[52vh]" style={{ marginTop: "10px" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px", paddingRight: "4px" }}>
              {Object.entries(taxonomy).map(([cat, niches]) => {
                const picked = selectedInterests.includes(cat);
                const open = !!expandedCats[cat];
                const nCount = nicheCount(cat);
                return (
                  <div key={cat} style={{ border: "1px solid rgba(255,255,255,0.07)", borderRadius: "12px", overflow: "hidden" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "10px", padding: "11px 12px" }}>
                      <button onClick={() => toggleCategory(cat)} aria-label={`Select ${cat}`}
                        style={{ width: "20px", height: "20px", borderRadius: "6px", flexShrink: 0, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
                          background: picked ? "#DC2626" : "transparent", border: picked ? "1.5px solid #DC2626" : "1.5px solid #4A453F" }}>
                        {picked && <Check className="w-3 h-3 text-white" />}
                      </button>
                      <button onClick={() => setExpandedCats((p) => ({ ...p, [cat]: !p[cat] }))}
                        style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "space-between", background: "none", border: "none", cursor: "pointer" }}>
                        <span style={{ color: "#ECE7E1", fontSize: "14.5px", fontWeight: 500 }}>{cat}{nCount > 0 && <span style={{ color: "#DC6B5A", fontSize: "12px", marginLeft: "7px" }}>{nCount}</span>}</span>
                        <ChevronDown className="w-4 h-4" style={{ color: "#6E6862", transform: open ? "rotate(180deg)" : "none", transition: "transform .2s" }} />
                      </button>
                    </div>
                    {open && (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "7px", padding: "0 12px 12px" }}>
                        {(niches || []).map((niche) => {
                          const on = selectedInterests.includes(niche);
                          const dim = !on && nCount >= MAX_NICHES_PER_CATEGORY;
                          return (
                            <button key={niche} onClick={() => toggleNiche(cat, niche)}
                              style={{ fontSize: "12px", padding: "6px 12px", borderRadius: "16px", cursor: "pointer", opacity: dim ? 0.4 : 1,
                                background: on ? "rgba(220,38,38,0.14)" : "#1a1917", color: on ? "#F0A090" : "#B6AFA6",
                                border: on ? "1px solid rgba(220,38,38,0.5)" : "1px solid rgba(255,255,255,0.08)" }}>
                              {niche}
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </ScrollArea>
          <div className="flex gap-3 pt-4 border-t border-white/10" style={{ marginTop: "12px" }}>
            <button onClick={() => setShowEditInterests(false)} className="flex-1 py-2 px-4 rounded-lg bg-white/5 text-gray-400 hover:bg-white/10 transition-colors">Cancel</button>
            <button onClick={saveInterests} disabled={savingInterests || selectedInterests.length < 3}
              className="flex-1 py-2 px-4 rounded-lg bg-red-600 text-white hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2">
              {savingInterests ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />} Save
            </button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Poll History Dialog */}
      <Dialog open={showPolls} onOpenChange={setShowPolls}>
        <DialogContent className="bg-[#0A0A0A] border-white/10 max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-white flex items-center gap-2">
              <BarChart2 className="w-5 h-5 text-red-500" /> Poll history
            </DialogTitle>
          </DialogHeader>
          <ScrollArea className="max-h-[60vh]">
            {loadingPolls ? (
              <div className="flex items-center justify-center py-12"><SuryaLogo className="w-12 h-12 animate-spin-slow" /></div>
            ) : votedPolls.length > 0 ? (
              <div className="space-y-4 py-4">
                {votedPolls.map((poll) => {
                  const status = getPollStatus(poll);
                  return (
                    <div key={poll.poll_id}
                      className={`glass-card rounded-xl p-4 cursor-pointer hover:border-red-500/30 transition-colors ${selectedPoll?.poll_id === poll.poll_id ? "border-red-500/50" : ""}`}
                      onClick={() => setSelectedPoll(selectedPoll?.poll_id === poll.poll_id ? null : poll)}>
                      <div className="flex items-start justify-between mb-2">
                        <p className="text-white font-medium text-sm flex-1 pr-4">{poll.question}</p>
                        <span className={`text-xs px-2 py-1 rounded ${status.active ? "bg-green-500/20 text-green-400" : "bg-gray-500/20 text-gray-400"}`}>
                          {status.active ? `${status.daysLeft}d left` : "Closed"}
                        </span>
                      </div>
                      <p className="text-gray-500 text-xs mb-2">Your vote: <span className="text-red-400">{poll.user_vote}</span></p>
                      <AnimatePresence>
                        {selectedPoll?.poll_id === poll.poll_id && (
                          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
                            <div className="pt-3 mt-3 border-t border-white/10 space-y-2">
                              {poll.options.map((option) => {
                                const percentage = getVotePercentage(poll, option);
                                const isUserVote = option === poll.user_vote;
                                return (
                                  <div key={option} className="relative">
                                    <div className={`p-2 rounded-lg ${isUserVote ? "bg-red-500/10" : "bg-white/5"}`}>
                                      <div className={`absolute inset-0 rounded-lg ${isUserVote ? "bg-red-500/20" : "bg-white/5"}`} style={{ width: `${percentage}%` }} />
                                      <div className="relative flex items-center justify-between">
                                        <span className={`text-sm ${isUserVote ? "text-red-400" : "text-gray-400"}`}>{option} {isUserVote && "✓"}</span>
                                        <span className="text-gray-500 text-xs font-mono">{percentage}%</span>
                                      </div>
                                    </div>
                                  </div>
                                );
                              })}
                              <p className="text-gray-600 text-xs text-center pt-2">{getTotalVotes(poll)} total votes</p>
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-center py-12">
                <BarChart2 className="w-12 h-12 text-gray-700 mx-auto mb-4" />
                <p className="text-gray-500">No polls voted in yet</p>
                <p className="text-gray-600 text-sm mt-1">Vote on polls in articles to see them here</p>
              </div>
            )}
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </div>
  );
};

const actionStyle = {
  display: "flex", alignItems: "center", gap: "12px", width: "100%",
  background: "#131211", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "13px",
  padding: "14px 15px", cursor: "pointer",
};

export default ProfilePage;

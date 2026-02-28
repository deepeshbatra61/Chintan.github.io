import React, { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import axios from "axios";
import { toast } from "sonner";
import { 
  ArrowLeft, User, Bookmark, BarChart2,
  LogOut, ChevronRight, Edit3, FileText,
  Check, Loader2, Clock
} from "lucide-react";
import { useAuth, SuryaLogo } from "../App";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { ScrollArea } from "../components/ui/scroll-area";

const BACKEND_URL = "https://chintangithubio-production.up.railway.app";
const API = `${BACKEND_URL}/api`;

const INTEREST_CATEGORIES = ["Politics", "Technology", "Business", "Sports", "Entertainment", "Science", "World", "Lifestyle"];

const ProfilePage = () => {
  const navigate = useNavigate();
  const { user, logout, checkAuth } = useAuth();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showEditInterests, setShowEditInterests] = useState(false);
  const [selectedInterests, setSelectedInterests] = useState([]);
  const [savingInterests, setSavingInterests] = useState(false);
  const [showReport, setShowReport] = useState(false);
  const [report, setReport] = useState(null);
  const [generatingReport, setGeneratingReport] = useState(false);
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
    if (user?.interests) {
      setSelectedInterests(user.interests);
    }
  }, [fetchStats, user]);

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  const toggleInterest = (interest) => {
    if (selectedInterests.includes(interest)) {
      setSelectedInterests(selectedInterests.filter(i => i !== interest));
    } else {
      setSelectedInterests([...selectedInterests, interest]);
    }
  };

  const saveInterests = async () => {
    if (selectedInterests.length < 3) {
      toast.error("Please select at least 3 interests");
      return;
    }
    setSavingInterests(true);
    try {
      await axios.put(
        `${API}/users/interests`,
        { interests: selectedInterests },
        { withCredentials: true }
      );
      await checkAuth();
      toast.success("Interests updated!");
      setShowEditInterests(false);
    } catch (error) {
      toast.error("Failed to update interests");
    } finally {
      setSavingInterests(false);
    }
  };

  const generateWeeklyReport = async () => {
    setGeneratingReport(true);
    setShowReport(true);
    
    try {
      const response = await axios.get(`${API}/users/weekly-report`, { withCredentials: true });
      setReport(response.data);
    } catch (error) {
      const localReport = generateLocalReport();
      setReport(localReport);
    } finally {
      setGeneratingReport(false);
    }
  };

  const generateLocalReport = () => {
    if (!stats) return null;
    
    const topCategory = stats.category_breakdown 
      ? Object.entries(stats.category_breakdown).sort(([,a], [,b]) => b - a)[0]?.[0]
      : null;
    
    const insights = [];
    
    if (stats.articles_read > 0) {
      insights.push(`You've engaged with ${stats.articles_read} articles this week, showing a healthy appetite for staying informed.`);
    }
    
    if (topCategory) {
      insights.push(`${topCategory} has captured most of your attention. This focus helps you build expertise in areas that matter to you.`);
    }
    
    if (stats.bookmarks_count > 0) {
      insights.push(`You've saved ${stats.bookmarks_count} articles for later, building a personal knowledge library.`);
    }

    return {
      summary: insights.length > 0 
        ? insights.join('\n\n')
        : "Start reading articles to generate your personalized weekly insights.",
      stats: {
        articlesRead: stats.articles_read || 0,
        topCategory: topCategory || "Not enough data"
      }
    };
  };

  const openPollsHistory = () => {
    setShowPolls(true);
    fetchVotedPolls();
  };

  const getPollStatus = (poll) => {
    if (!poll.created_at) return { active: true, daysLeft: 7 };
    const createdDate = new Date(poll.created_at);
    const now = new Date();
    const daysPassed = Math.floor((now - createdDate) / (1000 * 60 * 60 * 24));
    const daysLeft = 7 - daysPassed;
    return {
      active: daysLeft > 0,
      daysLeft: Math.max(0, daysLeft)
    };
  };

  const getTotalVotes = (poll) => {
    if (!poll?.votes) return 0;
    return Object.values(poll.votes).reduce((a, b) => a + b, 0);
  };

  const getVotePercentage = (poll, option) => {
    const total = getTotalVotes(poll);
    if (total === 0) return 0;
    return Math.round((poll.votes[option] || 0) / total * 100);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center">
        <SuryaLogo className="w-16 h-16 animate-spin-slow" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0A0A0A]" data-testid="profile-page">
      {/* Header */}
      <header className="glass-nav fixed top-0 left-0 right-0 z-40 px-4 py-3">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <button 
            onClick={() => navigate(-1)}
            className="p-2 hover:bg-white/5 rounded-lg transition-colors"
            data-testid="back-btn"
          >
            <ArrowLeft className="w-5 h-5 text-gray-400" />
          </button>
          
          <span className="text-white font-medium">Profile</span>

          <div className="w-9" />
        </div>
      </header>

      {/* Content */}
      <main className="pt-20 pb-12 px-6">
        <div className="max-w-3xl mx-auto">
          {/* Profile Card */}
          <motion.div
            className="glass-card rounded-2xl p-6 mb-8"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <div className="flex items-center gap-4">
              <div className="w-20 h-20 rounded-full bg-white/10 overflow-hidden flex-shrink-0">
                {user?.picture ? (
                  <img src={user.picture} alt={user.name} className="w-full h-full object-cover" />
                ) : (
                  <div className="w-full h-full flex items-center justify-center">
                    <User className="w-10 h-10 text-gray-500" />
                  </div>
                )}
              </div>
              <div>
                <h1 className="font-serif text-2xl text-white mb-1">{user?.name}</h1>
                <p className="text-gray-500 text-sm">{user?.email}</p>
              </div>
            </div>
          </motion.div>

          {/* Stats Grid - Simplified */}
          <motion.div
            className="grid grid-cols-2 gap-4 mb-8"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
          >
            <div className="glass-card rounded-xl p-4 text-center">
              <Bookmark className="w-6 h-6 text-red-500 mx-auto mb-2" />
              <p className="text-2xl font-bold text-white">
                {stats?.bookmarks_count || 0}
              </p>
              <p className="text-gray-500 text-xs">Bookmarks</p>
            </div>
            
            <div className="glass-card rounded-xl p-4 text-center">
              <BarChart2 className="w-6 h-6 text-red-500 mx-auto mb-2" />
              <p className="text-2xl font-bold text-white">
                {stats?.articles_read || 0}
              </p>
              <p className="text-gray-500 text-xs">Articles Read</p>
            </div>
          </motion.div>

          {/* Weekly Report Button */}
          <motion.button
            onClick={generateWeeklyReport}
            className="w-full glass-card rounded-xl p-4 mb-4 flex items-center justify-between hover:border-red-500/30 transition-colors group"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 }}
            data-testid="weekly-report-btn"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-red-600/20 flex items-center justify-center">
                <FileText className="w-5 h-5 text-red-500" />
              </div>
              <div className="text-left">
                <p className="text-white font-medium">Weekly Reading Report</p>
                <p className="text-gray-500 text-sm">Get a personalized summary</p>
              </div>
            </div>
            <ChevronRight className="w-5 h-5 text-gray-500 group-hover:text-red-500 transition-colors" />
          </motion.button>

          {/* Poll History Button */}
          <motion.button
            onClick={openPollsHistory}
            className="w-full glass-card rounded-xl p-4 mb-8 flex items-center justify-between hover:border-red-500/30 transition-colors group"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            data-testid="poll-history-btn"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-red-600/20 flex items-center justify-center">
                <BarChart2 className="w-5 h-5 text-red-500" />
              </div>
              <div className="text-left">
                <p className="text-white font-medium">Poll History</p>
                <p className="text-gray-500 text-sm">View polls you've voted in</p>
              </div>
            </div>
            <ChevronRight className="w-5 h-5 text-gray-500 group-hover:text-red-500 transition-colors" />
          </motion.button>

          {/* Interests with Edit Button */}
          <motion.div
            className="glass-card rounded-xl p-6 mb-8"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.25 }}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-white font-medium">Your Interests</h2>
              <button
                onClick={() => setShowEditInterests(true)}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white transition-colors text-sm"
                data-testid="edit-interests-btn"
              >
                <Edit3 className="w-4 h-4" />
                Edit
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {user?.interests?.map(interest => (
                <span 
                  key={interest}
                  className="px-3 py-1.5 bg-red-600/20 text-red-400 rounded-full text-sm"
                >
                  {interest}
                </span>
              ))}
              {(!user?.interests || user.interests.length === 0) && (
                <p className="text-gray-500 text-sm">No interests selected</p>
              )}
            </div>
          </motion.div>

          {/* Category Breakdown */}
          {stats?.category_breakdown && Object.keys(stats.category_breakdown).length > 0 && (
            <motion.div
              className="glass-card rounded-xl p-6 mb-8"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
            >
              <h2 className="text-white font-medium mb-4">Reading Breakdown</h2>
              <div className="space-y-3">
                {Object.entries(stats.category_breakdown)
                  .sort(([,a], [,b]) => b - a)
                  .map(([category, count]) => {
                    const total = Object.values(stats.category_breakdown).reduce((a, b) => a + b, 0);
                    const percentage = Math.round((count / total) * 100);
                    return (
                      <div key={category}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-gray-400 text-sm">{category}</span>
                          <span className="text-gray-500 text-xs font-mono">{percentage}%</span>
                        </div>
                        <div className="h-2 bg-white/5 rounded-full overflow-hidden">
                          <motion.div 
                            className="h-full bg-red-600 rounded-full"
                            initial={{ width: 0 }}
                            animate={{ width: `${percentage}%` }}
                            transition={{ duration: 0.5, delay: 0.5 }}
                          />
                        </div>
                      </div>
                    );
                  })}
              </div>
            </motion.div>
          )}

          {/* Menu Items */}
          <motion.div
            className="space-y-2"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.35 }}
          >
            <button
              onClick={() => navigate("/bookmarks")}
              className="w-full glass-card rounded-xl p-4 flex items-center justify-between hover:border-white/20 transition-colors"
              data-testid="bookmarks-link"
            >
              <div className="flex items-center gap-3">
                <Bookmark className="w-5 h-5 text-gray-400" />
                <span className="text-white">Saved Articles</span>
              </div>
              <ChevronRight className="w-5 h-5 text-gray-500" />
            </button>

            <button
              onClick={handleLogout}
              className="w-full glass-card rounded-xl p-4 flex items-center gap-3 text-red-500 hover:bg-red-500/10 transition-colors"
              data-testid="logout-btn"
            >
              <LogOut className="w-5 h-5" />
              <span>Sign Out</span>
            </button>
          </motion.div>

          {/* Footer */}
          <div className="text-center mt-12">
            <SuryaLogo className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p className="text-gray-600 text-xs">
              Chintan • Don't just consume. Contemplate.
            </p>
          </div>
        </div>
      </main>

      {/* Edit Interests Dialog */}
      <Dialog open={showEditInterests} onOpenChange={setShowEditInterests}>
        <DialogContent className="bg-[#0A0A0A] border-white/10 max-w-md">
          <DialogHeader>
            <DialogTitle className="text-white">Edit Interests</DialogTitle>
          </DialogHeader>
          
          <div className="py-4">
            <p className="text-gray-500 text-sm mb-4">Select at least 3 topics ({selectedInterests.length} selected)</p>
            <div className="flex flex-wrap gap-2">
              {INTEREST_CATEGORIES.map(interest => (
                <button
                  key={interest}
                  onClick={() => toggleInterest(interest)}
                  className={`px-4 py-2 rounded-full text-sm transition-colors ${
                    selectedInterests.includes(interest)
                      ? "bg-red-600 text-white"
                      : "bg-white/5 text-gray-400 hover:bg-white/10"
                  }`}
                >
                  {interest}
                </button>
              ))}
            </div>
          </div>

          <div className="flex gap-3 pt-4 border-t border-white/10">
            <button
              onClick={() => setShowEditInterests(false)}
              className="flex-1 py-2 px-4 rounded-lg bg-white/5 text-gray-400 hover:bg-white/10 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={saveInterests}
              disabled={savingInterests || selectedInterests.length < 3}
              className="flex-1 py-2 px-4 rounded-lg bg-red-600 text-white hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {savingInterests ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
              Save
            </button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Weekly Report Dialog */}
      <Dialog open={showReport} onOpenChange={setShowReport}>
        <DialogContent className="bg-[#0A0A0A] border-white/10 max-w-lg max-h-[80vh]">
          <DialogHeader>
            <DialogTitle className="text-white flex items-center gap-2">
              <FileText className="w-5 h-5 text-red-500" />
              Your Weekly Reading Report
            </DialogTitle>
          </DialogHeader>
          
          <ScrollArea className="max-h-[60vh]">
            {generatingReport ? (
              <div className="flex items-center justify-center py-12">
                <SuryaLogo className="w-12 h-12 animate-spin-slow" />
              </div>
            ) : report ? (
              <div className="space-y-6 py-4">
                <div className="grid grid-cols-2 gap-3">
                  <div className="glass-card rounded-lg p-3 text-center">
                    <p className="text-2xl font-bold text-white">{report.stats?.articlesRead || 0}</p>
                    <p className="text-gray-500 text-xs">Articles</p>
                  </div>
                  <div className="glass-card rounded-lg p-3 text-center">
                    <p className="text-lg font-bold text-white truncate">{report.stats?.topCategory || '-'}</p>
                    <p className="text-gray-500 text-xs">Top Interest</p>
                  </div>
                </div>

                <div className="glass-card rounded-xl p-5">
                  <h3 className="text-red-500 font-mono text-xs uppercase tracking-wider mb-3">Your Week in Review</h3>
                  <div className="text-gray-300 leading-relaxed text-sm whitespace-pre-line">
                    {report.summary}
                  </div>
                </div>

                <p className="text-gray-600 text-xs text-center italic">
                  Keep contemplating. Every article makes you wiser.
                </p>
              </div>
            ) : (
              <p className="text-gray-500 text-center py-8">Unable to generate report</p>
            )}
          </ScrollArea>
        </DialogContent>
      </Dialog>

      {/* Poll History Dialog */}
      <Dialog open={showPolls} onOpenChange={setShowPolls}>
        <DialogContent className="bg-[#0A0A0A] border-white/10 max-w-lg max-h-[80vh]">
          <DialogHeader>
            <DialogTitle className="text-white flex items-center gap-2">
              <BarChart2 className="w-5 h-5 text-red-500" />
              Poll History
            </DialogTitle>
          </DialogHeader>
          
          <ScrollArea className="max-h-[60vh]">
            {loadingPolls ? (
              <div className="flex items-center justify-center py-12">
                <SuryaLogo className="w-12 h-12 animate-spin-slow" />
              </div>
            ) : votedPolls.length > 0 ? (
              <div className="space-y-4 py-4">
                {votedPolls.map((poll) => {
                  const status = getPollStatus(poll);
                  return (
                    <div 
                      key={poll.poll_id}
                      className={`glass-card rounded-xl p-4 cursor-pointer hover:border-red-500/30 transition-colors ${
                        selectedPoll?.poll_id === poll.poll_id ? 'border-red-500/50' : ''
                      }`}
                      onClick={() => setSelectedPoll(selectedPoll?.poll_id === poll.poll_id ? null : poll)}
                    >
                      <div className="flex items-start justify-between mb-2">
                        <p className="text-white font-medium text-sm flex-1 pr-4">{poll.question}</p>
                        <span className={`text-xs px-2 py-1 rounded ${
                          status.active 
                            ? 'bg-green-500/20 text-green-400' 
                            : 'bg-gray-500/20 text-gray-400'
                        }`}>
                          {status.active ? `${status.daysLeft}d left` : 'Closed'}
                        </span>
                      </div>
                      
                      <p className="text-gray-500 text-xs mb-2">
                        Your vote: <span className="text-red-400">{poll.user_vote}</span>
                      </p>

                      {/* Expanded view */}
                      <AnimatePresence>
                        {selectedPoll?.poll_id === poll.poll_id && (
                          <motion.div
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: "auto", opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            className="overflow-hidden"
                          >
                            <div className="pt-3 mt-3 border-t border-white/10 space-y-2">
                              {poll.options.map(option => {
                                const percentage = getVotePercentage(poll, option);
                                const isUserVote = option === poll.user_vote;
                                return (
                                  <div key={option} className="relative">
                                    <div className={`p-2 rounded-lg ${isUserVote ? 'bg-red-500/10' : 'bg-white/5'}`}>
                                      <div 
                                        className={`absolute inset-0 rounded-lg ${isUserVote ? 'bg-red-500/20' : 'bg-white/5'}`}
                                        style={{ width: `${percentage}%` }}
                                      />
                                      <div className="relative flex items-center justify-between">
                                        <span className={`text-sm ${isUserVote ? 'text-red-400' : 'text-gray-400'}`}>
                                          {option} {isUserVote && '✓'}
                                        </span>
                                        <span className="text-gray-500 text-xs font-mono">{percentage}%</span>
                                      </div>
                                    </div>
                                  </div>
                                );
                              })}
                              <p className="text-gray-600 text-xs text-center pt-2">
                                {getTotalVotes(poll)} total votes
                              </p>
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
                <p className="text-gray-600 text-sm mt-1">
                  Vote on polls in articles to see them here
                </p>
              </div>
            )}
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ProfilePage;

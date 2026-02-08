import React, { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import axios from "axios";
import { 
  ArrowLeft, User, Clock, BookOpen, Bookmark, 
  TrendingUp, Settings, LogOut, ChevronRight
} from "lucide-react";
import { useAuth, SuryaLogo } from "../App";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const ProfilePage = () => {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

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

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  const formatTime = (seconds) => {
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
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

          {/* Stats Grid */}
          <motion.div
            className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
          >
            <div className="glass-card rounded-xl p-4 text-center">
              <Clock className="w-6 h-6 text-red-500 mx-auto mb-2" />
              <p className="text-2xl font-bold text-white">
                {formatTime(stats?.total_reading_time || 0)}
              </p>
              <p className="text-gray-500 text-xs">Reading Time</p>
            </div>
            
            <div className="glass-card rounded-xl p-4 text-center">
              <BookOpen className="w-6 h-6 text-red-500 mx-auto mb-2" />
              <p className="text-2xl font-bold text-white">
                {stats?.articles_read || 0}
              </p>
              <p className="text-gray-500 text-xs">Articles Read</p>
            </div>
            
            <div className="glass-card rounded-xl p-4 text-center">
              <TrendingUp className="w-6 h-6 text-red-500 mx-auto mb-2" />
              <p className="text-2xl font-bold text-white">
                {stats?.articles_completed || 0}
              </p>
              <p className="text-gray-500 text-xs">Completed</p>
            </div>
            
            <div className="glass-card rounded-xl p-4 text-center">
              <Bookmark className="w-6 h-6 text-red-500 mx-auto mb-2" />
              <p className="text-2xl font-bold text-white">
                {stats?.bookmarks_count || 0}
              </p>
              <p className="text-gray-500 text-xs">Bookmarks</p>
            </div>
          </motion.div>

          {/* Interests */}
          <motion.div
            className="glass-card rounded-xl p-6 mb-8"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
          >
            <h2 className="text-white font-medium mb-4">Your Interests</h2>
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
            transition={{ delay: 0.4 }}
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
    </div>
  );
};

export default ProfilePage;

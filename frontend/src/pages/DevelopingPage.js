import React, { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import axios from "axios";
import { ArrowLeft, Radio, Swords, Trophy, Clock, ChevronRight } from "lucide-react";
import { SuryaLogo } from "../App";

const BACKEND_URL = "https://chintangithubio-production.up.railway.app";
const API = `${BACKEND_URL}/api`;

const themeConfig = {
  war: {
    icon: Swords,
    color: "text-red-400",
    bg: "bg-red-500/10",
    border: "border-red-900/40",
    badge: "bg-red-950/80 text-red-400",
  },
  cricket: {
    icon: Trophy,
    color: "text-emerald-400",
    bg: "bg-emerald-500/10",
    border: "border-emerald-900/40",
    badge: "bg-emerald-950/80 text-emerald-400",
  },
};

const DevelopingPage = () => {
  const navigate = useNavigate();
  const [topics, setTopics] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchTopics = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/developing-stories`, { withCredentials: true });
      setTopics(response.data);
    } catch (error) {
      console.error("Error fetching developing stories:", error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTopics();
    const interval = setInterval(fetchTopics, 60000);
    return () => clearInterval(interval);
  }, [fetchTopics]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center">
        <SuryaLogo className="w-16 h-16 animate-spin-slow" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0A0A0A]" data-testid="developing-page">
      {/* Ambient red glow */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[300px] bg-red-500/5 rounded-full blur-3xl" />
      </div>

      {/* Header */}
      <header className="glass-nav fixed left-0 right-0 z-40 px-4 py-3" style={{ top: 'var(--sat)' }}>
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <button
            onClick={() => navigate(-1)}
            className="p-2 hover:bg-white/5 rounded-lg transition-colors"
            data-testid="back-btn"
          >
            <ArrowLeft className="w-5 h-5 text-gray-400" />
          </button>
          <div className="flex items-center gap-2">
            <div className="relative">
              <Radio className="w-5 h-5 text-red-500" />
              <div className="absolute inset-0 animate-ping opacity-50">
                <Radio className="w-5 h-5 text-red-500" />
              </div>
            </div>
            <span className="text-white font-medium">Developing Stories</span>
          </div>
          <div className="w-9" />
        </div>
      </header>

      {/* Content */}
      <main className="relative z-10 pb-12 px-6" style={{ paddingTop: 'calc(var(--sat) + 60px)' }}>
        <div className="max-w-2xl mx-auto">
          {/* Hero */}
          <motion.div
            className="text-center mb-10"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <div className="w-20 h-20 rounded-full bg-red-600/20 flex items-center justify-center mx-auto mb-6 relative">
              <Radio className="w-10 h-10 text-red-500" />
              <div className="absolute inset-0 rounded-full bg-red-500/20 animate-pulse" />
            </div>
            <h1 className="font-serif text-3xl font-bold text-white mb-3">Live & Developing</h1>
            <p className="text-gray-400 text-sm">Stories still unfolding. Auto-updated.</p>
          </motion.div>

          {/* Topic cards */}
          <div className="space-y-4">
            {topics.map((topic, idx) => {
              const cfg = themeConfig[topic.theme] || themeConfig.war;
              const Icon = cfg.icon;
              return (
                <motion.button
                  key={topic.story_id}
                  onClick={() => navigate(`/developing/${topic.story_id}`)}
                  className={`w-full text-left glass-card rounded-xl p-5 border ${cfg.border} hover:bg-white/5 transition-colors group`}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: idx * 0.1 }}
                  data-testid={`topic-${topic.story_id}`}
                >
                  <div className="flex items-start gap-4">
                    <div className={`w-10 h-10 rounded-full ${cfg.bg} flex items-center justify-center flex-shrink-0 mt-0.5`}>
                      <Icon className={`w-5 h-5 ${cfg.color}`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className={`text-xs font-mono px-2 py-0.5 rounded ${cfg.badge} flex items-center gap-1`}>
                          <span className={`w-1.5 h-1.5 rounded-full animate-pulse ${topic.theme === "war" ? "bg-red-400" : "bg-emerald-400"}`} />
                          LIVE
                        </span>
                        <span className="text-gray-600 text-xs font-mono">
                          {topic.article_count} update{topic.article_count !== 1 ? "s" : ""}
                        </span>
                      </div>
                      <h2 className={`text-white font-semibold text-base leading-snug group-hover:${cfg.color} transition-colors`}>
                        {topic.title}
                      </h2>
                      {topic.latest_article && (
                        <p className="text-gray-500 text-sm mt-1.5 line-clamp-2 leading-snug">
                          {topic.latest_article.title}
                        </p>
                      )}
                    </div>
                    <ChevronRight className={`w-4 h-4 ${cfg.color} opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0 mt-1`} />
                  </div>
                </motion.button>
              );
            })}
          </div>

          {topics.length === 0 && (
            <motion.div
              className="text-center py-20"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
            >
              <Radio className="w-12 h-12 text-gray-700 mx-auto mb-4" />
              <p className="text-gray-500">No developing stories right now</p>
              <p className="text-gray-600 text-sm mt-1">Check back later for live updates</p>
            </motion.div>
          )}

          <div className="text-center mt-8">
            <p className="text-gray-600 text-xs flex items-center justify-center gap-2">
              <Clock className="w-3 h-3" />
              Auto-refreshes every 60 seconds
            </p>
          </div>
        </div>
      </main>
    </div>
  );
};

export default DevelopingPage;

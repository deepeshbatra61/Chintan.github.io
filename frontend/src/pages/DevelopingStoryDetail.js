import React, { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import axios from "axios";
import { ArrowLeft, Swords, Trophy, Clock, ExternalLink } from "lucide-react";
import { SuryaLogo } from "../App";

const BACKEND_URL = "https://chintangithubio-production.up.railway.app";
const API = `${BACKEND_URL}/api`;

const themeConfig = {
  war: {
    icon: Swords,
    gradient: "from-red-900/40 via-red-950/20 to-[#0A0A0A]",
    accent: "text-red-400",
    accentBg: "bg-red-500/10",
    border: "border-red-900/40",
    liveColor: "bg-red-500",
    liveBadge: "bg-red-950/80 text-red-400",
    timelineDot: "bg-red-500",
    timelineLine: "bg-red-900/40",
  },
  cricket: {
    icon: Trophy,
    gradient: "from-emerald-900/30 via-emerald-950/20 to-[#0A0A0A]",
    accent: "text-emerald-400",
    accentBg: "bg-emerald-500/10",
    border: "border-emerald-900/40",
    liveColor: "bg-emerald-500",
    liveBadge: "bg-emerald-950/80 text-emerald-400",
    timelineDot: "bg-emerald-500",
    timelineLine: "bg-emerald-900/40",
  },
};

function formatRelativeTime(isoString) {
  if (!isoString) return "";
  const diff = (Date.now() - new Date(isoString).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

const DevelopingStoryDetail = () => {
  const { storyId } = useParams();
  const navigate = useNavigate();
  const [story, setStory] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchStory = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/developing-stories/${storyId}`, {
        withCredentials: true,
      });
      setStory(response.data);
    } catch (error) {
      console.error("Error fetching developing story:", error);
    } finally {
      setLoading(false);
    }
  }, [storyId]);

  useEffect(() => {
    fetchStory();
    const interval = setInterval(fetchStory, 60000);
    return () => clearInterval(interval);
  }, [fetchStory]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center">
        <SuryaLogo className="w-16 h-16 animate-spin-slow" />
      </div>
    );
  }

  if (!story) {
    return (
      <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-400 mb-4">Story not found</p>
          <button
            onClick={() => navigate(-1)}
            className="text-red-400 hover:text-red-300 transition-colors"
          >
            Go back
          </button>
        </div>
      </div>
    );
  }

  const cfg = themeConfig[story.theme] || themeConfig.war;
  const Icon = cfg.icon;

  return (
    <div className="min-h-screen bg-[#0A0A0A]" data-testid="developing-story-detail">
      {/* Background gradient */}
      <div className={`fixed inset-0 bg-gradient-to-b ${cfg.gradient} pointer-events-none`} />

      {/* Header — 56px, sits at top-0 (WebView already starts below status bar via overlaysWebView:false) */}
      <header
        className="glass-nav fixed left-0 right-0 z-40"
        style={{ height: '56px', top: 'var(--sat)' }}
      >
        {/* Relative container so the LIVE badge can be absolutely centred */}
        <div className="relative h-full flex items-center justify-between px-4">
          {/* Back arrow — left, vertically centred */}
          <button
            onClick={() => navigate(-1)}
            className="p-2 hover:bg-white/5 rounded-lg transition-colors"
            data-testid="back-btn"
          >
            <ArrowLeft className="w-5 h-5 text-gray-400" />
          </button>

          {/* LIVE badge — absolutely centred horizontally and vertically */}
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <span className={`text-xs font-mono px-2 py-0.5 rounded ${cfg.liveBadge} flex items-center gap-1`}>
              <span className={`w-1.5 h-1.5 ${cfg.liveColor} rounded-full animate-pulse`} />
              LIVE
            </span>
          </div>

          {/* Theme icon — right, 32×32, vertically centred */}
          <div className="w-8 h-8 flex items-center justify-center">
            <Icon className={`w-5 h-5 ${cfg.accent}`} />
          </div>
        </div>
      </header>

      {/* Content — top padding = 56px header + safe area already on outer div */}
      <main className="relative z-10 pb-16 px-6" style={{ paddingTop: '56px' }}>
        <div className="max-w-2xl mx-auto">
          {/* Story header */}
          <motion.div
            className="mt-6 mb-8"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <div className="flex items-center gap-3 mb-3">
              <div className={`w-9 h-9 rounded-full ${cfg.accentBg} flex items-center justify-center flex-shrink-0`}>
                <Icon className={`w-4.5 h-4.5 ${cfg.accent}`} />
              </div>
              <div>
                <h1 className="text-xl font-bold text-white leading-snug">{story.title}</h1>
                <div className="flex items-center gap-2 mt-0.5">
                  <Clock className="w-3 h-3 text-gray-600" />
                  <span className="text-gray-600 text-xs font-mono">
                    Updated {formatRelativeTime(story.last_updated)}
                  </span>
                  <span className="text-gray-700 text-xs">·</span>
                  <span className="text-gray-600 text-xs font-mono">
                    {story.articles.length} update{story.articles.length !== 1 ? "s" : ""}
                  </span>
                </div>
              </div>
            </div>
          </motion.div>

          {/* Timeline */}
          {story.articles.length > 0 ? (
            <div className="relative">
              {/* Vertical line */}
              <div className={`absolute left-3.5 top-0 bottom-0 w-px ${cfg.timelineLine}`} />

              <div className="space-y-0">
                {story.articles.map((article, idx) => (
                  <motion.div
                    key={article.article_id}
                    className="relative pl-10"
                    initial={{ opacity: 0, x: -12 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: idx * 0.07 }}
                  >
                    {/* Timeline dot */}
                    <div
                      className={`absolute left-2 top-5 w-3 h-3 rounded-full ${cfg.timelineDot} border-2 border-[#0A0A0A] ${idx === 0 ? "animate-pulse" : "opacity-60"}`}
                    />

                    {/* Card */}
                    <div
                      className={`mb-4 p-4 glass-card rounded-xl border ${cfg.border} cursor-pointer hover:bg-white/5 transition-colors group`}
                      onClick={() => navigate(`/article/${article.article_id}`)}
                      data-testid={`timeline-article-${article.article_id}`}
                    >
                      {idx === 0 && (
                        <span className={`inline-flex items-center gap-1 text-xs font-mono ${cfg.accent} mb-2`}>
                          <span className={`w-1.5 h-1.5 ${cfg.liveColor} rounded-full animate-pulse`} />
                          LATEST
                        </span>
                      )}
                      <h3 className="text-white text-sm font-medium leading-snug group-hover:text-red-400 transition-colors line-clamp-3">
                        {article.title}
                      </h3>
                      {article.description && (
                        <p className="text-gray-500 text-xs mt-1.5 line-clamp-2 leading-relaxed">
                          {article.description}
                        </p>
                      )}
                      <div className="flex items-center justify-between mt-3">
                        <span className="text-gray-600 text-xs font-mono">{article.source}</span>
                        <span className="text-gray-600 text-xs font-mono">
                          {formatRelativeTime(article.published_at)}
                        </span>
                      </div>
                    </div>
                  </motion.div>
                ))}
              </div>
            </div>
          ) : (
            <motion.div
              className="text-center py-16"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
            >
              <Icon className={`w-12 h-12 ${cfg.accent} opacity-30 mx-auto mb-4`} />
              <p className="text-gray-500">No updates yet</p>
              <p className="text-gray-600 text-sm mt-1">Check back soon as this story develops</p>
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

export default DevelopingStoryDetail;

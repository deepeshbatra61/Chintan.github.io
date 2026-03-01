import React, { useState, useEffect, useCallback, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import axios from "axios";
import { ArrowLeft, Sun, CloudSun, Moon, Clock } from "lucide-react";
import { SuryaLogo } from "../App";

const BACKEND_URL = "https://chintangithubio-production.up.railway.app";
const API = `${BACKEND_URL}/api`;

const briefThemes = {
  morning: {
    icon: Sun,
    gradient: "from-amber-900/40 via-orange-900/20 to-[#0A0A0A]",
    bgColor: "bg-gradient-to-br from-amber-950/30 to-[#0A0A0A]",
    accent: "text-amber-400",
    accentBg: "bg-amber-500/20",
    borderAccent: "border-amber-500/30",
    greeting: "Good Morning",
    subtitle: "while you were sleeping, we curated your morning brief",
  },
  midday: {
    icon: CloudSun,
    gradient: "from-orange-900/30 via-red-900/20 to-[#0A0A0A]",
    bgColor: "bg-gradient-to-br from-orange-950/30 to-[#0A0A0A]",
    accent: "text-orange-400",
    accentBg: "bg-orange-500/20",
    borderAccent: "border-orange-500/30",
    greeting: "Good Afternoon",
    subtitle: "while you were working, we were curating your tailored afternoon brief",
  },
  night: {
    icon: Moon,
    gradient: "from-indigo-900/40 via-purple-900/20 to-[#0A0A0A]",
    bgColor: "bg-gradient-to-br from-indigo-950/40 to-[#0A0A0A]",
    accent: "text-indigo-300",
    accentBg: "bg-indigo-500/20",
    borderAccent: "border-indigo-500/30",
    greeting: "Good Evening",
    subtitle: "while you wound down, here's what shaped your world today",
  },
};

const STAR_KEYFRAMES = `
@keyframes chintan-fall {
  0%   { transform: translateY(-10px); opacity: 0; }
  12%  { opacity: 1; }
  88%  { opacity: 1; }
  100% { transform: translateY(100vh); opacity: 0; }
}
`;

const FallingStars = () => {
  const stars = useMemo(
    () =>
      Array.from({ length: 18 }, (_, i) => ({
        id: i,
        left: `${(i * 5.5 + Math.sin(i * 1.7) * 8 + 50) % 100}%`,
        delay: `${(i * 0.6) % 10}s`,
        duration: `${8 + (i % 5)}s`,
        size: i % 3 === 0 ? "3px" : "2px",
        opacity: 0.3 + (i % 4) * 0.08,
      })),
    []
  );

  return (
    <>
      <style>{STAR_KEYFRAMES}</style>
      {stars.map((star) => (
        <div
          key={star.id}
          style={{
            position: "absolute",
            left: star.left,
            top: 0,
            width: star.size,
            height: star.size,
            borderRadius: "50%",
            background: "white",
            opacity: star.opacity,
            animation: `chintan-fall ${star.duration} ${star.delay} linear infinite`,
          }}
        />
      ))}
    </>
  );
};

const BriefPage = () => {
  const { briefType } = useParams();
  const navigate = useNavigate();
  const [brief, setBrief] = useState(null);
  const [loading, setLoading] = useState(true);

  const theme = briefThemes[briefType] || briefThemes.morning;
  const Icon = theme.icon;

  const fetchBrief = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/briefs/${briefType}`, {
        withCredentials: true,
      });
      setBrief(response.data);
    } catch (error) {
      console.error("Error fetching brief:", error);
    } finally {
      setLoading(false);
    }
  }, [briefType]);

  useEffect(() => {
    fetchBrief();
  }, [fetchBrief]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center">
        <SuryaLogo className="w-16 h-16 animate-spin-slow" />
      </div>
    );
  }

  const narrative =
    brief?.narrative || "No brief available right now. Check back soon.";
  const sourceArticles = brief?.source_articles || [];
  const readingTime = brief?.reading_time || "1 min read";

  return (
    <div
      className={`min-h-screen ${theme.bgColor}`}
      data-testid={`brief-${briefType}-page`}
    >
      {/* Background gradient */}
      <div
        className={`fixed inset-0 bg-gradient-to-b ${theme.gradient} pointer-events-none`}
      />

      {/* Night: falling stars */}
      {briefType === "night" && (
        <div className="fixed inset-0 pointer-events-none overflow-hidden">
          <FallingStars />
        </div>
      )}

      {/* Morning: warm glow */}
      {briefType === "morning" && (
        <div className="fixed inset-0 pointer-events-none">
          <div className="absolute top-10 left-1/2 -translate-x-1/2 w-96 h-96 bg-amber-500/10 rounded-full blur-3xl" />
        </div>
      )}

      {/* Nav */}
      <header className="glass-nav fixed top-0 left-0 right-0 z-40 px-4 py-3">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <button
            onClick={() => navigate(-1)}
            className="p-2 hover:bg-white/5 rounded-lg transition-colors"
            data-testid="back-btn"
          >
            <ArrowLeft className="w-5 h-5 text-gray-400" />
          </button>
          <span className="text-white font-medium text-sm">Daily Brief</span>
          <div className="w-9" />
        </div>
      </header>

      {/* Content */}
      <main className="relative z-10 pt-20 pb-16 px-6">
        <div className="max-w-2xl mx-auto">
          {/* Header row: icon + greeting inline */}
          <motion.div
            className="flex items-center gap-3 mt-6 mb-2"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <Icon className={`w-6 h-6 ${theme.accent} flex-shrink-0`} />
            <h1 className="text-2xl font-bold text-white">{theme.greeting}</h1>
          </motion.div>

          {/* Subtitle — one line, muted */}
          <motion.p
            className="text-sm text-gray-500 mb-5"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.1 }}
          >
            {theme.subtitle}
          </motion.p>

          {/* Read time */}
          <motion.div
            className="flex items-center gap-1.5 text-gray-600 text-xs mb-8"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.15 }}
          >
            <Clock className="w-3.5 h-3.5" />
            <span>{readingTime}</span>
          </motion.div>

          {/* Narrative */}
          <motion.p
            className="text-gray-200 leading-relaxed text-base mb-10"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
          >
            {narrative}
          </motion.p>

          {/* Divider + Referenced Stories */}
          {sourceArticles.length > 0 && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.3 }}
            >
              <div className={`border-t ${theme.borderAccent} mb-7`} />

              <p
                className={`text-xs font-mono uppercase tracking-wider ${theme.accent} mb-4`}
              >
                Referenced Stories
              </p>

              <div className="space-y-3">
                {sourceArticles.map((article, idx) => (
                  <motion.button
                    key={article.article_id}
                    onClick={() => navigate(`/article/${article.article_id}`)}
                    className={`w-full text-left p-4 rounded-xl glass-card border ${theme.borderAccent} hover:bg-white/5 transition-colors group`}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.35 + idx * 0.08 }}
                    data-testid={`ref-article-${article.article_id}`}
                  >
                    <p className="text-white text-sm font-medium leading-snug group-hover:text-red-400 transition-colors line-clamp-2">
                      {article.title}
                    </p>
                    <p className="text-gray-600 text-xs mt-1.5 font-mono">
                      {article.source}
                    </p>
                  </motion.button>
                ))}
              </div>
            </motion.div>
          )}

          {sourceArticles.length === 0 && (
            <p className="text-center text-gray-600 text-sm py-10">
              No stories available for this brief
            </p>
          )}
        </div>
      </main>
    </div>
  );
};

export default BriefPage;

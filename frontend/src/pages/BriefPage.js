import React, { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import axios from "axios";
import { ArrowLeft, Sun, CloudSun, Moon, Clock, ChevronRight } from "lucide-react";
import { SuryaLogo } from "../App";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const briefThemes = {
  morning: {
    icon: Sun,
    gradient: "from-amber-900/30 via-orange-900/20 to-[#0A0A0A]",
    accent: "text-amber-500",
    bgAccent: "bg-amber-500",
    borderAccent: "border-amber-500/30",
    title: "Morning Brief",
    subtitle: "Start your day informed",
    greeting: "Good Morning"
  },
  midday: {
    icon: CloudSun,
    gradient: "from-orange-900/30 via-red-900/20 to-[#0A0A0A]",
    accent: "text-orange-500",
    bgAccent: "bg-orange-500",
    borderAccent: "border-orange-500/30",
    title: "Midday Update",
    subtitle: "Catch up on what's happening",
    greeting: "Good Afternoon"
  },
  night: {
    icon: Moon,
    gradient: "from-indigo-900/30 via-purple-900/20 to-[#0A0A0A]",
    accent: "text-indigo-400",
    bgAccent: "bg-indigo-500",
    borderAccent: "border-indigo-500/30",
    title: "Night Summary",
    subtitle: "Reflect on the day",
    greeting: "Good Evening"
  }
};

const BriefPage = () => {
  const { briefType } = useParams();
  const navigate = useNavigate();
  const [brief, setBrief] = useState(null);
  const [loading, setLoading] = useState(true);
  const [currentIndex, setCurrentIndex] = useState(0);

  const theme = briefThemes[briefType] || briefThemes.morning;
  const Icon = theme.icon;

  const fetchBrief = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/briefs/${briefType}`, { withCredentials: true });
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

  const articles = brief?.articles || [];

  return (
    <div className={`min-h-screen bg-[#0A0A0A]`} data-testid={`brief-${briefType}-page`}>
      {/* Background gradient */}
      <div className={`fixed inset-0 bg-gradient-to-b ${theme.gradient} pointer-events-none`} />

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
          
          <div className="flex items-center gap-2">
            <Icon className={`w-5 h-5 ${theme.accent}`} />
            <span className="text-white font-medium">{theme.title}</span>
          </div>

          <div className="w-9" /> {/* Spacer for alignment */}
        </div>
      </header>

      {/* Content */}
      <main className="relative z-10 pt-24 pb-12 px-6">
        <div className="max-w-3xl mx-auto">
          {/* Hero */}
          <motion.div 
            className="text-center mb-12"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <div className={`w-20 h-20 rounded-full ${theme.bgAccent}/20 flex items-center justify-center mx-auto mb-6`}>
              <Icon className={`w-10 h-10 ${theme.accent}`} />
            </div>
            <h1 className="font-serif text-4xl md:text-5xl font-bold text-white mb-3">
              {theme.greeting}
            </h1>
            <p className="text-gray-400 text-lg">{theme.subtitle}</p>
            <div className="flex items-center justify-center gap-2 mt-4 text-gray-500">
              <Clock className="w-4 h-4" />
              <span className="text-sm">{brief?.reading_time || "5 min read"}</span>
            </div>
          </motion.div>

          {/* Progress Dots */}
          <div className="progress-dots mb-8">
            {articles.map((_, idx) => (
              <button
                key={idx}
                onClick={() => setCurrentIndex(idx)}
                className={`progress-dot ${idx === currentIndex ? "active" : ""}`}
              />
            ))}
          </div>

          {/* Articles */}
          <div className="space-y-6">
            {articles.map((article, idx) => (
              <motion.article
                key={article.article_id}
                className={`glass-card rounded-xl overflow-hidden ${theme.borderAccent} cursor-pointer`}
                onClick={() => navigate(`/article/${article.article_id}`)}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.1 }}
                data-testid={`brief-article-${article.article_id}`}
              >
                <div className="flex flex-col md:flex-row">
                  {/* Image */}
                  <div className="md:w-1/3 h-48 md:h-auto relative">
                    <img 
                      src={article.image_url} 
                      alt={article.title}
                      className="w-full h-full object-cover"
                    />
                    <div className="absolute inset-0 bg-gradient-to-r from-transparent to-[#0A0A0A] md:block hidden" />
                    <div className="absolute inset-0 bg-gradient-to-t from-[#0A0A0A] to-transparent md:hidden" />
                  </div>

                  {/* Content */}
                  <div className="md:w-2/3 p-6">
                    <div className="flex items-center gap-2 mb-3">
                      <span className={`text-xs font-mono uppercase tracking-wider ${theme.accent}`}>
                        {article.category}
                      </span>
                      {article.is_breaking && (
                        <span className="live-indicator text-xs">
                          <span className="live-dot" />
                          Breaking
                        </span>
                      )}
                    </div>

                    <h2 className="font-serif text-xl md:text-2xl text-white mb-3 leading-tight">
                      {article.title}
                    </h2>

                    <p className="text-gray-400 text-sm mb-4 line-clamp-2">
                      {article.description}
                    </p>

                    <div className="flex items-center justify-between">
                      <span className="text-gray-600 text-xs font-mono">{article.source}</span>
                      <span className={`flex items-center gap-1 text-sm ${theme.accent}`}>
                        Read more <ChevronRight className="w-4 h-4" />
                      </span>
                    </div>
                  </div>
                </div>
              </motion.article>
            ))}
          </div>

          {articles.length === 0 && (
            <div className="text-center py-20">
              <p className="text-gray-500">No stories available for this brief</p>
            </div>
          )}

          {/* Footer */}
          <motion.div 
            className="text-center mt-12"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5 }}
          >
            <p className="text-gray-600 text-sm mb-4">
              That's your {theme.title.toLowerCase()} for today
            </p>
            <button
              onClick={() => navigate("/feed")}
              className="btn-secondary"
              data-testid="explore-more-btn"
            >
              Explore More Stories
            </button>
          </motion.div>
        </div>
      </main>
    </div>
  );
};

export default BriefPage;

import React, { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import axios from "axios";
import { ArrowLeft, Sun, CloudSun, Moon, Clock, ChevronRight, Coffee, Briefcase, Stars } from "lucide-react";
import { SuryaLogo } from "../App";

const BACKEND_URL = "https://chintangithubio-production.up.railway.app";
const API = `${BACKEND_URL}/api`;

const briefThemes = {
  morning: {
    icon: Sun,
    secondaryIcon: Coffee,
    gradient: "from-amber-900/40 via-orange-900/20 to-[#0A0A0A]",
    bgColor: "bg-gradient-to-br from-amber-950/30 to-[#0A0A0A]",
    accent: "text-amber-400",
    accentBg: "bg-amber-500/20",
    borderAccent: "border-amber-500/30",
    cardBg: "bg-amber-950/20",
    title: "Morning Brief",
    subtitle: "Start your day informed",
    greeting: "Good Morning",
    timeContext: "Here's what happened overnight",
    summaryIntro: "While you were sleeping, the world kept moving. Here's what you need to know to start your day right.",
    closingNote: "Have a productive day ahead."
  },
  midday: {
    icon: CloudSun,
    secondaryIcon: Briefcase,
    gradient: "from-orange-900/30 via-red-900/20 to-[#0A0A0A]",
    bgColor: "bg-gradient-to-br from-orange-950/30 to-[#0A0A0A]",
    accent: "text-orange-400",
    accentBg: "bg-orange-500/20",
    borderAccent: "border-orange-500/30",
    cardBg: "bg-orange-950/20",
    title: "Midday Update",
    subtitle: "Catch up on what's happening",
    greeting: "Good Afternoon",
    timeContext: "Here's what's unfolding today",
    summaryIntro: "The day is in full swing. Here's a quick catch-up on the stories making headlines right now.",
    closingNote: "Stay informed, stay ahead."
  },
  night: {
    icon: Moon,
    secondaryIcon: Stars,
    gradient: "from-indigo-900/40 via-purple-900/20 to-[#0A0A0A]",
    bgColor: "bg-gradient-to-br from-indigo-950/40 to-[#0A0A0A]",
    accent: "text-indigo-300",
    accentBg: "bg-indigo-500/20",
    borderAccent: "border-indigo-500/30",
    cardBg: "bg-indigo-950/20",
    title: "Night Summary",
    subtitle: "Reflect on the day",
    greeting: "Good Evening",
    timeContext: "Here's how the day unfolded",
    summaryIntro: "As the day winds down, take a moment to reflect on what shaped our world today.",
    closingNote: "Rest well, tomorrow awaits."
  }
};

const BriefPage = () => {
  const { briefType } = useParams();
  const navigate = useNavigate();
  const [brief, setBrief] = useState(null);
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState(null);

  const theme = briefThemes[briefType] || briefThemes.morning;
  const Icon = theme.icon;
  const SecondaryIcon = theme.secondaryIcon;

  const fetchBrief = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/briefs/${briefType}`, { withCredentials: true });
      setBrief(response.data);
      
      // Generate a smart summary from articles
      if (response.data.articles?.length > 0) {
        const articles = response.data.articles;
        const summaryText = generateSmartSummary(articles, briefType);
        setSummary(summaryText);
      }
    } catch (error) {
      console.error("Error fetching brief:", error);
    } finally {
      setLoading(false);
    }
  }, [briefType]);

  useEffect(() => {
    fetchBrief();
  }, [fetchBrief]);

  // Generate a human-readable summary
  const generateSmartSummary = (articles, type) => {
    const categories = {};
    articles.forEach(a => {
      if (!categories[a.category]) categories[a.category] = [];
      categories[a.category].push(a);
    });

    const highlights = [];
    
    // Breaking news first
    const breaking = articles.filter(a => a.is_breaking);
    if (breaking.length > 0) {
      highlights.push({
        type: 'breaking',
        title: 'Breaking Now',
        content: breaking[0].title,
        category: breaking[0].category
      });
    }

    // Developing stories
    const developing = articles.filter(a => a.is_developing && !a.is_breaking);
    if (developing.length > 0) {
      highlights.push({
        type: 'developing',
        title: 'Still Unfolding',
        content: developing[0].title,
        category: developing[0].category
      });
    }

    // Top by category
    Object.entries(categories).slice(0, 3).forEach(([cat, catArticles]) => {
      if (!highlights.find(h => h.category === cat)) {
        highlights.push({
          type: 'category',
          title: cat,
          content: catArticles[0].title,
          category: cat
        });
      }
    });

    return {
      highlights: highlights.slice(0, 4),
      totalStories: articles.length,
      categories: Object.keys(categories)
    };
  };

  const getTimeBasedMessage = () => {
    const hour = new Date().getHours();
    if (briefType === 'morning') {
      return hour < 9 ? "Early riser! Here's your head start." : "Good morning! Let's get you up to speed.";
    } else if (briefType === 'midday') {
      return hour < 14 ? "Lunch break? Perfect time to catch up." : "Afternoon check-in. Here's what matters.";
    } else {
      return hour < 21 ? "Winding down? Here's your day in review." : "Before you rest, here's today's story.";
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center">
        <SuryaLogo className="w-16 h-16 animate-spin-slow" />
      </div>
    );
  }

  const articles = brief?.articles || [];

  return (
    <div className={`min-h-screen ${theme.bgColor}`} data-testid={`brief-${briefType}-page`}>
      {/* Background gradient */}
      <div className={`fixed inset-0 bg-gradient-to-b ${theme.gradient} pointer-events-none`} />
      
      {/* Ambient glow for night */}
      {briefType === 'night' && (
        <div className="fixed inset-0 pointer-events-none">
          <div className="absolute top-20 right-20 w-64 h-64 bg-indigo-500/10 rounded-full blur-3xl" />
          <div className="absolute bottom-40 left-10 w-48 h-48 bg-purple-500/10 rounded-full blur-3xl" />
        </div>
      )}
      
      {/* Warm glow for morning */}
      {briefType === 'morning' && (
        <div className="fixed inset-0 pointer-events-none">
          <div className="absolute top-10 left-1/2 -translate-x-1/2 w-96 h-96 bg-amber-500/10 rounded-full blur-3xl" />
        </div>
      )}

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

          <div className="w-9" />
        </div>
      </header>

      {/* Content */}
      <main className="relative z-10 pt-24 pb-12 px-6">
        <div className="max-w-3xl mx-auto">
          {/* Hero */}
          <motion.div 
            className="text-center mb-10"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <div className={`w-24 h-24 rounded-full ${theme.accentBg} flex items-center justify-center mx-auto mb-6 relative`}>
              <Icon className={`w-12 h-12 ${theme.accent}`} />
              <div className={`absolute -bottom-1 -right-1 w-8 h-8 rounded-full ${theme.accentBg} flex items-center justify-center`}>
                <SecondaryIcon className={`w-4 h-4 ${theme.accent}`} />
              </div>
            </div>
            <h1 className="font-serif text-4xl md:text-5xl font-bold text-white mb-3">
              {theme.greeting}
            </h1>
            <p className={`text-lg ${theme.accent} mb-2`}>{getTimeBasedMessage()}</p>
            <div className="flex items-center justify-center gap-2 mt-4 text-gray-500">
              <Clock className="w-4 h-4" />
              <span className="text-sm">{brief?.reading_time || "5 min read"}</span>
            </div>
          </motion.div>

          {/* Summary Card */}
          <motion.div 
            className={`glass-card rounded-2xl p-6 mb-8 ${theme.borderAccent}`}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
          >
            <p className="text-gray-300 leading-relaxed mb-6">
              {theme.summaryIntro}
            </p>
            
            {summary && (
              <div className="space-y-4">
                <p className={`text-xs font-mono uppercase tracking-wider ${theme.accent}`}>
                  {theme.timeContext}
                </p>
                
                {summary.highlights.map((highlight, idx) => (
                  <motion.div
                    key={idx}
                    className={`p-4 rounded-xl ${theme.cardBg} border ${theme.borderAccent}`}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.2 + idx * 0.1 }}
                  >
                    <div className="flex items-start gap-3">
                      <div className={`px-2 py-1 rounded text-xs font-mono ${theme.accentBg} ${theme.accent}`}>
                        {highlight.type === 'breaking' ? 'Breaking' : 
                         highlight.type === 'developing' ? 'Live' : 
                         highlight.category}
                      </div>
                    </div>
                    <p className="text-white mt-2 font-medium leading-snug">
                      {highlight.content}
                    </p>
                  </motion.div>
                ))}
                
                <p className="text-gray-500 text-sm text-center pt-4">
                  Covering {summary.categories.join(', ')}
                </p>
              </div>
            )}
          </motion.div>

          {/* Detailed Stories */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.4 }}
          >
            <h2 className={`text-xs font-mono uppercase tracking-wider ${theme.accent} mb-4`}>
              Full Stories
            </h2>
            
            <div className="space-y-4">
              {articles.map((article, idx) => (
                <motion.article
                  key={article.article_id}
                  className={`glass-card rounded-xl overflow-hidden ${theme.borderAccent} cursor-pointer group`}
                  onClick={() => navigate(`/article/${article.article_id}`)}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.5 + idx * 0.1 }}
                  whileHover={{ scale: 1.01 }}
                  data-testid={`brief-article-${article.article_id}`}
                >
                  <div className="flex">
                    {/* Image */}
                    <div className="w-24 h-24 md:w-32 md:h-32 flex-shrink-0">
                      <img 
                        src={article.image_url} 
                        alt={article.title}
                        className="w-full h-full object-cover"
                      />
                    </div>

                    {/* Content */}
                    <div className="flex-1 p-4 flex flex-col justify-between">
                      <div>
                        <div className="flex items-center gap-2 mb-2">
                          <span className={`text-xs font-mono ${theme.accent}`}>
                            {article.category}
                          </span>
                          {article.is_breaking && (
                            <span className="live-indicator text-xs">
                              <span className="live-dot" />
                              Breaking
                            </span>
                          )}
                        </div>
                        <h3 className="text-white font-medium line-clamp-2 group-hover:text-red-400 transition-colors">
                          {article.title}
                        </h3>
                      </div>

                      <div className="flex items-center justify-between mt-2">
                        <span className="text-gray-600 text-xs font-mono">{article.source}</span>
                        <ChevronRight className={`w-4 h-4 ${theme.accent} opacity-0 group-hover:opacity-100 transition-opacity`} />
                      </div>
                    </div>
                  </div>
                </motion.article>
              ))}
            </div>
          </motion.div>

          {articles.length === 0 && (
            <div className="text-center py-20">
              <p className="text-gray-500">No stories available for this brief</p>
            </div>
          )}

          {/* Closing Note */}
          <motion.div 
            className="text-center mt-12"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.8 }}
          >
            <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-full ${theme.accentBg} mb-4`}>
              <SecondaryIcon className={`w-4 h-4 ${theme.accent}`} />
              <span className={`text-sm ${theme.accent}`}>{theme.closingNote}</span>
            </div>
            <p className="text-gray-600 text-sm mb-6">
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

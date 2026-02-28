import React, { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import axios from "axios";
import { ArrowLeft, Radio, Clock, ChevronRight } from "lucide-react";
import { SuryaLogo } from "../App";

const BACKEND_URL = "https://chintangithubio-production.up.railway.app";
const API = `${BACKEND_URL}/api`;

const DevelopingPage = () => {
  const navigate = useNavigate();
  const [stories, setStories] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchStories = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/articles/developing`, { withCredentials: true });
      setStories(response.data);
    } catch (error) {
      console.error("Error fetching developing stories:", error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStories();
    // Refresh every 30 seconds
    const interval = setInterval(fetchStories, 30000);
    return () => clearInterval(interval);
  }, [fetchStories]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center">
        <SuryaLogo className="w-16 h-16 animate-spin-slow" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0A0A0A]" data-testid="developing-page">
      {/* Subtle red ambient glow */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[300px] bg-red-500/5 rounded-full blur-3xl" />
      </div>

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
            <div className="relative">
              <Radio className="w-5 h-5 text-red-500" />
              <div className="absolute inset-0 animate-ping">
                <Radio className="w-5 h-5 text-red-500/50" />
              </div>
            </div>
            <span className="text-white font-medium">Developing Stories</span>
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
            <div className="w-20 h-20 rounded-full bg-red-600/20 flex items-center justify-center mx-auto mb-6 relative">
              <Radio className="w-10 h-10 text-red-500" />
              {/* Breathing glow */}
              <div className="absolute inset-0 rounded-full bg-red-500/20 animate-pulse" />
            </div>
            <h1 className="font-serif text-3xl md:text-4xl font-bold text-white mb-3">
              Live & Developing
            </h1>
            <p className="text-gray-400">
              Stories that are still unfolding. Updates as they happen.
            </p>
          </motion.div>

          {/* Stories */}
          <div className="space-y-4">
            {stories.map((story, idx) => (
              <motion.article
                key={story.article_id}
                className="glass-card rounded-xl overflow-hidden border-red-900/30 cursor-pointer group"
                onClick={() => navigate(`/article/${story.article_id}`)}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.1 }}
                data-testid={`developing-story-${story.article_id}`}
              >
                <div className="flex">
                  <div className="w-32 h-32 md:w-40 md:h-40 flex-shrink-0 relative">
                    <img 
                      src={story.image_url} 
                      alt={story.title}
                      className="w-full h-full object-cover"
                    />
                    <div className="absolute inset-0 bg-gradient-to-r from-transparent to-[#0A0A0A]" />
                    
                    {/* Live indicator */}
                    <div className="absolute top-2 left-2">
                      {story.is_breaking ? (
                        <span className="live-indicator bg-black/80 backdrop-blur-sm px-2 py-1 rounded text-xs">
                          <span className="live-dot" />
                          Breaking
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 bg-red-950/80 backdrop-blur-sm px-2 py-1 rounded text-xs text-red-400">
                          <div className="w-1.5 h-1.5 bg-red-500 rounded-full animate-pulse" />
                          Live
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex-1 p-4 flex flex-col justify-between">
                    <div>
                      <span className="text-red-500 font-mono text-xs uppercase tracking-wider">
                        {story.category}
                      </span>
                      <h2 className="text-white font-medium mt-2 line-clamp-2 group-hover:text-red-400 transition-colors">
                        {story.title}
                      </h2>
                      <p className="text-gray-500 text-sm mt-2 line-clamp-2">
                        {story.description}
                      </p>
                    </div>

                    <div className="flex items-center justify-between mt-3">
                      <span className="text-gray-600 text-xs font-mono">{story.source}</span>
                      <ChevronRight className="w-4 h-4 text-red-500 opacity-0 group-hover:opacity-100 transition-opacity" />
                    </div>
                  </div>
                </div>
              </motion.article>
            ))}
          </div>

          {stories.length === 0 && (
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

          {/* Auto-refresh notice */}
          <div className="text-center mt-8">
            <p className="text-gray-600 text-xs flex items-center justify-center gap-2">
              <Clock className="w-3 h-3" />
              Auto-refreshes every 30 seconds
            </p>
          </div>
        </div>
      </main>
    </div>
  );
};

export default DevelopingPage;

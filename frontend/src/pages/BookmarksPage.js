import React, { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import axios from "axios";
import { ArrowLeft, Bookmark, Trash2, Clock, Eye } from "lucide-react";
import { toast } from "sonner";
import { SuryaLogo } from "../App";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const BookmarksPage = () => {
  const navigate = useNavigate();
  const [bookmarks, setBookmarks] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchBookmarks = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/bookmarks`, { withCredentials: true });
      setBookmarks(response.data);
    } catch (error) {
      console.error("Error fetching bookmarks:", error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchBookmarks();
  }, [fetchBookmarks]);

  const removeBookmark = async (articleId, e) => {
    e.stopPropagation();
    try {
      await axios.delete(`${API}/bookmarks/${articleId}`, { withCredentials: true });
      setBookmarks(bookmarks.filter(b => b.article_id !== articleId));
      toast.success("Removed from bookmarks");
    } catch (error) {
      toast.error("Failed to remove bookmark");
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
    <div className="min-h-screen bg-[#0A0A0A]" data-testid="bookmarks-page">
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
            <Bookmark className="w-5 h-5 text-red-500" />
            <span className="text-white font-medium">Bookmarks</span>
          </div>

          <div className="w-9" />
        </div>
      </header>

      {/* Content */}
      <main className="pt-20 pb-12 px-6">
        <div className="max-w-3xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-8"
          >
            <h1 className="font-serif text-3xl font-bold text-white mb-2">
              Saved Articles
            </h1>
            <p className="text-gray-500">
              {bookmarks.length} {bookmarks.length === 1 ? "article" : "articles"} saved for later
            </p>
          </motion.div>

          {bookmarks.length > 0 ? (
            <div className="space-y-4">
              <AnimatePresence>
                {bookmarks.map((article, idx) => (
                  <motion.article
                    key={article.article_id}
                    className="glass-card rounded-xl overflow-hidden cursor-pointer group"
                    onClick={() => navigate(`/article/${article.article_id}`)}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, x: -100 }}
                    transition={{ delay: idx * 0.05 }}
                    data-testid={`bookmark-${article.article_id}`}
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
                            <span className="category-badge text-xs">
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
                          <button
                            onClick={(e) => removeBookmark(article.article_id, e)}
                            className="p-2 hover:bg-red-500/20 rounded-lg transition-colors text-gray-500 hover:text-red-500"
                            data-testid={`remove-bookmark-${article.article_id}`}
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    </div>
                  </motion.article>
                ))}
              </AnimatePresence>
            </div>
          ) : (
            <motion.div 
              className="text-center py-20"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
            >
              <div className="w-20 h-20 rounded-full bg-white/5 flex items-center justify-center mx-auto mb-6">
                <Bookmark className="w-10 h-10 text-gray-600" />
              </div>
              <h2 className="text-xl text-white mb-2">No bookmarks yet</h2>
              <p className="text-gray-500 mb-6">Save articles to read them later</p>
              <button
                onClick={() => navigate("/feed")}
                className="btn-primary"
                data-testid="browse-articles-btn"
              >
                Browse Articles
              </button>
            </motion.div>
          )}
        </div>
      </main>
    </div>
  );
};

export default BookmarksPage;

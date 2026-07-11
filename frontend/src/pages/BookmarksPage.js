import React, { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import axios from "axios";
import { toast } from "sonner";
import { ArrowLeft, Bookmark, Trash2 } from "lucide-react";
import { SuryaLogo } from "../App";
import BottomNav from "../components/BottomNav";

const BACKEND_URL = "https://chintangithubio-production.up.railway.app";
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

  // Optimistic remove with an Undo affordance — no jarring instant deletion, and
  // a mistap is one tap to recover.
  const removeBookmark = async (article, idx, e) => {
    e.stopPropagation();
    setBookmarks((prev) => prev.filter((b) => b.article_id !== article.article_id));
    try {
      await axios.delete(`${API}/bookmarks/${article.article_id}`, { withCredentials: true });
    } catch (error) {
      console.error("Failed to remove bookmark:", error);
    }
    toast("Removed from saved", {
      action: {
        label: "Undo",
        onClick: async () => {
          try {
            await axios.post(`${API}/bookmarks/${article.article_id}`, {}, { withCredentials: true });
          } catch { /* already gone or duplicate — ignore */ }
          setBookmarks((prev) => {
            if (prev.some((b) => b.article_id === article.article_id)) return prev;
            const next = [...prev];
            next.splice(Math.min(idx, next.length), 0, article);
            return next;
          });
        },
      },
    });
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center">
        <SuryaLogo className="w-14 h-14 animate-spin-slow" />
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", background: "#0A0A0A" }} data-testid="bookmarks-page">
      {/* Header */}
      <header className="sticky z-40 px-4" style={{ top: 0, paddingTop: "var(--sat, 44px)", paddingBottom: "12px", background: "rgba(10,10,10,0.72)", backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)" }}>
        <div style={{ maxWidth: "640px", margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <button onClick={() => navigate(-1)} style={{ padding: "8px", background: "none", border: "none", cursor: "pointer" }} data-testid="back-btn">
            <ArrowLeft className="w-5 h-5" style={{ color: "#9A938A" }} />
          </button>
          <span style={{ color: "#82828A", fontFamily: "'JetBrains Mono', monospace", fontSize: "11px", letterSpacing: "0.12em", textTransform: "uppercase" }}>Saved</span>
          <div style={{ width: "36px" }} />
        </div>
      </header>

      {/* Content */}
      <main style={{ padding: "22px 22px 96px", maxWidth: "640px", margin: "0 auto" }}>
        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} style={{ marginBottom: "20px" }}>
          <h1 style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontWeight: 600, fontSize: "26px", color: "#F2EEE9", margin: "0 0 3px" }}>Saved articles</h1>
          <p style={{ color: "#6E6862", fontSize: "13px", margin: 0 }}>
            {bookmarks.length} {bookmarks.length === 1 ? "story" : "stories"} kept for later
          </p>
        </motion.div>

        {bookmarks.length > 0 ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            <AnimatePresence>
              {bookmarks.map((article, idx) => (
                <motion.div
                  key={article.article_id}
                  onClick={() => navigate(`/article/${article.article_id}`)}
                  data-testid={`bookmark-${article.article_id}`}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, height: 0, marginBottom: 0, transition: { duration: 0.25 } }}
                  transition={{ duration: 0.35, delay: Math.min(idx, 8) * 0.04 }}
                  style={{ display: "flex", gap: "13px", background: "#131211", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "16px", padding: "12px", cursor: "pointer", overflow: "hidden" }}
                >
                  <div style={{ width: "72px", height: "72px", borderRadius: "11px", overflow: "hidden", flexShrink: 0, background: "#1a1917" }}>
                    {article.image_url && <img src={article.image_url} alt={article.title} style={{ width: "100%", height: "100%", objectFit: "cover" }} />}
                  </div>
                  <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", justifyContent: "center" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "7px", marginBottom: "5px" }}>
                      {article.category && <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "9.5px", letterSpacing: "0.1em", color: "#DC2626", textTransform: "uppercase" }}>{article.category}</span>}
                      {article.source && <><span style={{ color: "#3A362F" }}>·</span><span style={{ color: "#6E6862", fontSize: "11px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{article.source}</span></>}
                    </div>
                    <h3 style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontWeight: 500, fontSize: "15px", lineHeight: 1.32, color: "#ECE7E1", margin: 0, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{article.title}</h3>
                  </div>
                  <button
                    onClick={(e) => removeBookmark(article, idx, e)}
                    aria-label="Remove from saved"
                    data-testid={`remove-bookmark-${article.article_id}`}
                    style={{ alignSelf: "flex-start", width: "36px", height: "36px", flexShrink: 0, borderRadius: "10px", background: "#1a1917", border: "1px solid rgba(255,255,255,0.06)", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", color: "#8A847C" }}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        ) : (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ textAlign: "center", padding: "70px 0" }}>
            <div style={{ width: "72px", height: "72px", borderRadius: "50%", background: "#131211", border: "1px solid rgba(255,255,255,0.06)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 20px" }}>
              <Bookmark className="w-8 h-8" style={{ color: "#4A453F" }} />
            </div>
            <h2 style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontSize: "20px", color: "#ECE7E1", margin: "0 0 6px" }}>Nothing saved yet</h2>
            <p style={{ color: "#6E6862", fontSize: "13.5px", margin: "0 0 22px" }}>Bookmark a story and it waits for you here.</p>
            <button onClick={() => navigate("/feed")} data-testid="browse-articles-btn"
              style={{ padding: "11px 22px", borderRadius: "12px", background: "#DC2626", color: "#fff", border: "none", cursor: "pointer", fontSize: "14px", fontWeight: 500 }}>
              Browse the feed
            </button>
          </motion.div>
        )}
      </main>

      <BottomNav />
    </div>
  );
};

export default BookmarksPage;

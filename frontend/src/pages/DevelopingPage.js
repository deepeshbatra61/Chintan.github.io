import React, { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import axios from "axios";
import { ArrowLeft, Radio, Flame, Clock, ChevronRight } from "lucide-react";
import { SuryaLogo } from "../App";

const BACKEND_URL = "https://chintangithubio-production.up.railway.app";
const API = `${BACKEND_URL}/api`;

function formatRelativeTime(isoString) {
  if (!isoString) return "";
  const diff = (Date.now() - new Date(isoString).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

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
        <SuryaLogo className="w-14 h-14 animate-spin-slow" />
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", background: "#0A0A0A" }} data-testid="developing-page">
      <div style={{ position: "fixed", top: 0, left: "50%", transform: "translateX(-50%)", width: "440px", height: "280px", background: "radial-gradient(ellipse at center, rgba(220,38,38,0.10), rgba(10,10,10,0) 70%)", pointerEvents: "none", zIndex: 0 }} />

      {/* Header */}
      <header className="sticky z-40 px-4" style={{ top: 0, paddingTop: "var(--sat, 44px)", paddingBottom: "12px", background: "rgba(10,10,10,0.72)", backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)" }}>
        <div style={{ maxWidth: "640px", margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <button onClick={() => navigate(-1)} style={{ padding: "8px", background: "none", border: "none", cursor: "pointer" }} data-testid="back-btn">
            <ArrowLeft className="w-5 h-5" style={{ color: "#9A938A" }} />
          </button>
          <span style={{ color: "#82828A", fontFamily: "'JetBrains Mono', monospace", fontSize: "11px", letterSpacing: "0.12em", textTransform: "uppercase" }}>Developing</span>
          <Radio className="w-5 h-5" style={{ color: "#DC6B5A" }} />
        </div>
      </header>

      {/* Content */}
      <main style={{ position: "relative", zIndex: 1, padding: "24px 22px 40px", maxWidth: "640px", margin: "0 auto" }}>
        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} style={{ marginBottom: "22px" }}>
          <h1 style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontWeight: 600, fontSize: "26px", color: "#F2EEE9", margin: "0 0 4px" }}>Live &amp; developing</h1>
          <p style={{ color: "#8A847C", fontSize: "13.5px", margin: 0 }}>Stories still unfolding, updated as news breaks.</p>
        </motion.div>

        {topics.length > 0 ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {topics.map((topic, idx) => (
              <motion.button
                key={topic.story_id}
                onClick={() => navigate(`/developing/${topic.story_id}`)}
                data-testid={`topic-${topic.story_id}`}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.35, delay: Math.min(idx, 8) * 0.06 }}
                style={{ textAlign: "left", width: "100%", background: "#131211", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "16px", padding: "16px", cursor: "pointer" }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "9px" }}>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", fontFamily: "'JetBrains Mono', monospace", fontSize: "9.5px", letterSpacing: "0.12em", color: "#DC6B5A", background: "rgba(220,38,38,0.12)", padding: "2px 8px", borderRadius: "20px" }}>
                    <span style={{ width: "5px", height: "5px", borderRadius: "50%", background: "#DC2626" }} className="animate-pulse" /> LIVE
                  </span>
                  <span style={{ color: "#6E6862", fontSize: "11px", fontFamily: "'JetBrains Mono', monospace" }}>
                    {topic.article_count} update{topic.article_count !== 1 ? "s" : ""}
                  </span>
                  {topic.last_updated && <><span style={{ color: "#3A362F" }}>·</span><span style={{ color: "#6E6862", fontSize: "11px", fontFamily: "'JetBrains Mono', monospace" }}>{formatRelativeTime(topic.last_updated)}</span></>}
                </div>
                <h2 style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontWeight: 600, fontSize: "17px", lineHeight: 1.28, color: "#F2EEE9", margin: 0 }}>{topic.title}</h2>
                {topic.latest_article && (
                  <p style={{ color: "#8A847C", fontSize: "13px", lineHeight: 1.4, margin: "7px 0 0", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{topic.latest_article.title}</p>
                )}
                <div style={{ display: "flex", alignItems: "center", gap: "4px", marginTop: "11px", color: "#8A847C", fontSize: "12px" }}>
                  Follow the thread <ChevronRight className="w-3.5 h-3.5" />
                </div>
              </motion.button>
            ))}
          </div>
        ) : (
          <div style={{ textAlign: "center", padding: "70px 0" }}>
            <div style={{ width: "72px", height: "72px", borderRadius: "50%", background: "#131211", border: "1px solid rgba(255,255,255,0.06)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 20px" }}>
              <Flame className="w-8 h-8" style={{ color: "#4A453F" }} />
            </div>
            <h2 style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontSize: "20px", color: "#ECE7E1", margin: "0 0 6px" }}>Nothing developing right now</h2>
            <p style={{ color: "#6E6862", fontSize: "13.5px", margin: 0 }}>When a story starts heating up, it lands here.</p>
          </div>
        )}

        <div style={{ textAlign: "center", marginTop: "24px", display: "flex", alignItems: "center", justifyContent: "center", gap: "6px", color: "#4A453F", fontSize: "11px" }}>
          <Clock className="w-3 h-3" /> Refreshes every 60 seconds
        </div>
      </main>
    </div>
  );
};

export default DevelopingPage;

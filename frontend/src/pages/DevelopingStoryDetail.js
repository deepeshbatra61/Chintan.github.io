import React, { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import axios from "axios";
import { ArrowLeft, Flame, Clock } from "lucide-react";
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

const trendLabel = (m) => {
  if (m?.state) {
    // Wave kind: surging/simmering/watching, not gaining/cooling/steady —
    // a quiet stretch is expected behavior for these stories, not decay.
    const head = m.state === "surging" ? "Surging" : m.state === "simmering" ? "Simmering" : "Watching";
    if (m.state === "watching") return `${head} · quiet ${m.quiet_days || 0}d`;
    return `${head} · ${m.today} update${m.today === 1 ? "" : "s"} today`;
  }
  const t = m?.trend;
  const n = m?.today || 0;
  const head = t === "gaining" ? "Gaining pace" : t === "cooling" ? "Cooling off" : "Holding steady";
  return `${head} · ${n} update${n === 1 ? "" : "s"} today`;
};

const WAVE_STATE_COLOR = { surging: "#DC2626", simmering: "#F59E0B", watching: "#4A453F" };

const DevelopingStoryDetail = () => {
  const { storyId } = useParams();
  const navigate = useNavigate();
  const [story, setStory] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchStory = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/developing-stories/${storyId}`, { withCredentials: true });
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
        <SuryaLogo className="w-14 h-14 animate-spin-slow" />
      </div>
    );
  }

  if (!story) {
    return (
      <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center">
        <div style={{ textAlign: "center" }}>
          <p style={{ color: "#8A847C", marginBottom: "14px" }}>Story not found</p>
          <button onClick={() => navigate(-1)} style={{ color: "#DC6B5A", background: "none", border: "none", cursor: "pointer" }}>Go back</button>
        </div>
      </div>
    );
  }

  const articles = story.articles || [];
  const momentum = story.momentum || {};
  const buckets = momentum.buckets || [];
  const maxBucket = Math.max(1, ...buckets);

  return (
    <div style={{ minHeight: "100vh", background: "#0A0A0A" }} data-testid="developing-story-detail">
      {/* faint top glow */}
      <div style={{ position: "fixed", top: 0, left: "50%", transform: "translateX(-50%)", width: "420px", height: "280px", background: "radial-gradient(ellipse at center, rgba(220,38,38,0.10), rgba(10,10,10,0) 70%)", pointerEvents: "none", zIndex: 0 }} />

      {/* Header */}
      <header className="sticky z-40 px-4" style={{ top: 0, paddingTop: "var(--sat, 44px)", paddingBottom: "12px", background: "rgba(10,10,10,0.72)", backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)" }}>
        <div style={{ maxWidth: "640px", margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <button onClick={() => navigate(-1)} style={{ padding: "8px", background: "none", border: "none", cursor: "pointer" }} data-testid="back-btn">
            <ArrowLeft className="w-5 h-5" style={{ color: "#9A938A" }} />
          </button>
          <span style={{ display: "inline-flex", alignItems: "center", gap: "6px", fontFamily: "'JetBrains Mono', monospace", fontSize: "10px", letterSpacing: "0.14em", color: "#DC6B5A", background: "rgba(220,38,38,0.12)", padding: "4px 10px", borderRadius: "20px" }}>
            <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "#DC2626" }} className="animate-pulse" />
            LIVE
          </span>
          <Flame className="w-5 h-5" style={{ color: "#DC6B5A" }} />
        </div>
      </header>

      {/* Content */}
      <main style={{ position: "relative", zIndex: 1, padding: "18px 22px 40px", maxWidth: "640px", margin: "0 auto" }}>
        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}>
          <h1 style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontWeight: 600, fontSize: "25px", lineHeight: 1.2, color: "#F2EEE9", margin: "0 0 8px" }}>{story.title}</h1>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", fontFamily: "'JetBrains Mono', monospace", fontSize: "11px", color: "#6E6862" }}>
            <span>{story.article_count || articles.length} update{(story.article_count || articles.length) === 1 ? "" : "s"}</span>
            <span>·</span>
            <span>updated {formatRelativeTime(story.last_updated)}</span>
          </div>
        </motion.div>

        {/* Where it stands */}
        {(story.state_summary || buckets.length > 0) && (
          <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 }}
            style={{ background: "linear-gradient(135deg, rgba(220,38,38,0.10), #131211 62%)", border: "1px solid rgba(220,38,38,0.22)", borderRadius: "16px", padding: "16px", margin: "16px 0 6px" }}>
            <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "9px", letterSpacing: "0.16em", color: "#DC6B5A", textTransform: "uppercase", marginBottom: "8px" }}>Where it stands</div>
            {story.state_summary && (
              <p style={{ margin: 0, fontFamily: "'Playfair Display', 'Georgia', serif", fontSize: "15.5px", lineHeight: 1.46, color: "#ECE7E1" }}>{story.state_summary}</p>
            )}
            <div style={{ display: "flex", alignItems: "center", gap: "9px", marginTop: story.state_summary ? "12px" : 0 }}>
              <div style={{ display: "flex", alignItems: "flex-end", gap: story.kind === "wave" ? "1.5px" : "2px", height: story.kind === "wave" ? "30px" : "18px" }}>
                {story.kind === "wave" ? (
                  // Direction 1: Seismograph — a literal waveform of the story's
                  // full life (weeks), not just today. Crests and troughs are
                  // the whole point, so every bar is colored by the CURRENT
                  // overall intensity rather than spotlighting only the newest.
                  buckets.map((b, i) => (
                    <span key={i} style={{ width: "3px", borderRadius: "2px 2px 0 0", minHeight: "2px", height: `${Math.max(2, (b / maxBucket) * 30)}px`, background: WAVE_STATE_COLOR[momentum.state] || "#4A453F" }} />
                  ))
                ) : (
                  buckets.map((b, i) => (
                    <span key={i} style={{ width: "4px", borderRadius: "1px", height: `${Math.max(3, (b / maxBucket) * 18)}px`, background: i === buckets.length - 1 ? "#DC2626" : "#7A2A24" }} />
                  ))
                )}
              </div>
              <span style={{ fontSize: "11px", color: "#8A847C", fontFamily: "'Manrope', sans-serif" }}>{trendLabel(momentum)}</span>
            </div>
          </motion.div>
        )}

        {/* Timeline */}
        {articles.length > 0 ? (
          <div style={{ position: "relative", marginTop: "20px", paddingLeft: "22px" }}>
            <div style={{ position: "absolute", left: "5px", top: "4px", bottom: "10px", width: "1px", background: "rgba(220,38,38,0.25)" }} />
            {articles.map((article, idx) => (
              <motion.div
                key={article.article_id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: Math.min(idx, 8) * 0.05 }}
                onClick={() => navigate(`/article/${article.article_id}`)}
                data-testid={`timeline-article-${article.article_id}`}
                style={{ position: "relative", marginBottom: "16px", cursor: "pointer" }}
              >
                <span style={{ position: "absolute", left: "-21px", top: "4px", width: "11px", height: "11px", borderRadius: "50%", background: idx === 0 ? "#DC2626" : "#5A544D", border: "2px solid #0A0A0A" }} className={idx === 0 ? "animate-pulse" : ""} />
                <div style={{ background: "#131211", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "14px", padding: "13px 14px" }}>
                  {idx === 0 && (
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", fontFamily: "'JetBrains Mono', monospace", fontSize: "9px", letterSpacing: "0.1em", color: "#DC6B5A", marginBottom: "6px" }}>
                      <span style={{ width: "5px", height: "5px", borderRadius: "50%", background: "#DC2626" }} className="animate-pulse" /> LATEST
                    </span>
                  )}
                  <h3 style={{ fontSize: "14px", lineHeight: 1.36, color: "#ECE7E1", margin: 0, fontWeight: 500 }}>{article.title}</h3>
                  <div style={{ display: "flex", justifyContent: "space-between", marginTop: "8px", fontFamily: "'JetBrains Mono', monospace", fontSize: "10px", color: "#6E6862" }}>
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "60%" }}>{article.source}</span>
                    <span>{formatRelativeTime(article.published_at)}</span>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        ) : (
          <div style={{ textAlign: "center", padding: "56px 0" }}>
            <Flame className="w-10 h-10" style={{ color: "#4A453F", margin: "0 auto 14px" }} />
            <p style={{ color: "#8A847C" }}>No updates yet</p>
            <p style={{ color: "#5A544D", fontSize: "13px", marginTop: "4px" }}>Check back as this story develops.</p>
          </div>
        )}

        <div style={{ textAlign: "center", marginTop: "24px", display: "flex", alignItems: "center", justifyContent: "center", gap: "6px", color: "#4A453F", fontSize: "11px" }}>
          <Clock className="w-3 h-3" /> Refreshes every 60 seconds
        </div>
      </main>
    </div>
  );
};

export default DevelopingStoryDetail;

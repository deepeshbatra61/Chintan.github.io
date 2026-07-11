import React, { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import axios from "axios";
import { ArrowLeft, Sun, CloudSun, Moon, Clock, ChevronRight } from "lucide-react";
import { SuryaLogo, useAuth } from "../App";
import BottomNav from "../components/BottomNav";

const BACKEND_URL = "https://chintangithubio-production.up.railway.app";
const API = `${BACKEND_URL}/api`;

// One theme (obsidian + red) across all three briefs — the only per-time cue is a
// quiet icon and a very faint top glow. No gradients-as-decoration, no stars.
const briefMeta = {
  morning: { Icon: Sun,      glow: "rgba(245,158,11,0.10)",  greeting: "Good morning",   sub: "Three stories to start the day." },
  midday:  { Icon: CloudSun, glow: "rgba(220,38,38,0.09)",   greeting: "Good afternoon", sub: "Three stories from the day so far." },
  night:   { Icon: Moon,     glow: "rgba(129,140,248,0.10)", greeting: "Good evening",   sub: "Three stories that shaped today." },
};

const cleanText = (text) =>
  (text || "").replace(/^#+\s*/gm, "").replace(/\*\*/g, "").trim();

// The backend writes exactly 3 sentences, one per top category, index-aligned
// with `categories` and `referenced_stories`.
const splitSentences = (text) =>
  cleanText(text)
    .split(/\.\s+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 3)
    .map((s) => s.replace(/\.$/, "") + ".");

const BriefPage = () => {
  const { briefType } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [brief, setBrief] = useState(null);
  const [loading, setLoading] = useState(true);

  const meta = briefMeta[briefType] || briefMeta.morning;
  const Icon = meta.Icon;
  const firstName = user?.name?.split(" ")[0] || "";

  const fetchBrief = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/briefs/${briefType}`, { withCredentials: true });
      setBrief(r.data);
    } catch (e) {
      console.error("Error fetching brief:", e);
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
        <SuryaLogo className="w-14 h-14 animate-spin-slow" />
      </div>
    );
  }

  const sentences = splitSentences(brief?.summary);
  const stories = brief?.referenced_stories || [];
  const categories = brief?.categories || [];
  const greeting = brief?.greeting || meta.greeting;
  const readTime = brief?.read_time || "1 min read";

  return (
    <div style={{ minHeight: "100vh", background: "#0A0A0A" }} data-testid={`brief-${briefType}-page`}>
      {/* Very faint time-of-day glow */}
      <div style={{ position: "fixed", top: 0, left: "50%", transform: "translateX(-50%)", width: "420px", height: "300px", background: `radial-gradient(ellipse at center, ${meta.glow}, rgba(10,10,10,0) 70%)`, pointerEvents: "none", zIndex: 0 }} />

      {/* Header */}
      <header
        className="sticky z-40 px-4"
        style={{ top: 0, paddingTop: "var(--sat, 44px)", paddingBottom: "12px", background: "rgba(10,10,10,0.72)", backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)" }}
      >
        <div style={{ maxWidth: "640px", margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <button onClick={() => navigate(-1)} style={{ padding: "8px", background: "none", border: "none", cursor: "pointer" }} data-testid="back-btn">
            <ArrowLeft className="w-5 h-5" style={{ color: "#9A938A" }} />
          </button>
          <span style={{ color: "#82828A", fontFamily: "'JetBrains Mono', monospace", fontSize: "11px", letterSpacing: "0.12em", textTransform: "uppercase" }}>Daily brief</span>
          <div style={{ width: "36px" }} />
        </div>
      </header>

      {/* Content */}
      <main style={{ position: "relative", zIndex: 1, padding: "0 22px 96px", maxWidth: "640px", margin: "0 auto" }}>
        {/* Greeting */}
        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45 }} style={{ paddingTop: "28px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "11px", marginBottom: "8px" }}>
            <Icon className="w-5 h-5" style={{ color: "#DC2626", flexShrink: 0 }} />
            <h1 style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontWeight: 600, fontSize: "27px", lineHeight: 1.15, color: "#F2EEE9", margin: 0 }}>
              {greeting}{firstName ? `, ${firstName}` : ""}
            </h1>
          </div>
          <p style={{ color: "#8E877E", fontSize: "14px", margin: "0 0 6px", fontFamily: "'Manrope', sans-serif" }}>{meta.sub}</p>
          <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "#5A544D", fontSize: "12px" }}>
            <Clock className="w-3.5 h-3.5" />
            <span>{readTime}</span>
          </div>
        </motion.div>

        {/* Section label */}
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "9.5px", letterSpacing: "0.2em", color: "#5A544D", textTransform: "uppercase", margin: "30px 0 14px" }}>
          Across your interests
        </div>

        {/* Three story cards */}
        {stories.length > 0 ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {stories.map((story, idx) => {
              const category = categories[idx];
              const take = sentences[idx] || story.title;
              return (
                <motion.button
                  key={story.article_id || idx}
                  onClick={() => story.article_id && navigate(`/article/${story.article_id}`)}
                  data-testid={`brief-story-${idx}`}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.4, delay: 0.12 + idx * 0.08, ease: [0.22, 1, 0.36, 1] }}
                  style={{
                    textAlign: "left", width: "100%", background: "#131211",
                    border: "1px solid rgba(255,255,255,0.06)", borderRadius: "16px",
                    padding: "17px 18px", cursor: "pointer",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "11px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px", minWidth: 0 }}>
                      {category && (
                        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "10px", letterSpacing: "0.12em", color: "#DC2626", textTransform: "uppercase" }}>{category}</span>
                      )}
                      {story.source && (
                        <>
                          <span style={{ color: "#3A362F" }}>·</span>
                          <span style={{ color: "#6E6862", fontSize: "12px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{story.source}</span>
                        </>
                      )}
                    </div>
                    <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "12px", color: "#2E2A25", flexShrink: 0 }}>{String(idx + 1).padStart(2, "0")}</span>
                  </div>
                  <p style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontWeight: 500, fontSize: "17px", lineHeight: 1.42, color: "#ECE7E1", margin: 0 }}>
                    {take}
                  </p>
                  <div style={{ display: "flex", alignItems: "center", gap: "4px", marginTop: "12px", color: "#8A847C", fontSize: "12px", fontFamily: "'Manrope', sans-serif" }}>
                    Read the story <ChevronRight className="w-3.5 h-3.5" />
                  </div>
                </motion.button>
              );
            })}
          </div>
        ) : (
          <p style={{ color: "#8A847C", textAlign: "center", padding: "48px 0", fontSize: "14px" }}>
            No stories are ready right now. Check back soon.
          </p>
        )}
      </main>

      <BottomNav />
    </div>
  );
};

export default BriefPage;

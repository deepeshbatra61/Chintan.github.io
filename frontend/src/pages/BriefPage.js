import React, { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion, useReducedMotion } from "framer-motion";
import axios from "axios";
import { ArrowLeft, Clock, ChevronRight } from "lucide-react";
import { SuryaLogo, useAuth } from "../App";
import BottomNav from "../components/BottomNav";

const BACKEND_URL = "https://chintangithubio-production.up.railway.app";
const API = `${BACKEND_URL}/api`;

const EASE = [0.16, 1, 0.3, 1];

// "The Dawn": a living time-of-day sky behind the brief. Each entry carries its
// own gradient (dawn amber / midday warmth / night indigo) and a drift/glow hue.
const briefMeta = {
  morning: {
    greeting: "Good morning", sub: "Three stories to start the day.",
    sky: "radial-gradient(130% 80% at 50% -8%, rgba(245,158,11,.26), rgba(220,38,38,.09) 32%, rgba(10,10,10,0) 60%), linear-gradient(180deg, #1a120c 0%, #100b09 30%, #0A0A0A 62%)",
    drift: "rgba(245,158,11,0.14)", glow: "rgba(245,158,11,0.55)",
  },
  midday: {
    greeting: "Good afternoon", sub: "Three stories from the day so far.",
    sky: "radial-gradient(130% 80% at 50% -8%, rgba(220,38,38,.20), rgba(234,88,12,.07) 34%, rgba(10,10,10,0) 60%), linear-gradient(180deg, #170f0c 0%, #0f0b0a 30%, #0A0A0A 62%)",
    drift: "rgba(234,88,12,0.12)", glow: "rgba(220,38,38,0.5)",
  },
  night: {
    greeting: "Good evening", sub: "Three stories that shaped today.",
    sky: "radial-gradient(130% 80% at 50% -8%, rgba(99,102,241,.22), rgba(124,58,237,.10) 34%, rgba(10,10,10,0) 60%), linear-gradient(180deg, #0f1018 0%, #0b0b12 30%, #0A0A0A 62%)",
    drift: "rgba(99,102,241,0.13)", glow: "rgba(129,140,248,0.5)",
  },
};

const cleanText = (text) => (text || "").replace(/^#+\s*/gm, "").replace(/\*\*/g, "").trim();

// The backend writes exactly 3 sentences, one per top category, index-aligned
// with `categories` and `referenced_stories`.
const splitSentences = (text) =>
  cleanText(text).split(/\.\s+/).map((s) => s.trim()).filter(Boolean).slice(0, 3).map((s) => s.replace(/\.$/, "") + ".");

const BriefPage = () => {
  const { briefType } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [brief, setBrief] = useState(null);
  const [loading, setLoading] = useState(true);
  const R = useReducedMotion();

  const meta = briefMeta[briefType] || briefMeta.morning;
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

  useEffect(() => { fetchBrief(); }, [fetchBrief]);

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
  const greetWords = `${greeting}${firstName ? `, ${firstName}` : ""}`.split(" ");

  return (
    <div style={{ minHeight: "100vh", background: "#0A0A0A", position: "relative" }} data-testid={`brief-${briefType}-page`}>
      {/* Living dawn sky */}
      <div style={{ position: "fixed", inset: 0, zIndex: 0, background: meta.sky, pointerEvents: "none" }}>
        {!R && (
          <motion.div
            animate={{ x: ["-4%", "6%"], y: ["0%", "3%"] }}
            transition={{ duration: 14, repeat: Infinity, repeatType: "reverse", ease: "easeInOut" }}
            style={{ position: "absolute", inset: "-20%", background: `radial-gradient(40% 30% at 60% 12%, ${meta.drift}, transparent 70%)` }}
          />
        )}
      </div>
      {/* Film grain */}
      <svg style={{ position: "fixed", inset: 0, zIndex: 0, opacity: 0.05, mixBlendMode: "overlay", pointerEvents: "none" }} xmlns="http://www.w3.org/2000/svg">
        <filter id="brief-grain"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch" /><feColorMatrix type="saturate" values="0" /></filter>
        <rect width="100%" height="100%" filter="url(#brief-grain)" />
      </svg>

      {/* Header */}
      <header className="sticky z-40 px-4" style={{ top: 0, paddingTop: "var(--sat, 44px)", paddingBottom: "12px", background: "rgba(10,10,10,0.55)", backdropFilter: "blur(14px)", WebkitBackdropFilter: "blur(14px)" }}>
        <div style={{ maxWidth: "640px", margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <button onClick={() => navigate(-1)} style={{ padding: "8px", background: "none", border: "none", cursor: "pointer" }} data-testid="back-btn">
            <ArrowLeft className="w-5 h-5" style={{ color: "#C9BFB4" }} />
          </button>
          <span style={{ color: "#9a8d80", fontFamily: "'JetBrains Mono', monospace", fontSize: "11px", letterSpacing: "0.12em", textTransform: "uppercase" }}>Daily brief</span>
          <div style={{ width: "36px" }} />
        </div>
      </header>

      {/* Content */}
      <main style={{ position: "relative", zIndex: 1, padding: "0 22px 96px", maxWidth: "640px", margin: "0 auto" }}>
        {/* Crown — turning Surya + word-by-word greeting */}
        <div style={{ textAlign: "center", paddingTop: "30px" }}>
          <motion.div
            animate={R ? {} : { rotate: 360 }}
            transition={R ? {} : { duration: 26, repeat: Infinity, ease: "linear" }}
            style={{ display: "inline-block", marginBottom: "18px", filter: `drop-shadow(0 0 14px ${meta.glow})` }}
          >
            <SuryaLogo className="w-14 h-14" />
          </motion.div>

          <h1 style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontWeight: 600, fontSize: "clamp(28px, 8vw, 34px)", lineHeight: 1.12, color: "#F4EEE6", margin: 0, letterSpacing: "-0.01em", textWrap: "balance" }}>
            {greetWords.map((w, i) => (
              <motion.span
                key={i}
                initial={R ? false : { opacity: 0, y: 18 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.7, delay: R ? 0 : 0.08 + i * 0.1, ease: EASE }}
                style={{ display: "inline-block", marginRight: "0.28em" }}
              >
                {w}
              </motion.span>
            ))}
          </h1>

          <motion.p
            initial={R ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: R ? 0 : 0.5, duration: 0.6 }}
            style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontStyle: "italic", fontSize: "15px", color: "#b7ada2", margin: "12px 0 0" }}
          >
            {meta.sub}
          </motion.p>
          <motion.div
            initial={R ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: R ? 0 : 0.62, duration: 0.6 }}
            style={{ display: "inline-flex", alignItems: "center", gap: "6px", color: "#8a7d70", fontSize: "12px", fontFamily: "'JetBrains Mono', monospace", marginTop: "10px" }}
          >
            <Clock className="w-3.5 h-3.5" /><span>{readTime}</span>
          </motion.div>
        </div>

        {/* Section label */}
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "9.5px", letterSpacing: "0.2em", color: "#6b625a", textTransform: "uppercase", margin: "36px 0 14px" }}>
          Across your interests
        </div>

        {/* Three story cards — cinematic unveil as they rise into view */}
        {stories.length > 0 ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
            {stories.map((story, idx) => {
              const category = categories[idx];
              const take = sentences[idx] || story.title;
              return (
                <motion.button
                  key={story.article_id || idx}
                  onClick={() => story.article_id && navigate(`/article/${story.article_id}`)}
                  data-testid={`brief-story-${idx}`}
                  initial={R ? false : { opacity: 0, y: 26, filter: "blur(8px)", clipPath: "inset(0 0 14% 0)" }}
                  whileInView={{ opacity: 1, y: 0, filter: "blur(0px)", clipPath: "inset(0 0 0% 0)" }}
                  viewport={{ once: true, amount: 0.35 }}
                  transition={{ duration: 0.8, ease: EASE }}
                  whileTap={R ? undefined : { scale: 0.985 }}
                  style={{
                    textAlign: "left", width: "100%",
                    background: "linear-gradient(180deg, rgba(26,20,15,0.66), rgba(19,18,17,0.9))",
                    border: "1px solid rgba(255,255,255,0.07)", borderRadius: "18px",
                    padding: "19px 18px", cursor: "pointer",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px", minWidth: 0 }}>
                      {category && (
                        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "10px", letterSpacing: "0.12em", color: "#DC6B5A", textTransform: "uppercase" }}>{category}</span>
                      )}
                      {story.source && (
                        <>
                          <span style={{ color: "#3A362F" }}>·</span>
                          <span style={{ color: "#6E6862", fontSize: "12px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{story.source}</span>
                        </>
                      )}
                    </div>
                    <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "12px", color: "#3a3128", flexShrink: 0 }}>{String(idx + 1).padStart(2, "0")}</span>
                  </div>
                  <p style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontWeight: 500, fontSize: "18px", lineHeight: 1.42, color: "#ECE3D6", margin: 0 }}>
                    {take}
                  </p>
                  <div style={{ display: "flex", alignItems: "center", gap: "4px", marginTop: "13px", color: "#c9b8a6", fontSize: "12px", fontFamily: "'Manrope', sans-serif" }}>
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

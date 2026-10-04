import React, { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import axios from "axios";
import { ArrowLeft, Flame, Clock, ExternalLink } from "lucide-react";
import { Browser } from "@capacitor/browser";
import { SuryaLogo, useAuth } from "../App";
import FollowBar from "../components/FollowBar";
import SignInPrompt from "../components/SignInPrompt";
import { CoverageSheet, mixSentence } from "../components/Coverage";
import { calendarIcon, formatCalendarDate } from "../lib/calendar";
import { formatRelativeTime, clockTime, sinceLooked } from "../lib/time";

// "Since you looked" for guests lives on the device; signed-in readers keep it
// on the server (POST /stories/{id}/seen returns the previous time).
const SEEN_KEY = "chintan.storySeen";
function guestSeen(storyId) {
  try {
    const all = JSON.parse(localStorage.getItem(SEEN_KEY) || "{}");
    const prev = all[storyId] || null;
    all[storyId] = new Date().toISOString();
    const keys = Object.keys(all);
    if (keys.length > 200) delete all[keys[0]];          // keep it small
    localStorage.setItem(SEEN_KEY, JSON.stringify(all));
    return prev;
  } catch {
    return null;
  }
}

// Same pattern as ArticlePage's openSource: in-app browser on native, new
// tab on web. Calendar citations are the one place this page links out.
const openSource = async (url) => {
  if (!url) return;
  if (window.Capacitor?.isNativePlatform()) {
    try { await Browser.open({ url }); return; } catch { /* fall through */ }
  }
  window.open(url, "_blank", "noopener,noreferrer");
};

const hostOf = (url) => {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; }
};

const BACKEND_URL = "https://chintangithubio-production.up.railway.app";
const API = `${BACKEND_URL}/api`;

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

const WAVE_STATE_COLOR = { surging: "#DC2626", simmering: "var(--c-warn-ink)", watching: "var(--c-dim)" };

const DevelopingStoryDetail = () => {
  const { storyId } = useParams();
  const navigate = useNavigate();
  const [story, setStory] = useState(null);
  const [loading, setLoading] = useState(true);
  const { user } = useAuth();
  const [prevSeen, setPrevSeen] = useState(undefined);   // undefined = not read yet
  const [signIn, setSignIn] = useState(false);
  const [coverageOpen, setCoverageOpen] = useState(false);
  const [barH, setBarH] = useState(84);
  const dividerRef = useRef(null);
  const scrolled = useRef(false);

  // Read (and move on) "since you looked" once per visit, not on each refresh.
  useEffect(() => {
    let alive = true;
    setPrevSeen(undefined);
    scrolled.current = false;
    if (user) {
      axios.post(`${API}/stories/${encodeURIComponent(storyId)}/seen`, {}, { withCredentials: true })
        .then((r) => { if (alive) setPrevSeen(r.data.previous_seen_at || null); })
        .catch(() => { if (alive) setPrevSeen(null); });
    } else {
      setPrevSeen(guestSeen(storyId));
    }
    return () => { alive = false; };
  }, [storyId, user]);

  // Opened from a follow ping (or any return visit with news): bring the
  // "since you looked" line into view once, if it's below the fold.
  useEffect(() => {
    const el = dividerRef.current;
    if (scrolled.current || !el) return;
    scrolled.current = true;
    if (el.getBoundingClientRect().top > window.innerHeight * 0.6) {
      el.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  });

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
      <div className="min-h-screen bg-page flex items-center justify-center">
        <SuryaLogo className="w-14 h-14 animate-spin-slow" />
      </div>
    );
  }

  if (!story) {
    return (
      <div className="min-h-screen bg-page flex items-center justify-center">
        <div style={{ textAlign: "center" }}>
          <p style={{ color: "var(--c-muted)", marginBottom: "14px" }}>Story not found</p>
          <button onClick={() => navigate(-1)} style={{ color: "var(--c-accent-ink)", background: "none", border: "none", cursor: "pointer" }}>Go back</button>
        </div>
      </div>
    );
  }

  // ── Chintan Calendar ──────────────────────────────────────────────────
  // A separate layout, not a variation on the one below. Everything the
  // timeline view is built around — updates, momentum, "latest" — is
  // meaningless for a date-driven entry with no articles, which is why
  // falling through to it rendered "0 updates / No updates yet" under a
  // LIVE badge. What matters here instead is the researched paragraph and,
  // above all, the sources: they're what let a reader check the claim.
  if (story.kind === "calendar") {
    const Icon = calendarIcon(story.category);
    const citations = story.citations || [];
    // Two URLs from one publication are one source to a reader, so dedupe by
    // host — the same idea the backend enforces numerically before it will
    // show this card at all.
    const sources = [];
    const seen = new Set();
    for (const c of citations) {
      const host = hostOf(c.url);
      if (host && !seen.has(host)) { seen.add(host); sources.push({ ...c, host }); }
    }

    return (
      <div style={{ minHeight: "100vh", background: "var(--c-bg)" }} data-testid="developing-story-detail">
        <div style={{ position: "fixed", top: 0, left: "50%", transform: "translateX(-50%)", width: "420px", height: "280px", background: "radial-gradient(ellipse at center, rgba(220,38,38,0.10), rgb(var(--c-bg-rgb) / 0) 70%)", pointerEvents: "none", zIndex: 0 }} />

        <header className="sticky z-40 px-4" style={{ top: 0, paddingTop: "var(--sat)", paddingBottom: "12px", background: "rgb(var(--c-bg-rgb) / 0.72)", backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)" }}>
          <div style={{ maxWidth: "640px", margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <button onClick={() => navigate(-1)} style={{ padding: "8px", background: "none", border: "none", cursor: "pointer" }} data-testid="back-btn">
              <ArrowLeft className="w-5 h-5" style={{ color: "var(--c-muted2)" }} />
            </button>
            {/* Deliberately not the LIVE pill: nothing here is live. */}
            <span style={{ color: "var(--c-muted)", fontFamily: "'JetBrains Mono', monospace", fontSize: "10px", letterSpacing: "0.14em", textTransform: "uppercase" }}>Chintan Calendar</span>
            <Icon className="w-5 h-5" style={{ color: "var(--c-accent-ink)" }} />
          </div>
        </header>

        <main style={{ position: "relative", zIndex: 1, padding: "18px 22px 40px", maxWidth: "640px", margin: "0 auto" }}>
          <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}>
            <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "10.5px", letterSpacing: "0.14em", color: "var(--c-accent-ink)", marginBottom: "10px" }}>
              {formatCalendarDate(story.calendar_date)}
            </div>
            <h1 style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontWeight: 600, fontSize: "25px", lineHeight: 1.2, color: "var(--c-ink)", margin: 0 }}>{story.title}</h1>
          </motion.div>

          {story.content && (
            <motion.p initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 }}
              style={{ marginTop: "18px", marginBottom: 0, fontSize: "15.5px", lineHeight: 1.62, color: "var(--c-sub)" }}>
              {story.content}
            </motion.p>
          )}

          {sources.length > 0 && (
            <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.14 }} style={{ marginTop: "26px" }}>
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "9px", letterSpacing: "0.16em", color: "var(--c-faint)", textTransform: "uppercase", marginBottom: "10px" }}>
                Sources
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                {sources.map((s) => (
                  <button
                    key={s.url}
                    onClick={() => openSource(s.url)}
                    data-testid={`calendar-source-${s.host}`}
                    style={{ textAlign: "left", width: "100%", display: "flex", alignItems: "center", gap: "10px", background: "var(--c-surface)", border: "1px solid rgb(var(--c-fg-rgb) / 0.06)", borderRadius: "12px", padding: "12px 13px", cursor: "pointer" }}
                  >
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "10.5px", color: "var(--c-accent-ink)", marginBottom: s.title ? "4px" : 0 }}>{s.host}</div>
                      {s.title && (
                        <div style={{ fontSize: "13px", lineHeight: 1.35, color: "var(--c-muted)", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{s.title}</div>
                      )}
                    </div>
                    <ExternalLink className="w-3.5 h-3.5" style={{ color: "var(--c-dim)", flexShrink: 0 }} />
                  </button>
                ))}
              </div>
            </motion.div>
          )}
        </main>
      </div>
    );
  }

  const articles = story.articles || [];
  const { isNew, newCount, showDivider } = sinceLooked(articles, prevSeen);
  const momentum = story.momentum || {};
  const buckets = momentum.buckets || [];
  const maxBucket = Math.max(1, ...buckets);

  return (
    <div style={{ minHeight: "100vh", background: "var(--c-bg)" }} data-testid="developing-story-detail">
      {/* faint top glow */}
      <div style={{ position: "fixed", top: 0, left: "50%", transform: "translateX(-50%)", width: "420px", height: "280px", background: "radial-gradient(ellipse at center, rgba(220,38,38,0.10), rgb(var(--c-bg-rgb) / 0) 70%)", pointerEvents: "none", zIndex: 0 }} />

      {/* Header */}
      <header className="sticky z-40 px-4" style={{ top: 0, paddingTop: "var(--sat)", paddingBottom: "12px", background: "rgb(var(--c-bg-rgb) / 0.72)", backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)" }}>
        <div style={{ maxWidth: "640px", margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <button onClick={() => navigate(-1)} style={{ padding: "8px", background: "none", border: "none", cursor: "pointer" }} data-testid="back-btn">
            <ArrowLeft className="w-5 h-5" style={{ color: "var(--c-muted2)" }} />
          </button>
          {/* LIVE only when something actually landed in the last 24h. It used
              to be unconditional, so it sat above "0 updates today". */}
          {(momentum.today || 0) > 0 ? (
            <span style={{ display: "inline-flex", alignItems: "center", gap: "6px", fontFamily: "'JetBrains Mono', monospace", fontSize: "10px", letterSpacing: "0.14em", color: "var(--c-accent-ink)", background: "rgba(220,38,38,0.12)", padding: "4px 10px", borderRadius: "20px" }}>
              <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "#DC2626" }} className="animate-pulse" />
              LIVE
            </span>
          ) : (
            <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "10px", letterSpacing: "0.14em", color: "var(--c-faint)", background: "rgb(var(--c-fg-rgb) / 0.05)", padding: "4px 10px", borderRadius: "20px" }}>
              DEVELOPING
            </span>
          )}
          <Flame className="w-5 h-5" style={{ color: "var(--c-accent-ink)" }} />
        </div>
      </header>

      {/* Content */}
      <main style={{ position: "relative", zIndex: 1, padding: `18px 22px ${40 + barH}px`, maxWidth: "640px", margin: "0 auto" }}>
        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}>
          <h1 style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontWeight: 600, fontSize: "25px", lineHeight: 1.2, color: "var(--c-ink)", margin: "0 0 8px" }}>{story.title}</h1>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap", fontFamily: "'JetBrains Mono', monospace", fontSize: "11px", color: "var(--c-faint)" }}>
            <span>{story.article_count || articles.length} update{(story.article_count || articles.length) === 1 ? "" : "s"}</span>
            {story.outlets_count > 1 && <><span>·</span><span>{story.outlets_count} outlets</span></>}
            <span>·</span>
            <span>updated {formatRelativeTime(story.last_updated)}</span>
          </div>
        </motion.div>

        {/* Where it stands */}
        {(story.state_summary || buckets.length > 0) && (
          <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 }}
            style={{ background: "linear-gradient(135deg, rgba(220,38,38,0.10), var(--c-surface) 62%)", border: "1px solid rgba(220,38,38,0.22)", borderRadius: "16px", padding: "16px", margin: "16px 0 6px" }}>
            <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "9px", letterSpacing: "0.16em", color: "var(--c-accent-ink)", textTransform: "uppercase", marginBottom: "8px" }}>Where it stands</div>
            {story.state_summary && (
              <p style={{ margin: 0, fontFamily: "'Playfair Display', 'Georgia', serif", fontSize: "15.5px", lineHeight: 1.46, color: "var(--c-ink2)" }}>{story.state_summary}</p>
            )}
            <div style={{ display: "flex", alignItems: "center", gap: "9px", marginTop: story.state_summary ? "12px" : 0 }}>
              <div style={{ display: "flex", alignItems: "flex-end", gap: story.kind === "wave" ? "1.5px" : "2px", height: story.kind === "wave" ? "30px" : "18px" }}>
                {story.kind === "wave" ? (
                  // Direction 1: Seismograph — a literal waveform of the story's
                  // full life (weeks), not just today. Crests and troughs are
                  // the whole point, so every bar is colored by the CURRENT
                  // overall intensity rather than spotlighting only the newest.
                  buckets.map((b, i) => (
                    <span key={i} style={{ width: "3px", borderRadius: "2px 2px 0 0", minHeight: "2px", height: `${Math.max(2, (b / maxBucket) * 30)}px`, background: WAVE_STATE_COLOR[momentum.state] || "var(--c-dim)" }} />
                  ))
                ) : (
                  buckets.map((b, i) => (
                    <span key={i} style={{ width: "4px", borderRadius: "1px", height: `${Math.max(3, (b / maxBucket) * 18)}px`, background: i === buckets.length - 1 ? "#DC2626" : "var(--c-accent-dim)" }} />
                  ))
                )}
              </div>
              <span style={{ fontSize: "11px", color: "var(--c-muted)", fontFamily: "'Manrope', sans-serif" }}>{trendLabel(momentum)}</span>
            </div>
            {story.kind === "event" && story.outlets_count > 1 && (
              <button type="button" onClick={() => setCoverageOpen(true)} data-testid="story-coverage"
                aria-label={`${mixSentence(story.outlets_count, story.coverage_mix)}. Show coverage`}
                style={{ display: "block", minHeight: 44, marginTop: 6, padding: 0, background: "none", border: "none", cursor: "pointer",
                  fontFamily: "'JetBrains Mono', monospace", fontSize: "11px", color: "var(--c-sub)", textAlign: "left" }}>
                {mixSentence(story.outlets_count, story.coverage_mix)} ›
              </button>
            )}
          </motion.div>
        )}

        {/* Timeline */}
        {articles.length > 0 ? (
          <div style={{ position: "relative", marginTop: "20px", paddingLeft: "22px" }}>
            <div style={{ position: "absolute", left: "5px", top: "4px", bottom: "10px", width: "1px", background: "rgba(220,38,38,0.25)" }} />
            {articles.map((article, idx) => (
              <React.Fragment key={article.article_id}>
              {showDivider && idx === newCount && (
                <div ref={dividerRef} data-testid="since-divider"
                  style={{ display: "flex", alignItems: "center", gap: 10, margin: "4px 0 14px -22px", fontFamily: "'JetBrains Mono', monospace", fontSize: "10px", letterSpacing: "0.1em", color: "var(--c-muted)" }}>
                  <span style={{ flex: 1, height: 1, background: "rgb(var(--c-fg-rgb) / 0.08)" }} />
                  SINCE YOU LOOKED · {clockTime(prevSeen)}
                  <span style={{ flex: 1, height: 1, background: "rgb(var(--c-fg-rgb) / 0.08)" }} />
                </div>
              )}
              <motion.div
                key={article.article_id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: Math.min(idx, 8) * 0.05 }}
                onClick={() => navigate(`/article/${article.article_id}`)}
                data-testid={`timeline-article-${article.article_id}`}
                style={{ position: "relative", marginBottom: "16px", cursor: "pointer" }}
              >
                <span style={{ position: "absolute", left: "-21px", top: "4px", width: "11px", height: "11px", borderRadius: "50%", background: idx === 0 ? "#DC2626" : "var(--c-faint2)", border: "2px solid var(--c-bg)" }} className={idx === 0 ? "animate-pulse" : ""} />
                <div style={{ background: "var(--c-surface)", border: "1px solid rgb(var(--c-fg-rgb) / 0.06)", borderRadius: "14px", padding: "13px 14px" }}>
                  {(idx === 0 || isNew(article)) && (
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", fontFamily: "'JetBrains Mono', monospace", fontSize: "9px", letterSpacing: "0.1em", color: "var(--c-accent-ink)", marginBottom: "6px" }}>
                      <span style={{ width: "5px", height: "5px", borderRadius: "50%", background: "#DC2626" }} className={idx === 0 ? "animate-pulse" : ""} />
                      {isNew(article) ? "NEW" : "LATEST"}
                    </span>
                  )}
                  <h3 style={{ fontSize: "14px", lineHeight: 1.36, color: "var(--c-ink2)", margin: 0, fontWeight: 500 }}>{article.title}</h3>
                  <div style={{ display: "flex", justifyContent: "space-between", marginTop: "8px", fontFamily: "'JetBrains Mono', monospace", fontSize: "10px", color: "var(--c-faint)" }}>
                    {/* One entry per set of facts; the outlets that repeated it are counted, not listed again. */}
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "70%" }}
                      title={(article.also_sources || []).join(", ")} data-testid="update-outlets">
                      {article.source}{article.also_count > 0 ? ` +${article.also_count} outlet${article.also_count === 1 ? "" : "s"}` : ""}
                    </span>
                    <span>{formatRelativeTime(article.published_at)}</span>
                  </div>
                </div>
              </motion.div>
              </React.Fragment>
            ))}
          </div>
        ) : (
          <div style={{ textAlign: "center", padding: "56px 0" }}>
            <Flame className="w-10 h-10" style={{ color: "var(--c-dim)", margin: "0 auto 14px" }} />
            <p style={{ color: "var(--c-muted)" }}>No updates yet</p>
            <p style={{ color: "var(--c-faint2)", fontSize: "13px", marginTop: "4px" }}>Check back as this story develops.</p>
          </div>
        )}

        <div style={{ textAlign: "center", marginTop: "24px", display: "flex", alignItems: "center", justifyContent: "center", gap: "6px", color: "var(--c-dim)", fontSize: "11px" }}>
          <Clock className="w-3 h-3" /> Refreshes every 60 seconds
        </div>
      </main>

      <FollowBar storyId={story.story_id} title={story.title} shareArticleId={articles[0]?.article_id}
        user={user} onNeedSignIn={() => setSignIn(true)} onHeight={setBarH} />
      <SignInPrompt open={signIn} onOpenChange={setSignIn} reason="follow" />
      {coverageOpen && (
        <CoverageSheet
          article={{ event_id: story.story_id, title: story.title, outlets_count: story.outlets_count, coverage_mix: story.coverage_mix }}
          onClose={() => setCoverageOpen(false)} />
      )}
    </div>
  );
};

export default DevelopingStoryDetail;

import React, { useState, useEffect, useRef, useLayoutEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Swiper, SwiperSlide } from 'swiper/react';
import 'swiper/css';
import { Haptics, ImpactStyle } from '@capacitor/haptics';
import axios from "axios";
import { toast } from "sonner";
import { Share } from '@capacitor/share';
import {
  Home, Bookmark, BookmarkCheck, Share2, MessageCircle,
  BarChart2, Sparkles, BrainCircuit,
  ThumbsUp, ThumbsDown, Send, Clock, Loader2,
  ChevronRight, MoreHorizontal
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useAuth, SuryaLogo } from "../App";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { ScrollArea } from "../components/ui/scroll-area";

const BACKEND_URL = "https://chintangithubio-production.up.railway.app";
const API = `${BACKEND_URL}/api`;

const triggerHaptic = (type = 'light') => {
  if ('vibrate' in navigator) {
    const patterns = {
      light: [10],
      medium: [20],
      heavy: [30],
      success: [10, 50, 10],
    };
    navigator.vibrate(patterns[type] || patterns.light);
  }
};

// Deeper expandable layers below the Gist. The contemplation model produces
// `beats` ([{hook, body}]); each tile leads with the hook and reveals the body.
// Falls back to any legacy {heading, content} sections. Empty until the LLM
// summariser runs — the always-visible Gist carries the article on its own.
const getBeats = (article) => {
  if (Array.isArray(article.beats) && article.beats.length > 0) {
    return article.beats
      .map(b => ({ hook: (b.hook || "").trim(), body: (b.body || "").trim() }))
      .filter(b => b.hook || b.body);
  }
  if (Array.isArray(article.sections) && article.sections.length > 0) {
    return article.sections
      .map(s => ({ hook: (s.heading || "").trim(), body: (s.content || "").trim() }))
      .filter(b => b.body);
  }
  return [];
};

const truncateWords = (text, maxWords) => {
  if (!text) return text;
  const words = text.trim().split(/\s+/);
  if (words.length <= maxWords) return text;
  return words.slice(0, maxWords).join(' ') + '…';
};

// Deep dive is a single generic long-form read (the backend "full" angle).
const DEEP_KEY = "full";

const LOADER_PHRASES = ["Contemplating…", "Reading past the headline…", "Weighing both sides…", "Finding the tension…"];

// The Chintan loading moment — the Surya mark breathing while a line of thought
// cross-fades underneath, at an unhurried pace. Shown while a deeper tier loads.
const SuryaThinking = () => {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI(x => x + 1), 3000);
    return () => clearInterval(t);
  }, []);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '74px 0', gap: '22px' }}>
      <motion.div
        animate={{ scale: [1, 1.08, 1], opacity: [0.78, 1, 0.78] }}
        transition={{ duration: 3.2, repeat: Infinity, ease: 'easeInOut' }}
      >
        <SuryaLogo className="w-12 h-12" />
      </motion.div>
      <div style={{ height: '22px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <AnimatePresence mode="wait">
          <motion.span
            key={i}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.9, ease: 'easeInOut' }}
            style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontStyle: 'italic', fontSize: '15px', color: '#9A938A' }}
          >
            {LOADER_PHRASES[i % LOADER_PHRASES.length]}
          </motion.span>
        </AnimatePresence>
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// ArticleContent — self-contained per-article slide
// ─────────────────────────────────────────────────────────────────────────────
const ArticleContent = ({ article: articleProp, navigate, isActive }) => {
  const articleId = articleProp.article_id;
  const hasFetched = useRef(false);

  // Full article data (upgraded from list summary on activation)
  const [article, setArticle] = useState(articleProp);

  // Per-article interactive state
  const [userReaction, setUserReaction] = useState({ liked: false, disliked: false });
  const [poll, setPoll] = useState(null);
  const [pollLoading, setPollLoading] = useState(false);
  const [userVoted, setUserVoted] = useState(false);
  const [comments, setComments] = useState([]);
  const [commentReactions, setCommentReactions] = useState({}); // { [commentId]: 'agree'|'disagree'|null }
  const [showComments, setShowComments] = useState(false);
  const [showActions, setShowActions] = useState(false);
  const [showPoll, setShowPoll] = useState(false);
  const [selectedOption, setSelectedOption] = useState(null);
  const [commentSubmitState, setCommentSubmitState] = useState('idle'); // 'idle'|'loading'|'success'
  const [showOtherSide, setShowOtherSide] = useState(false);
  const [otherSideAnalysis, setOtherSideAnalysis] = useState(null);
  const [loadingOtherSide, setLoadingOtherSide] = useState(false);
  const [newComment, setNewComment] = useState("");

  // Tiered reading depth: 0 Glance · 1 Understand · 2 Deep dive
  const [depth, setDepth] = useState(0);
  const [deepRead, setDeepRead] = useState(null);   // { title, paragraphs } once loaded
  const [deepLoading, setDeepLoading] = useState(false);
  const scrollRef = useRef(null);

  // Depth-rail: segments stay equal thirds (always fit), but the sliding pill is
  // measured to the active label's text width so it hugs the word, not the third.
  const railRef = useRef(null);
  const segRefs = useRef([]);
  const [pill, setPill] = useState({ left: 5, width: 0 });

  // Lazy-load all per-article data on first activation
  useEffect(() => {
    if (!isActive || hasFetched.current) return;
    hasFetched.current = true;

    // Full article data
    axios.get(`${API}/articles/${articleId}`, { withCredentials: true })
      .then(r => setArticle(r.data))
      .catch(e => console.error("Article fetch:", e));

    // Track view
    axios.post(`${API}/articles/${articleId}/interact`, { action: "view" }, { withCredentials: true })
      .catch(() => {});

    // Reaction state
    axios.get(`${API}/articles/${articleId}/reaction`, { withCredentials: true })
      .then(r => {
        setUserReaction({ liked: r.data.liked, disliked: r.data.disliked });
        setArticle(prev => prev ? {
          ...prev,
          likes: r.data.likes_count,
          dislikes: r.data.dislikes_count,
        } : prev);
      })
      .catch(() => {});

    // Poll
    setPollLoading(true);
    axios.get(`${API}/polls/${articleId}`, { withCredentials: true })
      .then(r => { if (r.data) setPoll(r.data); })
      .catch(e => {
        if (e.response?.status !== 404) console.error("Poll fetch:", e);
      })
      .finally(() => setPollLoading(false));

    // Comments
    axios.get(`${API}/comments/${articleId}`, { withCredentials: true })
      .then(r => setComments(r.data))
      .catch(e => console.error("Comments fetch:", e));

    // This user's existing agree/disagree per comment (for highlight state)
    axios.get(`${API}/comments/${articleId}/my-reactions`, { withCredentials: true })
      .then(r => setCommentReactions(r.data.reactions || {}))
      .catch(() => {});
  }, [isActive, articleId]);

  // ── Handlers ──────────────────────────────────────────────────────────────

  const handleLike = async () => {
    const wasLiked = userReaction.liked;
    const wasDisliked = userReaction.disliked;
    setUserReaction({ liked: !wasLiked, disliked: false });
    setArticle(prev => ({
      ...prev,
      likes: Math.max(0, (prev.likes || 0) + (wasLiked ? -1 : 1)),
      dislikes: wasDisliked ? Math.max(0, (prev.dislikes || 0) - 1) : (prev.dislikes || 0),
    }));
    try {
      triggerHaptic('success');
      const r = await axios.post(`${API}/articles/${articleId}/interact`, { action: "like" }, { withCredentials: true });
      setUserReaction({ liked: r.data.liked, disliked: r.data.disliked });
      setArticle(prev => ({ ...prev, likes: r.data.likes_count, dislikes: r.data.dislikes_count }));
    } catch {
      setUserReaction({ liked: wasLiked, disliked: wasDisliked });
      setArticle(prev => ({
        ...prev,
        likes: Math.max(0, (prev.likes || 0) + (wasLiked ? 1 : -1)),
        dislikes: wasDisliked ? (prev.dislikes || 0) + 1 : (prev.dislikes || 0),
      }));
      toast.error("Failed to update reaction");
    }
  };

  const handleDislike = async () => {
    const wasDisliked = userReaction.disliked;
    const wasLiked = userReaction.liked;
    setUserReaction({ liked: false, disliked: !wasDisliked });
    setArticle(prev => ({
      ...prev,
      dislikes: Math.max(0, (prev.dislikes || 0) + (wasDisliked ? -1 : 1)),
      likes: wasLiked ? Math.max(0, (prev.likes || 0) - 1) : (prev.likes || 0),
    }));
    try {
      triggerHaptic('light');
      const r = await axios.post(`${API}/articles/${articleId}/interact`, { action: "dislike" }, { withCredentials: true });
      setUserReaction({ liked: r.data.liked, disliked: r.data.disliked });
      setArticle(prev => ({ ...prev, likes: r.data.likes_count, dislikes: r.data.dislikes_count }));
    } catch {
      setUserReaction({ liked: wasLiked, disliked: wasDisliked });
      setArticle(prev => ({
        ...prev,
        dislikes: Math.max(0, (prev.dislikes || 0) + (wasDisliked ? 1 : -1)),
        likes: wasLiked ? (prev.likes || 0) + 1 : (prev.likes || 0),
      }));
      toast.error("Failed to update reaction");
    }
  };

  const handleVote = async (option) => {
    if (userVoted || !poll) return;
    setSelectedOption(option);
    if (window.Capacitor?.isNativePlatform()) {
      try { await Haptics.impact({ style: ImpactStyle.Light }); } catch {}
    } else {
      triggerHaptic('success');
    }
    try {
      const r = await axios.post(`${API}/polls/${poll.poll_id}/vote`, { option }, { withCredentials: true });
      setPoll(r.data);
      setUserVoted(true);
    } catch (error) {
      if (error.response?.data?.detail === "Already voted") setUserVoted(true);
      else setSelectedOption(null);
    }
  };

  const fetchOtherSide = async () => {
    if (otherSideAnalysis) { setShowOtherSide(true); return; }
    setLoadingOtherSide(true);
    setShowOtherSide(true);
    try {
      const r = await axios.get(`${API}/ai/other-side/${articleId}`, { withCredentials: true });
      setOtherSideAnalysis(r.data.analysis);
    } catch (e) {
      console.error("Other Side fetch:", e);
    } finally {
      setLoadingOtherSide(false);
    }
  };

  const submitComment = async () => {
    if (!newComment.trim() || commentSubmitState !== 'idle') return;
    setCommentSubmitState('loading');
    try {
      const r = await axios.post(`${API}/comments/${articleId}`, { content: newComment, stance: "neutral" }, { withCredentials: true });
      setComments([r.data, ...comments]);
      setNewComment("");
      setCommentSubmitState('success');
      if (window.Capacitor?.isNativePlatform()) {
        try { await Haptics.impact({ style: ImpactStyle.Light }); } catch {}
      } else {
        triggerHaptic('medium');
      }
      setTimeout(() => setCommentSubmitState('idle'), 1500);
    } catch {
      setCommentSubmitState('idle');
      toast.error("Failed to post comment");
    }
  };

  const handleCommentReaction = async (commentId, reaction) => {
    triggerHaptic('light');
    try {
      // Server toggles/switches and returns authoritative counts + the user's
      // resulting reaction (or null). No optimistic increment — no drift.
      const r = await axios.post(`${API}/comments/${commentId}/${reaction}`, {}, { withCredentials: true });
      setComments(prev => prev.map(c =>
        c.comment_id === commentId ? { ...c, agrees: r.data.agrees, disagrees: r.data.disagrees } : c
      ));
      setCommentReactions(prev => ({ ...prev, [commentId]: r.data.reaction }));
    } catch {
      toast.error("Couldn't update reaction");
    }
  };

  const getTotalVotes = () => {
    if (!poll?.votes) return 0;
    return Object.values(poll.votes).reduce((a, b) => a + b, 0);
  };

  const getVotePercentage = (option) => {
    const total = getTotalVotes();
    if (total === 0) return 0;
    return Math.round((poll.votes[option] || 0) / total * 100);
  };

  const formatOtherSide = (text) => {
    if (!text) return null;
    return text
      .replace(/\*\*/g, '')
      .replace(/\*/g, '')
      .replace(/#{1,3}\s/g, '')
      .replace(/^[\d\.\-\)]+\s/gm, '')
      .trim();
  };

  // ── Depth + deep-dive navigation ────────────────────────────────────────────
  const fetchDeepRead = async () => {
    if (deepRead) { if (scrollRef.current) scrollRef.current.scrollTop = 0; return; }
    setDeepLoading(true);
    try {
      const r = await axios.get(`${API}/ai/deep-dive/${articleId}/${DEEP_KEY}`, { withCredentials: true });
      setDeepRead({ title: r.data.title, paragraphs: r.data.paragraphs });
    } catch (e) {
      console.error("Deep dive fetch:", e);
      toast.error("Could not load the deep dive");
    } finally {
      setDeepLoading(false);
      if (scrollRef.current) scrollRef.current.scrollTop = 0;
    }
  };

  const goDepth = (d) => {
    if (d === depth) return;
    triggerHaptic('light');
    setDepth(d);
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
    if (d === 2 && !deepRead) fetchDeepRead();
  };

  // Size the pill to the active label's text (hug the word) + a little padding,
  // measured relative to the rail so it works regardless of segment width.
  useLayoutEffect(() => {
    if (!isActive) return;
    const PAD = 12;
    const measure = () => {
      const rail = railRef.current;
      const label = segRefs.current[depth];
      if (!rail || !label) return;
      const r = rail.getBoundingClientRect();
      const l = label.getBoundingClientRect();
      setPill({ left: l.left - r.left - PAD, width: l.width + PAD * 2 });
    };
    measure();
    const raf = requestAnimationFrame(measure);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(measure).catch(() => {});
    window.addEventListener('resize', measure);
    return () => { cancelAnimationFrame(raf); window.removeEventListener('resize', measure); };
  }, [depth, isActive]);

  const beats = getBeats(article);
  const deep = deepRead;
  const gistText = article.gist || article.summary || article.what || article.description;

  // Article-level actions live in one place: a bottom sheet opened from the rail,
  // so they don't repeat per depth mode.
  const articleActions = [
    { label: "Discuss", Icon: MessageCircle, onClick: () => { setShowActions(false); setShowComments(true); }, testid: "discuss-btn" },
    { label: "Poll", Icon: BarChart2, onClick: () => { setShowActions(false); setShowPoll(true); }, testid: "poll-btn" },
    { label: "The other side", Icon: BrainCircuit, onClick: () => { setShowActions(false); fetchOtherSide(); }, testid: "other-side-btn" },
    { label: "Ask Chintan", Icon: Sparkles, onClick: () => { setShowActions(false); navigate(`/ask-ai/${articleId}`); }, testid: "ask-ai-btn" },
  ];

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <>
      {/* Scrollable article content */}
      <main
        ref={scrollRef}
        style={{
          height: 'calc(100vh - var(--sat, 44px) - 56px)',
          overflowY: 'auto',
          overflowX: 'hidden',
          WebkitOverflowScrolling: 'touch',
          paddingBottom: '96px',
        }}
      >
        {depth === 2 && deepLoading ? (
          <SuryaThinking />
        ) : depth === 0 ? (
          /* ══════════ GLANCE — the cover: headline, gist, what's inside ══════════ */
          <motion.div
            key="glance"
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.42, ease: [0.22, 1, 0.36, 1] }}
          >
            <div style={{ width: '100%', height: '240px', overflow: 'hidden', position: 'relative' }}>
              <img src={article.image_url} alt={article.title} style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
              <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: '85%', background: 'linear-gradient(to bottom, transparent 0%, rgba(0,0,0,0.55) 45%, #0A0A0A 100%)', zIndex: 1, pointerEvents: 'none' }} />
            </div>
            <div style={{ padding: '4px 22px 0' }}>
              <div style={{ fontSize: '11px', color: '#888', display: 'flex', gap: '6px', alignItems: 'center', flexWrap: 'wrap', marginBottom: '12px' }}>
                {article.category && <span style={{ color: '#DC2626', textTransform: 'uppercase', letterSpacing: '0.14em', fontFamily: "'JetBrains Mono', monospace", fontSize: '10px' }}>{article.category}</span>}
                {article.is_breaking && <><span style={{ color: '#4A453F' }}>•</span><span style={{ color: '#f87171' }}>Breaking</span></>}
                {article.is_developing && !article.is_breaking && <><span style={{ color: '#4A453F' }}>•</span><span style={{ color: '#f59e0b' }}>Developing</span></>}
                {(article.source || article.domain || article.publisher) && <><span style={{ color: '#4A453F' }}>•</span><span style={{ color: '#82828A' }}>{article.source || article.domain || article.publisher}</span></>}
              </div>
              <h1 style={{ fontSize: 'clamp(1.5rem, 5.5vw, 1.95rem)', fontWeight: 600, lineHeight: 1.18, color: '#F2EEE9', margin: '0 0 16px', fontFamily: "'Playfair Display', 'Georgia', serif" }}>
                {article.title}
              </h1>
              {gistText && (
                <p style={{ margin: 0, color: '#B6AFA6', fontFamily: "'Playfair Display', 'Georgia', serif", fontStyle: 'italic', fontSize: '17px', lineHeight: 1.5 }}>
                  {gistText}
                </p>
              )}
              {beats.length > 0 && (
                <div style={{ marginTop: '26px', paddingTop: '18px', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                  <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '9.5px', letterSpacing: '0.18em', color: '#5A544D', textTransform: 'uppercase', marginBottom: '8px' }}>Inside this story</div>
                  {beats.map((b, idx) => (
                    <button key={idx} onClick={() => goDepth(1)} style={{ display: 'flex', alignItems: 'center', gap: '11px', padding: '9px 0', width: '100%', textAlign: 'left', background: 'none', border: 'none', cursor: 'pointer' }} data-testid={`glance-thread-${idx}`}>
                      <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '11px', color: '#DC2626', opacity: 0.75 }}>{String(idx + 1).padStart(2, '0')}</span>
                      <span style={{ color: '#9A938A', fontSize: '14px', fontFamily: "'Manrope', sans-serif", flex: 1, lineHeight: 1.35 }}>{b.hook || truncateWords(b.body, 10)}</span>
                      <ChevronRight className="w-4 h-4" style={{ flexShrink: 0, color: '#4A453F' }} />
                    </button>
                  ))}
                </div>
              )}
              <div style={{ height: '20px' }} />
            </div>
          </motion.div>
        ) : depth === 1 ? (
          /* ══════════ UNDERSTAND — the beats ══════════ */
          <motion.div
            key="understand"
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.42, ease: [0.22, 1, 0.36, 1] }}
            style={{ padding: '20px 22px 0' }}
          >
            <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '10px', letterSpacing: '0.16em', color: '#DC2626', textTransform: 'uppercase', marginBottom: '12px' }}>
              {article.category || 'Story'}
            </div>
            <h1 style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontWeight: 600, fontSize: '22px', lineHeight: 1.24, color: '#F2EEE9', margin: '0 0 20px' }}>
              {article.title}
            </h1>
            {beats.length > 0 ? beats.map((beat, idx) => (
              <motion.div key={idx} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.05 + idx * 0.07, ease: [0.22, 1, 0.36, 1] }}
                style={{ background: '#141311', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '14px', padding: '15px 16px', marginBottom: '11px' }} data-testid={`beat-${idx}`}>
                <p style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontWeight: 500, fontSize: '16.5px', lineHeight: 1.3, color: '#EFEAE4', margin: beat.body ? '0 0 7px' : 0 }}>
                  {beat.hook || beat.body}
                </p>
                {beat.hook && beat.body && (
                  <p style={{ fontSize: '13.5px', lineHeight: 1.62, color: '#948E86', margin: 0, fontFamily: "'Manrope', sans-serif" }}>{beat.body}</p>
                )}
              </motion.div>
            )) : gistText ? (
              <p style={{ color: '#B6AFA6', fontFamily: "'Manrope', sans-serif", fontSize: '15px', lineHeight: 1.65 }}>{gistText}</p>
            ) : null}
            <div style={{ height: '8px' }} />
          </motion.div>
        ) : (
          /* ══════════ DEEP DIVE — one long-form read ══════════ */
          <motion.div
            key="deep"
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.42, ease: [0.22, 1, 0.36, 1] }}
            style={{ padding: '20px 22px 0' }}
          >
            <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '10px', letterSpacing: '0.16em', color: '#6E6862', textTransform: 'uppercase', marginBottom: '14px' }}>
              Deep dive · {article.category || 'Story'}
            </div>
            {deep ? (
              <>
                <h2 style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontWeight: 600, fontSize: '23px', lineHeight: 1.26, color: '#F2EEE9', margin: '0 0 16px' }}>
                  {deep.title || 'The full story'}
                </h2>
                {deep.paragraphs.map((p, idx) => (
                  <p key={idx} style={{ fontSize: '15px', lineHeight: 1.75, color: '#B9B2A9', margin: '0 0 16px', fontFamily: "'Manrope', sans-serif" }}>
                    {idx === 0 && (
                      <span style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontWeight: 600, float: 'left', fontSize: '42px', lineHeight: 0.82, color: '#DC2626', padding: '4px 9px 0 0' }}>{p.charAt(0)}</span>
                    )}
                    {idx === 0 ? p.slice(1) : p}
                  </p>
                ))}
                <div style={{ height: '8px' }} />
              </>
            ) : (
              <p style={{ color: '#8A847C', textAlign: 'center', padding: '48px 0', fontSize: '14px' }}>
                Couldn’t load the deep dive. Tap Deep dive again to retry.
              </p>
            )}
          </motion.div>
        )}
      </main>

      {/* Depth rail + single actions trigger — the only bottom control (active slide) */}
      {isActive && (
        <div style={{ position: 'fixed', left: 0, right: 0, bottom: 0, zIndex: 50, padding: '8px 16px 10px', background: 'rgba(0,0,0,0.72)', backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' }}>
          <div style={{ maxWidth: '640px', margin: '0 auto', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div ref={railRef} style={{ position: 'relative', flex: 1, minWidth: 0, background: '#121110', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '16px', display: 'flex', padding: '5px' }}>
              <div style={{
                position: 'absolute', top: '5px', bottom: '5px', left: `${pill.left}px`, width: `${pill.width}px`,
                background: 'linear-gradient(180deg, #DC2626, #B91C1C)', borderRadius: '12px',
                transition: 'left .45s cubic-bezier(.34,1.4,.5,1), width .45s cubic-bezier(.34,1.4,.5,1)',
                boxShadow: '0 4px 16px rgba(220,38,38,0.28)', opacity: pill.width ? 1 : 0,
              }} />
              {['Glance', 'Understand', 'Deep dive'].map((lbl, i) => (
                <button
                  key={i}
                  onClick={() => goDepth(i)}
                  data-testid={`depth-${i}`}
                  style={{
                    flex: 1, minWidth: 0, display: 'flex', justifyContent: 'center', alignItems: 'center',
                    padding: '11px 2px', fontSize: '12px', fontWeight: 600,
                    color: depth === i ? '#120A06' : '#7C766E', position: 'relative', zIndex: 2,
                    background: 'none', border: 'none', cursor: 'pointer', transition: 'color .35s ease',
                  }}
                >
                  <span ref={el => { segRefs.current[i] = el; }} style={{ whiteSpace: 'nowrap' }}>{lbl}</span>
                </button>
              ))}
            </div>
            <button
              onClick={() => { triggerHaptic('light'); setShowActions(true); }}
              aria-label="More actions"
              data-testid="more-actions-btn"
              style={{ width: '48px', height: '48px', flexShrink: 0, borderRadius: '14px', background: '#121110', border: '1px solid rgba(255,255,255,0.07)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: '#9A938A' }}
            >
              <MoreHorizontal className="w-5 h-5" />
            </button>
          </div>
        </div>
      )}

      {/* Actions sheet — one home for Discuss / Poll / Other Side / Ask AI + reactions */}
      {isActive && showActions && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 60 }}>
          <div onClick={() => setShowActions(false)} style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.6)' }} />
          <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, background: '#141311', borderTopLeftRadius: '20px', borderTopRightRadius: '20px', border: '1px solid rgba(255,255,255,0.08)', padding: '10px 16px calc(18px + var(--sab, 16px))' }}>
            <div style={{ width: '38px', height: '4px', borderRadius: '2px', background: 'rgba(255,255,255,0.15)', margin: '6px auto 16px' }} />
            <div style={{ display: 'flex', gap: '10px', marginBottom: '14px' }}>
              <button onClick={handleLike} data-testid="like-btn"
                style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', padding: '12px', borderRadius: '12px', cursor: 'pointer',
                  border: '1px solid ' + (userReaction.liked ? 'rgba(34,197,94,0.5)' : 'rgba(255,255,255,0.08)'),
                  background: userReaction.liked ? 'rgba(34,197,94,0.12)' : '#181715',
                  color: userReaction.liked ? '#4ADE80' : '#9A938A' }}>
                <ThumbsUp className="w-4 h-4" /><span style={{ fontSize: '14px' }}>{article.likes || 0}</span>
              </button>
              <button onClick={handleDislike} data-testid="dislike-btn"
                style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', padding: '12px', borderRadius: '12px', cursor: 'pointer',
                  border: '1px solid ' + (userReaction.disliked ? 'rgba(220,38,38,0.5)' : 'rgba(255,255,255,0.08)'),
                  background: userReaction.disliked ? 'rgba(220,38,38,0.12)' : '#181715',
                  color: userReaction.disliked ? '#FCA5A5' : '#9A938A' }}>
                <ThumbsDown className="w-4 h-4" /><span style={{ fontSize: '14px' }}>{article.dislikes || 0}</span>
              </button>
            </div>
            {articleActions.map(({ label, Icon, onClick, testid }) => (
              <button key={label} onClick={onClick} data-testid={testid}
                style={{ display: 'flex', alignItems: 'center', gap: '13px', width: '100%', padding: '15px 6px', background: 'none', border: 'none', borderTop: '1px solid rgba(255,255,255,0.05)', cursor: 'pointer', color: '#DEDEE4', fontFamily: "'Manrope', sans-serif", fontSize: '15px' }}>
                <Icon className="w-5 h-5" style={{ color: '#9A938A', flexShrink: 0 }} />
                <span style={{ flex: 1, textAlign: 'left' }}>{label}</span>
                <ChevronRight className="w-4 h-4" style={{ color: '#4A453F' }} />
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Comments Dialog */}
      <Dialog open={showComments} onOpenChange={setShowComments}>
        <DialogContent className="bg-[#0A0A0A] border-white/10 max-w-lg max-h-[80vh]">
          <DialogHeader>
            <DialogTitle className="text-white">Discussion</DialogTitle>
          </DialogHeader>
          <div className="flex gap-2 mb-4">
            <input
              type="text"
              value={newComment}
              onChange={(e) => setNewComment(e.target.value)}
              placeholder="Share your thoughts..."
              className="flex-1 bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:border-red-500"
              data-testid="comment-input"
            />
            <button
              onClick={submitComment}
              disabled={commentSubmitState !== 'idle'}
              className="p-2 bg-red-600 rounded-lg hover:bg-red-700 transition-colors disabled:opacity-60"
              data-testid="submit-comment-btn"
            >
              {commentSubmitState === 'loading' ? (
                <Loader2 className="w-5 h-5 text-white animate-spin" />
              ) : commentSubmitState === 'success' ? (
                <span className="text-white text-lg leading-none">✓</span>
              ) : (
                <Send className="w-5 h-5 text-white" />
              )}
            </button>
          </div>
          <ScrollArea className="h-[400px]">
            <div className="space-y-4">
              {comments.map(comment => (
                <div key={comment.comment_id} className="p-4 rounded-lg bg-white/5">
                  <div className="flex items-center gap-3 mb-2">
                    <div className="w-8 h-8 rounded-full bg-white/10 overflow-hidden">
                      {comment.user_picture ? (
                        <img src={comment.user_picture} alt="" className="w-full h-full object-cover" />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-gray-500 text-sm">
                          {comment.user_name?.charAt(0)}
                        </div>
                      )}
                    </div>
                    <p className="text-white text-sm font-medium">{comment.user_name}</p>
                  </div>
                  <p className="text-gray-400 text-sm mb-3">{comment.content}</p>
                  <div className="flex items-center gap-3 pt-2 border-t border-white/5">
                    {(() => {
                      const myReaction = commentReactions[comment.comment_id];
                      return (
                        <>
                          <button
                            onClick={() => handleCommentReaction(comment.comment_id, 'agree')}
                            className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs transition-colors ${
                              myReaction === 'agree' ? "bg-green-500/20 text-green-400" : "bg-white/5 text-gray-400 hover:text-green-400"
                            }`}
                          >
                            <ThumbsUp className="w-3 h-3" />
                            Agree {comment.agrees > 0 && <span className="opacity-70">({comment.agrees})</span>}
                          </button>
                          <button
                            onClick={() => handleCommentReaction(comment.comment_id, 'disagree')}
                            className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs transition-colors ${
                              myReaction === 'disagree' ? "bg-red-500/20 text-red-400" : "bg-white/5 text-gray-400 hover:text-red-400"
                            }`}
                          >
                            <ThumbsDown className="w-3 h-3" />
                            Disagree {comment.disagrees > 0 && <span className="opacity-70">({comment.disagrees})</span>}
                          </button>
                        </>
                      );
                    })()}
                  </div>
                </div>
              ))}
              {comments.length === 0 && (
                <p className="text-gray-500 text-center py-8">Be the first to comment!</p>
              )}
            </div>
          </ScrollArea>
        </DialogContent>
      </Dialog>

      {/* Poll Dialog */}
      <Dialog open={showPoll} onOpenChange={setShowPoll}>
        <DialogContent className="bg-[#0A0A0A] border-white/10 max-w-lg" style={{ minWidth: '300px', minHeight: '200px', padding: '24px' }}>
          <DialogHeader>
            <DialogTitle className="text-white">Poll</DialogTitle>
          </DialogHeader>
          {pollLoading ? (
            <div className="flex flex-col items-center justify-center py-10 gap-3">
              <Loader2 className="w-8 h-8 text-red-500 animate-spin" />
              <p className="text-gray-400 text-sm">Generating poll…</p>
            </div>
          ) : poll ? (
            <div className="space-y-4">
              <p className="text-white font-medium">{poll.question}</p>
              <div className="space-y-2">
                {poll.options.map(option => {
                  const percentage = getVotePercentage(option);
                  return (
                    <button
                      key={option}
                      onClick={() => handleVote(option)}
                      disabled={userVoted}
                      className={`poll-option w-full text-left ${userVoted ? "cursor-default" : "hover:border-red-500"} ${selectedOption === option ? 'poll-option-pop' : ''}`}
                      style={selectedOption === option ? { borderColor: '#DC2626', background: 'rgba(220,38,38,0.15)' } : {}}
                      data-testid={`poll-option-${option}`}
                    >
                      {userVoted && <div className="poll-bar" style={{ width: `${percentage}%` }} />}
                      <div className="relative flex items-center justify-between">
                        <span className="text-gray-300">{option}</span>
                        {userVoted && <span className="text-gray-500 font-mono text-sm">{percentage}%</span>}
                      </div>
                    </button>
                  );
                })}
              </div>
              {!userVoted && <p className="text-gray-500 text-xs text-center">Tap an option to vote</p>}
              <p className="text-gray-500 text-sm text-center">{getTotalVotes()} votes</p>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-10 gap-3">
              <Clock className="w-8 h-8 text-gray-500" />
              <p className="text-gray-400 text-center">Poll coming soon for this article</p>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Other Side Dialog */}
      <Dialog open={showOtherSide} onOpenChange={setShowOtherSide}>
        <DialogContent className="bg-[#0A0A0A] border-white/10 max-w-2xl max-h-[80vh]">
          <DialogHeader>
            <DialogTitle className="text-white flex items-center gap-2">
              <BrainCircuit className="w-5 h-5 text-red-500" />
              The Other Side
            </DialogTitle>
          </DialogHeader>
          <ScrollArea className="h-[500px]">
            {loadingOtherSide ? (
              <div className="flex items-center justify-center py-12">
                <SuryaLogo className="w-12 h-12 animate-spin-slow" />
              </div>
            ) : otherSideAnalysis ? (
              <div className="py-4 space-y-3">
                {(() => {
                  try {
                    const parsed = JSON.parse(otherSideAnalysis);
                    return (parsed.points || []).slice(0, 3).map((point, idx) => (
                      <div key={idx} style={{ background: '#1a1a1a', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '12px', padding: '16px 18px', display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
                        <span style={{ color: '#DC2626', fontSize: '8px', marginTop: '5px', flexShrink: 0 }}>●</span>
                        <p style={{ color: '#d1d5db', fontSize: '13px', lineHeight: '1.6', margin: 0 }}>{truncateWords(point, 20)}</p>
                      </div>
                    ));
                  } catch {
                    return formatOtherSide(otherSideAnalysis).split('\n\n').filter(Boolean).slice(0, 3).map((para, idx) => (
                      <div key={idx} style={{ background: '#1a1a1a', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '12px', padding: '16px 18px', display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
                        <span style={{ color: '#DC2626', fontSize: '8px', marginTop: '5px', flexShrink: 0 }}>●</span>
                        <p style={{ color: '#d1d5db', fontSize: '13px', lineHeight: '1.6', margin: 0 }}>{truncateWords(para, 20)}</p>
                      </div>
                    ));
                  }
                })()}
                <p className="text-gray-600 text-xs text-center italic pt-2">
                  Consider multiple perspectives before forming your opinion
                </p>
              </div>
            ) : (
              <p className="text-gray-500 text-center py-8">Could not load alternative perspectives. Please try again.</p>
            )}
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// ArticlePage — Swiper shell + sticky header
// ─────────────────────────────────────────────────────────────────────────────
const ArticlePage = () => {
  const { articleId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [allArticles, setAllArticles] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [isBookmarked, setIsBookmarked] = useState(false);

  // Load article list and find initial index
  useEffect(() => {
    const load = async () => {
      try {
        const stored = sessionStorage.getItem('articleList');
        let list;
        if (stored) {
          list = JSON.parse(stored);
        } else {
          const r = await axios.get(`${API}/articles`, { withCredentials: true });
          list = r.data;
          sessionStorage.setItem('articleList', JSON.stringify(list));
        }
        setAllArticles(list);
        const idx = list.findIndex(a => a.article_id === articleId);
        if (idx !== -1) setCurrentIndex(idx);
      } catch (e) {
        console.error("Error loading articles:", e);
        toast.error("Could not load articles");
        navigate('/feed');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [articleId, navigate]);

  // Fetch bookmark state for current article
  useEffect(() => {
    const id = allArticles[currentIndex]?.article_id;
    if (!id) return;
    axios.get(`${API}/bookmarks/check/${id}`, { withCredentials: true })
      .then(r => setIsBookmarked(r.data.bookmarked))
      .catch(() => {});
  }, [currentIndex, allArticles]);

  const toggleBookmark = async () => {
    const id = allArticles[currentIndex]?.article_id;
    if (!id) return;
    try {
      if (isBookmarked) {
        await axios.delete(`${API}/bookmarks/${id}`, { withCredentials: true });
      } else {
        await axios.post(`${API}/bookmarks/${id}`, {}, { withCredentials: true });
      }
      setIsBookmarked(!isBookmarked);
      if (window.Capacitor?.isNativePlatform()) {
        try { await Haptics.impact({ style: ImpactStyle.Light }); } catch {}
      } else {
        triggerHaptic('medium');
      }
    } catch {
      console.error("Failed to update bookmark");
    }
  };

  const shareArticle = async () => {
    const art = allArticles[currentIndex];
    try {
      await Share.share({
        title: art?.title,
        text: 'Check this News article on Chintan!',
        url: `https://chintan-updated.vercel.app/article/${art?.article_id}`,
        dialogTitle: 'Share via',
      });
    } catch {
      // user dismissed or share not available — no feedback needed
    }
  };

  const handlePageChange = async (newIndex) => {
    if (newIndex === currentIndex) return;
    setCurrentIndex(newIndex);
    if (window.Capacitor?.isNativePlatform()) {
      try { await Haptics.impact({ style: ImpactStyle.Light }); } catch {}
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center">
        <SuryaLogo className="w-16 h-16 animate-spin-slow" />
      </div>
    );
  }

  if (!allArticles.length) return null;

  return (
    <div data-testid="article-page" style={{ background: '#0A0A0A' }}>
      {/* Sticky header — outside Swiper */}
      <header
        style={{
          position: 'sticky',
          top: 0,
          paddingTop: 'var(--sat, 44px)',
          paddingBottom: '12px',
          paddingLeft: '16px',
          paddingRight: '16px',
          zIndex: 40,
          background: 'rgba(0,0,0,0.6)',
          backdropFilter: 'blur(12px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <button
          onClick={() => navigate('/feed')}
          className="p-2 hover:bg-white/5 rounded-lg transition-colors"
          data-testid="back-btn"
        >
          <Home className="w-5 h-5 text-gray-400" />
        </button>

        <span className="text-gray-500 text-xs font-mono">
          {currentIndex + 1} / {allArticles.length}
        </span>

        <div className="flex items-center gap-2">
          <button
            onClick={toggleBookmark}
            className="p-2 hover:bg-white/5 rounded-lg transition-colors"
            data-testid="bookmark-btn"
          >
            {isBookmarked
              ? <BookmarkCheck className="w-5 h-5 text-red-500" />
              : <Bookmark className="w-5 h-5 text-gray-400" />}
          </button>
          <button
            onClick={shareArticle}
            className="p-2 hover:bg-white/5 rounded-lg transition-colors"
            data-testid="share-btn"
          >
            <Share2 className="w-5 h-5 text-gray-400" />
          </button>
        </div>
      </header>

      {/* Horizontal pager */}
      <Swiper
        direction="horizontal"
        slidesPerView={1}
        initialSlide={currentIndex}
        threshold={10}
        touchStartPreventDefault={false}
        nested={true}
        onSlideChange={(swiper) => handlePageChange(swiper.activeIndex)}
        style={{ height: 'calc(100vh - var(--sat, 44px) - 56px)' }}
      >
        {allArticles.map((art, idx) => (
          <SwiperSlide key={art.article_id}>
            <ArticleContent
              article={art}
              navigate={navigate}
              isActive={idx === currentIndex}
            />
          </SwiperSlide>
        ))}
      </Swiper>
    </div>
  );
};

export default ArticlePage;

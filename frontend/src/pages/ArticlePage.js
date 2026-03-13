import React, { useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Swiper, SwiperSlide } from 'swiper/react';
import 'swiper/css';
import { Haptics, ImpactStyle } from '@capacitor/haptics';
import axios from "axios";
import { toast } from "sonner";
import {
  ArrowLeft, Bookmark, BookmarkCheck, Share2, MessageCircle,
  BarChart2, Sparkles, BrainCircuit, ChevronDown, ChevronUp,
  ThumbsUp, ThumbsDown, Send, Clock, Loader2
} from "lucide-react";
import { useAuth, SuryaLogo } from "../App";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger
} from "../components/ui/collapsible";
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

const getSectionLabel = (key, category) => {
  const labels = {
    what: {
      default: "The Story",
      Science: "Discovery",
      Politics: "Decision",
      Sports: "Match Update",
      Business: "Development",
      Technology: "Innovation",
      Entertainment: "Premiere"
    },
    why: {
      default: "Significance",
      Science: "Implications",
      Politics: "Stakes",
      Sports: "Impact",
      Business: "Market Effect",
      Technology: "Disruption",
      Entertainment: "Cultural Shift"
    },
    context: {
      default: "Background",
      Science: "Research Trail",
      Politics: "Political Landscape",
      Sports: "Season Context",
      Business: "Industry View",
      Technology: "Tech Evolution",
      Entertainment: "Industry Backdrop"
    },
    impact: {
      default: "What's Next",
      Science: "Future Path",
      Politics: "Consequences",
      Sports: "Season Outlook",
      Business: "Market Forecast",
      Technology: "Adoption Curve",
      Entertainment: "Box Office Forecast"
    }
  };
  return labels[key]?.[category] || labels[key]?.default || key;
};

const truncateWords = (text, maxWords) => {
  if (!text) return text;
  const words = text.trim().split(/\s+/);
  if (words.length <= maxWords) return text;
  return words.slice(0, maxWords).join(' ') + '…';
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
  const [showComments, setShowComments] = useState(false);
  const [showPoll, setShowPoll] = useState(false);
  const [selectedOption, setSelectedOption] = useState(null);
  const [commentSubmitState, setCommentSubmitState] = useState('idle'); // 'idle'|'loading'|'success'
  const [showOtherSide, setShowOtherSide] = useState(false);
  const [otherSideAnalysis, setOtherSideAnalysis] = useState(null);
  const [loadingOtherSide, setLoadingOtherSide] = useState(false);
  const [aiQuestions, setAiQuestions] = useState([]);
  const [newComment, setNewComment] = useState("");
  const [expandedSections, setExpandedSections] = useState({
    what: false, why: false, context: false, impact: false,
  });
  const [showThinkDeeper, setShowThinkDeeper] = useState(false);

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

    // AI questions
    axios.get(`${API}/ai/questions/${articleId}`, { withCredentials: true })
      .then(r => setAiQuestions((r.data.questions || []).slice(0, 2)))
      .catch(e => console.error("AI questions fetch:", e));
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
    try {
      triggerHaptic('light');
      await axios.post(`${API}/comments/${commentId}/${reaction}`, {}, { withCredentials: true });
      setComments(prev => prev.map(c => {
        if (c.comment_id === commentId) {
          const key = reaction === 'agree' ? 'agrees' : 'disagrees';
          return { ...c, [key]: (c[key] || 0) + 1 };
        }
        return c;
      }));
    } catch (error) {
      if (error.response?.status === 400) toast.info("Already reacted");
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

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <>
      {/* Scrollable article content */}
      <main
        style={{
          height: 'calc(100vh - var(--sat, 44px) - 56px)',
          overflowY: 'auto',
          overflowX: 'hidden',
          WebkitOverflowScrolling: 'touch',
          paddingBottom: '80px',
        }}
      >
        {/* Hero image */}
        <div style={{ width: '100%', height: '260px', overflow: 'hidden', position: 'relative', margin: 0, padding: 0 }}>
          <img
            src={article.image_url}
            alt={article.title}
            style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
          />
          <div style={{
            position: 'absolute', bottom: 0, left: 0, right: 0,
            height: '80%',
            background: 'linear-gradient(to bottom, transparent 0%, rgba(0,0,0,0.5) 40%, #000000 100%)',
            zIndex: 1, pointerEvents: 'none',
          }} />
        </div>

        {/* Breadcrumb */}
        <div style={{
          padding: '10px 16px', fontSize: '11px', color: '#888888',
          display: 'flex', gap: '6px', alignItems: 'center', flexWrap: 'wrap',
        }}>
          {article.category && (
            <span style={{ color: '#ef4444', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              {article.category}
            </span>
          )}
          {article.is_breaking && <><span>•</span><span style={{ color: '#f87171' }}>Breaking</span></>}
          {article.is_developing && !article.is_breaking && <><span>•</span><span style={{ color: '#f59e0b' }}>Developing</span></>}
          {(article.source || article.domain || article.publisher) && (
            <><span>•</span><span>{article.source || article.domain || article.publisher}</span></>
          )}
          {article.published_at && (
            <><span>•</span><span>{new Date(article.published_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}</span></>
          )}
        </div>

        {/* Headline */}
        <h1 style={{
          padding: '4px 16px 16px',
          fontSize: 'clamp(1.3rem, 4vw, 1.75rem)',
          fontWeight: '700',
          lineHeight: '1.35',
          color: '#ffffff',
          margin: 0,
          fontFamily: "'Playfair Display', 'Georgia', serif",
        }}>
          {article.title}
        </h1>

        <div className="px-4 max-w-3xl mx-auto">
          {/* Accordions */}
          <div style={{ marginBottom: '32px' }}>
            {[
              { key: 'what', content: article.what },
              { key: 'why', content: article.why },
              { key: 'context', content: article.context },
              { key: 'impact', content: article.impact },
            ].filter(s => s.content).map(section => (
              <Collapsible
                key={section.key}
                open={expandedSections[section.key]}
                onOpenChange={(open) => setExpandedSections(prev => ({ ...prev, [section.key]: open }))}
              >
                <div style={{
                  background: 'rgba(255,255,255,0.05)',
                  borderRadius: '12px',
                  marginBottom: '8px',
                  marginLeft: '8px',
                  marginRight: '8px',
                  border: '1px solid rgba(255,255,255,0.08)',
                  overflow: 'hidden',
                }}>
                  <CollapsibleTrigger asChild>
                    <button
                      data-testid={`section-${section.key}`}
                      style={{
                        width: '100%', display: 'flex', alignItems: 'center',
                        justifyContent: 'space-between', padding: '14px 16px',
                        background: 'none', cursor: 'pointer', textAlign: 'left',
                      }}
                    >
                      <span style={{ color: '#ef4444', fontFamily: 'monospace', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                        {getSectionLabel(section.key, article.category)}
                      </span>
                      {expandedSections[section.key]
                        ? <ChevronUp className="w-5 h-5 text-gray-500" />
                        : <ChevronDown className="w-5 h-5 text-gray-500" />}
                    </button>
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <div style={{ padding: '0 12px 16px', color: '#9ca3af', lineHeight: '1.65', fontSize: '14px', textAlign: 'left' }}>
                      {truncateWords(section.content, 55)}
                    </div>
                  </CollapsibleContent>
                </div>
              </Collapsible>
            ))}
          </div>

          {/* Think Deeper */}
          {aiQuestions.length > 0 && (
            <div className="glass-card rounded-xl p-6 mb-8">
              <button
                className="flex items-center justify-between w-full gap-2"
                onClick={() => setShowThinkDeeper(prev => !prev)}
              >
                <span className="text-red-500 font-mono text-xs uppercase tracking-wider">Think Deeper</span>
                <span className="text-gray-500 text-xs">{showThinkDeeper ? '▲' : '▼'}</span>
              </button>
              {showThinkDeeper && (
                <div className="space-y-3 mt-4">
                  {aiQuestions.slice(0, 2).map((question, idx) => (
                    <button
                      key={idx}
                      onClick={() => navigate(`/ask-ai/${articleId}?q=${encodeURIComponent(question)}`)}
                      className="w-full text-left p-3 rounded-lg bg-white/5 hover:bg-white/10 transition-colors text-gray-400 text-sm"
                      data-testid={`ai-question-${idx}`}
                    >
                      {truncateWords(question, 15)}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Feedback */}
          <div className="flex items-center justify-center gap-6 py-6 border-t border-white/10">
            <button
              onClick={handleLike}
              className={`flex items-center gap-2 px-4 py-2 rounded-full transition-colors ${
                userReaction.liked ? "bg-green-500/20 text-green-400" : "bg-white/5 hover:bg-green-500/20 text-gray-400 hover:text-green-400"
              }`}
              data-testid="like-btn"
            >
              <ThumbsUp className="w-4 h-4" />
              <span className="text-sm">{article.likes || 0}</span>
            </button>
            <button
              onClick={handleDislike}
              className={`flex items-center gap-2 px-4 py-2 rounded-full transition-colors ${
                userReaction.disliked ? "bg-red-500/20 text-red-400" : "bg-white/5 hover:bg-red-500/20 text-gray-400 hover:text-red-400"
              }`}
              data-testid="dislike-btn"
            >
              <ThumbsDown className="w-4 h-4" />
              <span className="text-sm">{article.dislikes || 0}</span>
            </button>
          </div>
        </div>
      </main>

      {/* Action bar — only rendered for the active slide to avoid stacking */}
      {isActive && (
        <div className="fixed bottom-0 left-0 right-0 glass-nav py-3 px-4 z-50">
          <div className="max-w-3xl mx-auto flex items-center justify-around">
            <button
              onClick={() => setShowComments(true)}
              className="flex flex-col items-center gap-1 text-gray-400 hover:text-white transition-colors"
              data-testid="discuss-btn"
            >
              <MessageCircle className="w-5 h-5" />
              <span className="text-xs">Discuss</span>
            </button>
            <button
              onClick={() => setShowPoll(true)}
              className="flex flex-col items-center gap-1 text-gray-400 hover:text-white transition-colors"
              data-testid="poll-btn"
            >
              <BarChart2 className="w-5 h-5" />
              <span className="text-xs">Poll</span>
            </button>
            <button
              onClick={fetchOtherSide}
              className="flex flex-col items-center gap-1 text-gray-400 hover:text-white transition-colors"
              data-testid="other-side-btn"
            >
              <BrainCircuit className="w-5 h-5" />
              <span className="text-xs">Other Side</span>
            </button>
            <button
              onClick={() => navigate(`/ask-ai/${articleId}`)}
              className="flex flex-col items-center gap-1 text-red-500"
              data-testid="ask-ai-btn"
            >
              <Sparkles className="w-5 h-5" />
              <span className="text-xs">Ask AI</span>
            </button>
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
                    <button
                      onClick={() => handleCommentReaction(comment.comment_id, 'agree')}
                      className="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs bg-white/5 hover:bg-green-500/20 text-gray-400 hover:text-green-400 transition-colors"
                    >
                      <ThumbsUp className="w-3 h-3" />
                      Agree {comment.agrees > 0 && <span className="text-gray-500">({comment.agrees})</span>}
                    </button>
                    <button
                      onClick={() => handleCommentReaction(comment.comment_id, 'disagree')}
                      className="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs bg-white/5 hover:bg-red-500/20 text-gray-400 hover:text-red-400 transition-colors"
                    >
                      <ThumbsDown className="w-3 h-3" />
                      Disagree {comment.disagrees > 0 && <span className="text-gray-500">({comment.disagrees})</span>}
                    </button>
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
      triggerHaptic('medium');
      if (isBookmarked) {
        await axios.delete(`${API}/bookmarks/${id}`, { withCredentials: true });
        toast.success("Removed from bookmarks");
      } else {
        await axios.post(`${API}/bookmarks/${id}`, {}, { withCredentials: true });
        toast.success("Added to bookmarks");
      }
      setIsBookmarked(!isBookmarked);
    } catch {
      toast.error("Failed to update bookmark");
    }
  };

  const shareArticle = async () => {
    const art = allArticles[currentIndex];
    const shareUrl = `${window.location.origin}/article/${art?.article_id}`;
    try {
      if (navigator.share) {
        await navigator.share({ title: art?.title, url: shareUrl });
      } else {
        await navigator.clipboard.writeText(shareUrl);
        toast.success("Link copied to clipboard!");
      }
    } catch {
      await navigator.clipboard.writeText(shareUrl);
      toast.success("Link copied to clipboard!");
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
          <ArrowLeft className="w-5 h-5 text-gray-400" />
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

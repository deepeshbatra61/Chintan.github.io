import React, { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import axios from "axios";
import { toast } from "sonner";
import { 
  ArrowLeft, Bookmark, BookmarkCheck, Share2, MessageCircle, 
  BarChart2, Sparkles, BrainCircuit, ChevronDown, ChevronUp,
  ThumbsUp, ThumbsDown, Send, ChevronLeft, ChevronRight
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

// Haptic feedback utility
const triggerHaptic = (type = 'light') => {
  if ('vibrate' in navigator) {
    const patterns = {
      light: [10],
      medium: [20],
      heavy: [30],
      success: [10, 50, 10],
      swipe: [15, 30, 15]
    };
    navigator.vibrate(patterns[type] || patterns.light);
  }
};

// Custom section labels based on content type
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

const ArticlePage = () => {
  const { articleId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  
  const [article, setArticle] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isBookmarked, setIsBookmarked] = useState(false);
  const [userReaction, setUserReaction] = useState({ liked: false, disliked: false });
  const [poll, setPoll] = useState(null);
  const [userVoted, setUserVoted] = useState(false);
  const [comments, setComments] = useState([]);
  const [showComments, setShowComments] = useState(false);
  const [showPoll, setShowPoll] = useState(false);
  const [showOtherSide, setShowOtherSide] = useState(false);
  const [otherSideAnalysis, setOtherSideAnalysis] = useState(null);
  const [loadingOtherSide, setLoadingOtherSide] = useState(false);
  const [aiQuestions, setAiQuestions] = useState([]);
  const [newComment, setNewComment] = useState("");
  const [expandedSections, setExpandedSections] = useState({
    why: false,
    context: false,
    impact: false
  });

  // Parallax state
  const [scrollY, setScrollY] = useState(0);
  const onScroll = (e) => setScrollY(e.target.scrollTop);

  // Swipe navigation state - HORIZONTAL
  const [allArticles, setAllArticles] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const touchStartX = useRef(0);
  const touchEndX = useRef(0);
  const touchStartTime = useRef(0);
  const isModalOpen = showComments || showPoll || showOtherSide;
  const [showThinkDeeper, setShowThinkDeeper] = useState(false);

  const fetchArticle = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/articles/${articleId}`, { withCredentials: true });
      setArticle(response.data);
      
      // Track view
      await axios.post(`${API}/articles/${articleId}/interact`, 
        { action: "view" }, 
        { withCredentials: true }
      );
    } catch (error) {
      console.error("Error fetching article:", error);
      toast.error("Article not found");
      navigate("/feed");
    }
  }, [articleId, navigate]);

  const fetchAllArticles = useCallback(async () => {
    try {
      // Reuse the session-level ordered list so navigation order never changes
      const stored = sessionStorage.getItem('articleList');
      if (stored) {
        const list = JSON.parse(stored);
        setAllArticles(list);
        const idx = list.findIndex(a => a.article_id === articleId);
        if (idx !== -1) setCurrentIndex(idx);
        return;
      }
      const response = await axios.get(`${API}/articles`, { withCredentials: true });
      sessionStorage.setItem('articleList', JSON.stringify(response.data));
      setAllArticles(response.data);
      const idx = response.data.findIndex(a => a.article_id === articleId);
      if (idx !== -1) setCurrentIndex(idx);
    } catch (error) {
      console.error("Error fetching articles:", error);
    }
  }, [articleId]);

  const checkBookmark = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/bookmarks/check/${articleId}`, { withCredentials: true });
      setIsBookmarked(response.data.bookmarked);
    } catch (error) {
      console.error("Error checking bookmark:", error);
    }
  }, [articleId]);

  const fetchReaction = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/articles/${articleId}/reaction`, { withCredentials: true });
      setUserReaction({ liked: response.data.liked, disliked: response.data.disliked });
      setArticle(prev => prev ? {
        ...prev,
        likes: response.data.likes_count,
        dislikes: response.data.dislikes_count,
      } : prev);
    } catch (error) {
      // Not authenticated or article not found — leave defaults
    }
  }, [articleId]);

  const fetchPoll = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/polls/${articleId}`, { withCredentials: true });
      if (response.data) {
        setPoll(response.data);
      }
    } catch (error) {
      console.error("Error fetching poll:", error);
    }
  }, [articleId]);

  const fetchComments = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/comments/${articleId}`, { withCredentials: true });
      setComments(response.data);
    } catch (error) {
      console.error("Error fetching comments:", error);
    }
  }, [articleId]);

  const fetchAIQuestions = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/ai/questions/${articleId}`, { withCredentials: true });
      setAiQuestions((response.data.questions || []).slice(0, 3));
    } catch (error) {
      console.error("Error fetching AI questions:", error);
    }
  }, [articleId]);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await fetchArticle();
      await Promise.all([checkBookmark(), fetchReaction(), fetchPoll(), fetchComments(), fetchAIQuestions(), fetchAllArticles()]);
      setLoading(false);
    };
    loadData();
  }, [fetchArticle, checkBookmark, fetchReaction, fetchPoll, fetchComments, fetchAIQuestions, fetchAllArticles]);

  // HORIZONTAL swipe handlers for mobile navigation
  const handleTouchStart = (e) => {
    if (isModalOpen) return;
    const y = e.touches[0].clientY;
    if (y < window.innerHeight * 0.10) return;  // header dead zone
    if (y > window.innerHeight * 0.70) return;  // action bar dead zone
    touchStartX.current = e.touches[0].clientX;
    touchStartTime.current = Date.now();
  };

  const handleTouchMove = (e) => {
    if (isModalOpen) return;
    touchEndX.current = e.touches[0].clientX;
  };

  const handleTouchEnd = () => {
    if (isModalOpen) return;
    const diffX = touchStartX.current - touchEndX.current;
    const elapsed = Date.now() - touchStartTime.current;

    if (Math.abs(diffX) > 50 && elapsed < 200) {
      if (diffX > 0) {
        // Swipe LEFT - next article
        if (currentIndex < allArticles.length - 1) {
          triggerHaptic('swipe');
          const nextArticle = allArticles[currentIndex + 1];
          navigate(`/article/${nextArticle.article_id}`, { replace: true });
        }
      } else {
        // Swipe RIGHT - previous article
        if (currentIndex > 0) {
          triggerHaptic('swipe');
          const prevArticle = allArticles[currentIndex - 1];
          navigate(`/article/${prevArticle.article_id}`, { replace: true });
        }
      }
    }
  };

  const goToNextArticle = () => {
    if (currentIndex < allArticles.length - 1) {
      triggerHaptic('swipe');
      const nextArticle = allArticles[currentIndex + 1];
      navigate(`/article/${nextArticle.article_id}`, { replace: true });
    }
  };

  const goToPrevArticle = () => {
    if (currentIndex > 0) {
      triggerHaptic('swipe');
      const prevArticle = allArticles[currentIndex - 1];
      navigate(`/article/${prevArticle.article_id}`, { replace: true });
    }
  };

  // Back button goes to FEED, not previous article
  const handleBack = () => {
    navigate('/feed');
  };

  const toggleBookmark = async () => {
    try {
      triggerHaptic('medium');
      if (isBookmarked) {
        await axios.delete(`${API}/bookmarks/${articleId}`, { withCredentials: true });
        toast.success("Removed from bookmarks");
      } else {
        await axios.post(`${API}/bookmarks/${articleId}`, {}, { withCredentials: true });
        toast.success("Added to bookmarks");
      }
      setIsBookmarked(!isBookmarked);
    } catch (error) {
      toast.error("Failed to update bookmark");
    }
  };

  const handleLike = async () => {
    // Optimistic update
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
      const response = await axios.post(
        `${API}/articles/${articleId}/interact`,
        { action: "like" },
        { withCredentials: true }
      );
      setUserReaction({ liked: response.data.liked, disliked: response.data.disliked });
      setArticle(prev => ({ ...prev, likes: response.data.likes_count, dislikes: response.data.dislikes_count }));
    } catch (error) {
      // Revert on failure
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
    // Optimistic update
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
      const response = await axios.post(
        `${API}/articles/${articleId}/interact`,
        { action: "dislike" },
        { withCredentials: true }
      );
      setUserReaction({ liked: response.data.liked, disliked: response.data.disliked });
      setArticle(prev => ({ ...prev, likes: response.data.likes_count, dislikes: response.data.dislikes_count }));
    } catch (error) {
      // Revert on failure
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
    try {
      triggerHaptic('success');
      const response = await axios.post(
        `${API}/polls/${poll.poll_id}/vote`,
        { option },
        { withCredentials: true }
      );
      setPoll(response.data);
      setUserVoted(true);
      toast.success("Vote recorded!");
    } catch (error) {
      if (error.response?.data?.detail === "Already voted") {
        setUserVoted(true);
      }
      toast.error(error.response?.data?.detail || "Failed to vote");
    }
  };

  const fetchOtherSide = async () => {
    if (otherSideAnalysis) {
      setShowOtherSide(true);
      return;
    }
    setLoadingOtherSide(true);
    setShowOtherSide(true);
    try {
      const response = await axios.get(`${API}/ai/other-side/${articleId}`, { withCredentials: true });
      setOtherSideAnalysis(response.data.analysis);
    } catch (error) {
      console.error("Other Side fetch error:", error);
      // Keep modal open — fallback message renders when otherSideAnalysis is null
    } finally {
      setLoadingOtherSide(false);
    }
  };

  const submitComment = async () => {
    if (!newComment.trim()) return;
    try {
      triggerHaptic('medium');
      const response = await axios.post(
        `${API}/comments/${articleId}`,
        { content: newComment, stance: "neutral" },
        { withCredentials: true }
      );
      setComments([response.data, ...comments]);
      setNewComment("");
      toast.success("Comment posted!");
    } catch (error) {
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
      if (error.response?.status === 400) {
        toast.info("Already reacted");
      } else {
        console.error("Failed to react:", error);
      }
    }
  };

  const shareArticle = async () => {
    const shareUrl = window.location.href;
    try {
      if (navigator.share) {
        await navigator.share({
          title: article.title,
          text: article.description,
          url: shareUrl
        });
      } else {
        await navigator.clipboard.writeText(shareUrl);
        toast.success("Link copied to clipboard!");
      }
    } catch (error) {
      await navigator.clipboard.writeText(shareUrl);
      toast.success("Link copied to clipboard!");
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

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center">
        <SuryaLogo className="w-16 h-16 animate-spin-slow" />
      </div>
    );
  }

  if (!article) return null;

  return (
    <div
      className="flex flex-col h-screen overflow-hidden bg-[#0A0A0A]"
      data-testid="article-page"
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
    >
      {/* Header */}
      <header className="glass-nav sticky z-40 px-4" style={{ top: 0, paddingTop: 'var(--sat, 44px)', paddingBottom: '12px' }}>
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <button 
            onClick={handleBack}
            className="p-2 hover:bg-white/5 rounded-lg transition-colors"
            data-testid="back-btn"
          >
            <ArrowLeft className="w-5 h-5 text-gray-400" />
          </button>
          
          {/* Progress indicator */}
          <div className="flex items-center gap-1">
            {allArticles.length > 0 && (
              <span className="text-gray-500 text-xs font-mono">
                {currentIndex + 1} / {allArticles.length}
              </span>
            )}
          </div>
          
          <div className="flex items-center gap-2">
            <button 
              onClick={toggleBookmark}
              className="p-2 hover:bg-white/5 rounded-lg transition-colors"
              data-testid="bookmark-btn"
            >
              {isBookmarked ? (
                <BookmarkCheck className="w-5 h-5 text-red-500" />
              ) : (
                <Bookmark className="w-5 h-5 text-gray-400" />
              )}
            </button>
            <button 
              onClick={shareArticle}
              className="p-2 hover:bg-white/5 rounded-lg transition-colors"
              data-testid="share-btn"
            >
              <Share2 className="w-5 h-5 text-gray-400" />
            </button>
          </div>
        </div>
      </header>

      {/* Hero Image */}
      <div className="relative flex-shrink-0 overflow-hidden" style={{ height: '220px' }}>
        <img
          src={article.image_url}
          alt={article.title}
          className="w-full h-full object-cover"
          style={{ transform: `translateY(${Math.min(scrollY * 0.4, 80)}px)`, transition: 'transform 0.1s linear', willChange: 'transform' }}
        />
        <div className="absolute inset-0 bg-gradient-to-t from-[#0A0A0A] via-[#0A0A0A]/30 to-transparent" />
      </div>

      {/* Breadcrumb row: CATEGORY • SOURCE • DATE */}
      <div className="flex-shrink-0 flex items-center flex-wrap gap-x-2 gap-y-1 text-xs text-gray-500 font-mono" style={{ padding: '12px 16px' }}>
        {article.category && <span className="text-red-500 uppercase tracking-wider">{article.category}</span>}
        {article.is_breaking && <><span>•</span><span className="text-red-400">Breaking</span></>}
        {article.is_developing && !article.is_breaking && <><span>•</span><span className="text-amber-500">Developing</span></>}
        {(article.source || article.domain || article.publisher) && (
          <><span>•</span><span>{article.source || article.domain || article.publisher}</span></>
        )}
        {article.published_at && (
          <><span>•</span><span>{new Date(article.published_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}</span></>
        )}
      </div>

      {/* Scrollable content */}
      <main className="flex-1 overflow-y-auto pb-24 px-4" onScroll={onScroll}>
        <article className="max-w-3xl mx-auto">
          <motion.h1
            className="font-serif font-bold text-white mb-6 leading-tight"
            style={{ fontSize: 'clamp(1.4rem, 4vw, 1.8rem)', padding: '8px 0' }}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
          >
            {article.title}
          </motion.h1>

          {article.what && (
            <p className="text-gray-300 mb-8 leading-relaxed">
              {truncateWords(article.what, 60)}
            </p>
          )}

          {/* Collapsible Sections */}
          <div className="space-y-3 mb-8">
            {[
              { key: "why", content: article.why },
              { key: "context", content: article.context },
              { key: "impact", content: article.impact }
            ].map(section => (
              <Collapsible 
                key={section.key}
                open={expandedSections[section.key]}
                onOpenChange={(open) => setExpandedSections(prev => ({ ...prev, [section.key]: open }))}
              >
                <CollapsibleTrigger asChild>
                  <button 
                    className="collapsible-header w-full"
                    data-testid={`section-${section.key}`}
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-red-500 font-mono text-xs uppercase tracking-wider">
                        {getSectionLabel(section.key, article.category)}
                      </span>
                    </div>
                    {expandedSections[section.key] ? (
                      <ChevronUp className="w-5 h-5 text-gray-500" />
                    ) : (
                      <ChevronDown className="w-5 h-5 text-gray-500" />
                    )}
                  </button>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <motion.div
                    className="px-4 py-4 text-gray-400 leading-relaxed bg-white/[0.02] rounded-b-lg border-x border-b border-white/5"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                  >
                    {truncateWords(section.content, 55)}
                  </motion.div>
                </CollapsibleContent>
              </Collapsible>
            ))}
          </div>

          {/* AI Questions */}
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
                      {truncateWords(question, 20)}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Feedback */}
          <div className="flex items-center justify-center gap-6 py-6 border-t border-white/10">
            <span className="text-gray-500 text-sm">Was this helpful?</span>
            <button
              onClick={handleLike}
              className={`flex items-center gap-2 px-4 py-2 rounded-full transition-colors ${
                userReaction.liked
                  ? "bg-green-500/20 text-green-400"
                  : "bg-white/5 hover:bg-green-500/20 text-gray-400 hover:text-green-400"
              }`}
              data-testid="like-btn"
            >
              <ThumbsUp className="w-4 h-4" />
              <span className="text-sm">{article.likes || 0}</span>
            </button>
            <button
              onClick={handleDislike}
              className={`flex items-center gap-2 px-4 py-2 rounded-full transition-colors ${
                userReaction.disliked
                  ? "bg-red-500/20 text-red-400"
                  : "bg-white/5 hover:bg-red-500/20 text-gray-400 hover:text-red-400"
              }`}
              data-testid="dislike-btn"
            >
              <ThumbsDown className="w-4 h-4" />
              <span className="text-sm">{article.dislikes || 0}</span>
            </button>
          </div>

          {/* Swipe hint for mobile - HORIZONTAL */}
          <div className="text-center py-4 md:hidden">
            <div className="flex items-center justify-center gap-4 text-gray-600 text-xs">
              {currentIndex > 0 && (
                <button onClick={goToPrevArticle} className="flex items-center gap-1 hover:text-gray-400">
                  <ChevronLeft className="w-4 h-4" /> Previous
                </button>
              )}
              <span>Swipe left/right</span>
              {currentIndex < allArticles.length - 1 && (
                <button onClick={goToNextArticle} className="flex items-center gap-1 hover:text-gray-400">
                  Next <ChevronRight className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>
        </article>
      </main>

      {/* Action Bar */}
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
              className="p-2 bg-red-600 rounded-lg hover:bg-red-700 transition-colors"
              data-testid="submit-comment-btn"
            >
              <Send className="w-5 h-5 text-white" />
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
                    <div className="flex-1">
                      <p className="text-white text-sm font-medium">{comment.user_name}</p>
                    </div>
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

          {poll ? (
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
                      className={`poll-option w-full text-left ${userVoted ? "cursor-default" : ""}`}
                      data-testid={`poll-option-${option}`}
                    >
                      {userVoted && (
                        <div className="poll-bar" style={{ width: `${percentage}%` }} />
                      )}
                      <div className="relative flex items-center justify-between">
                        <span className="text-gray-300">{option}</span>
                        {userVoted && (
                          <span className="text-gray-500 font-mono text-sm">{percentage}%</span>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>

              <p className="text-gray-500 text-sm text-center">
                {getTotalVotes()} votes
              </p>
            </div>
          ) : (
            <p className="text-gray-500 text-center py-8">No poll available for this article</p>
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
                      <div
                        key={idx}
                        style={{
                          background: '#1a1a1a',
                          border: '1px solid rgba(255,255,255,0.08)',
                          borderRadius: '12px',
                          padding: '16px 18px',
                          display: 'flex',
                          alignItems: 'flex-start',
                          gap: '12px',
                        }}
                      >
                        <span style={{ color: '#DC2626', fontSize: '8px', marginTop: '5px', flexShrink: 0 }}>●</span>
                        <p style={{ color: '#d1d5db', fontSize: '13px', lineHeight: '1.6', margin: 0 }}>{truncateWords(point, 20)}</p>
                      </div>
                    ));
                  } catch {
                    return formatOtherSide(otherSideAnalysis).split('\n\n').filter(Boolean).slice(0, 3).map((para, idx) => (
                      <div
                        key={idx}
                        style={{
                          background: '#1a1a1a',
                          border: '1px solid rgba(255,255,255,0.08)',
                          borderRadius: '12px',
                          padding: '16px 18px',
                          display: 'flex',
                          alignItems: 'flex-start',
                          gap: '12px',
                        }}
                      >
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
    </div>
  );
};

export default ArticlePage;

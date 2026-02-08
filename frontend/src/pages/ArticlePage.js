import React, { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import axios from "axios";
import { toast } from "sonner";
import { 
  ArrowLeft, Bookmark, BookmarkCheck, Share2, MessageCircle, 
  BarChart2, Sparkles, BrainCircuit, ChevronDown, ChevronUp,
  ThumbsUp, ThumbsDown, Copy, Send, X, Check
} from "lucide-react";
import { useAuth, SuryaLogo } from "../App";
import { 
  Collapsible, 
  CollapsibleContent, 
  CollapsibleTrigger 
} from "../components/ui/collapsible";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { ScrollArea } from "../components/ui/scroll-area";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const ArticlePage = () => {
  const { articleId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  
  const [article, setArticle] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isBookmarked, setIsBookmarked] = useState(false);
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
  const [commentStance, setCommentStance] = useState("agree");
  const [expandedSections, setExpandedSections] = useState({
    what: true,
    why: false,
    context: false,
    impact: false
  });

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

  const checkBookmark = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/bookmarks/check/${articleId}`, { withCredentials: true });
      setIsBookmarked(response.data.bookmarked);
    } catch (error) {
      console.error("Error checking bookmark:", error);
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
      setAiQuestions(response.data.questions || []);
    } catch (error) {
      console.error("Error fetching AI questions:", error);
    }
  }, [articleId]);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await fetchArticle();
      await Promise.all([checkBookmark(), fetchPoll(), fetchComments(), fetchAIQuestions()]);
      setLoading(false);
    };
    loadData();
  }, [fetchArticle, checkBookmark, fetchPoll, fetchComments, fetchAIQuestions]);

  const toggleBookmark = async () => {
    try {
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
    try {
      await axios.post(`${API}/articles/${articleId}/interact`, 
        { action: "like" }, 
        { withCredentials: true }
      );
      setArticle(prev => ({ ...prev, likes: (prev.likes || 0) + 1 }));
      toast.success("Thanks for your feedback!");
    } catch (error) {
      toast.error("Failed to like");
    }
  };

  const handleDislike = async () => {
    try {
      await axios.post(`${API}/articles/${articleId}/interact`, 
        { action: "dislike" }, 
        { withCredentials: true }
      );
      setArticle(prev => ({ ...prev, dislikes: (prev.dislikes || 0) + 1 }));
      toast.success("Thanks for your feedback!");
    } catch (error) {
      toast.error("Failed to dislike");
    }
  };

  const handleVote = async (option) => {
    if (userVoted || !poll) return;
    try {
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
      toast.error("Failed to load alternative perspective");
      setShowOtherSide(false);
    } finally {
      setLoadingOtherSide(false);
    }
  };

  const submitComment = async () => {
    if (!newComment.trim()) return;
    try {
      const response = await axios.post(
        `${API}/comments/${articleId}`,
        { content: newComment, stance: commentStance },
        { withCredentials: true }
      );
      setComments([response.data, ...comments]);
      setNewComment("");
      toast.success("Comment posted!");
    } catch (error) {
      toast.error("Failed to post comment");
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

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center">
        <SuryaLogo className="w-16 h-16 animate-spin-slow" />
      </div>
    );
  }

  if (!article) return null;

  return (
    <div className="min-h-screen bg-[#0A0A0A]" data-testid="article-page">
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
      <div className="relative h-72 md:h-96">
        <img 
          src={article.image_url} 
          alt={article.title}
          className="w-full h-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-[#0A0A0A] via-[#0A0A0A]/50 to-transparent" />
        
        {/* Category & Status */}
        <div className="absolute bottom-6 left-6 right-6">
          <div className="flex items-center gap-2 mb-3">
            <span className="category-badge">{article.category}</span>
            {article.is_breaking && (
              <span className="live-indicator">
                <span className="live-dot" />
                Breaking
              </span>
            )}
            {article.is_developing && !article.is_breaking && (
              <span className="text-xs text-amber-500 font-medium">Developing</span>
            )}
          </div>
        </div>
      </div>

      {/* Content */}
      <main className="px-6 pb-32 -mt-4 relative">
        <article className="max-w-3xl mx-auto">
          {/* Title */}
          <motion.h1 
            className="font-serif text-3xl md:text-4xl font-bold text-white mb-4 leading-tight"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
          >
            {article.title}
          </motion.h1>

          {/* Meta */}
          <div className="flex items-center gap-4 text-sm text-gray-500 mb-6">
            <span className="font-mono">{article.source}</span>
            {article.author && <span>• {article.author}</span>}
          </div>

          {/* Description */}
          <p className="text-lg text-gray-300 mb-8 leading-relaxed">
            {article.description}
          </p>

          {/* Content */}
          <div className="text-gray-400 leading-relaxed mb-8">
            {article.content}
          </div>

          {/* Collapsible Sections */}
          <div className="space-y-3 mb-8">
            {[
              { key: "what", label: "What Happened", icon: "📰", content: article.what },
              { key: "why", label: "Why It Matters", icon: "💡", content: article.why },
              { key: "context", label: "Context", icon: "📚", content: article.context },
              { key: "impact", label: "Impact", icon: "🎯", content: article.impact }
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
                      <span>{section.icon}</span>
                      <span className="text-white font-medium">{section.label}</span>
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
                    {section.content}
                  </motion.div>
                </CollapsibleContent>
              </Collapsible>
            ))}
          </div>

          {/* AI Questions */}
          {aiQuestions.length > 0 && (
            <div className="glass-card rounded-xl p-6 mb-8">
              <div className="flex items-center gap-2 mb-4">
                <Sparkles className="w-5 h-5 text-red-500" />
                <span className="text-white font-medium">Questions to Consider</span>
              </div>
              <div className="space-y-3">
                {aiQuestions.map((question, idx) => (
                  <button
                    key={idx}
                    onClick={() => navigate(`/ask-ai/${articleId}?q=${encodeURIComponent(question)}`)}
                    className="w-full text-left p-3 rounded-lg bg-white/5 hover:bg-white/10 transition-colors text-gray-400 text-sm"
                    data-testid={`ai-question-${idx}`}
                  >
                    {question}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Feedback */}
          <div className="flex items-center justify-center gap-6 py-6 border-t border-white/10">
            <span className="text-gray-500 text-sm">Was this helpful?</span>
            <button 
              onClick={handleLike}
              className="flex items-center gap-2 px-4 py-2 rounded-full bg-white/5 hover:bg-green-500/20 transition-colors text-gray-400 hover:text-green-400"
              data-testid="like-btn"
            >
              <ThumbsUp className="w-4 h-4" />
              <span className="text-sm">{article.likes || 0}</span>
            </button>
            <button 
              onClick={handleDislike}
              className="flex items-center gap-2 px-4 py-2 rounded-full bg-white/5 hover:bg-red-500/20 transition-colors text-gray-400 hover:text-red-400"
              data-testid="dislike-btn"
            >
              <ThumbsDown className="w-4 h-4" />
              <span className="text-sm">{article.dislikes || 0}</span>
            </button>
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
          
          {poll && (
            <button 
              onClick={() => setShowPoll(true)}
              className="flex flex-col items-center gap-1 text-gray-400 hover:text-white transition-colors"
              data-testid="poll-btn"
            >
              <BarChart2 className="w-5 h-5" />
              <span className="text-xs">Poll</span>
            </button>
          )}
          
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
          
          {/* New Comment */}
          <div className="space-y-3 mb-4">
            <div className="flex gap-2">
              <button
                onClick={() => setCommentStance("agree")}
                className={`px-3 py-1.5 rounded-full text-sm transition-colors ${
                  commentStance === "agree" 
                    ? "bg-green-500/20 text-green-400 border border-green-500/50" 
                    : "bg-white/5 text-gray-400"
                }`}
              >
                Agree
              </button>
              <button
                onClick={() => setCommentStance("disagree")}
                className={`px-3 py-1.5 rounded-full text-sm transition-colors ${
                  commentStance === "disagree" 
                    ? "bg-red-500/20 text-red-400 border border-red-500/50" 
                    : "bg-white/5 text-gray-400"
                }`}
              >
                Disagree
              </button>
            </div>
            <div className="flex gap-2">
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
                    <div>
                      <p className="text-white text-sm font-medium">{comment.user_name}</p>
                      <span className={`text-xs ${
                        comment.stance === "agree" ? "text-green-400" : "text-red-400"
                      }`}>
                        {comment.stance === "agree" ? "Agrees" : "Disagrees"}
                      </span>
                    </div>
                  </div>
                  <p className="text-gray-400 text-sm">{comment.content}</p>
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
        <DialogContent className="bg-[#0A0A0A] border-white/10 max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-white">Poll</DialogTitle>
          </DialogHeader>
          
          {poll && (
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
              <div className="prose prose-invert prose-sm max-w-none">
                <div className="text-gray-300 whitespace-pre-wrap leading-relaxed">
                  {otherSideAnalysis}
                </div>
              </div>
            ) : (
              <p className="text-gray-500 text-center py-8">Failed to load analysis</p>
            )}
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ArticlePage;

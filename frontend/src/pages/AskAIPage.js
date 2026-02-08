import React, { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import axios from "axios";
import { toast } from "sonner";
import { ArrowLeft, Send, Sparkles, User, Loader2 } from "lucide-react";
import { useAuth, SuryaLogo } from "../App";
import { ScrollArea } from "../components/ui/scroll-area";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const AskAIPage = () => {
  const { articleId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  
  const [article, setArticle] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [suggestedQuestions, setSuggestedQuestions] = useState([]);
  
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const fetchArticle = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/articles/${articleId}`, { withCredentials: true });
      setArticle(response.data);
    } catch (error) {
      console.error("Error fetching article:", error);
      toast.error("Article not found");
      navigate("/feed");
    }
  }, [articleId, navigate]);

  const fetchChatHistory = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/ai/chat-history/${articleId}`, { withCredentials: true });
      setMessages(response.data);
    } catch (error) {
      console.error("Error fetching chat history:", error);
    }
  }, [articleId]);

  const fetchQuestions = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/ai/questions/${articleId}`, { withCredentials: true });
      setSuggestedQuestions(response.data.questions || []);
    } catch (error) {
      console.error("Error fetching questions:", error);
    }
  }, [articleId]);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await fetchArticle();
      await Promise.all([fetchChatHistory(), fetchQuestions()]);
      setLoading(false);
      
      // Check for pre-populated question
      const preQuestion = searchParams.get("q");
      if (preQuestion) {
        setInput(preQuestion);
        inputRef.current?.focus();
      }
    };
    loadData();
  }, [fetchArticle, fetchChatHistory, fetchQuestions, searchParams]);

  const sendMessage = async (text = input) => {
    if (!text.trim() || sending) return;

    const userMessage = {
      message_id: `temp_${Date.now()}`,
      role: "user",
      content: text,
      created_at: new Date().toISOString()
    };

    setMessages(prev => [...prev, userMessage]);
    setInput("");
    setSending(true);

    try {
      const response = await axios.post(
        `${API}/ai/ask`,
        { message: text, article_id: articleId },
        { withCredentials: true }
      );

      const aiMessage = {
        message_id: `ai_${Date.now()}`,
        role: "assistant",
        content: response.data.response,
        created_at: new Date().toISOString()
      };

      setMessages(prev => [...prev, aiMessage]);
    } catch (error) {
      console.error("Error sending message:", error);
      toast.error("Failed to get response");
      // Remove the user message on error
      setMessages(prev => prev.filter(m => m.message_id !== userMessage.message_id));
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center">
        <SuryaLogo className="w-16 h-16 animate-spin-slow" />
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-[#0A0A0A] flex flex-col" data-testid="ask-ai-page">
      {/* Header */}
      <header className="glass-nav px-4 py-3 flex-shrink-0">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <button 
            onClick={() => navigate(-1)}
            className="p-2 hover:bg-white/5 rounded-lg transition-colors"
            data-testid="back-btn"
          >
            <ArrowLeft className="w-5 h-5 text-gray-400" />
          </button>
          
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-red-500" />
            <span className="text-white font-medium">Ask AI</span>
          </div>

          <div className="w-9" />
        </div>
      </header>

      {/* Article Context */}
      {article && (
        <div className="px-4 py-3 border-b border-white/5 flex-shrink-0">
          <div className="max-w-3xl mx-auto">
            <p className="text-gray-500 text-xs mb-1">Discussing:</p>
            <p className="text-white text-sm line-clamp-1">{article.title}</p>
          </div>
        </div>
      )}

      {/* Messages */}
      <ScrollArea className="flex-1 px-4">
        <div className="max-w-3xl mx-auto py-6">
          {messages.length === 0 ? (
            <motion.div 
              className="text-center py-12"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <div className="w-16 h-16 rounded-full bg-red-600/20 flex items-center justify-center mx-auto mb-6">
                <Sparkles className="w-8 h-8 text-red-500" />
              </div>
              <h2 className="font-serif text-2xl text-white mb-3">Ask Chintan AI</h2>
              <p className="text-gray-500 mb-8 max-w-md mx-auto">
                I can help you understand this article better, explore different perspectives, 
                or answer any questions you have.
              </p>

              {/* Suggested Questions */}
              {suggestedQuestions.length > 0 && (
                <div className="space-y-2">
                  <p className="text-gray-600 text-sm mb-3">Try asking:</p>
                  {suggestedQuestions.slice(0, 3).map((question, idx) => (
                    <button
                      key={idx}
                      onClick={() => sendMessage(question)}
                      className="w-full max-w-md mx-auto block text-left p-3 rounded-lg bg-white/5 hover:bg-white/10 transition-colors text-gray-400 text-sm"
                      data-testid={`suggested-question-${idx}`}
                    >
                      {question}
                    </button>
                  ))}
                </div>
              )}
            </motion.div>
          ) : (
            <div className="space-y-4">
              <AnimatePresence>
                {messages.map((message, idx) => (
                  <motion.div
                    key={message.message_id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className={`flex gap-3 ${message.role === "user" ? "justify-end" : ""}`}
                  >
                    {message.role === "assistant" && (
                      <div className="w-8 h-8 rounded-full bg-red-600/20 flex items-center justify-center flex-shrink-0">
                        <Sparkles className="w-4 h-4 text-red-500" />
                      </div>
                    )}
                    
                    <div className={`max-w-[80%] ${
                      message.role === "user" 
                        ? "bg-red-600 text-white rounded-2xl rounded-br-md" 
                        : "bg-white/5 text-gray-300 rounded-2xl rounded-bl-md"
                    } px-4 py-3`}>
                      <p className="text-sm whitespace-pre-wrap leading-relaxed">
                        {message.content}
                      </p>
                    </div>

                    {message.role === "user" && (
                      <div className="w-8 h-8 rounded-full bg-white/10 overflow-hidden flex-shrink-0">
                        {user?.picture ? (
                          <img src={user.picture} alt="" className="w-full h-full object-cover" />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center">
                            <User className="w-4 h-4 text-gray-500" />
                          </div>
                        )}
                      </div>
                    )}
                  </motion.div>
                ))}
              </AnimatePresence>

              {sending && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="flex gap-3"
                >
                  <div className="w-8 h-8 rounded-full bg-red-600/20 flex items-center justify-center flex-shrink-0">
                    <Sparkles className="w-4 h-4 text-red-500" />
                  </div>
                  <div className="bg-white/5 rounded-2xl rounded-bl-md px-4 py-3">
                    <Loader2 className="w-5 h-5 text-gray-500 animate-spin" />
                  </div>
                </motion.div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Input */}
      <div className="glass-nav px-4 py-4 flex-shrink-0">
        <div className="max-w-3xl mx-auto flex gap-3">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything about this article..."
            className="flex-1 bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-gray-500 focus:border-red-500 focus:outline-none"
            disabled={sending}
            data-testid="ai-input"
          />
          <button
            onClick={() => sendMessage()}
            disabled={!input.trim() || sending}
            className={`p-3 rounded-xl transition-colors ${
              input.trim() && !sending
                ? "bg-red-600 hover:bg-red-700 text-white"
                : "bg-white/5 text-gray-600 cursor-not-allowed"
            }`}
            data-testid="send-message-btn"
          >
            {sending ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <Send className="w-5 h-5" />
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

export default AskAIPage;

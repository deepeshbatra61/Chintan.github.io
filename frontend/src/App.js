import React, { useState, useEffect, useRef, createContext, useContext } from "react";
import { BrowserRouter, Routes, Route, useNavigate, useLocation, Navigate } from "react-router-dom";
import axios from "axios";
import { Toaster, toast } from "sonner";
import "./App.css";

// Pages
import LoginPage from "./pages/LoginPage";
import OnboardingPage from "./pages/OnboardingPage";
import FeedPage from "./pages/FeedPage";
import ArticlePage from "./pages/ArticlePage";
import BriefPage from "./pages/BriefPage";
import BookmarksPage from "./pages/BookmarksPage";
import ProfilePage from "./pages/ProfilePage";
import AskAIPage from "./pages/AskAIPage";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Auth Context
const AuthContext = createContext(null);

export const useAuth = () => useContext(AuthContext);

// Auth Provider
const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const checkAuth = async () => {
    try {
      const response = await axios.get(`${API}/auth/me`, {
        withCredentials: true
      });
      setUser(response.data);
    } catch (error) {
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    checkAuth();
  }, []);

  const login = (userData) => {
    setUser(userData);
  };

  const logout = async () => {
    try {
      await axios.post(`${API}/auth/logout`, {}, { withCredentials: true });
    } catch (error) {
      console.error("Logout error:", error);
    }
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, checkAuth }}>
      {children}
    </AuthContext.Provider>
  );
};

// Auth Callback Handler
const AuthCallback = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();
  const hasProcessed = useRef(false);

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const processAuth = async () => {
      const hash = location.hash;
      const sessionIdMatch = hash.match(/session_id=([^&]+)/);
      
      if (sessionIdMatch) {
        const sessionId = sessionIdMatch[1];
        try {
          const response = await axios.post(
            `${API}/auth/session`,
            { session_id: sessionId },
            { withCredentials: true }
          );
          
          login(response.data.user);
          toast.success("Welcome to Chintan!");
          
          // Check if onboarding needed
          if (!response.data.user.onboarding_completed) {
            navigate("/onboarding", { replace: true, state: { user: response.data.user } });
          } else {
            navigate("/feed", { replace: true, state: { user: response.data.user } });
          }
        } catch (error) {
          console.error("Auth error:", error);
          toast.error("Authentication failed");
          navigate("/login", { replace: true });
        }
      } else {
        navigate("/login", { replace: true });
      }
    };

    processAuth();
  }, [location, login, navigate]);

  return (
    <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center">
      <div className="text-center">
        <SuryaLogo className="w-16 h-16 mx-auto animate-spin-slow" />
        <p className="mt-4 text-gray-400">Authenticating...</p>
      </div>
    </div>
  );
};

// Protected Route
const ProtectedRoute = ({ children }) => {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center">
        <div className="text-center">
          <SuryaLogo className="w-16 h-16 mx-auto animate-spin-slow" />
          <p className="mt-4 text-gray-400">Loading...</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Check onboarding
  if (!user.onboarding_completed && location.pathname !== "/onboarding") {
    return <Navigate to="/onboarding" replace />;
  }

  return children;
};

// Surya Logo Component
export const SuryaLogo = ({ className = "w-10 h-10" }) => (
  <svg viewBox="0 0 100 100" className={className}>
    <defs>
      <radialGradient id="sunGlow" cx="50%" cy="50%" r="50%">
        <stop offset="0%" stopColor="#DC2626" stopOpacity="0.8" />
        <stop offset="100%" stopColor="#DC2626" stopOpacity="0" />
      </radialGradient>
    </defs>
    {/* Glow */}
    <circle cx="50" cy="50" r="45" fill="url(#sunGlow)" />
    {/* Center */}
    <circle cx="50" cy="50" r="15" fill="#DC2626" />
    {/* 12 Rays */}
    {[...Array(12)].map((_, i) => {
      const angle = (i * 30) * (Math.PI / 180);
      const x1 = 50 + 20 * Math.cos(angle);
      const y1 = 50 + 20 * Math.sin(angle);
      const x2 = 50 + 40 * Math.cos(angle);
      const y2 = 50 + 40 * Math.sin(angle);
      return (
        <line
          key={i}
          x1={x1}
          y1={y1}
          x2={x2}
          y2={y2}
          stroke="#DC2626"
          strokeWidth="3"
          strokeLinecap="round"
        />
      );
    })}
  </svg>
);

// Main App Router
function AppRouter() {
  const location = useLocation();

  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
  // Check for session_id in hash FIRST (synchronously during render)
  if (location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/onboarding" element={
        <ProtectedRoute>
          <OnboardingPage />
        </ProtectedRoute>
      } />
      <Route path="/feed" element={
        <ProtectedRoute>
          <FeedPage />
        </ProtectedRoute>
      } />
      <Route path="/article/:articleId" element={
        <ProtectedRoute>
          <ArticlePage />
        </ProtectedRoute>
      } />
      <Route path="/brief/:briefType" element={
        <ProtectedRoute>
          <BriefPage />
        </ProtectedRoute>
      } />
      <Route path="/bookmarks" element={
        <ProtectedRoute>
          <BookmarksPage />
        </ProtectedRoute>
      } />
      <Route path="/profile" element={
        <ProtectedRoute>
          <ProfilePage />
        </ProtectedRoute>
      } />
      <Route path="/ask-ai/:articleId" element={
        <ProtectedRoute>
          <AskAIPage />
        </ProtectedRoute>
      } />
      <Route path="/" element={<Navigate to="/feed" replace />} />
      <Route path="*" element={<Navigate to="/feed" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Toaster 
          position="top-center" 
          toastOptions={{
            style: {
              background: '#171717',
              border: '1px solid rgba(255,255,255,0.1)',
              color: '#EDEDED'
            }
          }}
        />
        <AppRouter />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;

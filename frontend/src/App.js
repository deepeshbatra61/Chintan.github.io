import React, { useState, useEffect, useRef, createContext, useContext } from "react";
import { BrowserRouter, Routes, Route, useNavigate, useLocation, Navigate } from "react-router-dom";
import axios from "axios";
import { Toaster, toast } from "sonner";
import { App as CapApp } from "@capacitor/app";
import { Browser } from "@capacitor/browser";
import "./App.css";

// ── Global axios setup ────────────────────────────────────────────────────────
// Always send cookies AND, when available, the session token as a Bearer header.
// This dual approach handles browsers that drop cross-origin Set-Cookie headers.
axios.defaults.withCredentials = true;
axios.interceptors.request.use((config) => {
  const token = sessionStorage.getItem("chintan_session_token");
  if (token && !config.headers["Authorization"]) {
    config.headers["Authorization"] = `Bearer ${token}`;
  }
  return config;
});

// Pages
import LoginPage from "./pages/LoginPage";
import OnboardingPage from "./pages/OnboardingPage";
import FeedPage from "./pages/FeedPage";
import ArticlePage from "./pages/ArticlePage";
import BriefPage from "./pages/BriefPage";
import BookmarksPage from "./pages/BookmarksPage";
import ProfilePage from "./pages/ProfilePage";
import AskAIPage from "./pages/AskAIPage";
import DevelopingPage from "./pages/DevelopingPage";
import DevelopingStoryDetail from "./pages/DevelopingStoryDetail";

const BACKEND_URL = "https://chintangithubio-production.up.railway.app";
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

  const login = (userData, token = null) => {
    setUser(userData);
    if (token) {
      sessionStorage.setItem("chintan_session_token", token);
    }
  };

  const logout = async () => {
    try {
      await axios.post(`${API}/auth/logout`, {}, { withCredentials: true });
    } catch (error) {
      console.error("Logout error:", error);
    }
    sessionStorage.removeItem("chintan_session_token");
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, checkAuth }}>
      {children}
    </AuthContext.Provider>
  );
};

// Google OAuth Callback Handler
const AuthCallback = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();
  const hasProcessed = useRef(false);

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const processAuth = async () => {
      const params = new URLSearchParams(location.search);
      const code = params.get("code");
      const state = params.get("state");
      const error = params.get("error");

      if (error) {
        toast.error("Google sign-in was cancelled");
        navigate("/login", { replace: true });
        return;
      }

      // CSRF state validation
      const savedState = sessionStorage.getItem("oauth_state");
      sessionStorage.removeItem("oauth_state");

      if (!code || !state || state !== savedState) {
        toast.error("Authentication failed — invalid state");
        navigate("/login", { replace: true });
        return;
      }

      try {
        const redirectUri = `${window.location.origin}${process.env.PUBLIC_URL}/auth/callback`;
        const response = await axios.post(
          `${API}/auth/google`,
          { code, redirect_uri: redirectUri },
          { withCredentials: true }
        );

        login(response.data.user, response.data.session_token);
        toast.success("Welcome to Chintan!");

        if (!response.data.user.onboarding_completed) {
          navigate("/onboarding", { replace: true });
        } else {
          navigate("/feed", { replace: true });
        }
      } catch (err) {
        console.error("Auth error:", err);
        toast.error("Authentication failed");
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

// Handles Google OAuth deep-link callback for the native Capacitor app.
// Google redirects to the backend relay, which redirects back here via
// com.chintan.app://auth/callback?session_token=...&state=...
const NativeAuthHandler = () => {
  const { login } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!window.Capacitor?.isNativePlatform()) return;

    const handleUrl = async ({ url }) => {
      if (!url.startsWith("com.chintan.app://auth/callback")) return;

      // Close the in-app browser
      try { await Browser.close(); } catch (_) {}

      const params = new URLSearchParams(url.split("?")[1] || "");
      const sessionToken = params.get("session_token");
      const state = params.get("state");
      const error = params.get("error");

      if (error || !sessionToken) {
        toast.error("Google sign-in failed");
        navigate("/login", { replace: true });
        return;
      }

      // CSRF state validation
      const savedState = sessionStorage.getItem("oauth_state");
      sessionStorage.removeItem("oauth_state");
      if (state && state !== savedState) {
        toast.error("Authentication failed — invalid state");
        navigate("/login", { replace: true });
        return;
      }

      // Store token so the axios interceptor sends it as Bearer on every request
      sessionStorage.setItem("chintan_session_token", sessionToken);

      try {
        const response = await axios.get(`${API}/auth/me`, { withCredentials: true });
        login(response.data, sessionToken);
        toast.success("Welcome to Chintan!");
        if (!response.data.onboarding_completed) {
          navigate("/onboarding", { replace: true });
        } else {
          navigate("/feed", { replace: true });
        }
      } catch (err) {
        console.error("Native auth error:", err);
        toast.error("Authentication failed");
        navigate("/login", { replace: true });
      }
    };

    CapApp.addListener("appUrlOpen", handleUrl);
    return () => { CapApp.removeAllListeners(); };
  }, [login, navigate]);

  return null;
};

// Main App Router
function AppRouter() {
  return (
    <>
      <NativeAuthHandler />
      <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/auth/callback" element={<AuthCallback />} />
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
      <Route path="/developing" element={
        <ProtectedRoute>
          <DevelopingPage />
        </ProtectedRoute>
      } />
      <Route path="/developing/:storyId" element={
        <ProtectedRoute>
          <DevelopingStoryDetail />
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
    </>
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

import React, { useRef, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import axios from "axios";
import { toast } from "sonner";
import { SuryaLogo, useAuth } from "../App";
import { Browser } from "@capacitor/browser";
import { setTokens } from "../lib/tokenStore";

const NATIVE_REDIRECT_URI =
  "https://chintangithubio-production.up.railway.app/api/auth/native-callback";
const API = "https://chintangithubio-production.up.railway.app/api";

const isNative = () => !!window.Capacitor?.isNativePlatform();

const LoginPage = () => {
  const { login, setShowWelcome, setWelcomeDest } = useAuth();
  const navigate = useNavigate();
  const pollingRef = useRef(null);

  const [mode, setMode] = useState("login"); // 'login' | 'register'
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    return () => { if (pollingRef.current) clearInterval(pollingRef.current); };
  }, []);

  const goAfterAuth = (userData) => {
    const dest = userData.onboarding_completed ? "/feed" : "/onboarding";
    setWelcomeDest(dest);
    setShowWelcome(true);
  };

  // ── Email + password ────────────────────────────────────────────────────────
  const handleEmailAuth = async (e) => {
    e.preventDefault();
    if (submitting) return;
    if (!email.trim() || !password) {
      toast.error("Enter your email and password");
      return;
    }
    if (mode === "register" && password.length < 8) {
      toast.error("Password must be at least 8 characters");
      return;
    }
    setSubmitting(true);
    try {
      const path = mode === "register" ? "/auth/register" : "/auth/login";
      const body = mode === "register"
        ? { email: email.trim(), password, name: name.trim() }
        : { email: email.trim(), password };
      const r = await axios.post(`${API}${path}`, body, { withCredentials: true });
      await login(r.data.user, r.data.session_token, r.data.refresh_token);
      goAfterAuth(r.data.user);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Something went wrong. Try again.");
    } finally {
      setSubmitting(false);
    }
  };

  // ── Google (native poll + web redirect) ──────────────────────────────────────
  const stopPolling = () => {
    if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null; }
    sessionStorage.removeItem("native_auth_pending");
  };

  const finishNativeAuth = async (sessionToken, refreshToken) => {
    stopPolling();
    await setTokens(sessionToken, refreshToken);
    try { await Browser.close(); } catch (_) {}
    const meResp = await axios.get(`${API}/auth/me`);
    await login(meResp.data, sessionToken, refreshToken);
    goAfterAuth(meResp.data);
  };

  const startNativePoll = (state) => {
    sessionStorage.setItem("native_auth_pending", "true");
    const deadline = Date.now() + 60000;
    pollingRef.current = setInterval(async () => {
      if (!sessionStorage.getItem("native_auth_pending")) { stopPolling(); return; }
      if (Date.now() > deadline) { stopPolling(); toast.error("Sign-in timed out — please try again"); return; }
      try {
        const resp = await axios.get(`${API}/auth/native-poll?state=${state}`);
        if (resp.data?.session_token) await finishNativeAuth(resp.data.session_token, resp.data.refresh_token);
      } catch (e) { /* 404 = not ready yet */ }
    }, 2000);
  };

  const handleGoogleLogin = async () => {
    const clientId = process.env.REACT_APP_GOOGLE_CLIENT_ID;
    if (!clientId) { console.error("REACT_APP_GOOGLE_CLIENT_ID is not set"); return; }
    const state = crypto.randomUUID();
    sessionStorage.setItem("oauth_state", state);
    const redirectUri = isNative()
      ? NATIVE_REDIRECT_URI
      : `${window.location.origin}${process.env.PUBLIC_URL}/auth/callback`;
    const params = new URLSearchParams({
      client_id: clientId, redirect_uri: redirectUri, response_type: "code",
      scope: "openid email profile", state, access_type: "online",
    });
    const oauthUrl = `https://accounts.google.com/o/oauth2/v2/auth?${params}`;
    if (isNative()) { await Browser.open({ url: oauthUrl }); startNativePoll(state); }
    else { window.location.href = oauthUrl; }
  };

  const inputStyle = {
    width: "100%", background: "#131211", border: "1px solid rgba(255,255,255,0.09)",
    borderRadius: "12px", padding: "13px 14px", color: "#ECE7E1", fontSize: "15px",
    fontFamily: "'Manrope', sans-serif", outline: "none", marginBottom: "10px",
    transition: "border-color .2s",
  };
  const focusOn = (e) => { e.target.style.borderColor = "rgba(220,38,38,0.5)"; };
  const focusOff = (e) => { e.target.style.borderColor = "rgba(255,255,255,0.09)"; };

  return (
    <div style={{ minHeight: "100vh", background: "#0A0A0A", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", overflowY: "auto", padding: "40px 22px" }}>
      {/* Single calm dawn glow behind the mark — no full-screen rays */}
      <div style={{ position: "fixed", top: "8%", left: "50%", transform: "translateX(-50%)", width: "360px", height: "300px", background: "radial-gradient(ellipse at center, rgba(220,38,38,0.16), rgba(10,10,10,0) 70%)", pointerEvents: "none", zIndex: 0 }} />

      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}
        style={{ position: "relative", zIndex: 1, width: "100%", maxWidth: "360px", textAlign: "center" }}>
        {/* Mark */}
        <motion.div animate={{ scale: [1, 1.05, 1], opacity: [0.9, 1, 0.9] }} transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }} style={{ display: "inline-block", marginBottom: "18px" }}>
          <SuryaLogo className="w-16 h-16" />
        </motion.div>

        {/* Brand + tagline */}
        <h1 style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontWeight: 600, fontSize: "42px", color: "#F2EEE9", margin: "0 0 8px", letterSpacing: "-0.01em" }}>Chintan</h1>
        <p style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontStyle: "italic", fontSize: "16px", color: "#8E877E", margin: "0 0 28px" }}>
          Don't just consume. <span style={{ color: "#DC6B5A" }}>Contemplate.</span>
        </p>

        {/* Auth card */}
        <div style={{ background: "rgba(19,18,17,0.7)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: "18px", padding: "22px 18px", textAlign: "left" }}>
          <div style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontWeight: 600, fontSize: "18px", color: "#ECE7E1", marginBottom: "16px", textAlign: "center" }}>
            {mode === "register" ? "Create your account" : "Welcome back"}
          </div>

          <form onSubmit={handleEmailAuth}>
            {mode === "register" && (
              <input type="text" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} onFocus={focusOn} onBlur={focusOff} style={inputStyle} data-testid="name-input" />
            )}
            <input type="email" placeholder="Email" autoCapitalize="none" autoCorrect="off" value={email} onChange={(e) => setEmail(e.target.value)} onFocus={focusOn} onBlur={focusOff} style={inputStyle} data-testid="email-input" />
            <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} onFocus={focusOn} onBlur={focusOff} style={{ ...inputStyle, marginBottom: "14px" }} data-testid="password-input" />
            <button type="submit" disabled={submitting} data-testid="email-auth-btn"
              style={{ width: "100%", background: "#DC2626", color: "#fff", border: "none", borderRadius: "12px", padding: "13px", fontSize: "15px", fontWeight: 600, cursor: "pointer", opacity: submitting ? 0.6 : 1, fontFamily: "'Manrope', sans-serif" }}>
              {submitting ? "Please wait…" : mode === "register" ? "Create account" : "Sign in"}
            </button>
          </form>

          <div style={{ textAlign: "center", marginTop: "14px", fontSize: "13px", color: "#8A847C" }}>
            {mode === "register" ? "Already have an account? " : "New to Chintan? "}
            <button onClick={() => setMode(mode === "register" ? "login" : "register")} data-testid="toggle-mode-btn"
              style={{ background: "none", border: "none", color: "#DC6B5A", cursor: "pointer", fontWeight: 600, fontSize: "13px", padding: 0 }}>
              {mode === "register" ? "Sign in" : "Create one"}
            </button>
          </div>

          {/* Divider */}
          <div style={{ display: "flex", alignItems: "center", gap: "12px", margin: "18px 0 14px" }}>
            <div style={{ flex: 1, height: "1px", background: "rgba(255,255,255,0.08)" }} />
            <span style={{ color: "#5A544D", fontSize: "11px", fontFamily: "'JetBrains Mono', monospace" }}>or</span>
            <div style={{ flex: 1, height: "1px", background: "rgba(255,255,255,0.08)" }} />
          </div>

          {/* Google */}
          <button onClick={handleGoogleLogin} data-testid="google-login-btn"
            style={{ width: "100%", background: "#fff", color: "#1a1a1a", border: "none", borderRadius: "12px", padding: "12px", fontSize: "14px", fontWeight: 600, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: "9px", fontFamily: "'Manrope', sans-serif" }}>
            <svg className="w-5 h-5" viewBox="0 0 24 24" style={{ width: "18px", height: "18px" }}>
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            Continue with Google
          </button>
        </div>

        {/* Values */}
        <div style={{ display: "flex", justifyContent: "center", flexWrap: "wrap", gap: "16px", marginTop: "22px", fontSize: "11px", color: "#5A544D" }}>
          {["Truth over bias", "Depth over speed", "Reflection over reaction"].map((v) => (
            <span key={v} style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
              <span style={{ width: "4px", height: "4px", borderRadius: "50%", background: "#DC2626" }} />{v}
            </span>
          ))}
        </div>
      </motion.div>
    </div>
  );
};

export default LoginPage;

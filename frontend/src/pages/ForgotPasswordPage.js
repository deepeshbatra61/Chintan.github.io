import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import axios from "axios";
import { ArrowLeft, Mail, Check } from "lucide-react";

const BACKEND_URL = "https://chintangithubio-production.up.railway.app";
const API = `${BACKEND_URL}/api`;
const EASE = [0.16, 1, 0.3, 1];

const inputStyle = {
  width: "100%", background: "#131211", border: "1px solid rgba(255,255,255,0.09)",
  borderRadius: "12px", padding: "13px 14px", color: "#ECE7E1", fontSize: "15px",
  fontFamily: "'Manrope', sans-serif", outline: "none", marginBottom: "10px",
  transition: "border-color .16s cubic-bezier(.22,1,.36,1), box-shadow .16s cubic-bezier(.22,1,.36,1)",
};
const focusOn = (e) => { e.target.style.borderColor = "rgba(220,38,38,0.55)"; e.target.style.boxShadow = "0 0 0 3px rgba(220,38,38,0.14)"; };
const focusOff = (e) => { e.target.style.borderColor = "rgba(255,255,255,0.09)"; e.target.style.boxShadow = "none"; };

// The "Single Card" pattern approved via /design-shotgun: one card in place,
// its content morphs between states rather than navigating to a new screen.
// Two states live here (request the link, then confirm it's sent) -- the
// actual password-setting step happens on chintan.news/reset-password once
// the emailed link is opened, since that has to work reliably regardless of
// whether the app is installed on the device the email is read from.
const ForgotPasswordPage = () => {
  const navigate = useNavigate();
  const R = useReducedMotion();
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email.trim() || submitting) return;
    setSubmitting(true);
    try {
      await axios.post(`${API}/auth/forgot-password`, { email: email.trim() });
    } catch {
      // Backend always returns 200 with a generic message regardless of
      // whether the email exists, so a request-level failure here is a real
      // network problem -- but we still move to the confirmation state
      // rather than reveal account existence through a different UI path.
    } finally {
      setSubmitting(false);
      setSent(true);
    }
  };

  return (
    <div style={{ minHeight: "100vh", background: "#0A0A0A", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "40px 22px" }}>
      <button onClick={() => navigate(-1)} data-testid="back-btn"
        style={{ position: "fixed", top: "var(--sat, 44px)", left: "16px", padding: "8px", background: "none", border: "none", cursor: "pointer" }}>
        <ArrowLeft className="w-5 h-5" style={{ color: "#9A938A" }} />
      </button>

      <div style={{ width: "100%", maxWidth: "380px" }}>
        <div
          style={{
            background: "#131211", border: "1px solid rgba(255,255,255,0.08)", borderRadius: "18px",
            padding: "30px 26px", position: "relative", overflow: "hidden",
          }}
          data-testid="forgot-password-card"
        >
          <AnimatePresence mode="wait" initial={false}>
            {!sent ? (
              <motion.div
                key="request"
                initial={R ? false : { opacity: 0, x: -12 }}
                animate={{ opacity: 1, x: 0 }}
                exit={R ? { opacity: 0 } : { opacity: 0, x: -12 }}
                transition={{ duration: 0.32, ease: EASE }}
              >
                <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "9px", letterSpacing: "0.2em", color: "#5A544D", textTransform: "uppercase", marginBottom: "10px" }}>
                  Reset password
                </div>
                <h1 style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontWeight: 600, fontSize: "24px", color: "#F2EEE9", margin: "0 0 8px" }}>
                  Forgot your password?
                </h1>
                <p style={{ color: "#8A847C", fontSize: "13.5px", lineHeight: 1.55, margin: "0 0 22px" }}>
                  Enter the email on your account and we'll send you a link to set a new one.
                </p>
                <form onSubmit={handleSubmit}>
                  <input
                    type="email" placeholder="Email" autoCapitalize="none" autoCorrect="off"
                    value={email} onChange={(e) => setEmail(e.target.value)}
                    onFocus={focusOn} onBlur={focusOff} style={inputStyle} data-testid="forgot-email-input"
                  />
                  <motion.button
                    type="submit" disabled={submitting} data-testid="send-reset-link-btn"
                    whileTap={R ? undefined : { scale: 0.97 }}
                    style={{
                      width: "100%", background: "linear-gradient(180deg, #DC2626, #B91C1C)", color: "#fff",
                      border: "none", borderRadius: "12px", padding: "13px", fontSize: "15px", fontWeight: 600,
                      cursor: "pointer", opacity: submitting ? 0.6 : 1, fontFamily: "'Manrope', sans-serif",
                      marginTop: "4px",
                    }}
                  >
                    {submitting ? "Sending…" : "Send reset link"}
                  </motion.button>
                </form>
              </motion.div>
            ) : (
              <motion.div
                key="sent"
                initial={R ? false : { opacity: 0, x: 12 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.32, ease: EASE }}
                style={{ textAlign: "center" }}
                data-testid="reset-link-sent"
              >
                <div style={{
                  width: "52px", height: "52px", borderRadius: "50%", background: "rgba(34,197,94,0.12)",
                  border: "1px solid rgba(34,197,94,0.3)", display: "flex", alignItems: "center", justifyContent: "center",
                  margin: "0 auto 18px",
                }}>
                  <Check className="w-6 h-6" style={{ color: "#4ADE80" }} />
                </div>
                <h1 style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontWeight: 600, fontSize: "22px", color: "#F2EEE9", margin: "0 0 10px" }}>
                  Check your email
                </h1>
                <p style={{ color: "#8A847C", fontSize: "13.5px", lineHeight: 1.6, margin: "0 0 20px" }}>
                  If an account exists for <span style={{ color: "#B6AFA6" }}>{email.trim()}</span>, a reset link is
                  on its way. It expires in 30 minutes.
                </p>
                <button onClick={handleSubmit} disabled={submitting} data-testid="resend-link-btn"
                  style={{ display: "block", width: "100%", marginBottom: "14px", background: "#0A0A0A", border: "1px solid rgba(255,255,255,0.09)", borderRadius: "12px", padding: "11px", color: "#B6AFA6", cursor: "pointer", fontSize: "13.5px", fontFamily: "'Manrope', sans-serif", opacity: submitting ? 0.6 : 1 }}>
                  {submitting ? "Sending…" : "Didn't get it? Send again"}
                </button>
                <button onClick={() => navigate("/login")} data-testid="back-to-login-btn"
                  style={{ display: "inline-flex", alignItems: "center", gap: "6px", background: "none", border: "none", color: "#DC6B5A", cursor: "pointer", fontWeight: 600, fontSize: "13.5px" }}>
                  <Mail className="w-3.5 h-3.5" /> Back to sign in
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
};

export default ForgotPasswordPage;

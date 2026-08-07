import React from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, Mail, Globe, Building2, Newspaper } from "lucide-react";
import { Browser } from "@capacitor/browser";
import { SuryaLogo } from "../App";
import BottomNav from "../components/BottomNav";

// Single source of truth for how a reader (or a Play Store reviewer) reaches a
// human. Google's News & Magazines policy requires a clearly labelled contact
// page carrying a real email or phone number, in the app AND on the website —
// these values must stay in step with chintan.news/contact.
export const CONTACT_EMAIL = "team@chintan.news";
export const CONTACT_ENTITY = "Chintan Labs";
export const CONTACT_LOCATION = "New Delhi, India";
export const CONTACT_WEB = "https://chintan.news/contact";

const openExternal = async (url) => {
  if (window.Capacitor?.isNativePlatform()) {
    try {
      await Browser.open({ url });
      return;
    } catch {
      // fall through to a normal navigation
    }
  }
  window.open(url, "_blank", "noopener,noreferrer");
};

const EYEBROW = {
  fontFamily: "'JetBrains Mono', monospace",
  fontSize: "9px",
  letterSpacing: "0.2em",
  color: "#5A544D",
  textTransform: "uppercase",
  marginBottom: "13px",
};

const CARD = {
  background: "#131211",
  border: "1px solid rgba(255,255,255,0.06)",
  borderRadius: "14px",
  padding: "16px",
};

const ContactPage = () => {
  const navigate = useNavigate();

  return (
    <div style={{ minHeight: "100vh", background: "#0A0A0A" }} data-testid="contact-page">
      <header
        className="sticky z-40 px-4"
        style={{
          top: 0, paddingTop: "var(--sat)", paddingBottom: "12px",
          background: "rgba(10,10,10,0.72)", backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)",
        }}
      >
        <div style={{ maxWidth: "640px", margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <button onClick={() => navigate(-1)} style={{ padding: "8px", background: "none", border: "none", cursor: "pointer" }} data-testid="back-btn">
            <ArrowLeft className="w-5 h-5" style={{ color: "#9A938A" }} />
          </button>
          <span style={{ color: "#82828A", fontFamily: "'JetBrains Mono', monospace", fontSize: "11px", letterSpacing: "0.12em", textTransform: "uppercase" }}>Contact</span>
          <div style={{ width: "36px" }} />
        </div>
      </header>

      <main style={{ padding: "12px 22px 96px", maxWidth: "640px", margin: "0 auto" }}>
        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} style={{ textAlign: "center", paddingTop: "14px", marginBottom: "30px" }}>
          <SuryaLogo className="w-12 h-12 mx-auto" />
          <h1 style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontWeight: 600, fontSize: "28px", color: "#F2EEE9", margin: "16px 0 8px" }}>
            Contact us
          </h1>
          <p style={{ color: "#8A847C", fontSize: "14px", lineHeight: 1.55, margin: 0 }}>
            Questions, corrections, takedown requests, or anything else — reach a real person here.
          </p>
        </motion.div>

        {/* Email — the primary contact method */}
        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 }} style={{ marginBottom: "24px" }}>
          <div style={EYEBROW}>Email us</div>
          <a
            href={`mailto:${CONTACT_EMAIL}`}
            data-testid="contact-email"
            style={{
              ...CARD,
              display: "flex", alignItems: "center", gap: "13px", textDecoration: "none",
              border: "1px solid rgba(220,38,38,0.28)",
              background: "linear-gradient(135deg, rgba(220,38,38,0.09), #131211 62%)",
            }}
          >
            <Mail className="w-5 h-5" style={{ color: "#DC6B5A", flexShrink: 0 }} />
            <div style={{ minWidth: 0 }}>
              <div style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontSize: "17px", color: "#F2EEE9", wordBreak: "break-all" }}>
                {CONTACT_EMAIL}
              </div>
              <div style={{ color: "#8A847C", fontSize: "12px", marginTop: "3px" }}>We usually reply within 2 working days.</div>
            </div>
          </a>
        </motion.div>

        {/* Who operates Chintan */}
        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.14 }} style={{ marginBottom: "24px" }}>
          <div style={EYEBROW}>Who runs Chintan</div>
          <div style={{ ...CARD, display: "flex", alignItems: "flex-start", gap: "13px" }}>
            <Building2 className="w-5 h-5" style={{ color: "#9A938A", flexShrink: 0, marginTop: "2px" }} />
            <p style={{ margin: 0, color: "#B6AFA6", fontSize: "14px", lineHeight: 1.6 }}>
              Chintan is built and operated by <span style={{ color: "#F2EEE9", fontWeight: 500 }}>{CONTACT_ENTITY}</span>, based in {CONTACT_LOCATION}.
            </p>
          </div>
        </motion.div>

        {/* Aggregator disclosure — states plainly where the journalism comes from */}
        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} style={{ marginBottom: "24px" }}>
          <div style={EYEBROW}>Where our news comes from</div>
          <div style={{ ...CARD, display: "flex", alignItems: "flex-start", gap: "13px" }}>
            <Newspaper className="w-5 h-5" style={{ color: "#9A938A", flexShrink: 0, marginTop: "2px" }} />
            <p style={{ margin: 0, color: "#B6AFA6", fontSize: "14px", lineHeight: 1.6 }}>
              Chintan is a news aggregator. We don't employ reporters and we don't republish full articles.
              Every story credits the publisher who reported it, and links straight back to their original
              article so you can read it in full at the source.
            </p>
          </div>
        </motion.div>

        {/* Website */}
        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.26 }}>
          <div style={EYEBROW}>On the web</div>
          <button
            onClick={() => openExternal(CONTACT_WEB)}
            data-testid="contact-website"
            style={{ ...CARD, display: "flex", alignItems: "center", gap: "13px", width: "100%", cursor: "pointer", textAlign: "left" }}
          >
            <Globe className="w-5 h-5" style={{ color: "#9A938A", flexShrink: 0 }} />
            <div style={{ color: "#ECE7E1", fontSize: "14px" }}>chintan.news/contact</div>
          </button>
        </motion.div>

        <div style={{ textAlign: "center", marginTop: "40px" }}>
          <p style={{ color: "#4A453F", fontSize: "11px" }}>Chintan · Don't just consume. Contemplate.</p>
        </div>
      </main>

      <BottomNav />
    </div>
  );
};

export default ContactPage;

import React from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, Building2, Newspaper, Mail } from "lucide-react";
import { SuryaLogo } from "../App";
import { CONTACT_ENTITY, CONTACT_LOCATION } from "./ContactPage";
import BottomNav from "../components/BottomNav";

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

// Separate from ContactPage (though it shares the same entity/aggregator
// wording) so a Play Store reviewer scanning specifically for an "About Us"
// section, distinct from a contact form, finds one under that exact name.
const AboutPage = () => {
  const navigate = useNavigate();

  return (
    <div style={{ minHeight: "100vh", background: "#0A0A0A" }} data-testid="about-page">
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
          <span style={{ color: "#82828A", fontFamily: "'JetBrains Mono', monospace", fontSize: "11px", letterSpacing: "0.12em", textTransform: "uppercase" }}>About</span>
          <div style={{ width: "36px" }} />
        </div>
      </header>

      <main style={{ padding: "12px 22px 96px", maxWidth: "640px", margin: "0 auto" }}>
        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} style={{ textAlign: "center", paddingTop: "14px", marginBottom: "30px" }}>
          <SuryaLogo className="w-12 h-12 mx-auto" />
          <h1 style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontWeight: 600, fontSize: "28px", color: "#F2EEE9", margin: "16px 0 8px" }}>
            About Chintan
          </h1>
          <p style={{ color: "#8A847C", fontSize: "14px", lineHeight: 1.55, margin: 0 }}>
            Don't just consume. Contemplate.
          </p>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 }} style={{ marginBottom: "24px" }}>
          <div style={EYEBROW}>Who runs Chintan</div>
          <div style={{ ...CARD, display: "flex", alignItems: "flex-start", gap: "13px" }}>
            <Building2 className="w-5 h-5" style={{ color: "#9A938A", flexShrink: 0, marginTop: "2px" }} />
            <p style={{ margin: 0, color: "#B6AFA6", fontSize: "14px", lineHeight: 1.6 }}>
              Chintan is built and operated by <span style={{ color: "#F2EEE9", fontWeight: 500 }}>{CONTACT_ENTITY}</span>, based in {CONTACT_LOCATION}.
            </p>
          </div>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.14 }} style={{ marginBottom: "24px" }}>
          <div style={EYEBROW}>What Chintan is</div>
          <div style={{ ...CARD, display: "flex", alignItems: "flex-start", gap: "13px" }}>
            <Newspaper className="w-5 h-5" style={{ color: "#9A938A", flexShrink: 0, marginTop: "2px" }} />
            <p style={{ margin: 0, color: "#B6AFA6", fontSize: "14px", lineHeight: 1.6 }}>
              Chintan is a news aggregator. We don't employ reporters and we don't publish original
              journalism. Every story credits the publisher who reported it and links straight to
              their original article, so you can always read it in full at the source.
            </p>
          </div>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
          <div style={EYEBROW}>Get in touch</div>
          <button
            onClick={() => navigate("/contact")}
            data-testid="about-contact-link"
            style={{ ...CARD, display: "flex", alignItems: "center", gap: "13px", width: "100%", cursor: "pointer", textAlign: "left" }}
          >
            <Mail className="w-5 h-5" style={{ color: "#9A938A", flexShrink: 0 }} />
            <div style={{ color: "#ECE7E1", fontSize: "14px" }}>Contact us</div>
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

export default AboutPage;

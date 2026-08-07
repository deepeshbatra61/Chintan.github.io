import React from "react";
import { useNavigate } from "react-router-dom";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./ui/dialog";

// Shown to guests either on-demand (a write action they tried needs an
// account) or once, proactively, as a nudge toward personalization. `reason`
// swaps the body copy between the two without needing two components.
const SignInPrompt = ({ open, onOpenChange, reason = "personalize" }) => {
  const navigate = useNavigate();

  const copy = reason === "action"
    ? "Sign in to save this, react, or join the conversation."
    : "Sign in for a feed shaped around what you actually read — not just what's new.";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="sign-in-prompt">
        <DialogHeader>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '9px', letterSpacing: '0.2em', color: '#6E6862', textTransform: 'uppercase', marginBottom: '8px' }}>
            Browsing as guest
          </div>
          <DialogTitle>A more personalized Chintan</DialogTitle>
        </DialogHeader>
        <p style={{ color: '#8A847C', fontSize: '13.5px', lineHeight: 1.55, margin: '0 0 4px' }}>
          {copy}
        </p>
        <button
          onClick={() => { onOpenChange(false); navigate("/login"); }}
          data-testid="sign-in-prompt-cta"
          style={{
            width: '100%', background: 'linear-gradient(180deg, #DC2626, #B91C1C)', color: '#fff',
            border: 'none', borderRadius: '12px', padding: '13px', fontSize: '15px', fontWeight: 600,
            cursor: 'pointer', fontFamily: "'Manrope', sans-serif", marginTop: '6px',
          }}
        >
          Sign in
        </button>
        <button
          onClick={() => onOpenChange(false)}
          data-testid="sign-in-prompt-dismiss"
          style={{
            width: '100%', background: 'none', border: 'none', color: '#6E6862', cursor: 'pointer',
            fontSize: '13px', fontFamily: "'Manrope', sans-serif", padding: '10px', marginTop: '2px',
          }}
        >
          Not now
        </button>
      </DialogContent>
    </Dialog>
  );
};

export default SignInPrompt;

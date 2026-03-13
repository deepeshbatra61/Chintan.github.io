import React, { useState, useEffect } from "react";

const WelcomeSplash = ({ onComplete }) => {
  const [fadeOut, setFadeOut] = useState(false);
  const [taglineVisible, setTaglineVisible] = useState(false);

  useEffect(() => {
    const t1 = setTimeout(() => setTaglineVisible(true), 500);
    const t2 = setTimeout(() => setFadeOut(true), 2200);
    const t3 = setTimeout(() => onComplete(), 2500);
    return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3); };
  }, [onComplete]);

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      background: '#000000',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 9999,
      opacity: fadeOut ? 0 : 1,
      transition: 'opacity 0.3s ease',
    }}>
      <img
        src="/logo192.png"
        alt="Chintan"
        style={{ width: '80px', height: '80px', marginBottom: '24px' }}
      />
      <h1 style={{
        fontFamily: "'Playfair Display', Georgia, serif",
        fontSize: '2rem',
        fontWeight: '700',
        color: '#ffffff',
        marginBottom: '12px',
        textAlign: 'center',
      }}>
        Welcome to Chintan
      </h1>
      <p style={{
        fontSize: '1rem',
        color: '#888888',
        opacity: taglineVisible ? 1 : 0,
        transition: 'opacity 0.8s ease',
        textAlign: 'center',
      }}>
        Let's contemplate together
      </p>
    </div>
  );
};

export default WelcomeSplash;

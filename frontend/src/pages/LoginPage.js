import React from "react";
import { motion } from "framer-motion";
import { SuryaLogo } from "../App";

const LoginPage = () => {
  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
  const handleGoogleLogin = () => {
    const redirectUrl = window.location.origin + '/feed';
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="min-h-screen bg-[#0A0A0A] flex flex-col items-center justify-center relative overflow-hidden">
      {/* Background glow effect */}
      <div className="absolute inset-0 surya-glow opacity-30" />
      
      {/* Animated background rays */}
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="w-[600px] h-[600px] animate-spin-slow opacity-10">
          <SuryaLogo className="w-full h-full" />
        </div>
      </div>

      {/* Content */}
      <motion.div 
        className="relative z-10 text-center px-6 max-w-md"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
      >
        {/* Logo */}
        <motion.div
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ delay: 0.2, duration: 0.5 }}
        >
          <SuryaLogo className="w-24 h-24 mx-auto mb-8" />
        </motion.div>

        {/* Brand */}
        <motion.h1 
          className="font-serif text-5xl md:text-6xl font-bold text-white mb-4 tracking-tight"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
        >
          Chintan
        </motion.h1>

        {/* Motto */}
        <motion.p 
          className="text-xl text-gray-400 mb-2"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4 }}
        >
          Don't just consume.
        </motion.p>
        <motion.p 
          className="text-2xl text-red-500 font-semibold mb-12"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.5 }}
        >
          Contemplate.
        </motion.p>

        {/* Vision */}
        <motion.p 
          className="text-gray-500 text-sm mb-12 max-w-sm mx-auto leading-relaxed"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.6 }}
        >
          Transform passive news scrolling into active contemplation. 
          Become an informed, critical thinker.
        </motion.p>

        {/* Login Button */}
        <motion.button
          onClick={handleGoogleLogin}
          className="w-full max-w-xs mx-auto flex items-center justify-center gap-3 bg-white text-gray-900 py-4 px-6 rounded-full font-semibold text-lg hover:bg-gray-100 transition-colors"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.7 }}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          data-testid="google-login-btn"
        >
          <svg className="w-6 h-6" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
          </svg>
          Continue with Google
        </motion.button>

        {/* Core Values */}
        <motion.div 
          className="mt-16 flex flex-wrap justify-center gap-6 text-xs text-gray-600"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.9 }}
        >
          <span className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 bg-red-600 rounded-full" />
            Truth over bias
          </span>
          <span className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 bg-red-600 rounded-full" />
            Depth over speed
          </span>
          <span className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 bg-red-600 rounded-full" />
            Reflection over reaction
          </span>
        </motion.div>
      </motion.div>
    </div>
  );
};

export default LoginPage;

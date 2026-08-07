import { Capacitor } from '@capacitor/core';
import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";

// Safe-area insets are NOT read here. They come from env(safe-area-inset-*) in
// index.css, which the platform recomputes on rotation, fold, nav-mode change
// and split-screen. This file previously called SafeArea.getSafeAreaInsets(),
// a method that does not exist in @capacitor-community/safe-area v8 (its API
// is setSystemBarsStyle / showSystemBars / hideSystemBars). The promise
// rejected with no .catch(), so --sat/--sab/--sal/--sar were never assigned and
// every screen silently used hardcoded CSS fallbacks instead.
//
// All that remains is a platform marker, so the stylesheet can give web a
// little top spacing where a phone has a status bar. It sets no inset values.
if (Capacitor.isNativePlatform()) {
  document.documentElement.classList.add('native-platform');
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

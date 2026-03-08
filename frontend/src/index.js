import { SafeArea } from '@capacitor-community/safe-area';
import { Capacitor } from '@capacitor/core';
import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";

if (Capacitor.isNativePlatform()) {
  SafeArea.getSafeAreaInsets().then(({ insets }) => {
    document.documentElement.style.setProperty('--sat', insets.top + 'px');
    document.documentElement.style.setProperty('--sar', insets.right + 'px');
    document.documentElement.style.setProperty('--sab', insets.bottom + 'px');
    document.documentElement.style.setProperty('--sal', insets.left + 'px');
  });
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

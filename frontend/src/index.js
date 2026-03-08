import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";
import { StatusBar, Style } from '@capacitor/status-bar';
import { Capacitor } from '@capacitor/core';

const applyStatusBarPadding = async () => {
  if (Capacitor.isNativePlatform()) {
    try {
      await StatusBar.setOverlaysWebView({ overlay: true });
      await StatusBar.setStyle({ style: Style.Dark });
      // Get actual status bar height
      const info = await StatusBar.getInfo();
      console.log('StatusBar info:', JSON.stringify(info));
      // Apply padding via JS directly to root element
      const root = document.getElementById('root');
      if (root) {
        root.style.paddingTop = '48px'; // temporary hardcode to test
      }
    } catch (e) {
      console.error('StatusBar error:', e);
    }
  }
};

applyStatusBarPadding();

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

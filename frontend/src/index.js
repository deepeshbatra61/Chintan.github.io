import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";
import { StatusBar } from '@capacitor/status-bar';
import { Capacitor } from '@capacitor/core';

const applyStatusBarPadding = async () => {
  if (Capacitor.isNativePlatform()) {
    try {
      const info = await StatusBar.getInfo();
      // statusBarHeight is in pixels, convert to dp for CSS
      const pixelRatio = window.devicePixelRatio || 3;
      const heightInDp = (info.statusBarHeight || 48) / pixelRatio;
      const finalHeight = Math.max(heightInDp, 48); // minimum 48px
      document.getElementById('root').style.paddingTop = finalHeight + 'px';
      document.documentElement.style.setProperty('--status-bar-height', finalHeight + 'px');
      console.log('StatusBar height px:', info.statusBarHeight, 'dp:', heightInDp, 'final:', finalHeight);
    } catch (e) {
      document.getElementById('root').style.paddingTop = '48px';
      document.documentElement.style.setProperty('--status-bar-height', '48px');
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

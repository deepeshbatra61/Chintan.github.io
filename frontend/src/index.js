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
      const height = info.statusBarHeight || 48;
      document.getElementById('root').style.paddingTop = height + 'px';
    } catch (e) {
      document.getElementById('root').style.paddingTop = '48px';
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

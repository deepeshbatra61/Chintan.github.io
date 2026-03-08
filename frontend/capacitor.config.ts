import { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.chintan.app',
  appName: 'Chintan',
  webDir: 'build',
  server: {
    androidScheme: 'https'
  },
  plugins: {
    StatusBar: {
      // Do NOT overlay the WebView — content starts below the status bar automatically.
      // This means env(safe-area-inset-top) will be 0 and no manual padding is needed.
      overlaysWebView: false,
      backgroundColor: '#0a0a1a',  // match app dark background
      style: 'LIGHT',              // light icons on dark background
    }
  }
};

export default config;

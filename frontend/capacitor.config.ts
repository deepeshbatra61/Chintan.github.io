import { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.chintan.app',
  appName: 'Chintan',
  webDir: 'build',
  server: {
    androidScheme: 'https'
  },
  android: {
    adjustMarginsForEdgeToEdge: 'auto'
  },
  plugins: {
    StatusBar: {
      overlaysWebView: true
    }
  }
};

export default config;

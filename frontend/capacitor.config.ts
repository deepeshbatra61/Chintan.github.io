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
      overlaysWebView: false,
      backgroundColor: '#000000',
    }
  }
};

export default config;

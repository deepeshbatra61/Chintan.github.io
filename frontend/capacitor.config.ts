import { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.chintan.app',
  appName: 'Chintan',
  webDir: 'build',
  server: {
    androidScheme: 'https'
  }
};

export default config;

import { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.chintan.app',
  appName: 'Chintan',
  webDir: 'build',
  server: {
    androidScheme: 'https'
  },
  android: {
    // 'disable', not 'auto', per @capacitor-community/safe-area's README:
    // "It's advised to either omit this value or set it to `disable` to
    // prevent interference. This plugin already does a similar thing when it
    // detects a broken webview." Leaving it on 'auto' means Capacitor inserts
    // its own margins while the plugin is separately padding the webview, and
    // the two fight over the same space.
    adjustMarginsForEdgeToEdge: 'disable'
  },
  plugins: {
    // Required for Capacitor v8 (this project is on @capacitor/core ^8.2.0).
    // Without it Capacitor's own inset handling stays active and competes with
    // the plugin. Its absence is a root cause of the bottom-nav overlap, not a
    // tuning detail.
    SystemBars: {
      insetsHandling: 'disable'
    }
  }
};

export default config;

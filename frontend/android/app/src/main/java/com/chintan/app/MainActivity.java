package com.chintan.app;

import android.os.Bundle;
import androidx.activity.EdgeToEdge;
import androidx.core.splashscreen.SplashScreen;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        // Required by androidx.core:core-splashscreen (already a build.gradle
        // dependency) — without this call the library's Theme.SplashScreen
        // attributes never actually apply, so the OS falls back to deriving
        // its own splash from the adaptive launcher icon instead: hence the
        // near-black background and a small, non-crisp icon render.
        // Must run BEFORE super.onCreate().
        SplashScreen.installSplashScreen(this);
        super.onCreate(savedInstanceState);

        // Required by @capacitor-community/safe-area, and the piece that was
        // missing: the plugin reports and polyfills window insets, but it has
        // nothing to report unless the activity is genuinely laid out
        // edge-to-edge. Without this, env(safe-area-inset-*) stays 0 and the
        // web layer silently falls back to guessed spacing — which is how the
        // bottom nav ended up reserving 14px against a ~48dp button nav bar.
        //
        // This replaces a hand-rolled block that called setSystemUiVisibility
        // with SYSTEM_UI_FLAG_LAYOUT_STABLE | SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
        // and set only statusBarColor. Those flags are deprecated and are
        // no-ops from API 30 onward (this app targets 36), they never covered
        // the navigation bar at all, and they competed with the plugin for
        // ownership of the system bars.
        EdgeToEdge.enable(this);
    }
}

package com.chintan.app;

import android.content.res.Configuration;
import android.graphics.Color;
import android.view.View;
import android.view.Window;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsControllerCompat;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/**
 * Paints the status-bar and gesture-bar bands to match the page, per theme.
 *
 * Why this exists: on WebView < 140, @capacitor-community/safe-area pads the
 * WebView inside the edge-to-edge window, so the bands above and below it show
 * the decor view's background, not the page. Nothing set that background, so
 * it fell back to the DayNight window default: white on any phone in system
 * light mode, which is the white-bars bug. The plugin's own setSystemBarsStyle
 * only offers pure black or pure white, which never quite matches the page.
 *
 * Deliberately not using SafeArea.setSystemBarsStyle on Android as well: it
 * re-applies its black/white decor colour on every configuration change and
 * would overwrite the exact colour set here.
 */
@CapacitorPlugin(name = "ThemeBars")
public class ThemeBarsPlugin extends Plugin {

    // Last applied values, re-painted after configuration changes. Flipping
    // the phone's own dark mode re-applies the DayNight window theme, which
    // resets the decor background and icon appearance underneath us -- black
    // bars around a light page. Seen on the emulator, not theoretical.
    private Integer lastColor = null;
    private boolean lastLightContent = true;

    @PluginMethod
    public void apply(PluginCall call) {
        String background = call.getString("background", "#0A0A0A");
        boolean lightContent = Boolean.TRUE.equals(call.getBoolean("lightContent", true));

        final int color;
        try {
            color = Color.parseColor(background);
        } catch (IllegalArgumentException e) {
            call.reject("Invalid colour: " + background);
            return;
        }

        lastColor = color;
        lastLightContent = lightContent;
        getBridge().executeOnMainThread(() -> {
            paint(color, lightContent);
            JSObject ret = new JSObject();
            ret.put("background", background);
            call.resolve(ret);
        });
    }

    @Override
    protected void handleOnConfigurationChanged(Configuration newConfig) {
        super.handleOnConfigurationChanged(newConfig);
        if (lastColor == null) return;
        final int color = lastColor;
        final boolean lightContent = lastLightContent;
        // Post, so this lands after the framework has finished re-theming.
        getActivity().getWindow().getDecorView().post(() -> paint(color, lightContent));
    }

    private void paint(int color, boolean lightContent) {
        Window window = getActivity().getWindow();
        View decor = window.getDecorView();
        decor.setBackgroundColor(color);
        // The WebView's own background shows for a frame before first paint
        // and during overscroll; keep it in step with the page too.
        getBridge().getWebView().setBackgroundColor(color);

        WindowInsetsControllerCompat controller = WindowCompat.getInsetsController(window, decor);
        // "Appearance light" means DARK icons, for a light background.
        controller.setAppearanceLightStatusBars(!lightContent);
        controller.setAppearanceLightNavigationBars(!lightContent);
    }
}

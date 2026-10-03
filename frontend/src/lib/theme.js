// Appearance (1.13): one Light/Dark switch. A reader who never flipped it
// follows the phone ("system", the default); the first flip stores light or
// dark for good. 1.12 offered System / Light / Dark; stored values carry over.
//
// The preference lives in localStorage so the inline script in
// public/index.html can apply it before React's first paint (no flash of the
// wrong theme). Everything visual keys off <html data-theme="light|dark">; the
// colour tokens themselves are in index.css.
//
// A tiny external store rather than a React context: the theme has to be
// applied before React mounts, and the only UI that reads it is the
// Appearance control, so a provider would be ceremony.

import { useSyncExternalStore } from 'react';
import { Capacitor, registerPlugin } from '@capacitor/core';
import { SafeArea, SystemBarsStyle } from '@capacitor-community/safe-area';

export const THEME_KEY = 'chintan.theme';
export const THEME_PREFS = ['system', 'light', 'dark'];

// Must equal --c-bg for each theme in index.css (and the pre-render script).
const PAGE_BG = { dark: '#0A0A0A', light: '#FAF4F3' };

const ThemeBars = registerPlugin('ThemeBars');
const lightQuery = typeof window !== 'undefined' && window.matchMedia
  ? window.matchMedia('(prefers-color-scheme: light)')
  : null;

function readPref() {
  try {
    const v = localStorage.getItem(THEME_KEY);
    return THEME_PREFS.includes(v) ? v : 'system';
  } catch {
    return 'system';
  }
}

function resolve(pref) {
  if (pref === 'system') return lightQuery?.matches ? 'light' : 'dark';
  return pref;
}

let state = { pref: readPref(), resolved: resolve(readPref()) };
const listeners = new Set();

function paintSystemBars(resolved) {
  if (!Capacitor.isNativePlatform()) return;
  const dark = resolved === 'dark';
  if (Capacitor.getPlatform() === 'android') {
    // Exact page colour behind the bars; see ThemeBarsPlugin.java for why the
    // safe-area plugin's own black/white setter isn't used here.
    ThemeBars.apply({ background: PAGE_BG[resolved], lightContent: dark }).catch(() => {});
  } else {
    // iOS draws the page under the bars already; only the icon contrast needs setting.
    SafeArea.setSystemBarsStyle({ style: dark ? SystemBarsStyle.Dark : SystemBarsStyle.Light }).catch(() => {});
  }
}

function apply(resolved) {
  const root = document.documentElement;
  root.dataset.theme = resolved;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', PAGE_BG[resolved]);
  paintSystemBars(resolved);
}

function set(next) {
  state = next;
  apply(state.resolved);
  listeners.forEach((l) => l());
}

export function setThemePref(pref) {
  if (!THEME_PREFS.includes(pref)) return;
  try { localStorage.setItem(THEME_KEY, pref); } catch { /* private mode: session-only */ }
  set({ pref, resolved: resolve(pref) });
}

// Follow the OS while on "System".
lightQuery?.addEventListener?.('change', () => {
  if (state.pref === 'system') set({ ...state, resolved: resolve('system') });
});

// Called once at startup (index.js). The pre-render script has already set
// data-theme; this adds the parts it can't do: native system bars.
export function initTheme() {
  apply(state.resolved);
}

const subscribe = (l) => { listeners.add(l); return () => listeners.delete(l); };
const getSnapshot = () => state;

export function useTheme() {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

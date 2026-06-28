// Session token store.
//
// The session token used to live in localStorage, which any JavaScript running
// in the WebView (including injected/malicious code) can read. We now keep it in
// @capacitor/preferences, which on native maps to app-private storage reachable
// only through the Capacitor bridge — not readable by WebView JS or other apps.
//
// Preferences is async, but axios request interceptors need a synchronous read,
// so we mirror the token in memory (`cached`). Call loadToken() once at startup
// (before the first authenticated request) to populate the mirror; setToken()
// and clearToken() keep the mirror and the vault in sync.

import { Preferences } from "@capacitor/preferences";

const KEY = "chintan_session_token";
let cached = null;

/**
 * Load the token from the vault into the in-memory mirror. Migrates any legacy
 * token still sitting in localStorage into the vault, then scrubs localStorage
 * so the old open-shelf copy stops existing. Call once before checkAuth().
 */
export async function loadToken() {
  const { value } = await Preferences.get({ key: KEY });
  let token = value || null;

  if (!token && typeof localStorage !== "undefined") {
    const legacy = localStorage.getItem(KEY);
    if (legacy) {
      token = legacy;
      await Preferences.set({ key: KEY, value: legacy });
    }
  }
  if (typeof localStorage !== "undefined") localStorage.removeItem(KEY);

  cached = token;
  return token;
}

/** Synchronous read of the in-memory mirror (used by the axios interceptor). */
export function getCachedToken() {
  return cached;
}

/** Persist the token to the vault and update the in-memory mirror. */
export async function setToken(token) {
  cached = token || null;
  if (token) {
    await Preferences.set({ key: KEY, value: token });
  }
}

/** Remove the token from the vault, the mirror, and any legacy localStorage copy. */
export async function clearToken() {
  cached = null;
  await Preferences.remove({ key: KEY });
  if (typeof localStorage !== "undefined") localStorage.removeItem(KEY);
}

// Session token store.
//
// Holds two tokens in @capacitor/preferences (app-private native storage,
// reachable only through the Capacitor bridge — not by WebView JS or other apps):
//   - access token:  short-lived, sent on every request as Bearer
//   - refresh token: long-lived, used only to mint a new access token on 401
//
// Preferences is async, but the axios request interceptor needs a synchronous
// read, so we mirror the access token in memory (`cachedAccess`). Call loadToken()
// once at startup (before the first authenticated request) to populate the mirror.

import { Preferences } from "@capacitor/preferences";

const ACCESS_KEY = "chintan_session_token";
const REFRESH_KEY = "chintan_refresh_token";

let cachedAccess = null;
let cachedRefresh = null;

/**
 * Load both tokens from the vault into the in-memory mirrors. Migrates any
 * legacy access token still sitting in localStorage into the vault, then scrubs
 * localStorage so the old open-shelf copy stops existing. Call once before checkAuth().
 */
export async function loadToken() {
  const { value: access } = await Preferences.get({ key: ACCESS_KEY });
  const { value: refresh } = await Preferences.get({ key: REFRESH_KEY });

  let accessToken = access || null;
  if (!accessToken && typeof localStorage !== "undefined") {
    const legacy = localStorage.getItem(ACCESS_KEY);
    if (legacy) {
      accessToken = legacy;
      await Preferences.set({ key: ACCESS_KEY, value: legacy });
    }
  }
  if (typeof localStorage !== "undefined") localStorage.removeItem(ACCESS_KEY);

  cachedAccess = accessToken;
  cachedRefresh = refresh || null;
  return cachedAccess;
}

/** Synchronous read of the access token (used by the axios request interceptor). */
export function getCachedToken() {
  return cachedAccess;
}

/** Synchronous read of the refresh token (used by the 401 refresh interceptor). */
export function getRefreshToken() {
  return cachedRefresh;
}

/** Persist both tokens to the vault and update the in-memory mirrors. */
export async function setTokens(access, refresh) {
  cachedAccess = access || null;
  if (access) await Preferences.set({ key: ACCESS_KEY, value: access });
  // The backend rotates refresh tokens, so only overwrite when a new one is given.
  if (refresh) {
    cachedRefresh = refresh;
    await Preferences.set({ key: REFRESH_KEY, value: refresh });
  }
}

/** Remove both tokens from the vault, the mirrors, and any legacy localStorage copy. */
export async function clearToken() {
  cachedAccess = null;
  cachedRefresh = null;
  await Preferences.remove({ key: ACCESS_KEY });
  await Preferences.remove({ key: REFRESH_KEY });
  if (typeof localStorage !== "undefined") localStorage.removeItem(ACCESS_KEY);
}

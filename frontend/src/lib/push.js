// Push notifications (phase 1).
//
//   app start / resume ──▶ permission granted? ──▶ register() ──▶ 'registration' ──▶ POST /push/devices
//   foreground push ─────▶ Breaking? banner (PushBanner) : nothing (slot pushes are silent, R4)
//   tap ──────────────────▶ POST /push/opened ──▶ navigate(route)   e.g. /brief/morning?pin=…
//   logout ───────────────▶ DELETE /push/devices
//
// The server decides everything else (slots, caps, copy). This file only
// keeps the device's token registered and routes taps. Permission is NEVER
// requested on launch: only from the soft ask (PushAsk) or Profile.

import axios from "axios";
import { App as CapApp } from "@capacitor/app";
import { Capacitor } from "@capacitor/core";
import { Preferences } from "@capacitor/preferences";
import { PushNotifications } from "@capacitor/push-notifications";

const API = "https://chintangithubio-production.up.railway.app/api";
const TOKEN_KEY = "chintan_push_token";
const ASK_KEY = "chintan_push_ask";

export const isPushSupported = () => Capacitor.isNativePlatform();
const platform = () => Capacitor.getPlatform(); // "android" | "ios"

let cachedToken = null;
let listenersReady = false;
let lastRegistration = null; // server response: { device_id, first_brief? }
const waiters = [];
const bannerSubs = new Set();

function timeZone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  } catch {
    return "";
  }
}

async function storedToken() {
  if (cachedToken) return cachedToken;
  const { value } = await Preferences.get({ key: TOKEN_KEY });
  cachedToken = value || null;
  return cachedToken;
}

export async function getPushToken() {
  return isPushSupported() ? storedToken() : null;
}

let appVersion = null;
async function version() {
  if (appVersion === null) {
    try {
      appVersion = (await CapApp.getInfo()).version || "";
    } catch {
      appVersion = "";
    }
  }
  return appVersion;
}

async function sendRegistration(token) {
  try {
    const r = await axios.post(`${API}/push/devices`, {
      token, platform: platform(), tz: timeZone(), app_version: await version(),
    });
    lastRegistration = r.data;
  } catch (e) {
    lastRegistration = null;
  }
  while (waiters.length) waiters.shift()(lastRegistration);
}

/** "granted" | "denied" | "prompt" | "unsupported" */
export async function permissionState() {
  if (!isPushSupported()) return "unsupported";
  try {
    const { receive } = await PushNotifications.checkPermissions();
    return receive === "granted" ? "granted" : receive === "denied" ? "denied" : "prompt";
  } catch {
    return "unsupported";
  }
}

async function ensureChannels() {
  if (platform() !== "android") return;
  try {
    await PushNotifications.createChannel({
      id: "daily", name: "Daily briefs", description: "Sunrise, High Noon and Dusk briefs",
      importance: 3, visibility: 1, lights: false, vibration: false,
    });
    await PushNotifications.createChannel({
      id: "breaking", name: "Breaking", description: "Rare. At most once a day.",
      importance: 4, visibility: 1, lights: true, lightColor: "#DC2626", vibration: true,
    });
  } catch {
    /* older Android: channels don't exist */
  }
}

/**
 * Ask the OS (only call from a user action: the soft ask or Profile) and
 * register. Resolves to { permission, registration } where registration is
 * the server's reply (includes first_brief for signed-in readers) or null.
 */
export async function enablePush() {
  if (!isPushSupported()) return { permission: "unsupported", registration: null };
  let { receive } = await PushNotifications.checkPermissions();
  if (receive === "prompt" || receive === "prompt-with-rationale") {
    ({ receive } = await PushNotifications.requestPermissions());
  }
  if (receive !== "granted") return { permission: "denied", registration: null };
  await ensureChannels();
  const registration = await new Promise((resolve) => {
    waiters.push(resolve);
    PushNotifications.register().catch(() => resolve(null));
    setTimeout(() => resolve(lastRegistration), 8000);
  });
  await markAsk({ optedIn: true });
  return { permission: "granted", registration };
}

/** Re-register silently (resume, sign-in). No prompt, ever. */
export async function refreshRegistration() {
  if (!isPushSupported()) return;
  if ((await permissionState()) !== "granted") return;
  try {
    await PushNotifications.register();
  } catch {
    /* no Firebase config in this build */
  }
}

/** Logout: forget this device on the server. */
export async function unregisterDevice() {
  const token = await getPushToken();
  if (!token) return;
  try {
    await axios.delete(`${API}/push/devices`, { data: { token } });
  } catch {
    /* best effort */
  }
}

export async function getPrefs() {
  const token = await getPushToken();
  const r = await axios.get(`${API}/push/prefs`, { params: token ? { token } : {} });
  return r.data; // { prefs, guest }
}

export async function setPrefs(patch) {
  const token = await getPushToken();
  const r = await axios.put(`${API}/push/prefs`, { prefs: patch, token });
  return r.data;
}

// ── soft-ask bookkeeping (design review DR-6A: first finished article, one
//    re-ask >= 7 days after "Not now", then Profile only) ─────────────────────
export async function getAsk() {
  const { value } = await Preferences.get({ key: ASK_KEY });
  try {
    return { count: 0, lastAt: 0, optedIn: false, afterLogin: false, ...(value ? JSON.parse(value) : {}) };
  } catch {
    return { count: 0, lastAt: 0, optedIn: false, afterLogin: false };
  }
}

export async function markAsk(patch) {
  const next = { ...(await getAsk()), ...patch };
  await Preferences.set({ key: ASK_KEY, value: JSON.stringify(next) });
  return next;
}

const WEEK_MS = 7 * 24 * 3600 * 1000;

/** null (don't ask) | "first" | "again" */
export async function askStage(now = Date.now()) {
  if (!isPushSupported()) return null;
  const perm = await permissionState();
  if (perm === "denied" || perm === "unsupported") return null;
  const a = await getAsk();
  if (a.optedIn) return null;
  if (a.count === 0) return "first";
  if (a.count === 1 && now - a.lastAt >= WEEK_MS) return "again";
  return null;
}

// ── foreground Breaking banner ──────────────────────────────────────────────
export function onBreakingBanner(fn) {
  bannerSubs.add(fn);
  return () => bannerSubs.delete(fn);
}

async function reportOpened(pushId) {
  if (!pushId || pushId === "test") return;
  try {
    await axios.post(`${API}/push/opened`, { push_id: pushId });
  } catch {
    /* best effort */
  }
}

/**
 * Install listeners once. `navigate` routes taps; `onResume` hooks app resume.
 */
export async function initPush({ navigate, addResumeListener }) {
  if (!isPushSupported() || listenersReady) return;
  listenersReady = true;

  await PushNotifications.addListener("registration", async ({ value }) => {
    cachedToken = value;
    await Preferences.set({ key: TOKEN_KEY, value });
    await sendRegistration(value);
  });
  await PushNotifications.addListener("registrationError", () => {
    while (waiters.length) waiters.shift()(null);
  });
  await PushNotifications.addListener("pushNotificationReceived", (n) => {
    const data = n?.data || {};
    if (data.kind === "breaking") {
      bannerSubs.forEach((fn) => fn({ title: n.title, body: n.body, route: data.route, pushId: data.push_id }));
    }
    // Slot pushes in the foreground are silent; the app is already open.
  });
  await PushNotifications.addListener("pushNotificationActionPerformed", ({ notification }) => {
    const data = notification?.data || {};
    reportOpened(data.push_id);
    if (typeof data.route === "string" && data.route.startsWith("/")) navigate(data.route);
  });

  if (addResumeListener) addResumeListener(() => refreshRegistration());
  await ensureChannels();
  await refreshRegistration();
}

export { reportOpened };

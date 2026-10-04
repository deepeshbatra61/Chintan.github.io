// The app's feature version, sent on every API call as X-Chintan-Client so the
// server can keep answering older installs the way they were built (News v2:
// 1.12 keeps the 7 legacy categories and interest names; 1.13 gets taxonomy
// v2, States, Follow). Bump with versionName in android/app/build.gradle and
// the iOS marketing version.
export const APP_VERSION = "1.14.2";
export const CLIENT_HEADER = "X-Chintan-Client";

// Module-level cache for FeedPage: survives the component's unmount/remount
// (React Router tears FeedPage down on every navigation to an article and
// rebuilds it from scratch on the way back), but resets on a real app
// reload/relaunch or logout. Lives in its own module (not inside FeedPage.js)
// so App.js can clear it on logout without a circular import between the two.
let feedCache = null; // { articles, developingStories, notifications, unreadCount, activeCategory, page, hasMore }

export function getFeedCache() {
  return feedCache;
}

export function setFeedCache(patch) {
  feedCache = { ...(feedCache || {}), ...patch };
}

export function clearFeedCache() {
  feedCache = null;
}

// Tracks the newest article_id the user has actually loaded into the feed, so
// BottomNav can poll the backend independently and light up a dot the moment
// a newer top article shows up -- without needing FeedPage to be mounted.
let latestSeenArticleId = null;
let newArticlesAvailable = false;

export function getLatestSeenArticleId() {
  return latestSeenArticleId;
}

export function setLatestSeenArticleId(id) {
  latestSeenArticleId = id;
}

export function getNewArticlesAvailable() {
  return newArticlesAvailable;
}

export function setNewArticlesAvailable(value) {
  newArticlesAvailable = value;
}

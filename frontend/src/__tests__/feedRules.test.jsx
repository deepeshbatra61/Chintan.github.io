/* OWNER RULES for the feed (2026-10-04). If one of these fails, the change
 * that broke it is wrong, not the test:
 *   1. Pull-to-refresh reshuffles: each refresh asks the server with a NEW seed.
 *   2. Back from an article = the same spot in the list, never the top. */
import React from "react";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import "@testing-library/jest-dom";
import { MemoryRouter } from "react-router-dom";
import axios from "axios";
import FeedPage from "../pages/FeedPage";
import { setFeedCache, clearFeedCache } from "../lib/feedCache";

jest.mock("axios", () => {
  const api = { get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() };
  return { __esModule: true, default: api, ...api };
});
jest.mock("../App", () => ({
  useAuth: () => ({ user: null, isGuest: false, logout: jest.fn(), checkAuth: jest.fn() }),
  SuryaLogo: () => null,
}));
jest.mock("../components/BottomNav", () => () => null);
jest.mock("../components/SidebarFollowing", () => () => null);
jest.mock("@capacitor/haptics", () => ({ Haptics: { impact: jest.fn() }, ImpactStyle: { Light: "LIGHT" } }));
jest.mock("@capacitor/share", () => ({ Share: { share: jest.fn() } }));
jest.mock("@capacitor/browser", () => ({ Browser: { open: jest.fn() } }));
jest.mock("sonner", () => ({ toast: Object.assign(jest.fn(), { error: jest.fn(), success: jest.fn(), info: jest.fn() }) }));

const story = (i) => ({ article_id: `a${i}`, title: `Story ${i}`, description: "", category: "Politics",
  published_at: new Date().toISOString(), image_url: "" });
const page = Array.from({ length: 20 }, (_, i) => story(i));

beforeAll(() => {
  global.IntersectionObserver = class { observe() {} disconnect() {} };
  window.HTMLElement.prototype.scrollTo = function scrollTo(opts) { this.scrollTop = opts?.top ?? 0; };
});
beforeEach(() => {
  clearFeedCache();
  axios.get.mockReset();
  axios.get.mockImplementation((url) => {
    if (url.includes("/articles?")) return Promise.resolve({ data: page });
    if (url.includes("/bureau/status")) return Promise.resolve({ data: { enabled: false } });
    return Promise.resolve({ data: [] });
  });
});

const seedsSent = () => axios.get.mock.calls.map(([u]) => u).filter((u) => u.includes("/articles?"))
  .map((u) => new URL(u).searchParams.get("seed"));

test("rule 1: pull-to-refresh asks for a new order (new seed); paging keeps it", async () => {
  render(<MemoryRouter><FeedPage /></MemoryRouter>);
  await screen.findByText("Story 0");
  const main = document.querySelector("main");
  main.scrollTop = 0;
  fireEvent.touchStart(main, { touches: [{ clientY: 100 }] });
  fireEvent.touchMove(main, { touches: [{ clientY: 400 }] });
  fireEvent.touchEnd(main);
  await waitFor(() => expect(seedsSent().length).toBe(2));
  const [first, afterPull] = seedsSent();
  expect(first).toBeTruthy();
  expect(afterPull).toBeTruthy();
  expect(afterPull).not.toBe(first);
  // The Feed tab (tap while on the feed) refreshes the same way, once the
  // pull's refresh has finished (a refresh in flight ignores another).
  await waitFor(() => expect(screen.queryByTestId("pull-to-refresh-indicator")).toBeNull());
  act(() => { window.dispatchEvent(new Event("chintan:feed-refresh")); });
  await waitFor(() => expect(seedsSent().length).toBe(3));
  expect(seedsSent()[2]).not.toBe(afterPull);
});

test("rule 2: coming back to the feed restores the reader's place", async () => {
  setFeedCache({ articles: page, page: 1, hasMore: true, activeCategory: null, scrollTop: 1460,
    developingStories: [], notifications: [], unreadCount: 0, seed: 7 });
  render(<MemoryRouter><FeedPage /></MemoryRouter>);
  expect(screen.getByText("Story 0")).toBeInTheDocument();
  expect(document.querySelector("main").scrollTop).toBe(1460);
  // ...and it did not refetch (no reshuffle behind the reader's back).
  expect(seedsSent()).toEqual([]);
});

test("rule 2: scrolling is remembered for the next return", async () => {
  const { unmount } = render(<MemoryRouter><FeedPage /></MemoryRouter>);
  await screen.findByText("Story 0");
  const main = document.querySelector("main");
  main.scrollTop = 900;
  fireEvent.scroll(main);
  unmount();
  render(<MemoryRouter><FeedPage /></MemoryRouter>);
  expect(document.querySelector("main").scrollTop).toBe(900);
});

/* App 1.13 (News v2) component tests: every state from the design review's
 * interaction table, plus "old server sends none of the new fields". */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { MemoryRouter } from "react-router-dom";
import axios from "axios";

import { CoverageStrip, mixSentence } from "../components/Coverage";
import { SubPills } from "../components/SubFilters";
import FollowBar from "../components/FollowBar";
import AppearanceControl from "../components/AppearanceControl";
import { sinceLooked } from "../lib/time";
import { parseFilter, filterKey, filterParams, homeStateOf, STATES, SUBCATEGORIES, TOP_CHIPS } from "../lib/taxonomy";

jest.mock("axios", () => {
  const api = { get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() };
  return { __esModule: true, default: api, ...api };
});
jest.mock("@capacitor/share", () => ({ Share: { share: jest.fn() } }));
jest.mock("@capacitor/core", () => ({
  Capacitor: { isNativePlatform: () => false, getPlatform: () => "web" },
  registerPlugin: () => ({ apply: () => Promise.resolve() }),
}));
jest.mock("@capacitor-community/safe-area", () => ({ SafeArea: {}, SystemBarsStyle: {} }));
jest.mock("../lib/push", () => ({
  enablePush: jest.fn(() => Promise.resolve({ permission: "granted" })),
  permissionState: jest.fn(() => Promise.resolve("unsupported")),
  getAsk: jest.fn(() => Promise.resolve({})),
}));
jest.mock("sonner", () => ({ toast: Object.assign(jest.fn(), { error: jest.fn(), success: jest.fn() }) }));

const { toast } = require("sonner");

// ── coverage strip ─────────────────────────────────────────────────────────
describe("CoverageStrip", () => {
  const base = { article_id: "a1", source: "The Hindu" };

  test("old server / events not live: today's footer, no strip", () => {
    render(<CoverageStrip article={base} onOpen={jest.fn()} />);
    expect(screen.getByText("The Hindu")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  test("one outlet: says so, no circles or bar", () => {
    render(<CoverageStrip article={{ ...base, outlets_count: 1, outlet_strip: [{ i: "TH", g: "national", n: "The Hindu" }] }} onOpen={jest.fn()} />);
    expect(screen.getByText("The Hindu · 1 outlet")).toBeInTheDocument();
  });

  test("event: initials, count, label for screen readers; tap opens the sheet without opening the article", () => {
    const onOpen = jest.fn();
    const parentClick = jest.fn();
    const article = { ...base, outlets_count: 6, coverage_mix: { national: 3, regional: 2, international: 1 },
      outlet_strip: [{ i: "TH", g: "national", n: "The Hindu" }, { i: "TR", g: "regional", n: "The Tribune" }, { i: "AJ", g: "international", n: "Al Jazeera" }] };
    render(<div onClick={parentClick}><CoverageStrip article={article} onOpen={onOpen} /></div>);
    const btn = screen.getByRole("button", { name: "6 outlets: 3 national, 2 regional, 1 international. Show coverage" });
    expect(screen.getByText("The Hindu +5")).toBeInTheDocument();
    expect(screen.getByText("TR")).toBeInTheDocument();
    fireEvent.click(btn);
    expect(onOpen).toHaveBeenCalledWith(article);
    expect(parentClick).not.toHaveBeenCalled();
  });

  test("mix sentence lists groups in a fixed order and skips empty ones", () => {
    expect(mixSentence(4, { wire: 1, national: 3 })).toBe("4 outlets: 3 national, 1 wire");
    expect(mixSentence(2, null)).toBe("2 outlets");
  });
});

// ── sub-pills & States ─────────────────────────────────────────────────────
describe("SubPills", () => {
  beforeEach(() => { axios.get.mockResolvedValue({ data: { states: [{ state: "Kerala", count: 9 }, { state: "Punjab", count: 4 }] } }); });

  test("All shows no sub row", () => {
    const { container } = render(<SubPills filter={null} onChange={jest.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  test("a category shows All + its sub-categories, with the active one pressed", () => {
    const onChange = jest.fn();
    render(<SubPills filter="Sports/Hockey" onChange={onChange} />);
    expect(screen.getByRole("list", { name: "Sports topics" })).toBeInTheDocument();
    expect(screen.getByTestId("sub-Hockey")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("sub-all")).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(screen.getByTestId("sub-Chess"));
    expect(onChange).toHaveBeenCalledWith("Sports/Chess");
    fireEvent.click(screen.getByTestId("sub-all"));
    expect(onChange).toHaveBeenCalledWith("Sports");
  });

  test("States: your state first, then trending, then More states (the only way to change)", async () => {
    const onPick = jest.fn();
    render(<SubPills filter="States/Maharashtra" onChange={jest.fn()} homeState="Maharashtra" onPickState={onPick} />);
    expect(await screen.findByTestId("state-Kerala")).toBeInTheDocument();
    expect(screen.getByTestId("state-home")).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByText("· change")).toBeNull();
    fireEvent.click(screen.getByTestId("state-more"));
    expect(onPick).toHaveBeenCalledTimes(1);
  });
});

// ── follow bar ─────────────────────────────────────────────────────────────
describe("FollowBar", () => {
  const props = { storyId: "ev-1", title: "Pradhan resigns", onHeight: jest.fn() };
  beforeEach(() => { jest.clearAllMocks(); axios.get.mockResolvedValue({ data: { follows: [] } }); });

  test("guest: asks to sign in, never calls the API", () => {
    const onNeedSignIn = jest.fn();
    render(<FollowBar {...props} user={null} onNeedSignIn={onNeedSignIn} />);
    fireEvent.click(screen.getByTestId("follow-button"));
    expect(onNeedSignIn).toHaveBeenCalled();
    expect(axios.post).not.toHaveBeenCalled();
  });

  test("signed in: follow → Following (aria-pressed), unfollow → back", async () => {
    axios.post.mockResolvedValue({ data: { following: true } });
    axios.delete.mockResolvedValue({ data: { following: false } });
    render(<FollowBar {...props} user={{ user_id: "u" }} onNeedSignIn={jest.fn()} />);
    const btn = screen.getByTestId("follow-button");
    fireEvent.click(btn);
    await waitFor(() => expect(btn).toHaveAttribute("aria-pressed", "true"));
    expect(btn).toHaveTextContent("Following");
    fireEvent.click(btn);
    await waitFor(() => expect(btn).toHaveAttribute("aria-pressed", "false"));
  });

  test("already following when the page opens", async () => {
    axios.get.mockResolvedValue({ data: { follows: [{ story_id: "ev-1" }] } });
    render(<FollowBar {...props} user={{ user_id: "u" }} onNeedSignIn={jest.fn()} />);
    await waitFor(() => expect(screen.getByTestId("follow-button")).toHaveTextContent("Following"));
  });

  test("error: reverts and says so", async () => {
    axios.post.mockRejectedValue({ response: { status: 500 } });
    render(<FollowBar {...props} user={{ user_id: "u" }} onNeedSignIn={jest.fn()} />);
    fireEvent.click(screen.getByTestId("follow-button"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Couldn’t follow, try again"));
    expect(screen.getByTestId("follow-button")).toHaveAttribute("aria-pressed", "false");
  });

  test("story no longer developing (404) gets its own message", async () => {
    axios.post.mockRejectedValue({ response: { status: 404 } });
    render(<FollowBar {...props} user={{ user_id: "u" }} onNeedSignIn={jest.fn()} />);
    fireEvent.click(screen.getByTestId("follow-button"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("This story isn’t developing any more."));
  });
});

// ── since you looked ───────────────────────────────────────────────────────
describe("sinceLooked", () => {
  const arts = [{ published_at: "2026-10-03T10:00:00Z" }, { published_at: "2026-10-03T08:00:00Z" }, { published_at: "2026-10-02T20:00:00Z" }];

  test("first visit: nothing new, no divider", () => {
    expect(sinceLooked(arts, null)).toMatchObject({ newCount: 0, showDivider: false });
  });
  test("some new: divider after them", () => {
    const r = sinceLooked(arts, "2026-10-03T07:00:00Z");
    expect(r.newCount).toBe(2);
    expect(r.showDivider).toBe(true);
    expect(r.isNew(arts[0])).toBe(true);
    expect(r.isNew(arts[2])).toBe(false);
  });
  test("nothing new / everything new: no divider", () => {
    expect(sinceLooked(arts, "2026-10-03T11:00:00Z").showDivider).toBe(false);
    expect(sinceLooked(arts, "2026-10-01T00:00:00Z").showDivider).toBe(false);
  });
});

// ── appearance switch ──────────────────────────────────────────────────────
describe("AppearanceControl", () => {
  test("one switch: flips dark/light and remembers it", () => {
    localStorage.clear();
    render(<MemoryRouter><AppearanceControl /></MemoryRouter>);
    const sw = screen.getByRole("switch", { name: "Dark appearance" });
    const was = sw.getAttribute("aria-checked");
    fireEvent.click(sw);
    expect(sw.getAttribute("aria-checked")).not.toBe(was);
    expect(["light", "dark"]).toContain(localStorage.getItem("chintan.theme"));
    expect(screen.queryByText("System")).toBeNull();
  });
});

// ── taxonomy keys ──────────────────────────────────────────────────────────
describe("taxonomy", () => {
  test("filter keys round-trip to query params", () => {
    expect(parseFilter("Sports/Hockey")).toEqual({ top: "Sports", sub: "Hockey", state: null });
    expect(filterKey("States", "Kerala")).toBe("States/Kerala");
    expect(filterParams("Sports/Hockey", new URLSearchParams()).toString()).toBe("category=Sports&subcategory=Hockey");
    expect(filterParams("States/Kerala", new URLSearchParams()).toString()).toBe("state=Kerala");
    expect(filterParams("States", new URLSearchParams()).toString()).toBe("state=*");
    expect(filterParams(null, new URLSearchParams("page=1")).toString()).toBe("page=1");
  });
  test("chips and states", () => {
    expect(TOP_CHIPS).toHaveLength(10);
    expect(TOP_CHIPS).toEqual(expect.arrayContaining(["Health", "States"]));
    expect(STATES).toHaveLength(34);
    expect(Object.keys(SUBCATEGORIES)).toHaveLength(8);
    expect(homeStateOf({ interests_v2: ["Cricket", "Kerala"] })).toBe("Kerala");
  });
});

// ── card age ───────────────────────────────────────────────────────────────
describe("compactAge", () => {
  const { compactAge } = require("../lib/time");
  const now = Date.parse("2026-10-04T12:00:00Z");
  test("exact minutes, then hours, then days", () => {
    expect(compactAge("2026-10-04T11:59:40Z", now)).toBe("now");
    expect(compactAge("2026-10-04T11:47:00Z", now)).toBe("13m");
    expect(compactAge("2026-10-04T07:00:00Z", now)).toBe("5h");
    expect(compactAge("2026-10-02T13:00:00Z", now)).toBe("47h");
    expect(compactAge("2026-10-01T12:00:00Z", now)).toBe("3d");
    expect(compactAge(null, now)).toBe("");
    expect(compactAge("garbage", now)).toBe("");
  });
});

// ── poll ───────────────────────────────────────────────────────────────────
describe("PollOptions", () => {
  const PollOptions = require("../components/PollOptions").default;
  const props = { options: ["Yes", "No"], votes: { Yes: 3, No: 1 } };

  test("not voted: choices only, tap votes", () => {
    const onVote = jest.fn();
    render(<PollOptions {...props} myVote={null} justVoted={false} onVote={onVote} />);
    expect(screen.queryByText("75%")).toBeNull();
    fireEvent.click(screen.getByTestId("poll-option-Yes"));
    expect(onVote).toHaveBeenCalledWith("Yes");
  });

  test("reopened after voting: shows results, your pick, and can't vote again", () => {
    const onVote = jest.fn();
    render(<PollOptions {...props} myVote="No" justVoted={false} onVote={onVote} />);
    expect(screen.getByText("75%")).toBeInTheDocument();
    expect(screen.getByTestId("poll-option-No")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("poll-option-Yes")).toBeDisabled();
    expect(screen.getByTestId("poll-voted-note")).toHaveTextContent("You voted · 4 votes");
  });

  test("just voted: says the vote counted", () => {
    render(<PollOptions {...props} myVote="Yes" justVoted onVote={jest.fn()} />);
    expect(screen.getByTestId("poll-voted-note")).toHaveTextContent("Vote counted");
  });
});

// ── copy answer ────────────────────────────────────────────────────────────
describe("CopyButton", () => {
  const CopyButton = require("../components/CopyButton").default;
  test("copies the answer and says so", async () => {
    const writeText = jest.fn(() => Promise.resolve());
    Object.assign(navigator, { clipboard: { writeText } });
    render(<CopyButton text="An answer" />);
    fireEvent.click(screen.getByTestId("copy-answer"));
    await waitFor(() => expect(screen.getByText("Copied")).toBeInTheDocument());
    expect(writeText).toHaveBeenCalledWith("An answer");
  });
});

/* App 1.14: The Bureau. Formatting rules, the flashcard, the feed's states
 * (loading / quiet day / empty / error / preview / delayed) and the item page. */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import axios from "axios";

import {
  formatNumber, formatDelta, spokenNumber, visualFor, facesOf, groupByDay, dayLabel, istTime,
  isBureauKey, lensOf, bureauKey, getBureauStatus, resetBureauStatus,
} from "../lib/bureau";
import BureauFeed, { Flashcard, clearBureauMemo } from "../components/bureau/BureauFeed";
import BureauItemPage from "../pages/BureauItemPage";

jest.mock("axios", () => {
  const api = { get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() };
  return { __esModule: true, default: api, ...api };
});
jest.mock("@capacitor/share", () => ({ Share: { share: jest.fn(() => Promise.resolve()) } }));
jest.mock("@capacitor/browser", () => ({ Browser: { open: jest.fn() } }));

beforeAll(() => {
  global.IntersectionObserver = class { observe() {} disconnect() {} };
});
beforeEach(() => { axios.get.mockReset(); clearBureauMemo(); resetBureauStatus(); });

const NOW = Date.parse("2026-10-06T09:00:00Z");   // Tue 14:30 IST

const rbi = {
  official_id: "rbi1", issuer: "RBI", issuer_key: "rbi", kind: "policy", published_at: "2026-10-06T04:32:00Z",
  what_changed: "Loans may get a little cheaper.", title: "Monetary policy",
  key_number: { value: "5.25", unit: "%", label: "repo rate", delta: "-0.25" },
  facts: ["From today", "Home loans"], who: ["Borrowers"], sectors: ["Banking"],
  analogy: "Your bank's own borrowing got cheaper.", source_url: "https://www.rbi.org.in/x", source_name: "RBI",
};

// ── rules ─────────────────────────────────────────────────────────────────
describe("bureau rules", () => {
  test("numbers keep the source's unit", () => {
    expect(formatNumber({ value: "5.25", unit: "%" })).toBe("5.25%");
    expect(formatNumber({ value: "12,000", unit: "₹ crore" })).toBe("₹12,000 crore");
    expect(formatNumber({ value: "₹500", unit: "Rs" })).toBe("₹500");
    expect(formatNumber({ value: "25", unit: "basis points" })).toBe("25 bps");
    expect(formatNumber({ value: "3", unit: "years" })).toBe("3 years");
    expect(formatNumber(null)).toBe("");
    expect(formatNumber({ value: "" })).toBe("");
  });

  test("deltas are neutral arrows with spoken words", () => {
    expect(formatDelta(rbi.key_number)).toEqual({ arrow: "▼", text: "0.25%", spoken: "down 0.25 percent" });
    expect(formatDelta({ delta: "+1.5", unit: "" }).arrow).toBe("▲");
    expect(formatDelta({ delta: "0" })).toBeNull();
    expect(formatDelta({ delta: "n/a" })).toBeNull();
    expect(spokenNumber(rbi.key_number)).toBe("repo rate, 5.25 percent, down 0.25 percent");
  });

  test("a drawing per kind", () => {
    expect(visualFor(rbi)).toBe("dial");
    expect(visualFor({ kind: "bill" })).toBe("pillar");
    expect(visualFor({ kind: "data_release" })).toBe("bars");
    expect(visualFor({ kind: "scheme" })).toBe("crate");
    expect(visualFor({ kind: "consultation" })).toBe("calendar");
    expect(visualFor({ kind: "circular", issuer_key: "sebi" })).toBe("scales");
    expect(visualFor({ kind: "notification" })).toBe("document");
  });

  test("faces only when there is something to say", () => {
    expect(facesOf(rbi)).toEqual(["what", "who", "like"]);
    expect(facesOf({ who: [], sectors: [], analogy: " " })).toEqual(["what"]);
  });

  test("days and times are India's", () => {
    expect(istTime("2026-10-06T04:32:00Z")).toBe("10:02");
    expect(dayLabel("2026-10-05T19:00:00Z", NOW)).toBe("Today");          // 00:30 IST on the 6th
    expect(dayLabel("2026-10-05T18:00:00Z", NOW)).toBe("Yesterday");
    expect(dayLabel("2026-10-03T06:00:00Z", NOW)).toBe("Sat 3 Oct");
    const g = groupByDay([{ published_at: "2026-10-06T04:00:00Z" }, { published_at: "2026-10-06T01:00:00Z" },
      { published_at: "2026-10-04T06:00:00Z" }], NOW);
    expect(g.map(([l, xs]) => [l, xs.length])).toEqual([["Today", 2], ["Sun 4 Oct", 1]]);
  });

  test("filter keys", () => {
    expect(isBureauKey("Bureau")).toBe(true);
    expect(isBureauKey("Bureau/rbi")).toBe(true);
    expect(isBureauKey("Business")).toBe(false);
    expect(isBureauKey(null)).toBe(false);
    expect(lensOf("Bureau/rbi")).toBe("rbi");
    expect(bureauKey("")).toBe("Bureau");
  });

  test("status: hidden on error and not cached, so the next try can succeed", async () => {
    axios.get.mockRejectedValueOnce(new Error("offline"));
    expect(await getBureauStatus()).toEqual({ enabled: false, preview: false });
    axios.get.mockResolvedValueOnce({ data: { enabled: true, preview: true } });
    expect(await getBureauStatus()).toEqual({ enabled: true, preview: true });
    expect(await getBureauStatus()).toEqual({ enabled: true, preview: true });
    expect(axios.get).toHaveBeenCalledTimes(2);
  });
});

// ── flashcard ─────────────────────────────────────────────────────────────
describe("Flashcard", () => {
  test("number first, then the faces by tapping the bars; tap opens", async () => {
    const open = jest.fn();
    render(<Flashcard item={rbi} onOpen={open} showHint />);
    expect(screen.getByText("5.25%")).toBeInTheDocument();
    expect(screen.getByLabelText("repo rate, 5.25 percent, down 0.25 percent")).toBeInTheDocument();
    expect(screen.getByText("Swipe → what it means for you")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /2 of 3/ }));
    expect(open).not.toHaveBeenCalled();
    expect(await screen.findByText("Borrowers")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /3 of 3/ }));
    expect(await screen.findByText(rbi.analogy)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("bureau-card-rbi1"));
    expect(open).toHaveBeenCalledWith(rbi);
  });

  test("no number (unverified or none): leads with the line; scanned: summary coming", () => {
    render(<Flashcard item={{ ...rbi, key_number: null, who: [], sectors: [], analogy: "", title_only: true }} onOpen={jest.fn()} />);
    expect(screen.queryByText("5.25%")).toBeNull();
    expect(screen.queryByRole("button", { name: /of/ })).toBeNull();
    expect(screen.getByText(/Summary coming soon/)).toBeInTheDocument();
  });

  test("PIB items name the ministry; Desk flag only when the server sends it", () => {
    render(<Flashcard item={{ ...rbi, issuer: "PIB", issuer_key: "pib", ministry: "Ministry of Finance", needs_desk: true }} onOpen={jest.fn()} />);
    expect(screen.getByText(/Finance · Policy/)).toBeInTheDocument();
    expect(screen.getByTestId("desk-flag")).toBeInTheDocument();
  });
});

// ── feed states ───────────────────────────────────────────────────────────
const feed = (over = {}) => ({ data: { items: [rbi], today_count: 1, has_more: false, delayed: [], preview: false, ...over } });
const renderFeed = (key = "Bureau", onChange = jest.fn()) => render(
  <MemoryRouter><BureauFeed filterKey={key} onFilterChange={onChange} /></MemoryRouter>);

describe("BureauFeed", () => {
  test("loading, then cards under a day divider; lens pills change the filter", async () => {
    let resolve;
    axios.get.mockReturnValueOnce(new Promise((r) => { resolve = r; }));
    const onChange = jest.fn();
    renderFeed("Bureau", onChange);
    expect(screen.getByTestId("bureau-loading")).toBeInTheDocument();
    resolve(feed());
    expect(await screen.findByTestId("bureau-card-rbi1")).toBeInTheDocument();
    expect(screen.getByText("Official announcements, decoded")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("bureau-lens-sebi"));
    expect(onChange).toHaveBeenCalledWith("Bureau/sebi");
    expect(axios.get.mock.calls[0][0]).toContain("/bureau?limit=20");
  });

  test("lens is sent to the server", async () => {
    axios.get.mockResolvedValueOnce(feed());
    renderFeed("Bureau/rbi");
    await screen.findByTestId("bureau-card-rbi1");
    expect(axios.get.mock.calls[0][0]).toContain("lens=rbi");
  });

  test("quiet day shows no filler line (owner); preview and delayed lines", async () => {
    axios.get.mockResolvedValueOnce(feed({ today_count: 0, preview: true, delayed: ["RBI"],
      items: [{ ...rbi, published_at: "2026-09-30T05:00:00Z" }] }));
    renderFeed();
    expect(await screen.findByTestId("bureau-card-rbi1")).toBeInTheDocument();
    expect(screen.queryByText(/off for the weekend|No announcements yet today/)).toBeNull();
    expect(screen.getByTestId("bureau-preview")).toHaveTextContent("only Desk admins");
    expect(screen.getByTestId("bureau-delayed")).toHaveTextContent("RBI updates delayed");
  });

  test("empty lens; Parliament says it is not in session; error with retry", async () => {
    axios.get.mockResolvedValueOnce(feed({ items: [], today_count: 0 }));
    let view = renderFeed("Bureau/parliament");
    expect(await screen.findByTestId("bureau-empty")).toHaveTextContent("Parliament isn’t in session");
    view.unmount();
    clearBureauMemo();
    axios.get.mockResolvedValueOnce(feed({ items: [], today_count: 0 }));
    view = renderFeed("Bureau/sebi");
    expect(await screen.findByTestId("bureau-empty")).toHaveTextContent("Nothing from SEBI");
    const unmount = view.unmount;
    unmount();
    clearBureauMemo();
    axios.get.mockRejectedValueOnce(new Error("down")).mockResolvedValueOnce(feed());
    renderFeed();
    fireEvent.click(await screen.findByTestId("bureau-retry"));
    expect(await screen.findByTestId("bureau-card-rbi1")).toBeInTheDocument();
  });
});

// ── item page ─────────────────────────────────────────────────────────────
const renderItem = () => render(
  <MemoryRouter initialEntries={["/bureau/rbi1"]}>
    <Routes><Route path="/bureau/:officialId" element={<BureauItemPage />} /></Routes>
  </MemoryRouter>);

describe("BureauItemPage", () => {
  test("number, line, comparison, who, earlier steps, original", async () => {
    axios.get.mockResolvedValueOnce({ data: { ...rbi, summary: "Plain words.", dates: [{ label: "effective", date: "6 October 2026" }],
      earlier: [{ official_id: "rbi0", what_changed: "Rate held in August.", published_at: "2026-08-06T04:30:00Z" }] } });
    renderItem();
    expect(await screen.findByTestId("bureau-number")).toHaveTextContent("5.25%");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(rbi.what_changed);
    expect(screen.getByText("6 October 2026")).toBeInTheDocument();
    expect(screen.getByText(rbi.analogy)).toBeInTheDocument();
    expect(screen.getByTestId("bureau-earlier")).toHaveTextContent("Rate held in August.");
    expect(screen.getByTestId("bureau-original")).toHaveTextContent("rbi.org.in");
    expect(screen.getByText(/not a government body/)).toBeInTheDocument();
  });

  test("scanned document says so; error offers retry", async () => {
    axios.get.mockResolvedValueOnce({ data: { ...rbi, key_number: null, title_only: true, summary: "", earlier: [] } });
    const { unmount } = renderItem();
    expect(await screen.findByTestId("bureau-title-only")).toBeInTheDocument();
    unmount();
    axios.get.mockRejectedValueOnce(new Error("404")).mockResolvedValueOnce({ data: { ...rbi, earlier: [] } });
    renderItem();
    fireEvent.click(await screen.findByText("Try again"));
    await waitFor(() => expect(screen.getByTestId("bureau-item")).toBeInTheDocument());
  });
});

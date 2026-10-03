// Loaded by CRA before every test file.
import "@testing-library/jest-dom";
import { TextEncoder, TextDecoder } from "util";

// jsdom (Jest 27) lacks these; React Router 7 needs them at import time.
if (!global.TextEncoder) global.TextEncoder = TextEncoder;
if (!global.TextDecoder) global.TextDecoder = TextDecoder;

// jsdom has no matchMedia; lib/theme.js reads it for "follow the phone".
if (!window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false, media: query, onchange: null,
    addListener: () => {}, removeListener: () => {},
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
  });
}

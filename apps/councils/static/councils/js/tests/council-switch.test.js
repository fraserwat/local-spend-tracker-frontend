// Regression tests for council-switch.js's showCouncil():
//  1. a rejected CouncilIndex.load() used to be silently swallowed (no
//     .catch), leaving the click with no visible effect at all.
//  2. a slower, earlier showCouncil() call's CouncilIndex.load() response
//     could resolve after a faster, later call's and overwrite
//     document.title/status/heading with stale data.
// Loads the real script via vm against a minimal fake DOM, since it's a
// plain script (not an ES module) that wires itself up on DOMContentLoaded.
import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC_PATH = path.join(__dirname, "..", "council-switch.js");
const SRC = fs.readFileSync(SRC_PATH, "utf8");

function loadCouncilSwitch({ councilIndexLoad }) {
  const state = { locationHref: null, documentTitle: "", headingText: "" };

  const sidebarEl = {
    addEventListener() {},
    querySelector() {
      return null;
    },
  };
  const statusEl = {
    _html: "",
    _text: "",
    children: [],
    get innerHTML() {
      return this._html;
    },
    set innerHTML(v) {
      this._html = v;
      this.children = [];
    },
    get textContent() {
      return this._text;
    },
    set textContent(v) {
      this._text = v;
    },
    appendChild(child) {
      this.children.push(child);
    },
  };
  const headingEl = {
    get textContent() {
      return state.headingText;
    },
    set textContent(v) {
      state.headingText = v;
    },
    focus() {},
  };
  const announcerEl = {
    _text: "",
    get textContent() {
      return this._text;
    },
    set textContent(v) {
      this._text = v;
    },
  };
  const searchContainerEl = {
    getAttribute(name) {
      return name === "data-index-url" ? "/council-index.json" : null;
    },
  };

  let domReadyCallback = null;
  const fakeDocument = {
    addEventListener(event, cb) {
      if (event === "DOMContentLoaded") domReadyCallback = cb;
    },
    querySelector(sel) {
      return sel === ".council-sidebar" ? sidebarEl : null;
    },
    getElementById(id) {
      if (id === "status") return statusEl;
      if (id === "council-route-heading") return headingEl;
      if (id === "council-switch-announcer") return announcerEl;
      if (id === "council-search-container") return searchContainerEl;
      return null;
    },
    createElement() {
      return { dataset: {}, classList: { add() {}, remove() {} }, setAttribute() {} };
    },
    get title() {
      return state.documentTitle;
    },
    set title(v) {
      state.documentTitle = v;
    },
  };

  const sandbox = {
    document: fakeDocument,
    location: {
      pathname: "/",
      get href() {
        return state.locationHref;
      },
      set href(v) {
        state.locationHref = v;
      },
    },
    history: { pushState() {} },
    councilUrlTemplate: "/councils/__SLUG__/",
    councilSpendUrlTemplate: "/councils/__SLUG__/spend/",
    councilCoverageUrlTemplate: "/api/v1/councils/__SLUG__/coverage/",
    CouncilIndex: {
      load: councilIndexLoad,
      findBySlug(rows, slug) {
        return rows.find((r) => r.slug === slug) || null;
      },
    },
    councilMap: { renderSelectedCouncil() {}, showIdleState() {} },
    addEventListener() {},
    encodeURIComponent,
    console,
    Promise,
    setTimeout,
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(SRC, sandbox, { filename: "council-switch.js" });
  domReadyCallback();

  return {
    showCouncil: sandbox.councilSwitch.showCouncil,
    getLocationHref: () => state.locationHref,
    getDocumentTitle: () => state.documentTitle,
    getHeadingText: () => state.headingText,
  };
}

describe("council-switch showCouncil", () => {
  it("falls back to a hard navigation when CouncilIndex.load() rejects", async () => {
    const { showCouncil, getLocationHref } = loadCouncilSwitch({
      councilIndexLoad: () => Promise.reject(new Error("council-index fetch failed: 503")),
    });

    showCouncil("haringey");
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(getLocationHref()).toBe("/councils/haringey/");
  });

  it("ignores a stale CouncilIndex.load() response once a newer switch has started", async () => {
    const rows = [
      { slug: "camden", name: "Camden" },
      { slug: "haringey", name: "Haringey" },
    ];
    const resolvers = [];
    const { showCouncil, getDocumentTitle, getHeadingText } = loadCouncilSwitch({
      councilIndexLoad: () => new Promise((resolve) => resolvers.push(resolve)),
    });

    showCouncil("camden"); // call 1 -- slow
    showCouncil("haringey"); // call 2 -- user changed their mind before call 1 resolved

    // Call 2's response lands first; call 1's (stale) response lands after --
    // realistic whenever the earlier request took a slower network path.
    resolvers[1](rows);
    await new Promise((resolve) => setTimeout(resolve, 0));
    resolvers[0](rows);
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(getDocumentTitle()).toBe("Haringey — Local Spend Tracker");
    expect(getHeadingText()).toBe("Haringey");
  });
});

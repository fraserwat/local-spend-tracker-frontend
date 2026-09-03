// Regression test for renderSelectedCouncil()'s missing request-sequencing
// guard: a slower, earlier boundary fetch resolving after a faster, later
// switch used to overwrite selectedLayer/selectedSlugState/the camera with
// stale data and leave the correct layer's map add clobbered. Loads the
// real script via vm against a minimal fake Leaflet + DOM, since it's a
// plain script (not an ES module) that wires itself up on DOMContentLoaded.
import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC_PATH = path.join(__dirname, "..", "map.js");
let SRC = fs.readFileSync(SRC_PATH, "utf8");

// Test-only instrumentation: expose the closured `manifestEntriesBySlug`
// setter and `selectedSlugState` getter so the harness can seed the
// manifest directly (bypassing the manifest.json fetch) and observe the
// final selection. Edits only the in-memory string handed to vm.
const HOOK_ANCHOR = "window.councilMap = { renderSelectedCouncil, showIdleState };";
if (!SRC.includes(HOOK_ANCHOR)) throw new Error("hook anchor not found -- map.js source changed shape");
SRC = SRC.replace(
  HOOK_ANCHOR,
  HOOK_ANCHOR +
    "\n  window.__setManifest = (v) => { manifestEntriesBySlug = v; };" +
    "\n  window.__getSelectedSlug = () => selectedSlugState;"
);

function makeEl(overrides) {
  return Object.assign(
    {
      dataset: {},
      classList: { add() {}, remove() {}, contains: () => false },
      style: {},
      addEventListener() {},
      appendChild() {},
      setAttribute() {},
      removeAttribute() {},
      textContent: "",
      innerHTML: "",
    },
    overrides
  );
}

function loadCouncilMap() {
  const mapEl = makeEl({
    dataset: { geojsonUrl: "", manifestUrl: "", spendUrl: "", coverageUrl: "", selectedSlug: "" },
  });
  const statusEl = makeEl({});
  const badgeEl = makeEl({});

  let domReadyCallback = null;
  const fakeDocument = {
    addEventListener(event, cb) {
      if (event === "DOMContentLoaded") domReadyCallback = cb;
    },
    getElementById(id) {
      if (id === "map") return mapEl;
      if (id === "status") return statusEl;
      if (id === "coverage-badge") return badgeEl;
      return makeEl({});
    },
  };

  const geoJSONCalls = [];
  const mapEvents = [];
  function fakeLayer(name) {
    return {
      name,
      addTo() {
        mapEvents.push("addTo:" + name);
        return this;
      },
      on() {},
      getBounds() {
        return { pad: () => "BOUNDS" };
      },
    };
  }
  const L = {
    control: { zoom: () => ({ addTo: () => undefined }) },
    latLngBounds: () => ({ pad: () => "UKBOUNDS" }),
    map: () => ({
      setView() {
        return this;
      },
      setMaxBounds() {
        return this;
      },
      fitBounds(b) {
        mapEvents.push("fitBounds:" + b);
      },
      flyToBounds(b) {
        mapEvents.push("flyToBounds:" + b);
      },
      flyTo() {},
      on() {},
      removeLayer(l) {
        mapEvents.push("removeLayer:" + l.name);
      },
    }),
    tileLayer: () => ({ addTo: function () { return this; } }),
    geoJSON(geojson) {
      geoJSONCalls.push(geojson.__name);
      return fakeLayer(geojson.__name);
    },
    DomEvent: { stopPropagation() {} },
  };

  // Each URL gets its own FIFO queue of resolvers -- calling the same URL
  // twice (e.g. re-requesting a slug) doesn't clobber the earlier caller.
  const pendingFetches = {};
  function fakeFetch(url) {
    return new Promise((resolve) => {
      (pendingFetches[url] = pendingFetches[url] || []).push(resolve);
    });
  }
  function resolveFetch(url, body) {
    const queue = pendingFetches[url];
    if (!queue || !queue.length) throw new Error("no pending fetch for " + url);
    queue.shift()({ ok: true, json: () => Promise.resolve(body) });
  }

  const sandbox = {
    document: fakeDocument,
    L,
    fetch: fakeFetch,
    Promise,
    console,
    Map,
    encodeURIComponent,
    decodeURIComponent,
    councilUrlTemplate: "/councils/__SLUG__/",
    councilSpendUrlTemplate: "/councils/__SLUG__/spend/",
    councilCoverageUrlTemplate: "/api/v1/councils/__SLUG__/coverage/",
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(SRC, sandbox, { filename: "map.js" });
  domReadyCallback();

  sandbox.window.__setManifest({
    haringey: { file: "haringey.geojson", slug: "haringey" },
    camden: { file: "camden.geojson", slug: "camden" },
  });

  return {
    councilMap: sandbox.window.councilMap,
    resolveFetch,
    geoJSONCalls,
    mapEvents,
    getSelectedSlug: () => sandbox.window.__getSelectedSlug(),
  };
}

describe("map.js renderSelectedCouncil race guard", () => {
  it("keeps the last-requested council selected when an earlier switch's fetch resolves later", async () => {
    const { councilMap, resolveFetch, getSelectedSlug } = loadCouncilMap();

    // Step 1: user opens Haringey. Its geometry lands in boundaryCache.
    const p1 = councilMap.renderSelectedCouncil("haringey", null);
    resolveFetch("haringey.geojson", { __name: "haringey-geo" });
    await p1;

    // Step 2: user double-switches fast -- Camden, then back to Haringey.
    const pCamden = councilMap.renderSelectedCouncil("camden", null); // cache-cold: hits network
    const pHaringey = councilMap.renderSelectedCouncil("haringey", null); // cache-warm: resolves off cache

    // Camden's response is slow and lands AFTER the (synchronous, cache-hit)
    // Haringey re-render has already finished -- realistic on any real
    // network. Without the generation guard this stale response overwrites
    // the correct Haringey selection.
    resolveFetch("camden.geojson", { __name: "camden-geo" });
    await Promise.all([pCamden, pHaringey]);

    expect(getSelectedSlug()).toBe("haringey");
  });

  it("does not re-add a stale layer to the map once a later render has started", async () => {
    const { councilMap, resolveFetch, mapEvents } = loadCouncilMap();

    const pCamden = councilMap.renderSelectedCouncil("camden", null);
    const pHaringey = councilMap.renderSelectedCouncil("haringey", null);

    resolveFetch("camden.geojson", { __name: "camden-geo" });
    resolveFetch("haringey.geojson", { __name: "haringey-geo" });
    await Promise.all([pCamden, pHaringey]);

    // The stale Camden layer must never reach the map.
    expect(mapEvents).not.toContain("addTo:camden-geo");
    expect(mapEvents).toContain("addTo:haringey-geo");
  });
});

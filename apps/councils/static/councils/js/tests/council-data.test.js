// Regression test for the cache-poisoning bug: CouncilIndex.load() used to
// cache a rejected promise forever, so one transient fetch failure
// permanently broke every future load() call for the rest of the page
// session. Loads the real script via vm (it's a plain script that assigns
// to `window`, not an ES module) rather than re-implementing its logic.
import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC_PATH = path.join(__dirname, "..", "council-data.js");

function loadCouncilIndex(fetchImpl) {
  const src = fs.readFileSync(SRC_PATH, "utf8");
  const sandbox = { window: {}, fetch: fetchImpl, console, Promise };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "council-data.js" });
  return sandbox.window.CouncilIndex;
}

describe("CouncilIndex.load", () => {
  it("retries after a transient failure instead of caching the rejection forever", async () => {
    let callCount = 0;
    const CouncilIndex = loadCouncilIndex(() => {
      callCount += 1;
      // First call: simulates a transient blip (server briefly 503s, or a
      // dropped connection).
      if (callCount === 1) {
        return Promise.resolve({ ok: false, status: 503 });
      }
      // Every call after that: server has recovered.
      return Promise.resolve({ ok: true, json: () => Promise.resolve([{ slug: "haringey" }]) });
    });

    await expect(CouncilIndex.load("/council-index.json")).rejects.toThrow(/503/);

    const rows = await CouncilIndex.load("/council-index.json");
    expect(rows).toEqual([{ slug: "haringey" }]);
    expect(callCount).toBe(2);
  });

  it("still de-duplicates concurrent in-flight calls into a single fetch", async () => {
    let callCount = 0;
    const CouncilIndex = loadCouncilIndex(() => {
      callCount += 1;
      return Promise.resolve({ ok: true, json: () => Promise.resolve([{ slug: "camden" }]) });
    });

    const [a, b] = await Promise.all([
      CouncilIndex.load("/council-index.json"),
      CouncilIndex.load("/council-index.json"),
    ]);

    expect(a).toEqual([{ slug: "camden" }]);
    expect(b).toEqual([{ slug: "camden" }]);
    expect(callCount).toBe(1);
  });
});

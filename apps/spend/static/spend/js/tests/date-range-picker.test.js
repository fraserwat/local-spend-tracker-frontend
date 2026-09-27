// Unit tests for the pure date-math window.DateRangePicker exposes --
// the DOM-wiring half (panel open/close, calendar click handlers) is
// exercised by hand in the browser instead, same split as
// council-data.test.js takes for CouncilIndex.load().
import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC_PATH = path.join(__dirname, "..", "date-range-picker.js");

function loadDateRangePicker() {
  const src = fs.readFileSync(SRC_PATH, "utf8");
  const sandbox = {
    window: {},
    document: { addEventListener: () => {} },
    console,
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "date-range-picker.js" });
  return sandbox.window.DateRangePicker;
}

const d = (year, month, day) => new Date(year, month - 1, day);

describe("buildMonthWeeks", () => {
  it("pads January 2026 (starts on a Thursday) with 3 leading blanks", () => {
    const { buildMonthWeeks } = loadDateRangePicker();
    const weeks = buildMonthWeeks(2026, 0);
    expect(weeks[0]).toEqual([null, null, null, d(2026, 1, 1), d(2026, 1, 2), d(2026, 1, 3), d(2026, 1, 4)]);
    expect(weeks[weeks.length - 1].filter(Boolean).at(-1)).toEqual(d(2026, 1, 31));
  });

  it("has no leading blanks for a month starting on a Monday", () => {
    const { buildMonthWeeks } = loadDateRangePicker();
    // June 2026 starts on a Monday.
    const weeks = buildMonthWeeks(2026, 5);
    expect(weeks[0][0]).toEqual(d(2026, 6, 1));
  });
});

describe("commitClick", () => {
  it("starts a fresh single-day selection from an empty state", () => {
    const { commitClick } = loadDateRangePicker();
    expect(commitClick({ start: null, end: null }, d(2026, 3, 10))).toEqual({
      start: d(2026, 3, 10),
      end: null,
    });
  });

  it("closes the range on a second, later click", () => {
    const { commitClick } = loadDateRangePicker();
    const state = { start: d(2026, 3, 10), end: null };
    expect(commitClick(state, d(2026, 3, 15))).toEqual({
      start: d(2026, 3, 10),
      end: d(2026, 3, 15),
    });
  });

  it("swaps start/end when the second click lands before the first", () => {
    const { commitClick } = loadDateRangePicker();
    const state = { start: d(2026, 3, 10), end: null };
    expect(commitClick(state, d(2026, 3, 1))).toEqual({
      start: d(2026, 3, 1),
      end: d(2026, 3, 10),
    });
  });

  it("starts a new range when clicking again after one is already closed", () => {
    const { commitClick } = loadDateRangePicker();
    const state = { start: d(2026, 3, 1), end: d(2026, 3, 10) };
    expect(commitClick(state, d(2026, 4, 1))).toEqual({
      start: d(2026, 4, 1),
      end: null,
    });
  });
});

describe("inRange", () => {
  it("is exclusive of the start and end days themselves", () => {
    const { inRange } = loadDateRangePicker();
    const start = d(2026, 3, 10);
    const end = d(2026, 3, 12);
    expect(inRange(d(2026, 3, 10), start, end)).toBe(false);
    expect(inRange(d(2026, 3, 11), start, end)).toBe(true);
    expect(inRange(d(2026, 3, 12), start, end)).toBe(false);
  });

  it("is false with no end set yet", () => {
    const { inRange } = loadDateRangePicker();
    expect(inRange(d(2026, 3, 11), d(2026, 3, 10), null)).toBe(false);
  });
});

describe("parseDMYInputs / writeDMYInputs", () => {
  it("round-trips a date through the three DMY inputs", () => {
    const { parseDMYInputs, writeDMYInputs } = loadDateRangePicker();
    const inputs = { day: { value: "" }, month: { value: "" }, year: { value: "" } };
    writeDMYInputs(inputs.day, inputs.month, inputs.year, d(2026, 3, 5));
    expect(inputs).toEqual({ day: { value: "5" }, month: { value: "3" }, year: { value: "2026" } });
    expect(parseDMYInputs(inputs.day, inputs.month, inputs.year)).toEqual(d(2026, 3, 5));
  });

  it("treats a partially-filled triple as no date, not a crash", () => {
    const { parseDMYInputs } = loadDateRangePicker();
    const inputs = { day: { value: "5" }, month: { value: "" }, year: { value: "2026" } };
    expect(parseDMYInputs(inputs.day, inputs.month, inputs.year)).toBeNull();
  });

  it("clears all three fields when writing a null date", () => {
    const { writeDMYInputs } = loadDateRangePicker();
    const inputs = { day: { value: "5" }, month: { value: "3" }, year: { value: "2026" } };
    writeDMYInputs(inputs.day, inputs.month, inputs.year, null);
    expect(inputs).toEqual({ day: { value: "" }, month: { value: "" }, year: { value: "" } });
  });
});

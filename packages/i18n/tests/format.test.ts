import { describe, expect, it } from "vitest";

import {
  formatDate,
  formatNumber,
  formatPercent,
  formatTime,
  WEEK_STARTS_ON,
} from "../src/index.ts";

// 20 Oct 2026, 07:30 in Berlin (CEST, UTC+2).
const demo = new Date("2026-10-20T05:30:00Z");

describe("format", () => {
  it("formats dates per locale", () => {
    expect(formatDate(demo, "de")).toBe("20.10.2026");
    expect(formatDate(demo, "en")).toBe("20 Oct 2026");
    expect(formatDate(new Date("2026-09-03T10:00:00Z"), "en")).toBe("3 Sep 2026");
  });

  it("uses the 24-hour clock in Berlin time", () => {
    expect(formatTime(demo)).toBe("07:30");
    expect(formatTime(new Date("2026-10-20T20:00:00Z"))).toBe("22:00");
  });

  it("uses the locale decimal separator", () => {
    expect(formatNumber(9.75, "de")).toBe("9,75");
    expect(formatNumber(9.75, "en")).toBe("9.75");
  });

  it("puts a space before % in German only", () => {
    expect(formatPercent(0.91, "de")).toBe("91\u00a0%");
    expect(formatPercent(0.91, "en")).toBe("91%");
  });

  it("starts weeks on Monday", () => {
    expect(WEEK_STARTS_ON).toBe(1);
  });
});

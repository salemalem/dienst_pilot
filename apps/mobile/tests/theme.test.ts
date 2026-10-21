// @vitest-environment node
import { describe, expect, it } from "vitest";

import { isNight, resolveTheme } from "../src/lib/theme";

// The demo clock is Europe/Berlin: 2026-10-20 is CEST (UTC+2).
const at = (hhmm: string): string => `2026-10-20T${hhmm}:00+02:00`;

describe("night theme follows the demo clock, 20:00 to 07:00", () => {
  it.each([
    ["06:59", true],
    ["07:00", false],
    ["12:00", false],
    ["19:59", false],
    ["20:00", true],
    ["23:30", true],
    ["00:10", true],
  ])("%s is night: %s", (time, night) => {
    expect(isNight(at(time))).toBe(night);
  });

  it("reads the Berlin hour whatever the instant's offset (winter time too)", () => {
    expect(isNight("2026-12-01T19:30:00Z")).toBe(true); // 20:30 CET
    expect(isNight("2026-12-01T18:30:00Z")).toBe(false); // 19:30 CET
  });

  it("automatic follows the clock; a manual choice wins; no clock yet means light", () => {
    expect(resolveTheme("auto", at("06:00"))).toBe("dark");
    expect(resolveTheme("auto", at("08:00"))).toBe("light");
    expect(resolveTheme("light", at("06:00"))).toBe("light");
    expect(resolveTheme("dark", at("12:00"))).toBe("dark");
    expect(resolveTheme("auto", null)).toBe("light");
  });
});

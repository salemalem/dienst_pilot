import { describe, expect, it } from "vitest";

import { addMonths, buildFmt, daysInMonth, isWeekend, weekdayIndex } from "../src/lib/fmt.ts";

describe("date formats (CLAUDE.md, design system)", () => {
  const de = buildFmt("de");
  const en = buildFmt("en");

  it("writes two consecutive days with a slash, never an arrow", () => {
    expect(de.daySpan("2026-12-14", "2026-12-15")).toBe("14./15.12.");
    expect(en.daySpan("2026-12-14", "2026-12-15")).toBe("14/15 Dec");
  });

  it("writes a longer range with an en dash", () => {
    expect(de.range("2026-07-14", "2026-07-27")).toBe("14.–27.07.");
    expect(en.range("2026-07-14", "2026-07-27")).toBe("14–27 Jul");
  });

  it("formats dates per locale", () => {
    expect(de.date("2026-10-20")).toBe("20.10.2026");
    expect(en.date("2026-10-20")).toBe("20 Oct 2026");
    expect(de.dayMonth("2026-12-23")).toBe("23.12.");
    expect(en.dayMonth("2026-12-23")).toBe("23 Dec");
  });

  it("uses a 24-hour clock in the department's time zone", () => {
    expect(de.time("2026-10-20T04:43:00Z")).toBe("06:43");
    expect(en.time("2026-10-20T04:43:00Z")).toBe("06:43");
  });

  it("puts a space before the German percent sign and uses locale decimals", () => {
    expect(de.percent(0.91).replace(/\s/g, " ")).toBe("91 %");
    expect(en.percent(0.91)).toBe("91%");
    expect(de.number(9.75)).toBe("9,75");
    expect(en.number(9.75)).toBe("9.75");
  });

  it("names months and weekdays per language", () => {
    expect(de.month("2026-12")).toBe("Dezember 2026");
    expect(en.month("2026-12")).toBe("December 2026");
    expect(de.weekday("2026-10-20")).toBe("Di");
    expect(en.weekday("2026-10-20")).toBe("Tu");
  });
});

describe("calendar helpers", () => {
  it("weeks start on Monday", () => {
    expect(weekdayIndex("2026-10-19")).toBe(0);
    expect(isWeekend("2026-10-24")).toBe(true);
    expect(isWeekend("2026-10-23")).toBe(false);
  });

  it("moves across year ends and lists a month's days", () => {
    expect(addMonths("2026-12", 1)).toBe("2027-01");
    expect(addMonths("2026-01", -1)).toBe("2025-12");
    expect(daysInMonth("2026-12")).toHaveLength(31);
    expect(daysInMonth("2026-11")).toHaveLength(30);
  });
});

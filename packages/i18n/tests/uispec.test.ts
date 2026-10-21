import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { IntlMessageFormat } from "intl-messageformat";
import { describe, expect, it } from "vitest";

import { messages, type Locale } from "../src/index.ts";

// The M5 and M6 copy in docs/UI_SPEC.md §3 is the source; the catalog must render it exactly.
const spec = readFileSync(
  fileURLToPath(new URL("../../../docs/UI_SPEC.md", import.meta.url)),
  "utf8",
);
const row = (id: string): string => {
  const line = spec.split("\n").find((l: string) => l.startsWith(`| ${id} |`));
  if (!line) throw new Error(`UI_SPEC has no ${id} row`);
  return line;
};
const render = (locale: Locale, text: string, values: Record<string, unknown> = {}): string =>
  String(new IntlMessageFormat(text, locale).format(values));

describe("M5 and M6 copy follows UI_SPEC", () => {
  it.each([
    ["de", "Juni"],
    ["en", "June"],
  ] as const)("M5 in %s", (locale, month) => {
    const m5 = messages[locale].m5;
    for (const text of [
      render(locale, m5.coverable, { count: 2 }),
      m5.requestLeave,
      render(locale, m5.tradeOff, { month }),
      m5.requestWithTrade,
      m5.requestWithoutTrade,
    ]) {
      expect(row("M5"), text).toContain(`"${text}"`);
    }
  });

  it.each(["de", "en"] as const)("M6 in %s", (locale) => {
    const m6 = messages[locale].m6;
    for (const text of [m6.offerExchange, m6.audience, m6.giveawayBelowHours]) {
      expect(row("M6"), text).toContain(`"${text}"`);
    }
  });

  it("M5 stays correct for other counts", () => {
    expect(render("de", messages.de.m5.coverable, { count: 3 })).toContain("3 Kolleg:innen haben");
    expect(render("en", messages.en.m5.coverable, { count: 1 })).toContain("One colleague has");
  });
});

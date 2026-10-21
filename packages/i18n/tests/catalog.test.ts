import { IntlMessageFormat } from "intl-messageformat";
import { describe, expect, it } from "vitest";

import { defaultLocale, isLocale, locales, messages } from "../src/index.ts";

type Tree = { [key: string]: string | Tree };

function leaves(tree: Tree, prefix = ""): [string, string][] {
  return Object.entries(tree).flatMap(([k, v]) =>
    typeof v === "string"
      ? [[`${prefix}${k}`, v] as [string, string]]
      : leaves(v, `${prefix}${k}.`),
  );
}

describe("catalog", () => {
  it("German is the default locale", () => {
    expect(defaultLocale).toBe("de");
    expect(isLocale("en")).toBe(true);
    expect(isLocale("fr")).toBe(false);
  });

  it("DE and EN have exactly the same keys", () => {
    const keys = (l: (typeof locales)[number]): string[] =>
      leaves(messages[l])
        .map(([k]) => k)
        .sort();
    expect(keys("en")).toEqual(keys("de"));
  });

  it("no key contains a dot (both apps nest on dots, so 'run.requested' must be 'run_requested')", () => {
    const dotted = (tree: Tree, path = ""): string[] =>
      Object.entries(tree).flatMap(([k, v]) => [
        ...(k.includes(".") ? [`${path}${k}`] : []),
        ...(typeof v === "string" ? [] : dotted(v, `${path}${k}.`)),
      ]);
    expect(dotted(messages.de)).toEqual([]);
    expect(dotted(messages.en)).toEqual([]);
  });

  it.each(locales)("every %s message is non-empty, valid ICU", (locale) => {
    for (const [key, value] of leaves(messages[locale])) {
      expect(value.trim(), key).not.toBe("");
      expect(() => new IntlMessageFormat(value, locale), key).not.toThrow();
    }
  });

  it("shift letters follow UI_SPEC §5 and switch with the language", () => {
    const letters = (l: (typeof locales)[number]): string[] =>
      Object.values(messages[l].shift).map((s) => s.letter);
    expect(letters("de")).toEqual(["F", "S", "N", "B", "R", "U"]);
    expect(letters("en")).toEqual(["E", "L", "N", "O", "H", "V"]);
  });

  it("carries the environment badge in both languages", () => {
    expect(messages.de.app.env).toBe("Demo-Umgebung, synthetische Daten");
    expect(messages.en.app.env).toBe("Demo environment, synthetic data");
  });
});

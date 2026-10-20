import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { toCss, toNative, toTailwind } from "../scripts/emit.ts";
import {
  loadSource,
  resolve,
  SHIFT_TYPES,
  SOURCE_DIR,
  THEMES,
  type TokenSource,
} from "../scripts/source.ts";
import { colors, shiftColors, shiftTypes, typography } from "../src/index.ts";

const tokens = resolve(loadSource());

/** Custom properties declared in the first block whose selector is exactly `selector`. */
function declarations(css: string, selector: string): Record<string, string> {
  const start = css.indexOf(`\n${selector} {`);
  if (start < 0) throw new Error(`No ${selector} block`);
  const body = css.slice(start, css.indexOf("\n}", start));
  return Object.fromEntries(
    [...body.matchAll(/--([\w-]+):\s*([^;]+);/g)].map((m) => [m[1], m[2]?.trim()]),
  );
}

describe("shift types", () => {
  it("has all six shift types from UI_SPEC §5, including Rufbereitschaft", () => {
    expect(shiftTypes).toEqual(["frueh", "spaet", "nacht", "bereitschaft", "ruf", "frei"]);
  });

  it.each(THEMES.flatMap((t) => SHIFT_TYPES.map((s) => [t, s] as const)))(
    "%s theme has solid, on, wash and ink for %s",
    (theme, shift) => {
      const c = shiftColors(theme, shift);
      for (const v of [c.solid, c.on, c.wash, c.ink]) expect(v).toMatch(/^#[0-9A-F]{6}$/i);
    },
  );

  it("gives night an edge in both themes and no other shift one", () => {
    for (const t of THEMES) {
      for (const s of SHIFT_TYPES) {
        expect(shiftColors(t, s).edge !== undefined).toBe(s === "nacht");
      }
    }
  });
});

describe("resolution", () => {
  it("resolves aliases (focus → action) per theme", () => {
    for (const t of THEMES) expect(colors[t].focus).toBe(colors[t].action);
  });

  it("dark differs from light", () => {
    expect(colors.dark.paper).not.toBe(colors.light.paper);
  });

  it("rejects an alias to a missing token", () => {
    const src: TokenSource = structuredClone(loadSource());
    src.color.tokens.push({ name: "broken", value: { light: "{nope}" } });
    expect(() => resolve(src)).toThrow(/unknown colour token "nope"/);
  });

  it("converts em tracking to px for native", () => {
    expect(typography.display.letterSpacing).toBe(-0.32);
    expect(typography.gridLetter.lineHeight).toBe(15);
    expect(typography.numTime.fontVariant).toEqual(["tabular-nums"]);
  });
});

describe("web output matches the design system's official stylesheet", () => {
  const official = readFileSync(`${SOURCE_DIR}css/dienstpilot-tokens.css`, "utf8");
  const ours = toCss(tokens);

  it.each([":root", ".dp-dark"])("%s declares the same variables with the same values", (sel) => {
    expect(declarations(ours, sel)).toEqual(declarations(official, sel));
  });

  it("declares the same type classes", () => {
    const classes = (css: string): string[] =>
      [...css.matchAll(/^\.([\w-]+) \{/gm)].map((m) => m[1] ?? "").filter((c) => c !== "dp-dark");
    expect(classes(ours)).toEqual(classes(official));
  });
});

describe("tailwind theme", () => {
  const tw = toTailwind(tokens);

  it("maps every colour token and removes the default palette", () => {
    expect(tw).toContain("--color-*: initial;");
    for (const name of Object.keys(tokens.colors.light)) {
      expect(tw).toContain(`--color-${name}: var(--${name});`);
    }
  });

  it("maps spacing, radius and shadow to the token variables", () => {
    expect(tw).toContain("--spacing-4: var(--space-4);");
    expect(tw).toContain("--radius-control: var(--radius-control);");
    expect(tw).toContain("--shadow-sheet: var(--shadow-sheet);");
  });
});

describe("build inputs", () => {
  it("native module is generated from the current tokens.json", () => {
    const generated = readFileSync(new URL("../src/generated/native.ts", import.meta.url), "utf8");
    expect(generated).toBe(toNative(tokens));
  });

  it.each(tokens.fonts.map((f) => f.file))("copies font %s unchanged", (file) => {
    const sha = (p: string | URL): string =>
      createHash("sha256").update(readFileSync(p)).digest("hex");
    const name = file.split("/").pop() ?? "";
    expect(sha(new URL(`../dist/fonts/${name}`, import.meta.url))).toBe(
      sha(`${SOURCE_DIR}${file}`),
    );
  });
});

describe("native typography", () => {
  it("rounds variable-font weights to native steps", async () => {
    const { nativeTypography } = await import("../src/index.ts");
    expect(typography.label.fontWeight).toBe("550");
    expect(nativeTypography.label.fontWeight).toBe("600");
    expect(nativeTypography.body.fontWeight).toBe("400");
    expect(nativeTypography.display.letterSpacing).toBe(-0.32);
  });
});

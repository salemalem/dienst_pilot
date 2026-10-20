// DienstPilot: builds css/dienstpilot-tokens.css from tokens.json.
// Usage (from the folder that holds tokens.json, css/ and fonts/):
//   node css/build-tokens-css.mjs [path/to/tokens.json] [path/to/output.css]
// Node 18+, no dependencies. Rerun after every change to tokens.json; never edit the CSS by hand.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = resolve(process.argv[2] || resolve(here, "../tokens.json"));
const out = resolve(process.argv[3] || resolve(here, "dienstpilot-tokens.css"));
const DARK_CLASS = "dp-dark";
const FONT_URL_PREFIX = "../fonts/"; // font files relative to the CSS file

const t = JSON.parse(readFileSync(src, "utf8"));
const themes = t.color.themes.map((x) => x.id);
const [first, second] = themes;
if (themes.length !== 2) throw new Error("Expected exactly two themes (light, dark); found " + themes.join(", "));

const cssValue = (v) => (typeof v === "string" && /^\{.+\}$/.test(v) ? `var(--${v.slice(1, -1)})` : v);
const themed = (tok, theme) => {
  if (typeof tok.value === "string") return theme === first ? tok.value : null;
  return tok.value[theme] ?? (theme === first ? null : tok.value[first]);
};
const decl = (name, value) => `  --${name}: ${value};`;
const block = (selector, lines) => `${selector} {\n${lines.join("\n")}\n}`;

// colours + shadows per theme. Every colour, aliases included, is re-declared in the dark block,
// because a custom property that aliases another is resolved where it is declared.
const colorLines = (theme) => t.color.tokens.map((c) => { const v = themed(c, theme); return v ? decl(c.name, cssValue(v)) : null; }).filter(Boolean);
const shadowLines = (theme) => (t.shadow?.tokens || []).map((s) => { const v = themed(s, theme); return v ? decl(s.name, v) : null; }).filter(Boolean);

// theme-independent scales
const scaleLines = [];
for (const fam of ["spacing", "radius", "size"]) for (const x of t[fam]?.tokens || []) scaleLines.push(decl(x.name, x.value));
for (const [k, v] of Object.entries(t.type.families)) scaleLines.push(decl(`font-${k}`, v));

// type styles as font shorthands: font: var(--type-body);
const typeLines = [];
for (const g of t.type.groups) for (const s of g.styles) {
  const fam = `var(--font-${s.family || g.family})`;
  typeLines.push(decl(`type-${s.name}`, `${s.fontStyle === "italic" ? "italic " : ""}${s.fontWeight} ${s.fontSize}/${s.lineHeight} ${fam}`));
  if (s.letterSpacing) typeLines.push(decl(`type-${s.name}-tracking`, s.letterSpacing));
}

// one class per type style, matching the class names the design-system page generates (.body, .num-time ...),
// so components/bundle.css works the same with this file.
const NUMERIC = /^(num-|grid-letter$)/;
const typeClasses = [];
for (const g of t.type.groups) for (const s of g.styles) {
  const lines = [`  font: var(--type-${s.name});`];
  if (s.letterSpacing) lines.push(`  letter-spacing: var(--type-${s.name}-tracking);`);
  if (NUMERIC.test(s.name)) lines.push("  font-variant-numeric: tabular-nums;");
  typeClasses.push(block(`.${s.name}`, lines));
}

const fontFaces = t.type.fonts.map((f) => {
  const file = f.file.replace(/^fonts\//, "");
  return `@font-face {\n  font-family: "${f.family}";\n  src: url("${FONT_URL_PREFIX}${file}") format("woff2");\n  font-weight: ${f.weight};\n  font-style: ${f.style || "normal"};\n  font-display: swap;\n}`;
});

const header = `/*
 * DienstPilot design tokens: the official stylesheet. GENERATED from tokens.json (${t.name} v${t.version}) by css/build-tokens-css.mjs.
 * Do not edit by hand: change tokens.json, then run  node css/build-tokens-css.mjs
 *
 * Light theme is the default on :root.
 * Dark theme: add the class "${DARK_CLASS}" to <html> (or to any container; everything inside switches).
 *   document.documentElement.classList.toggle("${DARK_CLASS}", isNight)   // staff app: 20:00-07:00
 * Type: use the classes (.body, .label, .num-time ...) or the properties: font: var(--type-body);
 *   numeric styles (num-*, grid-letter) also need font-variant-numeric: tabular-nums after the font shorthand,
 *   which resets it. The classes already include it.
 */`;

const css = [
  header,
  ...fontFaces,
  block(":root", ["  color-scheme: light;", ...colorLines(first), ...shadowLines(first), ...scaleLines, ...typeLines]),
  block(`.${DARK_CLASS}`, ["  color-scheme: dark;", ...colorLines(second), ...shadowLines(second)]),
  "/* Type style classes */",
  ...typeClasses,
  "",
].join("\n\n");

writeFileSync(out, css);
console.log(`wrote ${out}: ${t.color.tokens.length} colours x ${themes.length} themes, ${typeLines.length} type properties`);

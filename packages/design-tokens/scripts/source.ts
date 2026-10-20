/**
 * Reads the design system's tokens.json and resolves it into flat, typed theme values.
 * Pure functions only: the build script and the tests share them.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export const SOURCE_DIR = fileURLToPath(
  new URL("../../../design/reference/design-system/project/", import.meta.url),
);
export const SOURCE_TOKENS = `${SOURCE_DIR}tokens.json`;

export type ThemeId = "light" | "dark";
export const THEMES: readonly ThemeId[] = ["light", "dark"];

/** The six shift types, in UI_SPEC §5 order. Letters and names live in packages/i18n. */
export const SHIFT_TYPES = ["frueh", "spaet", "nacht", "bereitschaft", "ruf", "frei"] as const;
export type ShiftType = (typeof SHIFT_TYPES)[number];

interface Entry<V> {
  name: string;
  value: V;
  usage?: string;
}
type Themed = string | Partial<Record<ThemeId, string>>;

export interface TypeStyle {
  name: string;
  fontSize: string;
  lineHeight: string;
  fontWeight: number | string;
  letterSpacing?: string;
  family: string;
}

export interface TokenSource {
  name: string;
  version: number;
  color: { tokens: Entry<Themed>[] };
  type: {
    fonts: { family: string; file: string; weight: string; style: string }[];
    families: Record<string, string>;
    groups: { name: string; family: string; styles: Omit<TypeStyle, "family">[] }[];
  };
  spacing: { tokens: Entry<string>[] };
  radius: { tokens: Entry<string>[] };
  shadow: { tokens: Entry<Themed>[] };
  size: { tokens: Entry<string>[] };
}

export interface Resolved {
  name: string;
  version: number;
  /** Colour tokens per theme, aliases resolved to plain values. */
  colors: Record<ThemeId, Record<string, string>>;
  /** Colour aliases as written in the source (e.g. focus → action), for the CSS output. */
  aliases: Record<string, Partial<Record<ThemeId, string>>>;
  shadows: Record<ThemeId, Record<string, string>>;
  spacing: Record<string, string>;
  radius: Record<string, string>;
  size: Record<string, string>;
  fonts: TokenSource["type"]["fonts"];
  families: Record<string, string>;
  typeStyles: TypeStyle[];
}

export function loadSource(path: string = SOURCE_TOKENS): TokenSource {
  return JSON.parse(readFileSync(path, "utf8")) as TokenSource;
}

const ALIAS = /^\{([A-Za-z0-9][A-Za-z0-9_.-]*)\}$/;

function themedValue(value: Themed, theme: ThemeId): string | undefined {
  // A plain string is the first theme's value; a missing theme inherits the first theme's.
  if (typeof value === "string") return value;
  return value[theme] ?? value.light;
}

function flat(entries: Entry<string>[]): Record<string, string> {
  return Object.fromEntries(entries.map((e) => [e.name, e.value]));
}

export function resolve(src: TokenSource): Resolved {
  const raw: Record<ThemeId, Record<string, string>> = { light: {}, dark: {} };
  const aliases: Resolved["aliases"] = {};
  for (const token of src.color.tokens) {
    for (const theme of THEMES) {
      const v = themedValue(token.value, theme);
      if (v === undefined) throw new Error(`Colour token "${token.name}" has no value`);
      raw[theme][token.name] = v;
      const m = ALIAS.exec(v);
      if (m?.[1] !== undefined) (aliases[token.name] ??= {})[theme] = m[1];
    }
  }
  const colors: Resolved["colors"] = { light: {}, dark: {} };
  for (const theme of THEMES) {
    const lookup = (name: string, seen: Set<string>): string => {
      const v = raw[theme][name];
      if (v === undefined) throw new Error(`Alias to unknown colour token "${name}"`);
      const m = ALIAS.exec(v);
      if (m?.[1] === undefined) return v;
      if (seen.has(m[1])) throw new Error(`Alias cycle at "${name}"`);
      return lookup(m[1], new Set([...seen, name]));
    };
    for (const name of Object.keys(raw[theme])) colors[theme][name] = lookup(name, new Set());
  }

  const shadows: Resolved["shadows"] = { light: {}, dark: {} };
  for (const token of src.shadow.tokens) {
    for (const theme of THEMES) {
      const v = themedValue(token.value, theme);
      if (v === undefined) throw new Error(`Shadow token "${token.name}" has no value`);
      shadows[theme][token.name] = v;
    }
  }

  return {
    name: src.name,
    version: src.version,
    colors,
    aliases,
    shadows,
    spacing: flat(src.spacing.tokens),
    radius: flat(src.radius.tokens),
    size: flat(src.size.tokens),
    fonts: src.type.fonts,
    families: src.type.families,
    typeStyles: src.type.groups.flatMap((g) => g.styles.map((s) => ({ ...s, family: g.family }))),
  };
}

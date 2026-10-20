/**
 * Typed tokens for React Native (and any JS consumer). Web apps use the CSS files instead:
 * `@dienstpilot/design-tokens/tokens.css` and `@dienstpilot/design-tokens/tailwind.css`.
 */
import { colors, shiftTypes, typography } from "./generated/native.ts";

export * from "./generated/native.ts";

export type ThemeId = keyof typeof colors;
export type Theme = (typeof colors)[ThemeId];
export type ShiftType = (typeof shiftTypes)[number];

export interface ShiftColors {
  /** Solid fill: chip, legend swatch, marker underline. */
  solid: string;
  /** Letter on the solid fill. */
  on: string;
  /** Grid-cell background. */
  wash: string;
  /** Letter on the wash. */
  ink: string;
  /** Chip edge; only night has one (keeps navy visible on the dark sheet). */
  edge?: string;
}

const cap = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1);

/** The four colours of a shift type in a theme. */
export function shiftColors(theme: ThemeId, shift: ShiftType): ShiftColors {
  const t: Record<string, string> = colors[theme];
  const get = (key: string): string => {
    const v = t[key];
    if (v === undefined) throw new Error(`Missing token ${key}`);
    return v;
  };
  const k = cap(shift);
  const result: ShiftColors = {
    solid: get(`shift${k}`),
    on: get(`onShift${k}`),
    wash: get(`shift${k}Wash`),
    ink: get(`shift${k}Ink`),
  };
  const edge = t[`shift${k}Edge`];
  if (edge !== undefined) result.edge = edge;
  return result;
}

export type TypeName = keyof typeof typography;

/** A text style in the shape React Native's `TextStyle` accepts. */
export interface NativeTextStyle {
  fontFamily: string;
  fontSize: number;
  lineHeight: number;
  fontWeight: "100" | "200" | "300" | "400" | "500" | "600" | "700" | "800" | "900";
  letterSpacing?: number;
  fontVariant?: "tabular-nums"[];
}

/**
 * Text styles for iOS and Android. The design uses variable-font weights (450, 550, 650, 750);
 * native platforms only render steps of 100, so weights round to the nearest step (650 → 700).
 * On web (react-native-web) use `typography`, which keeps the exact weights.
 */
export const nativeTypography = Object.fromEntries(
  Object.entries(typography).map(([name, s]) => {
    const step = Math.min(900, Math.max(100, Math.round(Number(s.fontWeight) / 100) * 100));
    const style: NativeTextStyle = {
      fontFamily: s.fontFamily,
      fontSize: s.fontSize,
      lineHeight: s.lineHeight,
      fontWeight: String(step) as NativeTextStyle["fontWeight"],
    };
    if ("letterSpacing" in s) style.letterSpacing = s.letterSpacing;
    if ("fontVariant" in s) style.fontVariant = ["tabular-nums"];
    return [name, style];
  }),
) as Record<TypeName, NativeTextStyle>;

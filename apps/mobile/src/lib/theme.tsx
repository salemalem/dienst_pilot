import { colors, type Theme, type ThemeId } from "@dienstpilot/design-tokens";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { StyleSheet, type ImageStyle, type TextStyle, type ViewStyle } from "react-native";

import { API_URL } from "./config";

export type ThemePref = "auto" | "light" | "dark";

/** Dark from 20:00 to 07:00 Europe/Berlin (UI_SPEC §2), read from an instant such as the demo clock. */
export function isNight(instant: string): boolean {
  const hour = Number(
    new Intl.DateTimeFormat("en-GB", {
      timeZone: "Europe/Berlin",
      hour: "numeric",
      hourCycle: "h23",
    }).format(new Date(instant)),
  );
  return hour >= 20 || hour < 7;
}

/** The theme in force: the person's choice, or "auto" by the demo clock (never the device clock). */
export function resolveTheme(pref: ThemePref, clockNow: string | null): ThemeId {
  if (pref === "light" || pref === "dark") return pref;
  return clockNow !== null && isNight(clockNow) ? "dark" : "light";
}

interface ThemeValue {
  theme: Theme;
  themeId: ThemeId;
  pref: ThemePref;
  setPref: (pref: ThemePref) => void;
  /** The demo clock's current instant (ISO), null until the API answered. */
  clockNow: string | null;
}

const Ctx = createContext<ThemeValue>({
  theme: colors.light,
  themeId: "light",
  pref: "auto",
  setPref: () => undefined,
  clockNow: null,
});

export const useTheme = (): ThemeValue => useContext(Ctx);

/** Re-reads the demo clock every 30 seconds, so the theme follows it (and the Administrator moving it). */
export function ThemeProvider({
  children,
  initialPref = "auto",
  onPref,
}: {
  children: ReactNode;
  initialPref?: ThemePref;
  onPref?: (pref: ThemePref) => void;
}): ReactNode {
  const [pref, setPrefState] = useState<ThemePref>(initialPref);
  const [clockNow, setClockNow] = useState<string | null>(null);

  useEffect(() => {
    setPrefState(initialPref);
  }, [initialPref]);

  useEffect(() => {
    let alive = true;
    const read = (): void => {
      fetch(`${API_URL}/clock`)
        .then((r) => r.json() as Promise<{ now: string }>)
        .then((c) => {
          if (alive) setClockNow(c.now);
        })
        .catch(() => undefined);
    };
    read();
    const id = setInterval(read, 30_000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const value = useMemo<ThemeValue>(() => {
    const themeId = resolveTheme(pref, clockNow);
    return {
      theme: colors[themeId],
      themeId,
      pref,
      clockNow,
      setPref: (next) => {
        setPrefState(next);
        onPref?.(next);
      },
    };
  }, [pref, clockNow, onPref]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** Styles that depend on the theme: `const s = useStyles(makeStyles)`. */
type Styles = Record<string, ViewStyle | TextStyle | ImageStyle>;

export function useStyles<T extends Styles>(make: (t: Theme) => T): T {
  const { theme } = useTheme();
  return useMemo(() => StyleSheet.create(make(theme)), [make, theme]);
}

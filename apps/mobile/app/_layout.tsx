import { useFonts } from "expo-font";
import { Redirect, Stack, usePathname } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useEffect, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Platform, View } from "react-native";

import "../src/i18n";
import { EnvBadge } from "../src/components/chrome";
import { SessionProvider, useSession } from "../src/lib/session";
import { useTheme } from "../src/lib/theme";

// The design system ships woff2 only, which iOS and Android cannot load. On web the real face is
// used; native falls back to the system font until TTF files are added.
const fontSources =
  Platform.OS === "web"
    ? {
        "Atkinson Hyperlegible Next":
          require("@dienstpilot/design-tokens/fonts/AtkinsonHyperlegibleNext-Variable.woff2") as number,
      }
    : {};

function Frame(): ReactNode {
  const { theme, themeId } = useTheme();
  const { i18n } = useTranslation();
  const { me, ready } = useSession();
  const pathname = usePathname();
  useEffect(() => {
    // The page language follows the app's (screen readers pick the voice from it).
    if (Platform.OS === "web") document.documentElement.lang = i18n.language;
  }, [i18n.language]);
  // Every screen but sign-in needs a signed-in person; each screen keeps its own URL.
  if (ready && !me && pathname !== "/sign-in") return <Redirect href="/sign-in" />;
  return (
    <View
      style={{ flex: 1, backgroundColor: theme.paper, paddingTop: Platform.OS === "web" ? 0 : 47 }}
    >
      <StatusBar style={themeId === "dark" ? "light" : "dark"} />
      <EnvBadge />
      <Stack
        screenOptions={{ headerShown: false, contentStyle: { backgroundColor: theme.paper } }}
      />
    </View>
  );
}

export default function Root(): ReactNode {
  const [loaded, error] = useFonts(fontSources);
  if (!loaded && error === null) return null;
  return (
    <SessionProvider>
      <Frame />
    </SessionProvider>
  );
}

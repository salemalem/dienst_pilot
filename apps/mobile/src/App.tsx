import { spacing } from "@dienstpilot/design-tokens";
import { useFonts } from "expo-font";
import { StatusBar } from "expo-status-bar";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Platform, ScrollView, StyleSheet, Text, View } from "react-native";

import "./i18n";
import { EnvBadge } from "./components/EnvBadge";
import { LocaleSwitch } from "./components/LocaleSwitch";
import { ShiftLegend } from "./components/ShiftLegend";
import { theme } from "./theme";
import { type } from "./type";

// The design system ships woff2 only, which iOS and Android cannot load. On web the real face is
// used; native falls back to the system font until TTF files are added.
const fontSources =
  Platform.OS === "web"
    ? {
        "Atkinson Hyperlegible Next":
          require("@dienstpilot/design-tokens/fonts/AtkinsonHyperlegibleNext-Variable.woff2") as number,
      }
    : {};

export function App(): ReactNode {
  const { t } = useTranslation();
  const [fontsLoaded, fontError] = useFonts(fontSources);
  if (!fontsLoaded && fontError === null) return null;

  return (
    <View style={styles.root}>
      <StatusBar style="dark" />
      <EnvBadge />
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <Text style={[type.title, styles.ink]}>{t("app.name")}</Text>
          <LocaleSwitch />
        </View>
        <Text style={[type.caption, styles.muted]}>{t("app.department")}</Text>
        <Text style={[type.title, styles.ink]}>{t("shell.mobileTitle")}</Text>
        <Text style={[type.body, styles.muted]}>{t("shell.scaffold")}</Text>
        <ShiftLegend />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: theme.paper, paddingTop: Platform.OS === "web" ? 0 : 47 },
  content: { padding: spacing[4], gap: spacing[3] },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing[3],
  },
  ink: { color: theme.ink },
  muted: { color: theme.inkMuted },
});

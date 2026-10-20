import { spacing } from "@dienstpilot/design-tokens";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { StyleSheet, Text, View } from "react-native";

import { theme } from "../theme";
import { type } from "../type";

/** Full-width strip under the status bar: "Demo-Umgebung, synthetische Daten". Never dismissible. */
export function EnvBadge(): ReactNode {
  const { t } = useTranslation();
  return (
    <View accessibilityRole="summary" style={styles.bar}>
      <Text style={[type.caption, styles.text]}>{t("app.env")}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    height: 28,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing[2],
    backgroundColor: theme.envWash,
    borderBottomWidth: 1,
    borderBottomColor: theme.env,
  },
  text: { color: theme.env },
});

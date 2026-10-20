import { locales, type Locale } from "@dienstpilot/i18n";
import { radius, size } from "@dienstpilot/design-tokens";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { theme } from "../theme";
import { type } from "../type";

/** DE | EN toggle. Switches the language at runtime. */
export function LocaleSwitch(): ReactNode {
  const { t, i18n } = useTranslation();
  const active = i18n.language as Locale;
  return (
    <View
      accessibilityRole="radiogroup"
      accessibilityLabel={t("locale.label")}
      style={styles.group}
    >
      {locales.map((locale) => {
        const on = locale === active;
        return (
          <Pressable
            key={locale}
            accessibilityRole="radio"
            accessibilityState={{ checked: on }}
            accessibilityLabel={t(`locale.${locale}`)}
            onPress={() => void i18n.changeLanguage(locale)}
            style={[styles.option, on && styles.optionOn]}
          >
            <Text style={[type.label, { color: on ? theme.onAction : theme.ink }]}>
              {locale.toUpperCase()}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  group: {
    flexDirection: "row",
    gap: 2,
    padding: 2,
    borderWidth: 1,
    borderColor: theme.ruleStrong,
    borderRadius: radius.control,
    backgroundColor: theme.sheet,
  },
  option: {
    minWidth: size.touchMin,
    height: size.touchMin - 6,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 4,
  },
  optionOn: { backgroundColor: theme.action },
});

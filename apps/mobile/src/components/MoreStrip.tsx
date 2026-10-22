import { spacing } from "@dienstpilot/design-tokens";
import { useRouter } from "expo-router";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, View } from "react-native";

import { useTheme } from "../lib/theme";
import { TOUCH_MIN, Txt } from "./ui";

const ITEMS = [
  { key: "fairness", href: "/fairness" },
  { key: "hours", href: "/hours" },
  { key: "settings", href: "/settings" },
] as const;

/** The "Mehr" screens (M9, M10, M12) share one strip: Fairness-Bilanz | Stunden | Einstellungen. */
export function MoreStrip({ active }: { active: (typeof ITEMS)[number]["key"] }): ReactNode {
  const { t } = useTranslation();
  const { theme } = useTheme();
  const router = useRouter();
  return (
    <View
      accessibilityRole="tablist"
      style={{
        flexDirection: "row",
        gap: spacing[4],
        borderBottomWidth: 1,
        borderBottomColor: theme.rule,
        marginHorizontal: -spacing[4],
        paddingHorizontal: spacing[4],
      }}
    >
      {ITEMS.map((i) => {
        const on = i.key === active;
        return (
          <Pressable
            key={i.key}
            accessibilityRole="tab"
            accessibilityLabel={t(`more.${i.key}`)}
            accessibilityState={{ selected: on }}
            aria-selected={on}
            onPress={() => {
              if (!on) router.replace(i.href);
            }}
            testID={`more-${i.key}`}
            style={{
              minHeight: TOUCH_MIN,
              minWidth: TOUCH_MIN,
              alignItems: "center",
              justifyContent: "center",
              borderBottomWidth: 3,
              borderBottomColor: on ? theme.action : "transparent",
            }}
          >
            <Txt variant="label" color={on ? theme.action : theme.ink}>
              {t(`more.${i.key}`)}
            </Txt>
          </Pressable>
        );
      })}
    </View>
  );
}

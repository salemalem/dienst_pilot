import { spacing, type Theme } from "@dienstpilot/design-tokens";
import { useRouter } from "expo-router";
import { ChevronLeft } from "lucide-react-native";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, ScrollView, View } from "react-native";

import { useStyles, useTheme } from "../lib/theme";
import { TOUCH_MIN, Txt } from "./ui";

const screenStyles = (t: Theme) => ({
  root: { flex: 1, backgroundColor: t.paper },
  content: { padding: spacing[4], gap: spacing[4], paddingBottom: spacing[6] },
  footer: {
    padding: spacing[4],
    gap: spacing[2],
    backgroundColor: t.sheet,
    borderTopWidth: 1,
    borderTopColor: t.rule,
  },
});

/**
 * A screen: status line first (what do I need to know or do now), then the detail. The primary
 * actions sit in `footer`, at the bottom of the screen, within thumb reach.
 */
export function Screen({
  title,
  status,
  children,
  footer,
  testID,
  back,
}: {
  back?: boolean;
  title: string;
  status?: string | undefined;
  children: ReactNode;
  footer?: ReactNode;
  testID?: string;
}): ReactNode {
  const s = useStyles(screenStyles);
  const router = useRouter();
  const { t } = useTranslation();
  const { theme } = useTheme();
  return (
    <View style={s.root} testID={testID}>
      <ScrollView
        tabIndex={0}
        contentContainerStyle={s.content}
        keyboardShouldPersistTaps="handled"
      >
        {back === true ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t("common.back")}
            onPress={() => {
              if (router.canGoBack()) router.back();
              else router.replace("/today");
            }}
            style={{
              minHeight: TOUCH_MIN,
              alignSelf: "flex-start",
              flexDirection: "row",
              alignItems: "center",
              gap: spacing[1],
              marginLeft: -spacing[2],
              paddingHorizontal: spacing[2],
            }}
          >
            <ChevronLeft size={20} color={theme.action} strokeWidth={1.75} />
            <Txt variant="label" color={theme.action}>
              {t("common.back")}
            </Txt>
          </Pressable>
        ) : null}
        <View style={{ gap: spacing[1] }}>
          <Txt variant="title" accessibilityRole="header">
            {title}
          </Txt>
          {status !== undefined && status !== "" ? (
            <Txt variant="body" muted>
              {status}
            </Txt>
          ) : null}
        </View>
        {children}
      </ScrollView>
      {footer ? <View style={s.footer}>{footer}</View> : null}
    </View>
  );
}

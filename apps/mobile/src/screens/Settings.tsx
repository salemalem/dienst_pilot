import { unwrap } from "@dienstpilot/api-client";
import { locales, type Locale } from "@dienstpilot/i18n";
import { spacing } from "@dienstpilot/design-tokens";
import { useRouter } from "expo-router";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import { DemoMenu } from "../components/DemoMenu";
import { MoreStrip } from "../components/MoreStrip";
import { Screen } from "../components/Screen";
import { Button, Card, Segmented, ToggleRow, Txt } from "../components/ui";
import { setLanguage } from "../i18n";
import { useFmt } from "../lib/fmt";
import { useQuery } from "../lib/hooks";
import { useSession } from "../lib/session";
import { useTheme, type ThemePref } from "../lib/theme";

/** M12: language, theme (automatic by the demo clock, with a manual override), switches, demo menu. */
export function SettingsScreen(): ReactNode {
  const { t, i18n } = useTranslation();
  const fmt = useFmt();
  const router = useRouter();
  const { me, settings, saveSettings, signOut } = useSession();
  const { pref, setPref, themeId, clockNow } = useTheme();
  const clock = useQuery((a) => unwrap(a.GET("/clock")), []);
  const lang = (i18n.language === "en" ? "en" : "de") as Locale;
  const now = clockNow ?? clock.data?.now ?? null;
  return (
    <Screen
      title={me?.display_name ?? t("m12.title")}
      eyebrow={t("m12.title")}
      strip={<MoreStrip active="settings" />}
      testID="screen-settings"
    >
      <View
        style={{
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "space-between",
          gap: spacing[3],
        }}
      >
        <Txt muted style={{ flex: 1 }}>
          {t("app.department")}
        </Txt>
        <Button
          label={t("m12.signOut")}
          onPress={() => {
            signOut();
            router.replace("/sign-in");
          }}
          testID="sign-out"
        />
      </View>
      <View style={{ gap: spacing[2] }}>
        <Txt variant="label">{t("m12.language")}</Txt>
        <Segmented
          label={t("m12.language")}
          value={lang}
          options={locales.map((l) => ({ value: l, label: t(`locale.${l}`) }))}
          onChange={(l) => {
            setLanguage(l);
            void saveSettings({ language: l });
          }}
          testID="settings-language"
        />
      </View>
      <View style={{ gap: spacing[2] }}>
        <Txt variant="label">{t("m12.theme")}</Txt>
        <Segmented<ThemePref>
          label={t("m12.theme")}
          value={pref}
          options={[
            { value: "auto", label: t("m12.themeAuto") },
            { value: "light", label: t("m12.themeLight") },
            { value: "dark", label: t("m12.themeDark") },
          ]}
          onChange={setPref}
          testID="settings-theme"
        />
        <Txt variant="caption" muted testID="theme-note">
          {pref === "auto"
            ? t("m12.themeAutoNote", {
                time: now ? fmt.time(now) : "",
                theme: t(`m12.now.${themeId}`),
              })
            : t("m12.themeFixedNote")}
        </Txt>
      </View>
      {settings ? (
        <Card style={{ gap: 0 }}>
          <ToggleRow
            label={t("m12.notifications")}
            value={settings.notifications}
            onChange={(v) => void saveSettings({ notifications: v })}
            testID="toggle-notifications"
          />
          <ToggleRow
            label={t("m12.sync")}
            hint={t("m12.syncHint")}
            value={settings.calendar_sync}
            onChange={(v) => void saveSettings({ calendar_sync: v })}
            testID="toggle-sync"
          />
          <ToggleRow
            label={t("m12.suggestions")}
            hint={t("m12.suggestionsHint")}
            value={settings.preference_suggestions}
            onChange={(v) => void saveSettings({ preference_suggestions: v })}
            testID="toggle-suggestions"
          />
        </Card>
      ) : null}
      <DemoMenu />
    </Screen>
  );
}

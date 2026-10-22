import { locales, type Locale } from "@dienstpilot/i18n";
import { radius, spacing } from "@dienstpilot/design-tokens";
import { FlaskConical, PencilLine } from "lucide-react-native";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import { setLanguage } from "../i18n";
import { useTheme } from "../lib/theme";
import { Segmented, Txt } from "./ui";

/** Full-width strip under the status bar: "Demo-Umgebung, synthetische Daten". Never dismissible. */
export function EnvBadge(): ReactNode {
  const { t } = useTranslation();
  const { theme } = useTheme();
  return (
    <View
      accessibilityRole="summary"
      style={{
        minHeight: 28,
        flexDirection: "row",
        gap: spacing[2],
        alignItems: "center",
        justifyContent: "center",
        paddingHorizontal: spacing[2],
        backgroundColor: theme.envWash,
        borderBottomWidth: 1,
        borderBottomColor: theme.env,
      }}
    >
      <FlaskConical size={14} color={theme.env} strokeWidth={1.75} />
      <Txt variant="caption" color={theme.env}>
        {t("app.env")}
      </Txt>
    </View>
  );
}

/** DE | EN toggle; the choice is remembered on the device. */
export function LocaleSwitch(): ReactNode {
  const { t, i18n } = useTranslation();
  const active = (i18n.language === "en" ? "en" : "de") as Locale;
  return (
    <Segmented
      label={t("locale.label")}
      value={active}
      options={locales.map((l) => ({ value: l, label: t(`locale.${l}`) }))}
      onChange={setLanguage}
      testID="locale"
    />
  );
}

export interface EngineLabel {
  component: string;
  implementation: string;
  version: string;
  note: string;
}

/**
 * Marks text a language model wrote ("KI-generiert"), and says when it is a recording of a real
 * answer (screenshots, tests) rather than a live one. Every AI-generated text carries it.
 */
export function AiLabel({ replayed = false }: { replayed?: boolean }): ReactNode {
  const { t } = useTranslation();
  const { theme } = useTheme();
  return (
    <View
      testID="ai-label"
      accessible
      accessibilityLabel={
        replayed ? `${t("ai.generated")}, ${t("ai.recorded")}` : t("ai.generated")
      }
      style={{
        alignSelf: "flex-start",
        borderWidth: 1,
        borderColor: theme.ruleStrong,
        borderRadius: radius.mark,
        paddingHorizontal: spacing[2],
        paddingVertical: 2,
      }}
    >
      <Txt variant="caption" color={theme.inkMuted}>
        {t("ai.generated")}
        {replayed ? ` · ${t("ai.recorded")}` : ""}
      </Txt>
    </View>
  );
}

/**
 * Tells whether an answer came from a built component or a stand-in, as the API reports it:
 * the same label as the dashboard ("C6 · Platzhalter · standin-0.1"), driven by `engine`.
 */
export function EngineBadge({ engine }: { engine: EngineLabel }): ReactNode {
  const { t } = useTranslation();
  const { theme } = useTheme();
  const standIn = engine.implementation === "stand-in";
  return (
    <View
      accessible
      accessibilityLabel={`${engine.component}, ${standIn ? t("common.standIn") : t("common.built")}`}
      testID={`engine-${engine.component}`}
      style={{
        alignSelf: "flex-start",
        flexDirection: "row",
        alignItems: "center",
        gap: 4,
        borderWidth: 1,
        borderStyle: standIn ? "dashed" : "solid",
        borderColor: standIn ? theme.pencil : theme.ruleStrong,
        backgroundColor: standIn ? theme.pencilWash : "transparent",
        borderRadius: radius.mark,
        paddingHorizontal: spacing[2],
        paddingVertical: 2,
      }}
    >
      {standIn ? <PencilLine size={12} color={theme.pencil} strokeWidth={1.75} /> : null}
      <Txt variant="caption" color={standIn ? theme.pencil : theme.inkMuted}>
        {engine.component} · {standIn ? t("common.standIn") : t("common.built")} · {engine.version}
      </Txt>
    </View>
  );
}

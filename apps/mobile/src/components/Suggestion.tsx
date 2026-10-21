import { radius, spacing } from "@dienstpilot/design-tokens";
import { CircleQuestionMark, PencilLine } from "lucide-react-native";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, View } from "react-native";

import { useTheme } from "../lib/theme";
import { EngineBadge, type EngineLabel } from "./chrome";
import { TOUCH_MIN, Txt } from "./ui";

/**
 * Everything the system proposes is pencil until a person acts on it, always with "Warum? / Why?"
 * and, for C3 to C8, the stand-in label from the API's `engine`. Never a publish or approve action.
 */
export function Suggestion({
  engine,
  children,
  reasons,
  actions,
  testID,
}: {
  engine?: EngineLabel | undefined;
  children: ReactNode;
  reasons?: string[];
  actions?: ReactNode;
  testID?: string;
}): ReactNode {
  const { t } = useTranslation();
  const { theme } = useTheme();
  const [open, setOpen] = useState(false);
  return (
    <View
      testID={testID}
      style={{
        backgroundColor: theme.pencilWash,
        borderWidth: 1.5,
        borderStyle: "dashed",
        borderColor: theme.pencil,
        borderRadius: radius.panel,
        padding: spacing[4],
        gap: spacing[3],
      }}
    >
      <View
        style={{ flexDirection: "row", alignItems: "center", gap: spacing[2], flexWrap: "wrap" }}
      >
        <PencilLine size={16} color={theme.pencil} strokeWidth={1.75} />
        <Txt variant="label" color={theme.pencil}>
          {t("common.suggestion")}
        </Txt>
        {engine ? <EngineBadge engine={engine} /> : null}
      </View>
      <View style={{ gap: spacing[2] }}>{children}</View>
      <View
        style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing[2], alignItems: "center" }}
      >
        {actions}
        {reasons && reasons.length > 0 ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t("common.why")}
            accessibilityState={{ expanded: open }}
            onPress={() => {
              setOpen((v) => !v);
            }}
            style={{
              minHeight: TOUCH_MIN,
              minWidth: TOUCH_MIN,
              flexDirection: "row",
              alignItems: "center",
              gap: spacing[1],
              paddingHorizontal: spacing[2],
              marginLeft: "auto",
            }}
          >
            <CircleQuestionMark size={16} color={theme.ink} strokeWidth={1.75} />
            <Txt variant="label">{t("common.why")}</Txt>
          </Pressable>
        ) : null}
      </View>
      {open && reasons ? (
        <View
          style={{
            borderTopWidth: 1,
            borderTopColor: theme.pencil,
            borderStyle: "dashed",
            paddingTop: spacing[3],
            gap: spacing[1],
          }}
        >
          {reasons.map((r) => (
            <Txt key={r}>{`• ${r}`}</Txt>
          ))}
          <Txt variant="caption" muted>
            {t("common.suggestionNote")}
          </Txt>
        </View>
      ) : null}
    </View>
  );
}

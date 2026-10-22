import { unwrap, type components } from "@dienstpilot/api-client";
import { spacing } from "@dienstpilot/design-tokens";
import { Bell } from "lucide-react-native";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import { Async, Card, Txt } from "../components/ui";
import { Screen } from "../components/Screen";
import { useFmt } from "../lib/fmt";
import { useQuery } from "../lib/hooks";
import { useTheme } from "../lib/theme";

type Note = components["schemas"]["Notification"];

/** M11: roster published or changed (with the reason), swaps, leave decided (with the reason), cover. */
export function NotificationsScreen(): ReactNode {
  const { t } = useTranslation();
  const { theme } = useTheme();
  const fmt = useFmt();
  const q = useQuery((a) => unwrap(a.GET("/me/notifications")), []);
  const text = (n: Note): string => {
    const d = n.data;
    const s = (k: string): string => d[k] ?? "";
    const key = `notification.${n.kind}`;
    return t(key, {
      defaultValue: n.kind,
      month: s("roster_month") ? fmt.month(s("roster_month")) : "",
      date: s("date") ? fmt.dayMonth(s("date")) : "",
      range: s("start_date") && s("end_date") ? fmt.range(s("start_date"), s("end_date")) : "",
      shift: s("shift_type") ? t(`shift.${s("shift_type") as "frueh"}.name`) : "",
      closes: s("closes_at") ? fmt.dateTime(s("closes_at")) : "",
      reason: s("reason"),
      change: s("change") ? t(`notification.change.${s("change") as "added"}`) : "",
    });
  };
  return (
    <Screen
      title={t("m11.title")}
      status={q.data ? t("m11.status", { count: q.data.length }) : undefined}
      testID="screen-notifications"
    >
      <Async query={q}>
        {(list) => (
          <View style={{ gap: spacing[2] }}>
            {list.length === 0 ? <Txt muted>{t("m11.empty")}</Txt> : null}
            {list.map((n, i) => (
              <Card key={`${n.kind}-${n.at}-${String(i)}`} testID={`note-${n.kind}`}>
                <View style={{ flexDirection: "row", gap: spacing[2], alignItems: "flex-start" }}>
                  <Bell size={18} color={theme.ink} strokeWidth={1.75} />
                  <View style={{ flex: 1, gap: 2 }}>
                    <Txt variant="bodyStrong">{text(n)}</Txt>
                    <Txt variant="caption" muted>
                      {fmt.dateTime(n.at)}
                    </Txt>
                  </View>
                </View>
              </Card>
            ))}
          </View>
        )}
      </Async>
    </Screen>
  );
}

import { unwrap } from "@dienstpilot/api-client";
import { addMonths } from "@dienstpilot/i18n";
import { spacing } from "@dienstpilot/design-tokens";
import { CircleCheck } from "lucide-react-native";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import { EngineBadge } from "../components/chrome";
import { MoreStrip } from "../components/MoreStrip";
import { Screen } from "../components/Screen";
import { Async, Card, Segmented, Txt } from "../components/ui";
import { useFmt } from "../lib/fmt";
import { useQuery } from "../lib/hooks";
import { useTheme } from "../lib/theme";

/** M10: contract hours, worked, overtime and rest-period compliance (from C2) for a month. */
export function HoursScreen(): ReactNode {
  const { t } = useTranslation();
  const { theme } = useTheme();
  const fmt = useFmt();
  const today = useQuery((a) => unwrap(a.GET("/me/today")), []);
  const [picked, setPicked] = useState<string | null>(null);
  const current = today.data?.now.slice(0, 7) ?? null;
  const month = picked ?? current;
  const q = useQuery(
    (a) =>
      month ? unwrap(a.GET("/me/hours", { params: { query: { month } } })) : Promise.resolve(null),
    [month],
  );
  return (
    <Screen
      title={q.data ? t("m10.overtimeMonth") : t("m10.title")}
      eyebrow={
        month
          ? t("m10.eyebrow", {
              month: fmt.month(month),
              date: today.data ? fmt.dayMonth(today.data.now.slice(0, 10)) : "",
            })
          : undefined
      }
      strip={<MoreStrip active="hours" />}
      testID="screen-hours"
    >
      {current ? (
        <Segmented
          label={t("m10.title")}
          value={month ?? current}
          options={[addMonths(current, -1), current].map((m) => ({
            value: m,
            label: fmt.monthShort(m),
          }))}
          onChange={setPicked}
          testID="hours-month"
        />
      ) : null}
      <Async query={q}>
        {(h) =>
          h ? (
            <View style={{ gap: spacing[3] }}>
              <Txt variant="display" testID="overtime">
                {fmt.hours(h.overtime_hours)}
              </Txt>
              <Card style={{ padding: 0, gap: 0 }}>
                {(
                  [
                    [t("m10.contract"), fmt.hours(h.contract_hours), false],
                    [t("m10.worked"), fmt.hours(h.worked_hours), false],
                    [t("m10.planned"), fmt.hours(h.planned_hours), false],
                    [t("m10.leaveCredit"), fmt.hours(h.leave_credit_hours), false],
                    [t("m10.overtime"), fmt.hours(h.overtime_hours), true],
                  ] as const
                ).map(([k, v, strong], i) => (
                  <View
                    key={k}
                    style={{
                      flexDirection: "row",
                      justifyContent: "space-between",
                      padding: spacing[3],
                      borderTopWidth: i === 0 ? 0 : 1,
                      borderTopColor: theme.rule,
                    }}
                  >
                    <Txt variant={strong ? "bodyStrong" : "body"}>{k}</Txt>
                    <Txt variant="bodyStrong">{v}</Txt>
                  </View>
                ))}
              </Card>
              {h.rest_compliance ? (
                <Card>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: spacing[2] }}>
                    {h.rest_compliance.compliant ? (
                      <CircleCheck size={20} color={theme.ink} strokeWidth={1.75} />
                    ) : null}
                    <Txt variant="heading">
                      {h.rest_compliance.compliant ? t("m10.restAllOk") : t("m10.rest")}
                    </Txt>
                  </View>
                  <Txt testID="rest">
                    {h.rest_compliance.compliant
                      ? t("m10.restOk", { hours: h.rest_compliance.min_rest_hours })
                      : t("m10.restViolations", {
                          count: h.rest_compliance.violations,
                          hours: h.rest_compliance.min_rest_hours,
                        })}
                  </Txt>
                  <EngineBadge engine={h.rest_compliance.validator} />
                </Card>
              ) : null}
              <Txt variant="caption" muted>
                {t("m10.footnote")}
              </Txt>
            </View>
          ) : null
        }
      </Async>
    </Screen>
  );
}

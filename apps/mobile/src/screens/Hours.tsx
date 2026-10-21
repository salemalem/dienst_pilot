import { unwrap } from "@dienstpilot/api-client";
import { spacing } from "@dienstpilot/design-tokens";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import { EngineBadge } from "../components/chrome";
import { MonthCalendar } from "../components/MonthCalendar";
import { Async, Card, Txt } from "../components/ui";
import { Screen } from "../components/Screen";
import { useFmt } from "../lib/fmt";
import { useQuery } from "../lib/hooks";

/** M10: contract hours, worked, overtime and rest-period compliance (from C2) for a month. */
export function HoursScreen(): ReactNode {
  const { t } = useTranslation();
  const fmt = useFmt();
  const today = useQuery((a) => unwrap(a.GET("/me/today")), []);
  const [picked, setPicked] = useState<string | null>(null);
  const month = picked ?? today.data?.now.slice(0, 7) ?? null;
  const q = useQuery(
    (a) =>
      month ? unwrap(a.GET("/me/hours", { params: { query: { month } } })) : Promise.resolve(null),
    [month],
  );
  const rows = (h: NonNullable<typeof q.data>): [string, string][] => [
    [t("m10.contract"), fmt.hours(h.contract_hours)],
    [t("m10.planned"), fmt.hours(h.planned_hours)],
    [t("m10.worked"), fmt.hours(h.worked_hours)],
    [t("m10.leaveCredit"), fmt.hours(h.leave_credit_hours)],
  ];
  return (
    <Screen
      title={t("m10.title")}
      status={month ? fmt.month(month) : undefined}
      back
      testID="screen-hours"
    >
      {month ? (
        <MonthCalendar
          month={month}
          onMonth={setPicked}
          decorate={() => ({ disabled: true })}
          testID="hours-month"
        />
      ) : null}
      <Async query={q}>
        {(h) =>
          h ? (
            <View style={{ gap: spacing[3] }}>
              <Card>
                <Txt variant="label" muted>
                  {t("m10.overtimeMonth")}
                </Txt>
                <Txt variant="numFigure" testID="overtime">
                  {fmt.hours(h.overtime_hours)}
                </Txt>
              </Card>
              <Card>
                {rows(h).map(([k, v]) => (
                  <View key={k} style={{ flexDirection: "row", justifyContent: "space-between" }}>
                    <Txt>{k}</Txt>
                    <Txt variant="bodyStrong">{v}</Txt>
                  </View>
                ))}
              </Card>
              {h.rest_compliance ? (
                <Card>
                  <Txt variant="heading">{t("m10.rest")}</Txt>
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
            </View>
          ) : null
        }
      </Async>
    </Screen>
  );
}

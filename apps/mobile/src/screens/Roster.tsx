import { unwrap } from "@dienstpilot/api-client";
import { spacing } from "@dienstpilot/design-tokens";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import { MonthCalendar } from "../components/MonthCalendar";
import { ShiftChip, ShiftLabel, ShiftLegend } from "../components/ShiftChip";
import { Async, Card, ToggleRow, Txt } from "../components/ui";
import { Screen } from "../components/Screen";
import { useFmt } from "../lib/fmt";
import { useQuery } from "../lib/hooks";
import { useSession } from "../lib/session";

/** M3: my roster as a month view with letter chips, the list below it, and the calendar-sync toggle. */
export function RosterScreen(): ReactNode {
  const { t } = useTranslation();
  const fmt = useFmt();
  const { settings, saveSettings } = useSession();
  const today = useQuery((api) => unwrap(api.GET("/me/today")), []);
  const [picked, setPicked] = useState<string | null>(null);
  const month = picked ?? today.data?.now.slice(0, 7) ?? null;
  const q = useQuery(
    (api) =>
      month
        ? unwrap(api.GET("/me/roster", { params: { query: { month } } }))
        : Promise.resolve(null),
    [month],
  );
  if (!month) return <Screen title={t("m3.title")}>{null}</Screen>;
  return (
    <Screen
      title={t("m3.title")}
      status={
        q.data?.published_at
          ? t("m3.published", { date: fmt.date(q.data.published_at) })
          : undefined
      }
      testID="screen-roster"
    >
      <Async query={q}>
        {(r) => {
          if (!r) return null;
          const byDay = new Map(r.days.map((d) => [d.date, d]));
          const working = r.days.filter((d) => d.shifts.length > 0);
          return (
            <>
              <Card>
                <MonthCalendar
                  month={month}
                  onMonth={setPicked}
                  testID="calendar"
                  renderShift={(c) => <ShiftChip code={c} box={22} />}
                  decorate={(date) => {
                    const d = byDay.get(date);
                    return {
                      shifts: d?.shifts.map((s) => s.shift_type) ?? [],
                      description: d?.shifts.length
                        ? d.shifts.map((s) => t(`shift.${s.shift_type as "frueh"}.name`)).join(", ")
                        : t("m3.free"),
                    };
                  }}
                />
              </Card>
              <View style={{ gap: spacing[2] }}>
                <Txt variant="heading" accessibilityRole="header">
                  {t("m3.list")}
                </Txt>
                {working.length === 0 ? <Txt muted>{t("m3.empty")}</Txt> : null}
                {working.map((d) =>
                  d.shifts.map((s) => (
                    <Card key={s.assignment_id}>
                      <View
                        style={{
                          flexDirection: "row",
                          alignItems: "center",
                          justifyContent: "space-between",
                          gap: spacing[2],
                        }}
                      >
                        <ShiftLabel code={s.shift_type} />
                        <View style={{ alignItems: "flex-end" }}>
                          <Txt variant="bodyStrong">
                            {fmt.weekday(d.date)} {fmt.dayMonth(d.date)}
                          </Txt>
                          {s.starts_at && s.ends_at ? (
                            <Txt variant="caption" muted>
                              {fmt.time(s.starts_at)}–{fmt.time(s.ends_at)}
                            </Txt>
                          ) : null}
                        </View>
                      </View>
                      {s.changed ? (
                        <Txt variant="label" testID={`changed-${s.assignment_id}`}>
                          {t("m3.changed")}
                        </Txt>
                      ) : null}
                      {d.wish ? (
                        <Txt variant="caption" muted>
                          {t(`m3.wish.${d.wish}`)}
                        </Txt>
                      ) : null}
                    </Card>
                  )),
                )}
              </View>
              <ShiftLegend />
              {settings ? (
                <ToggleRow
                  label={t("m3.sync")}
                  value={settings.calendar_sync}
                  onChange={(v) => void saveSettings({ calendar_sync: v })}
                  testID="sync-toggle"
                />
              ) : null}
            </>
          );
        }}
      </Async>
    </Screen>
  );
}

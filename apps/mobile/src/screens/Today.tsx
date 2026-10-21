import { unwrap } from "@dienstpilot/api-client";
import { spacing } from "@dienstpilot/design-tokens";
import { useRouter } from "expo-router";
import { Bell, CalendarClock, Plane, Repeat2, ThermometerSun } from "lucide-react-native";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import { ShiftChip, ShiftLabel } from "../components/ShiftChip";
import { Async, Button, Card, Txt } from "../components/ui";
import { Screen } from "../components/Screen";
import { useFmt } from "../lib/fmt";
import { useQuery } from "../lib/hooks";
import { useTheme } from "../lib/theme";

/** M2: status first: the next shift, what is open (wishes, cover request), and the quick actions. */
export function TodayScreen(): ReactNode {
  const { t } = useTranslation();
  const { theme } = useTheme();
  const fmt = useFmt();
  const router = useRouter();
  const q = useQuery((api) => unwrap(api.GET("/me/today")), []);
  return (
    <Async query={q}>
      {(d) => {
        const next = d.next_shift;
        const cover = d.cover_requests[0];
        const status = cover
          ? t("m2.statusCover")
          : next
            ? t("m2.statusNext", {
                day: fmt.weekday(next.shift.date),
                date: fmt.dayMonth(next.shift.date),
              })
            : t("m2.statusNone");
        return (
          <Screen
            title={t("m2.title", { name: d.display_name })}
            status={status}
            testID="screen-today"
            footer={
              <View style={{ flexDirection: "row", gap: spacing[2] }}>
                <Button
                  label={t("m2.sick")}
                  kind="primary"
                  style={{ flex: 1 }}
                  icon={<ThermometerSun size={18} color={theme.onInk} strokeWidth={1.75} />}
                  onPress={() => {
                    router.push("/sick");
                  }}
                  testID="quick-sick"
                />
                <Button
                  label={t("m2.swap")}
                  style={{ flex: 1 }}
                  icon={<Repeat2 size={18} color={theme.ink} strokeWidth={1.75} />}
                  onPress={() => {
                    router.push("/swap");
                  }}
                  testID="quick-swap"
                />
              </View>
            }
          >
            {cover ? (
              <Card dashed>
                <View style={{ flexDirection: "row", alignItems: "center", gap: spacing[2] }}>
                  <Bell size={20} color={theme.pencil} strokeWidth={1.75} />
                  <Txt variant="heading">{t("m2.coverTitle")}</Txt>
                </View>
                <ShiftLabel code={cover.shift.shift_type} />
                <Txt>
                  {fmt.weekday(cover.shift.date)} {fmt.dayMonth(cover.shift.date)}
                  {cover.shift.starts_at && cover.shift.ends_at
                    ? `, ${fmt.time(cover.shift.starts_at)}–${fmt.time(cover.shift.ends_at)}`
                    : ""}
                </Txt>
                {cover.deadline_at ? (
                  <Txt variant="bodyStrong">
                    {t("m8.replyBy", { time: fmt.time(cover.deadline_at) })}
                  </Txt>
                ) : null}
                <Button
                  label={t("m2.coverOpen")}
                  kind="primary"
                  onPress={() => {
                    router.push("/cover");
                  }}
                  testID="open-cover"
                />
              </Card>
            ) : null}
            <Card>
              <Txt variant="label" muted>
                {t("m2.nextShift")}
              </Txt>
              {next ? (
                <>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: spacing[3] }}>
                    <ShiftChip code={next.shift.shift_type} box={48} />
                    <View style={{ flex: 1 }}>
                      <Txt variant="heading">
                        {t(`shift.${next.shift.shift_type as "frueh"}.name`)}
                      </Txt>
                      <Txt variant="bodyStrong">
                        {fmt.weekday(next.shift.date)} {fmt.date(next.shift.date)}
                      </Txt>
                      {next.shift.starts_at && next.shift.ends_at ? (
                        <Txt muted>
                          {fmt.time(next.shift.starts_at)}–{fmt.time(next.shift.ends_at)}
                        </Txt>
                      ) : null}
                    </View>
                  </View>
                  {next.colleagues.length > 0 ? (
                    <View>
                      <Txt variant="label" muted>
                        {t("m2.colleagues")}
                      </Txt>
                      <Txt>{next.colleagues.map((c) => c.display_name).join(", ")}</Txt>
                    </View>
                  ) : null}
                </>
              ) : (
                <Txt>{t("m2.noShift")}</Txt>
              )}
            </Card>
            {d.open_window ? (
              <Card>
                <View style={{ flexDirection: "row", alignItems: "center", gap: spacing[2] }}>
                  <CalendarClock size={20} color={theme.ink} strokeWidth={1.75} />
                  <Txt variant="heading">
                    {t("m2.wishes", {
                      month: fmt.monthShort(d.open_window.roster_month),
                      days: d.open_window.days_left,
                    })}
                  </Txt>
                </View>
                <Button
                  label={t("m2.wishesOpen")}
                  onPress={() => {
                    router.push("/wishes");
                  }}
                  testID="open-wishes"
                />
              </Card>
            ) : null}
            <Card>
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing[2] }}>
                <Plane size={20} color={theme.ink} strokeWidth={1.75} />
                <Txt variant="heading">{t("m2.leave")}</Txt>
              </View>
              <Button
                label={t("m5.requestLeave")}
                onPress={() => {
                  router.push("/leave");
                }}
                testID="open-leave"
              />
            </Card>
          </Screen>
        );
      }}
    </Async>
  );
}

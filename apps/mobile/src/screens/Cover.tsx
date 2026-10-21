import { unwrap } from "@dienstpilot/api-client";
import { spacing } from "@dienstpilot/design-tokens";
import { useRouter } from "expo-router";
import { CircleCheck, Timer } from "lucide-react-native";
import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import { ShiftChip } from "../components/ShiftChip";
import { Async, Button, Card, ErrorBox, Txt } from "../components/ui";
import { Screen } from "../components/Screen";
import { formatCountdown } from "../lib/countdown";
import { useFmt } from "../lib/fmt";
import { useAction, useQuery } from "../lib/hooks";
import { useSession } from "../lib/session";
import { useTheme } from "../lib/theme";

/** M8: a cover request from the colleague's side: shift, countdown, hours impact, accept or decline. */
export function CoverScreen(): ReactNode {
  const { t } = useTranslation();
  const { theme } = useTheme();
  const fmt = useFmt();
  const router = useRouter();
  const { api } = useSession();
  const q = useQuery((a) => unwrap(a.GET("/me/cover-requests")), []);
  const [answer, setAnswer] = useState<null | {
    accepted: boolean;
    status: string;
    reason: string | null;
  }>(null);

  // The countdown follows the demo clock: the list is read again every 15 seconds.
  const reload = q.reload;
  useEffect(() => {
    const id = setInterval(reload, 15_000);
    return () => {
      clearInterval(id);
    };
  }, [reload]);

  const respond = useAction(async (offerId: string, accept: boolean) => {
    const r = await unwrap(
      api.POST("/me/cover-requests/{offer_id}", {
        params: { path: { offer_id: offerId } },
        body: { accept },
      }),
    );
    setAnswer({ accepted: accept, status: r.status, reason: r.escalation_reason ?? null });
    q.reload();
  });

  if (answer) {
    return (
      <Screen
        title={answer.accepted ? t("m8.confirmedTitle") : t("m8.declinedTitle")}
        status={
          answer.accepted
            ? answer.status === "closed"
              ? t("m8.confirmedClosed")
              : t("m8.confirmedPlanner")
            : t("m8.declinedBody")
        }
        back
        testID="screen-cover-done"
        footer={
          <Button
            label={t("m8.backToday")}
            kind="primary"
            onPress={() => {
              router.replace("/today");
            }}
            testID="cover-done"
          />
        }
      >
        <Card>
          <View style={{ flexDirection: "row", alignItems: "center", gap: spacing[2] }}>
            <CircleCheck size={24} color={theme.ink} strokeWidth={1.75} />
            <Txt variant="heading" testID="cover-result">
              {answer.accepted ? t("m8.accepted") : t("m8.declined")}
            </Txt>
          </View>
        </Card>
      </Screen>
    );
  }

  return (
    <Async query={q}>
      {(list) => {
        const r = list[0];
        if (!r)
          return (
            <Screen title={t("m8.title")} status={t("m8.none")} back testID="screen-cover">
              <Txt>{t("m8.noneBody")}</Txt>
            </Screen>
          );
        const s = r.shift;
        const left = r.seconds_left;
        return (
          <Screen
            title={t("m8.title")}
            status={
              s.starts_at && s.ends_at
                ? t("m8.question", {
                    date: `${fmt.weekday(s.date)} ${fmt.dayMonth(s.date)}`,
                    shift: t(`shift.${s.shift_type as "frueh"}.name`),
                    from: fmt.time(s.starts_at),
                    to: fmt.time(s.ends_at),
                  })
                : t("m8.questionPlain", {
                    date: `${fmt.weekday(s.date)} ${fmt.dayMonth(s.date)}`,
                    shift: t(`shift.${s.shift_type as "frueh"}.name`),
                  })
            }
            back
            testID="screen-cover"
            footer={
              <>
                {respond.error ? <ErrorBox error={respond.error} /> : null}
                <Button
                  label={t("m8.take")}
                  kind="primary"
                  busy={respond.pending}
                  onPress={() => void respond.run(r.offer_id, true)}
                  testID="cover-accept"
                />
                <Button
                  label={t("m8.decline")}
                  disabled={respond.pending}
                  onPress={() => void respond.run(r.offer_id, false)}
                  testID="cover-decline"
                />
              </>
            }
          >
            <Card>
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing[3] }}>
                <ShiftChip code={s.shift_type} box={48} />
                <View style={{ flex: 1 }}>
                  <Txt variant="heading">{t(`shift.${s.shift_type as "frueh"}.name`)}</Txt>
                  <Txt variant="bodyStrong">
                    {fmt.weekday(s.date)} {fmt.date(s.date)}
                  </Txt>
                </View>
              </View>
            </Card>
            <Card>
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing[2] }}>
                <Timer size={20} color={theme.ink} strokeWidth={1.75} />
                <Txt variant="heading">
                  {r.deadline_at
                    ? t("m8.replyBy", { time: fmt.time(r.deadline_at) })
                    : t("m8.replySoon")}
                </Txt>
              </View>
              {left !== null && left !== undefined ? (
                <Txt
                  variant="numFigure"
                  testID="countdown"
                  accessibilityLabel={t("m8.left", { time: formatCountdown(left) })}
                >
                  {formatCountdown(left)}
                </Txt>
              ) : null}
            </Card>
            <Card>
              <Txt variant="label" muted>
                {t("m8.hours")}
              </Txt>
              <Txt testID="hours-impact">
                {t("m8.hoursImpact", {
                  before: fmt.number(r.hours.planned_hours_before, 1),
                  after: fmt.number(r.hours.planned_hours_after, 1),
                  contract: fmt.number(r.hours.contract_hours, 1),
                })}
              </Txt>
              <Txt variant="caption" muted>
                {t("m8.checked")}
              </Txt>
            </Card>
          </Screen>
        );
      }}
    </Async>
  );
}

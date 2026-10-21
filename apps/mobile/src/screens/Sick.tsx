import { unwrap, type components } from "@dienstpilot/api-client";
import { addDays } from "@dienstpilot/i18n";
import { spacing } from "@dienstpilot/design-tokens";
import { useRouter } from "expo-router";
import { HeartHandshake, Minus, Plus } from "lucide-react-native";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import { Button, Card, ErrorBox, Txt } from "../components/ui";
import { Screen } from "../components/Screen";
import { useFmt } from "../lib/fmt";
import { useAction, useQuery } from "../lib/hooks";
import { useSession } from "../lib/session";
import { useTheme } from "../lib/theme";

/** M7: one tap and a date range. No diagnosis, no reason: the confirmation says cover is being organised. */
export function SickScreen(): ReactNode {
  const { t } = useTranslation();
  const { theme } = useTheme();
  const fmt = useFmt();
  const router = useRouter();
  const { api } = useSession();
  const today = useQuery((a) => unwrap(a.GET("/me/today")), []);
  const [days, setDays] = useState(0);
  const [result, setResult] = useState<components["schemas"]["SickOut"] | null>(null);
  const start = today.data?.now.slice(0, 10) ?? null;
  const end = start ? addDays(start, days) : null;

  const report = useAction(async () => {
    if (!start || !end) return;
    setResult(await unwrap(api.POST("/me/sick", { body: { start_date: start, end_date: end } })));
  });

  if (result) {
    const first = result.affected_shifts[0];
    return (
      <Screen
        title={t("m7.doneTitle")}
        status={
          first
            ? t("m7.done", { shift: t(`shift.${first.shift_type as "frueh"}.name`) })
            : t("m7.doneNoShift")
        }
        back
        testID="screen-sick-done"
        footer={
          <Button
            label={t("m7.toToday")}
            kind="primary"
            onPress={() => {
              router.replace("/today");
            }}
            testID="sick-done"
          />
        }
      >
        <Card>
          <View style={{ flexDirection: "row", alignItems: "center", gap: spacing[2] }}>
            <HeartHandshake size={24} color={theme.ink} strokeWidth={1.75} />
            <Txt variant="heading" testID="sick-result">
              {t("m7.absent", {
                range:
                  result.start_date === result.end_date
                    ? fmt.date(result.start_date)
                    : `${fmt.date(result.start_date)} – ${fmt.date(result.end_date)}`,
              })}
            </Txt>
          </View>
          <Txt testID="cover-started">
            {t("m7.coverStarted", { count: result.cover_searches_started })}
          </Txt>
        </Card>
      </Screen>
    );
  }

  return (
    <Screen
      title={t("m7.title")}
      status={t("m7.status")}
      back
      testID="screen-sick"
      footer={
        <>
          {report.error ? <ErrorBox error={report.error} /> : null}
          <Button
            label={t("m7.report")}
            kind="primary"
            disabled={!start}
            busy={report.pending}
            onPress={() => void report.run()}
            testID="report-sick"
          />
        </>
      }
    >
      <Card>
        <Txt variant="label" muted>
          {t("m7.range")}
        </Txt>
        {start && end ? (
          <Txt variant="heading" testID="sick-range">
            {days === 0 ? fmt.date(start) : `${fmt.date(start)} – ${fmt.date(end)}`}
          </Txt>
        ) : null}
        <View style={{ flexDirection: "row", gap: spacing[2], alignItems: "center" }}>
          <Button
            label={t("m7.less")}
            disabled={days === 0}
            icon={<Minus size={16} color={theme.ink} strokeWidth={1.75} />}
            onPress={() => {
              setDays((d) => Math.max(0, d - 1));
            }}
            testID="sick-less"
          />
          <Button
            label={t("m7.more")}
            icon={<Plus size={16} color={theme.ink} strokeWidth={1.75} />}
            onPress={() => {
              setDays((d) => d + 1);
            }}
            testID="sick-more"
          />
        </View>
        <Txt variant="caption" muted>
          {t("m7.noDiagnosis")}
        </Txt>
      </Card>
    </Screen>
  );
}

import { ApiError, unwrap, type components } from "@dienstpilot/api-client";
import { spacing } from "@dienstpilot/design-tokens";
import { useRouter } from "expo-router";
import { CircleCheck } from "lucide-react-native";
import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import { MonthCalendar } from "../components/MonthCalendar";
import { Suggestion } from "../components/Suggestion";
import { Button, Card, ErrorBox, Txt } from "../components/ui";
import { LeaveActions, LeaveResult, type Result } from "../components/LeaveParts";
import { Screen } from "../components/Screen";
import { useFmt } from "../lib/fmt";
import { useAction, useQuery } from "../lib/hooks";
import { useSession } from "../lib/session";
import { useTheme } from "../lib/theme";

type Check = components["schemas"]["TradeOffCheck"];

/**
 * M5: request leave. Instant C6 hint (a stand-in estimate), then the real C1 check. The default
 * state is "coverable"; the trade-off appears only when the solver finds one. No colleague names.
 */
export function LeaveScreen(): ReactNode {
  const { t } = useTranslation();
  const { theme } = useTheme();
  const fmt = useFmt();
  const router = useRouter();
  const { api } = useSession();
  const today = useQuery((a) => unwrap(a.GET("/me/today")), []);
  const [picked, setPicked] = useState<string | null>(null);
  const [start, setStart] = useState<string | null>(null);
  const [end, setEnd] = useState<string | null>(null);
  const [hint, setHint] = useState<components["schemas"]["LeaveCheck"] | null>(null);
  const [check, setCheck] = useState<Check | null>(null);
  const [editing, setEditing] = useState(false);
  const [created, setCreated] = useState<components["schemas"]["LeaveOut"] | null>(null);
  const month = picked ?? start?.slice(0, 7) ?? today.data?.now.slice(0, 7) ?? null;

  const tap = (date: string): void => {
    setHint(null);
    setCheck(null);
    if (start !== null && end === null && date >= start) setEditing(false);
    if (start === null || end !== null || date < start) {
      setStart(date);
      setEnd(null);
    } else setEnd(date);
  };

  const run = useAction(async (s: string, e: string) => {
    const h = await unwrap(api.POST("/me/leave/check", { body: { start_date: s, end_date: e } }));
    setHint(h);
    setCheck(null);
    // The C1 check runs in the worker: poll until it is done.
    for (let i = 0; i < 90; i++) {
      const c = await unwrap(
        api.GET("/me/leave/checks/{check_id}", {
          params: { path: { check_id: h.trade_off_check_id } },
        }),
      );
      setCheck(c);
      if (c.status === "done" || c.status === "failed") return;
      await new Promise((r) => setTimeout(r, 1000));
    }
  });
  useEffect(() => {
    if (start && end) void run.run(start, end);
  }, [start, end]);

  const result = (check?.status === "done" ? check.result : null) as Result | null;
  const outcome = result?.outcome ?? null;
  const request = useAction(async (withTrade: boolean) => {
    if (!start || !end) return;
    try {
      const r = await unwrap(
        api.POST("/me/leave", {
          body: {
            start_date: start,
            end_date: end,
            with_trade: withTrade,
            check_id: withTrade ? (hint?.trade_off_check_id ?? null) : null,
          },
        }),
      );
      setCreated(r);
    } catch (e) {
      if (e instanceof ApiError) throw e;
      throw e;
    }
  });

  if (created) {
    return (
      <Screen
        title={t("m5.sentTitle")}
        status={t("m5.sentBody")}
        back
        testID="screen-leave-sent"
        footer={
          <Button
            label={t("m5.toToday")}
            kind="primary"
            onPress={() => {
              router.replace("/today");
            }}
            testID="leave-done"
          />
        }
      >
        <Card>
          <View style={{ flexDirection: "row", alignItems: "center", gap: spacing[2] }}>
            <CircleCheck size={24} color={theme.ink} strokeWidth={1.75} />
            <Txt variant="heading" testID="leave-created">
              {fmt.range(created.start_date, created.end_date)} {created.end_date.slice(0, 4)}
            </Txt>
          </View>
          <Txt muted>{t("m5.statusOpen")}</Txt>
        </Card>
      </Screen>
    );
  }

  const covered = t("m5.coverable", { count: hint?.overlapping_colleagues ?? 0 });
  const checking =
    start !== null &&
    end !== null &&
    (run.pending ||
      (check !== null && check.status !== "done" && check.status !== "failed") ||
      (hint !== null && check === null));
  const tradeMonth = result?.trade_off?.month ? fmt.month(String(result.trade_off.month)) : "";
  const hintText =
    hint === null
      ? null
      : hint.outcome === "not_coverable"
        ? t("m5.hintNotCoverable")
        : hint.outcome === "tight"
          ? t("m5.hintTight", { count: hint.overlapping_colleagues })
          : covered;

  return (
    <Screen
      title={t("m5.title")}
      status={
        start && end
          ? t("m5.range", { range: `${fmt.range(start, end)} ${end.slice(0, 4)}` })
          : t("m5.pick")
      }
      back
      testID="screen-leave"
      footer={
        <>
          {request.error ? <ErrorBox error={request.error} /> : null}
          <LeaveActions
            outcome={outcome}
            canRequest={Boolean(start && end) && !checking}
            busy={request.pending}
            onRequest={(withTrade) => void request.run(withTrade)}
          />
        </>
      }
    >
      {start && end && !editing ? (
        <Card testID="leave-range">
          <View
            style={{
              flexDirection: "row",
              alignItems: "center",
              justifyContent: "space-between",
              gap: spacing[3],
            }}
          >
            <Txt variant="heading">{`${fmt.range(start, end)} ${end.slice(0, 4)}`}</Txt>
            <Button label={t("m5.change")} onPress={() => setEditing(true)} testID="leave-change" />
          </View>
        </Card>
      ) : null}
      {month && !(start && end && !editing) ? (
        <Card>
          <MonthCalendar
            month={month}
            onMonth={setPicked}
            onDay={tap}
            testID="leave-calendar"
            decorate={(date) => ({
              selected: start !== null && date >= start && date <= (end ?? start),
              description: date === start ? t("m5.startDay") : date === end ? t("m5.endDay") : "",
            })}
          />
        </Card>
      ) : null}
      {run.error ? <ErrorBox error={run.error} /> : null}
      {hint && hintText ? (
        <Suggestion
          engine={hint.engine}
          testID="leave-hint"
          reasons={[t("m5.hintWhy", { max: hint.max_on_leave_same_day, limit: hint.limit })]}
        >
          <Txt testID="leave-hint-text">{hintText}</Txt>
        </Suggestion>
      ) : null}
      {checking ? (
        <Txt muted accessibilityRole="progressbar" testID="leave-checking">
          {t("m5.checking")}
        </Txt>
      ) : null}
      {check?.status === "failed" ? <Txt color={theme.alert}>{t("m5.checkFailed")}</Txt> : null}
      {result && outcome ? (
        <LeaveResult
          outcome={outcome}
          result={result}
          engine={
            check?.engine ?? { component: "C1", implementation: "built", version: "", note: "" }
          }
          coveredText={covered}
          tradeMonth={tradeMonth}
        />
      ) : null}
    </Screen>
  );
}

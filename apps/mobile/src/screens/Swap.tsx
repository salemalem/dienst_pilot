import { unwrap, type components } from "@dienstpilot/api-client";
import { spacing } from "@dienstpilot/design-tokens";
import { useRouter } from "expo-router";
import { CircleCheck } from "lucide-react-native";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, View } from "react-native";

import { ShiftLabel } from "../components/ShiftChip";
import { Async, Button, Card, ErrorBox, TOUCH_MIN, Txt } from "../components/ui";
import { Screen } from "../components/Screen";
import { useFmt } from "../lib/fmt";
import { useAction, useQuery } from "../lib/hooks";
import { useSession } from "../lib/session";
import { useTheme } from "../lib/theme";

type Shift = components["schemas"]["ShiftOut"];
type Swap = components["schemas"]["SwapOut"];

/**
 * M6: offer a shift as an exchange (the offer goes only to colleagues who may take it: a count,
 * never names), and answer offers addressed to me, alone or as an exchange.
 */
export function SwapScreen(): ReactNode {
  const { t } = useTranslation();
  const { theme } = useTheme();
  const fmt = useFmt();
  const router = useRouter();
  const { api } = useSession();
  const today = useQuery((a) => unwrap(a.GET("/me/today")), []);
  const now = today.data?.now ?? null;
  const months = now ? [now.slice(0, 7), nextMonth(now.slice(0, 7))] : [];
  const mine = useQuery(
    async (a) => {
      if (!now) return [] as Shift[];
      const rosters = await Promise.all(
        months.map((m) => unwrap(a.GET("/me/roster", { params: { query: { month: m } } }))),
      );
      return rosters
        .flatMap((r) => r.days.flatMap((d) => d.shifts))
        .filter((s) => s.date > now.slice(0, 10) && s.shift_type !== "frei");
    },
    [now],
  );
  const offers = useQuery((a) => unwrap(a.GET("/me/swap-offers")), []);
  const [picked, setPicked] = useState<Shift | null>(null);
  const [done, setDone] = useState<Swap | null>(null);

  const audience = useQuery(
    (a) =>
      picked
        ? unwrap(
            a.GET("/me/swaps/audience", {
              params: { query: { assignment_id: picked.assignment_id } },
            }),
          )
        : Promise.resolve(null),
    [picked?.assignment_id],
  );
  const offer = useAction(async () => {
    if (!picked) return;
    setDone(await unwrap(api.POST("/me/swaps", { body: { assignment_id: picked.assignment_id } })));
  });
  const take = useAction(async (swapId: string, give: string | null) => {
    setDone(
      await unwrap(
        api.POST("/me/swap-offers/{swap_id}/take", {
          params: { path: { swap_id: swapId } },
          body: give ? { give_assignment_id: give } : null,
        }),
      ),
    );
    offers.reload();
  });

  if (done) {
    const approved = done.status === "approved";
    return (
      <Screen
        title={t(
          done.role === "offered"
            ? "m6.offeredTitle"
            : approved
              ? "m6.takenTitle"
              : "m6.pendingTitle",
        )}
        status={
          done.role === "offered"
            ? t("m6.offeredBody")
            : approved
              ? t("m6.takenApproved")
              : t("m6.takenPending", {
                  reason: done.escalation_reason
                    ? t(`escalation.${done.escalation_reason as "overtime"}`, {
                        defaultValue: done.escalation_reason,
                      })
                    : "",
                })
        }
        back
        testID="screen-swap-done"
        footer={
          <Button
            label={t("m6.toToday")}
            kind="primary"
            onPress={() => {
              router.replace("/today");
            }}
            testID="swap-done"
          />
        }
      >
        <Card>
          <View style={{ flexDirection: "row", alignItems: "center", gap: spacing[2] }}>
            <CircleCheck size={24} color={theme.ink} strokeWidth={1.75} />
            <Txt variant="heading" testID="swap-result">
              {t(`m6.status.${done.status as "approved"}`, { defaultValue: done.status })}
            </Txt>
          </View>
          {done.shift ? <ShiftLabel code={done.shift.shift_type} /> : null}
          {done.shift ? (
            <Txt>
              {fmt.weekday(done.shift.date)} {fmt.date(done.shift.date)}
            </Txt>
          ) : null}
          {done.exchange ? (
            <Txt testID="swap-exchange">
              {t("m6.inReturn", {
                date: `${fmt.weekday(done.exchange.date)} ${fmt.date(done.exchange.date)}`,
                shift: t(`shift.${done.exchange.shift_type as "frueh"}.name`),
              })}
            </Txt>
          ) : null}
        </Card>
      </Screen>
    );
  }

  const mustExchange =
    audience.data?.needs_planner === true &&
    audience.data.own_rules.includes("contract_hours_band");
  return (
    <Screen
      title={t("m6.title")}
      status={
        picked
          ? t("m6.picked", { date: `${fmt.weekday(picked.date)} ${fmt.date(picked.date)}` })
          : t("m6.pick")
      }
      back
      testID="screen-swap"
      footer={
        <>
          {offer.error ? <ErrorBox error={offer.error} /> : null}
          <Button
            label={t("m6.offerExchange")}
            kind="primary"
            disabled={!picked || audience.data === null}
            busy={offer.pending}
            onPress={() => void offer.run()}
            testID="offer-exchange"
          />
        </>
      }
    >
      {picked ? (
        <Card testID="swap-picked">
          <View
            style={{
              flexDirection: "row",
              alignItems: "center",
              justifyContent: "space-between",
              gap: spacing[3],
            }}
          >
            <View style={{ gap: spacing[1], flex: 1 }}>
              <ShiftLabel code={picked.shift_type} />
              <Txt variant="bodyStrong">
                {fmt.weekday(picked.date)} {fmt.date(picked.date)}
              </Txt>
            </View>
            <Button
              label={t("m6.change")}
              onPress={() => {
                setPicked(null);
              }}
              testID="swap-change"
            />
          </View>
        </Card>
      ) : (
        <Async query={mine}>
          {(list) => (
            <View style={{ gap: spacing[2] }}>
              {list.length === 0 ? <Txt muted>{t("m6.noShifts")}</Txt> : null}
              {list.map((s) => {
                return (
                  <Pressable
                    key={s.assignment_id}
                    accessibilityRole="radio"
                    accessibilityState={{ selected: false, checked: false }}
                    aria-checked={false}
                    accessibilityLabel={`${fmt.weekday(s.date)} ${fmt.date(s.date)}, ${t(`shift.${s.shift_type as "frueh"}.name`)}`}
                    onPress={() => {
                      setPicked(s);
                    }}
                    testID={`shift-${s.date}-${s.shift_type}`}
                    style={{
                      minHeight: TOUCH_MIN,
                      flexDirection: "row",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: spacing[3],
                      gap: spacing[2],
                      backgroundColor: theme.sheet,
                      borderWidth: 1,
                      borderColor: theme.rule,
                    }}
                  >
                    <ShiftLabel code={s.shift_type} />
                    <Txt variant="bodyStrong">
                      {fmt.weekday(s.date)} {fmt.dayMonth(s.date)}
                    </Txt>
                  </Pressable>
                );
              })}
            </View>
          )}
        </Async>
      )}
      {picked && audience.data ? (
        <Card testID="swap-audience">
          <Txt testID="audience-text">
            {t("m6.audience", { n: audience.data.eligible_colleagues })}
          </Txt>
          {mustExchange ? (
            <Txt variant="bodyStrong" testID="giveaway-below-hours">
              {t("m6.giveawayBelowHours")}
            </Txt>
          ) : null}
        </Card>
      ) : null}
      <Txt variant="heading" accessibilityRole="header">
        {t("m6.incoming")}
      </Txt>
      <Async query={offers}>
        {(list) =>
          list.length === 0 ? (
            <Txt muted>{t("m6.noOffers")}</Txt>
          ) : (
            <View style={{ gap: spacing[3] }}>
              {list.map((o) => (
                <Card key={o.swap_id} testID={`offer-${o.swap_id}`}>
                  <ShiftLabel code={o.shift.shift_type} />
                  <Txt variant="bodyStrong">
                    {fmt.weekday(o.shift.date)} {fmt.date(o.shift.date)}
                  </Txt>
                  {o.can_take_alone ? (
                    <Button
                      label={t("m6.take")}
                      kind="primary"
                      busy={take.pending}
                      onPress={() => void take.run(o.swap_id, null)}
                      testID="take-alone"
                    />
                  ) : null}
                  {o.exchange_options.length > 0 ? (
                    <Txt variant="label" muted>
                      {t("m6.exchangeFor")}
                    </Txt>
                  ) : null}
                  {o.exchange_options.map((x) => (
                    <Button
                      key={x.assignment_id}
                      label={t("m6.takeAgainst", {
                        date: `${fmt.weekday(x.date)} ${fmt.dayMonth(x.date)}`,
                        shift: t(`shift.${x.shift_type as "frueh"}.name`),
                      })}
                      busy={take.pending}
                      onPress={() => void take.run(o.swap_id, x.assignment_id)}
                      testID={`take-for-${x.date}`}
                    />
                  ))}
                </Card>
              ))}
              {take.error ? <ErrorBox error={take.error} /> : null}
            </View>
          )
        }
      </Async>
    </Screen>
  );
}

function nextMonth(m: string): string {
  const [y, mo] = m.split("-").map(Number);
  const t = (y ?? 2026) * 12 + (mo ?? 1);
  return `${String(Math.floor(t / 12))}-${String((t % 12) + 1).padStart(2, "0")}`;
}

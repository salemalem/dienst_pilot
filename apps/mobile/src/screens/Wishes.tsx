import { unwrap, type components } from "@dienstpilot/api-client";
import { daysInMonth, formatPercent, weekdayIndex } from "@dienstpilot/i18n";
import { spacing } from "@dienstpilot/design-tokens";
import { Check, Star, X } from "lucide-react-native";
import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import { MonthCalendar } from "../components/MonthCalendar";
import { Suggestion } from "../components/Suggestion";
import { Async, Button, Card, ErrorBox, Field, Txt } from "../components/ui";
import { Screen } from "../components/Screen";
import { useFmt } from "../lib/fmt";
import { useAction, useQuery } from "../lib/hooks";
import { useSession } from "../lib/session";
import { useTheme } from "../lib/theme";

type Entry = components["schemas"]["WishEntry"];
type Parsed = components["schemas"]["ParsedOut"];
type Hint = components["schemas"]["Suggestion"];

const SHIFT_KEYS = ["frueh", "spaet", "nacht", "bereitschaft", "ruf"] as const;

/** M4: tap days ("kann nicht" then "möchte arbeiten"), star up to two, free text read by C7, C4 chips. */
export function WishesScreen(): ReactNode {
  const { t, i18n } = useTranslation();
  const { theme } = useTheme();
  const fmt = useFmt();
  const pct = (v: number): string => formatPercent(v, i18n.language === "en" ? "en" : "de", 1);
  const { api, settings } = useSession();
  const q = useQuery((a) => unwrap(a.GET("/me/wishes")), []);
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [parsed, setParsed] = useState<Parsed | null>(null);
  const [dismissed, setDismissed] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);

  const month = q.data?.roster_month.slice(0, 7) ?? null;
  useEffect(() => {
    if (q.data) setEntries(q.data.entries);
  }, [q.data]);

  const cycle = (date: string): void => {
    setSaved(false);
    setSelected(date);
    setEntries((prev) => {
      const list = prev ?? [];
      const cur = list.find((e) => e.date === date);
      const rest = list.filter((e) => e.date !== date);
      if (!cur) return [...rest, { date, kind: "unavailable", shift_type: null, important: false }];
      if (cur.kind === "unavailable") return [...rest, { ...cur, kind: "wish_work" }];
      return rest;
    });
  };
  const max = q.data?.max_important ?? 2;
  const important = (entries ?? []).filter((e) => e.important).length;
  const star = (date: string): void => {
    setSaved(false);
    setEntries((prev) =>
      (prev ?? []).map((e) =>
        e.date === date && (e.important || important < max) ? { ...e, important: !e.important } : e,
      ),
    );
  };

  const parse = useAction(async () => {
    const r = await unwrap(
      api.POST("/me/wishes/parse", {
        body: { text, language: i18n.language === "en" ? "en" : "de" },
      }),
    );
    setParsed(r);
  });
  const applyParsed = (): void => {
    if (!parsed) return;
    setSaved(false);
    setEntries((prev) => {
      const list = prev ?? [];
      const add = parsed.unavailable
        .filter((d) => !list.some((e) => e.date === d))
        .map((d): Entry => ({ date: d, kind: "unavailable", shift_type: null, important: false }));
      return [...list, ...add];
    });
    setParsed(null);
    setText("");
  };
  const applyHint = (h: Hint): void => {
    if (!month) return;
    setSaved(false);
    const shift = SHIFT_KEYS.find((s) => s === h.shift_type) ?? null;
    setEntries((prev) => {
      const list = prev ?? [];
      const days = daysInMonth(month).filter(
        (d) => weekdayIndex(d) === h.weekday && !list.some((e) => e.date === d),
      );
      return [
        ...list,
        ...days.map((d): Entry =>
          h.kind === "avoid"
            ? { date: d, kind: "unavailable", shift_type: null, important: false }
            : { date: d, kind: "wish_work", shift_type: shift, important: false },
        ),
      ];
    });
    setDismissed((x) => [...x, `${h.kind}-${String(h.weekday)}-${h.shift_type}`]);
  };

  const save = useAction(async () => {
    await unwrap(api.PUT("/me/wishes", { body: entries ?? [] }));
    setSaved(true);
    q.reload();
  });

  const sel = (entries ?? []).find((e) => e.date === selected);
  const hints =
    settings?.preference_suggestions === false
      ? []
      : (q.data?.suggestions ?? []).filter(
          (h) => !dismissed.includes(`${h.kind}-${String(h.weekday)}-${h.shift_type}`),
        );
  const weekdayNames = [
    "2026-10-19",
    "2026-10-20",
    "2026-10-21",
    "2026-10-22",
    "2026-10-23",
    "2026-10-24",
    "2026-10-25",
  ];

  return (
    <Screen
      title={t("m4.title")}
      status={
        q.data
          ? t("m4.status", { month: fmt.month(q.data.roster_month), days: q.data.days_left })
          : undefined
      }
      back
      testID="screen-wishes"
      footer={
        <>
          {saved ? (
            <Txt variant="bodyStrong" testID="wishes-saved">
              {t("m4.saved")}
            </Txt>
          ) : null}
          {save.error ? <ErrorBox error={save.error} /> : null}
          <Button
            label={t("m4.save")}
            kind="primary"
            busy={save.pending}
            onPress={() => void save.run()}
            testID="wishes-save"
          />
        </>
      }
    >
      <Async query={q}>
        {() =>
          month ? (
            <>
              <Txt muted>{t("m4.howTo")}</Txt>
              <Card>
                <MonthCalendar
                  month={month}
                  onDay={cycle}
                  testID="wish-calendar"
                  decorate={(date) => {
                    const e = (entries ?? []).find((x) => x.date === date);
                    return {
                      selected: date === selected,
                      description: e
                        ? (e.kind === "unavailable" ? t("m4.cannot") : t("m4.want")) +
                          (e.important ? `, ${t("m4.important")}` : "")
                        : t("m4.none"),
                      adornment: e ? (
                        <>
                          {e.kind === "unavailable" ? (
                            <X size={14} color={theme.ink} strokeWidth={2} />
                          ) : (
                            <Check size={14} color={theme.ink} strokeWidth={2} />
                          )}
                          {e.important ? (
                            <Star size={12} color={theme.ink} fill={theme.ink} strokeWidth={1.75} />
                          ) : null}
                        </>
                      ) : null,
                    };
                  }}
                />
                <View style={{ flexDirection: "row", gap: spacing[3], flexWrap: "wrap" }}>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: spacing[1] }}>
                    <X size={14} color={theme.ink} strokeWidth={2} />
                    <Txt variant="caption">{t("m4.cannot")}</Txt>
                  </View>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: spacing[1] }}>
                    <Check size={14} color={theme.ink} strokeWidth={2} />
                    <Txt variant="caption">{t("m4.want")}</Txt>
                  </View>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: spacing[1] }}>
                    <Star size={12} color={theme.ink} fill={theme.ink} strokeWidth={1.75} />
                    <Txt variant="caption">{t("m4.important")}</Txt>
                  </View>
                </View>
              </Card>
              {sel ? (
                <Button
                  label={sel.important ? t("m4.unstar") : t("m4.star", { max, used: important })}
                  disabled={!sel.important && important >= max}
                  onPress={() => {
                    star(sel.date);
                  }}
                  icon={
                    <Star
                      size={16}
                      color={theme.ink}
                      fill={sel.important ? theme.ink : "none"}
                      strokeWidth={1.75}
                    />
                  }
                  testID="star"
                />
              ) : null}
              {hints.map((h) => (
                <Suggestion
                  key={`${h.kind}-${String(h.weekday)}-${h.shift_type}`}
                  engine={q.data?.suggestions_engine}
                  reasons={[
                    t(h.kind === "avoid" ? "m4.hintWhyAvoid" : "m4.hintWhyPrefer", {
                      shift: t(`shift.${h.shift_type as "frueh"}.name`),
                      weekday: fmt.weekday(weekdayNames[h.weekday] ?? "2026-10-19"),
                      n: h.evidence,
                      trials: h.trials,
                      own: pct(h.evidence / Math.max(h.trials, 1)),
                      dept: pct(h.department_rate),
                    }),
                    t("m4.hintWhyModel", { model: q.data?.suggestions_engine.version ?? "" }),
                  ]}
                  testID="hint"
                  actions={
                    <>
                      <Button
                        label={t("m4.hintApply")}
                        kind="primary"
                        onPress={() => {
                          applyHint(h);
                        }}
                      />
                      <Button
                        label={t("m4.hintDismiss")}
                        kind="quiet"
                        onPress={() => {
                          setDismissed((x) => [
                            ...x,
                            `${h.kind}-${String(h.weekday)}-${h.shift_type}`,
                          ]);
                        }}
                      />
                    </>
                  }
                >
                  <Txt>
                    {t(h.kind === "avoid" ? "m4.hintAvoid" : "m4.hintPrefer", {
                      shift: t(`shift.${h.shift_type as "frueh"}.name`),
                      weekday: fmt.weekday(weekdayNames[h.weekday] ?? "2026-10-19"),
                    })}
                  </Txt>
                </Suggestion>
              ))}
              <Card>
                <Field
                  label={t("m4.freeText")}
                  value={text}
                  onChangeText={setText}
                  placeholder={t("m4.example")}
                  multiline
                  testID="free-text"
                />
                <Button
                  label={t("m4.understand")}
                  disabled={text.trim() === ""}
                  busy={parse.pending}
                  onPress={() => void parse.run()}
                  testID="parse"
                />
                {parse.error ? <ErrorBox error={parse.error} /> : null}
              </Card>
              {parsed ? (
                <Suggestion
                  engine={parsed.engine}
                  testID="parsed"
                  reasons={[t("m4.parseWhy")]}
                  actions={
                    parsed.unavailable.length > 0 ? (
                      <Button
                        label={t("m4.parseApply")}
                        kind="primary"
                        onPress={applyParsed}
                        testID="parse-apply"
                      />
                    ) : undefined
                  }
                >
                  <Txt variant="bodyStrong">{t("m4.understood")}</Txt>
                  {parsed.unavailable.length > 0 ? (
                    <Txt>
                      {t("m4.parsedDays", {
                        days: parsed.unavailable.map((d) => fmt.dayMonth(d)).join(", "),
                      })}
                    </Txt>
                  ) : null}
                  {parsed.prefer_shifts.length > 0 ? (
                    <Txt>
                      {t("m4.parsedPrefer", {
                        shifts: parsed.prefer_shifts
                          .map((s) => t(`shift.${s as "frueh"}.name`))
                          .join(", "),
                      })}
                    </Txt>
                  ) : null}
                  {parsed.avoid_shifts.length > 0 ? (
                    <Txt>
                      {t("m4.parsedAvoid", {
                        shifts: parsed.avoid_shifts
                          .map((s) => t(`shift.${s as "frueh"}.name`))
                          .join(", "),
                      })}
                    </Txt>
                  ) : null}
                  {parsed.avoid_weekends ? <Txt>{t("m4.parsedWeekends")}</Txt> : null}
                  {parsed.clarifying_question ? <Txt>{parsed.clarifying_question}</Txt> : null}
                </Suggestion>
              ) : null}
            </>
          ) : null
        }
      </Async>
    </Screen>
  );
}

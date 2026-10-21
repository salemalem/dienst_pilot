"use client";

import { unwrap, type components } from "@dienstpilot/api-client";
import { useLocale, useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";

import {
  Async,
  Button,
  ErrorState,
  Field,
  PageHeader,
  Section,
  Switch,
  Table,
  useToast,
} from "@/components/ui";
import { useShiftName } from "@/components/shift";
import { useFmt } from "@/lib/fmt";
import { useAction, useQuery } from "@/lib/hooks";
import { useSession } from "@/lib/session";

type RuleSet = components["schemas"]["RuleSetOut"];

const EDITABLE = [
  "min_rest_hours",
  "max_consecutive_nights",
  "max_weekends_per_month",
  "max_on_call_per_month",
  "max_on_call_home_per_month",
] as const;
const KNOWN = [
  ...EDITABLE,
  "contract_hours_band",
  "contract_hours_band_min_days",
  "free_day_after_on_call",
  "bereitschaft_credited_hours",
] as const;

/** Berlin's UTC offset on a given day, as "+02:00" (the demo clock changes with the seasons). */
function berlinOffset(day: string): string {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Berlin",
    timeZoneName: "longOffset",
  }).formatToParts(new Date(`${day}T12:00:00Z`));
  const raw = parts.find((p) => p.type === "timeZoneName")?.value ?? "GMT+01:00";
  return raw.replace("GMT", "") || "+00:00";
}

function RuleValues({ rules }: { rules: Record<string, unknown> }): ReactNode {
  const t = useTranslations("w11");
  const fmt = useFmt();
  const show = (v: unknown): string => {
    if (typeof v === "boolean") return v ? t("yes") : t("no");
    if (typeof v === "number") return fmt.number(v, 2);
    if (Array.isArray(v))
      return v.map((x) => (typeof x === "number" ? fmt.number(x, 2) : String(x))).join(" – ");
    return JSON.stringify(v);
  };
  return (
    <dl className="body m-0 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1">
      {KNOWN.filter((k) => k in rules).map((k) => (
        <div key={k} className="contents">
          <dt>{t(`rule.${k}`)}</dt>
          <dd className="num-time m-0 text-right">{show(rules[k])}</dd>
        </div>
      ))}
    </dl>
  );
}

function NewRuleSet({ latest, onDone }: { latest: RuleSet; onDone: () => void }): ReactNode {
  const t = useTranslations("w11");
  const fmt = useFmt();
  const toast = useToast();
  const { api } = useSession();
  const rules = latest.rules as Record<string, unknown>;
  const [version, setVersion] = useState("2027-1");
  const [from, setFrom] = useState("2027-01-01");
  const [de, setDe] = useState("");
  const [en, setEn] = useState("");
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(EDITABLE.map((k) => [k, String(rules[k] ?? "")])),
  );
  const create = useAction(async () => {
    const next: Record<string, unknown> = { ...rules };
    for (const k of EDITABLE) next[k] = Number(values[k]);
    await unwrap(
      api.POST("/admin/rule-sets", {
        body: {
          version,
          effective_from: from,
          rules: next,
          change_note_de: de,
          change_note_en: en,
        },
      }),
    );
    toast.show(t("created", { date: fmt.date(from) }));
    onDone();
  });
  const valid =
    version.trim() !== "" &&
    de.trim() !== "" &&
    en.trim() !== "" &&
    EDITABLE.every((k) => values[k] !== "" && !Number.isNaN(Number(values[k])));
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        void create.run();
      }}
    >
      <p className="body m-0 text-ink-muted">{t("newHint", { version: latest.version })}</p>
      <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(220px,1fr))]">
        <Field label={t("version")}>
          {(p) => (
            <input
              {...p}
              className="dp-input"
              value={version}
              onChange={(e) => {
                setVersion(e.target.value);
              }}
            />
          )}
        </Field>
        <Field label={t("effectiveFrom")} hint={t("effectiveHint")}>
          {(p) => (
            <input
              {...p}
              type="date"
              className="dp-input"
              value={from}
              onChange={(e) => {
                setFrom(e.target.value);
              }}
            />
          )}
        </Field>
        {EDITABLE.map((k) => (
          <Field key={k} label={t(`rule.${k}`)}>
            {(p) => (
              <input
                {...p}
                inputMode="decimal"
                className="dp-input"
                value={values[k] ?? ""}
                onChange={(e) => {
                  setValues((v) => ({ ...v, [k]: e.target.value }));
                }}
              />
            )}
          </Field>
        ))}
      </div>
      <Field label={t("noteDe")}>
        {(p) => (
          <textarea
            {...p}
            className="dp-input"
            value={de}
            onChange={(e) => {
              setDe(e.target.value);
            }}
          />
        )}
      </Field>
      <Field label={t("noteEn")}>
        {(p) => (
          <textarea
            {...p}
            className="dp-input"
            value={en}
            onChange={(e) => {
              setEn(e.target.value);
            }}
          />
        )}
      </Field>
      {create.error ? <ErrorState error={create.error} /> : null}
      <Button
        variant="primary"
        type="submit"
        disabled={!valid || create.pending}
        className="self-start"
      >
        {t("create")}
      </Button>
    </form>
  );
}

function DemoClock(): ReactNode {
  const t = useTranslations("w11");
  const fmt = useFmt();
  const toast = useToast();
  const { api, refresh } = useSession();
  const clock = useQuery((a) => unwrap(a.GET("/clock")), []);
  const [day, setDay] = useState("2026-10-20");
  const [time, setTime] = useState("06:00");
  const set = useAction(async (reset: boolean) => {
    const body = reset
      ? { now: null, reset: true }
      : { now: `${day}T${time}:00${berlinOffset(day)}`, reset: false };
    const c = await unwrap(api.PUT("/demo/clock", { body }));
    toast.show(t("clockSet", { time: fmt.dateTime(c.now) }));
    await refresh();
    clock.reload();
  });
  return (
    <Async query={clock}>
      {(c) =>
        c.demo_mode ? (
          <div className="flex flex-col gap-4">
            <p className="body m-0" data-testid="clock-now">
              {t("clockNow", { time: fmt.dateTime(c.now) })}
            </p>
            <div className="flex flex-wrap items-end gap-4">
              <Field label={t("clockDay")}>
                {(p) => (
                  <input
                    {...p}
                    type="date"
                    className="dp-input"
                    value={day}
                    onChange={(e) => {
                      setDay(e.target.value);
                    }}
                  />
                )}
              </Field>
              <Field label={t("clockTime")}>
                {(p) => (
                  <input
                    {...p}
                    type="time"
                    className="dp-input"
                    value={time}
                    onChange={(e) => {
                      setTime(e.target.value);
                    }}
                  />
                )}
              </Field>
              <Button
                variant="primary"
                disabled={set.pending}
                onClick={() => void set.run(false)}
                data-testid="set-clock"
              >
                {t("clockSetButton")}
              </Button>
              <Button disabled={set.pending} onClick={() => void set.run(true)}>
                {t("clockReset")}
              </Button>
            </div>
            <p className="caption m-0 text-ink-muted">{t("clockNote")}</p>
            {set.error ? <ErrorState error={set.error} /> : null}
          </div>
        ) : (
          <p className="body m-0">{t("clockOff")}</p>
        )
      }
    </Async>
  );
}

/** W11: master data and versioned rule sets; the Planner's auto-approval policy; the demo clock (Administrator). */
export default function RulesPage(): ReactNode {
  const t = useTranslations("w11");
  const locale = useLocale();
  const fmt = useFmt();
  const toast = useToast();
  const names = useShiftName();
  const { api, me } = useSession();
  const admin = me.role === "admin";
  const q = useQuery((a) => unwrap(a.GET("/master-data")), []);
  const policy = useQuery(
    (a) => (me.role === "planner" ? unwrap(a.GET("/planner/policy")) : Promise.resolve(null)),
    [me.role],
  );
  const savePolicy = useAction(
    async (next: { auto_approve_swaps: boolean; auto_approve_cover: boolean }) => {
      await unwrap(api.PUT("/planner/policy", { body: next }));
      toast.show(t("policySaved"));
      policy.reload();
    },
  );
  const de = locale === "de";

  return (
    <>
      <PageHeader title={t("title")} status={admin ? t("statusAdmin") : t("statusPlanner")} />
      {admin ? (
        <Section title={t("clockTitle")}>
          <DemoClock />
        </Section>
      ) : null}
      {policy.data ? (
        <Section title={t("policyTitle")}>
          <p className="body m-0 text-ink-muted">{t("policyNote")}</p>
          <Switch
            label={t("policySwaps")}
            checked={policy.data.auto_approve_swaps}
            disabled={savePolicy.pending}
            onChange={(v) =>
              void savePolicy.run({
                auto_approve_swaps: v,
                auto_approve_cover: policy.data?.auto_approve_cover ?? false,
              })
            }
          />
          <Switch
            label={t("policyCover")}
            checked={policy.data.auto_approve_cover}
            disabled={savePolicy.pending}
            onChange={(v) =>
              void savePolicy.run({
                auto_approve_swaps: policy.data?.auto_approve_swaps ?? false,
                auto_approve_cover: v,
              })
            }
          />
          {savePolicy.error ? <ErrorState error={savePolicy.error} /> : null}
        </Section>
      ) : null}
      <Async query={q}>
        {(d) => {
          const sets = [...d.rule_sets].sort((a, b) =>
            b.effective_from.localeCompare(a.effective_from),
          );
          const latest = sets[0];
          return (
            <>
              <Section title={t("ruleSetsTitle")}>
                <div className="flex flex-col gap-6" data-testid="rule-sets">
                  {sets.map((s) => (
                    <div key={s.version} className="flex flex-col gap-2 border-b border-rule pb-4">
                      <div className="flex flex-wrap items-baseline gap-3">
                        <h3 className="heading m-0">
                          {t("ruleSetVersion", { version: s.version })}
                        </h3>
                        <span className="label text-ink-muted">
                          {t("effective", { date: fmt.date(s.effective_from) })}
                        </span>
                      </div>
                      <p className="body m-0">{de ? s.change_note_de : s.change_note_en}</p>
                      <RuleValues rules={s.rules as Record<string, unknown>} />
                    </div>
                  ))}
                </div>
              </Section>
              {admin && latest ? (
                <Section title={t("newTitle")}>
                  <NewRuleSet latest={latest} onDone={q.reload} />
                </Section>
              ) : null}
              <Section title={t("shiftTypesTitle")}>
                <Table label={t("shiftTypesTitle")}>
                  <thead>
                    <tr>
                      <th scope="col">{t("colShift")}</th>
                      <th scope="col">{t("colTimes")}</th>
                      <th scope="col" className="text-right">
                        {t("colNet")}
                      </th>
                      <th scope="col" className="text-right">
                        {t("colBurden")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.shift_types.map((s) => (
                      <tr key={s.code}>
                        <td>
                          <strong>{de ? s.letter_de : s.letter_en}</strong> {names.name(s.code)}
                        </td>
                        <td className="num-time">
                          {s.start_time
                            ? `${s.start_time}–${s.end_time ?? ""}${s.ends_next_day ? t("nextDay") : ""}`
                            : t("allDay")}
                        </td>
                        <td className="num-time text-right">{fmt.number(s.net_hours, 2)} h</td>
                        <td className="num-time text-right">{fmt.number(s.burden_weight, 1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </Section>
              <Section title={t("qualTitle")}>
                <ul className="body m-0 list-disc pl-5">
                  {d.qualifications.map(([code, nameDe, nameEn]) => (
                    <li key={code}>
                      <strong>{code}</strong>: {de ? nameDe : nameEn}
                    </li>
                  ))}
                </ul>
              </Section>
              <Section title={t("demandTitle")}>
                {d.demand_examples[0] ? (
                  <>
                    <p className="caption m-0 text-ink-muted">
                      {t("demandNote", { date: fmt.date(d.demand_examples[0].date) })}
                    </p>
                    <Table label={t("demandTitle")}>
                      <thead>
                        <tr>
                          <th scope="col">{t("colShift")}</th>
                          <th scope="col">{t("colQual")}</th>
                          <th scope="col" className="text-right">
                            {t("colRequired")}
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {d.demand_examples[0].rows.map(([shift, qual, n]) => (
                          <tr key={`${shift}-${qual}`}>
                            <td>{names.name(String(shift))}</td>
                            <td>{qual}</td>
                            <td className="num-time text-right">{n}</td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  </>
                ) : null}
              </Section>
              <Section title={t("contractsTitle", { count: d.contracts.length })}>
                <Table label={t("contractsTitle", { count: d.contracts.length })}>
                  <thead>
                    <tr>
                      <th scope="col">{t("colPerson")}</th>
                      <th scope="col">{t("colRole")}</th>
                      <th scope="col" className="text-right">
                        {t("colWeekly")}
                      </th>
                      <th scope="col">{t("colQuals")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.contracts.map((c) => (
                      <tr key={c.staff_id}>
                        <td>{c.display_name}</td>
                        <td>{de ? c.title_de : c.title_en}</td>
                        <td className="num-time text-right">{fmt.number(c.weekly_hours, 1)} h</td>
                        <td>{c.qualifications.join(", ") || "–"}</td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </Section>
            </>
          );
        }}
      </Async>
    </>
  );
}

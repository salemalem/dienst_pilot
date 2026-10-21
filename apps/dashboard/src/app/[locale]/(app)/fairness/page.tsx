"use client";

import { unwrap } from "@dienstpilot/api-client";
import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";

import { Bars, DotStrip } from "@/components/charts";
import { EngineBadge } from "@/components/EngineBadge";
import { MonthSwitch } from "@/components/MonthSwitch";
import { Async, Loading, PageHeader, Section, Table } from "@/components/ui";
import { useFmt } from "@/lib/fmt";
import { useQuery } from "@/lib/hooks";
import { useSession } from "@/lib/session";

const METRICS = ["nights", "weekends", "holidays"] as const;

/** W8: burden per person (planner) or as anonymous statistics (oversight), rest compliance, overtime. */
export default function FairnessPage(): ReactNode {
  const t = useTranslations("w8");
  const fmt = useFmt();
  const { me } = useSession();
  const planner = me.role === "planner";
  const clock = useQuery((api) => unwrap(api.GET("/clock")), []);
  const [year, setYear] = useState<number | null>(null);
  const [month, setMonth] = useState<string | null>(null);
  const now = clock.data?.now ?? null;
  const y = year ?? (now ? Number(now.slice(0, 4)) : null);
  const m = month ?? (now ? now.slice(0, 7) : null);

  const fairness = useQuery(
    (api) =>
      y ? unwrap(api.GET("/fairness", { params: { query: { year: y } } })) : Promise.resolve(null),
    [y],
  );
  const hours = useQuery(
    (api) =>
      m
        ? unwrap(api.GET("/compliance/hours", { params: { query: { month: m } } }))
        : Promise.resolve(null),
    [m],
  );
  const trend = useQuery(
    (api) => unwrap(api.GET("/compliance/overtime-trend", { params: { query: { months: 6 } } })),
    [],
  );

  if (!y || !m) return <Loading />;
  return (
    <>
      <PageHeader
        title={
          hours.data
            ? hours.data.rest_violations_total === 0
              ? t("headlineRestOk", { month: fmt.month(m) })
              : t("headlineRestBad", {
                  month: fmt.month(m),
                  count: hours.data.rest_violations_total,
                })
            : t("title")
        }
        status={planner ? t("statusPlanner") : t("statusOversight")}
      />
      {hours.data && fairness.data ? (
        <div
          className="grid gap-6 [grid-template-columns:repeat(auto-fit,minmax(240px,1fr))]"
          data-testid="kpis"
        >
          <div className="flex flex-col gap-1 border border-rule bg-sheet p-5">
            <span className="label text-ink-muted">
              {t("kpiRest", { month: fmt.monthShort(m) })}
            </span>
            <span className="num-figure">
              {hours.data.rest_violations_total === 0
                ? t("restOk")
                : t("restViolations", { count: hours.data.rest_violations_total })}
            </span>
          </div>
          <div className="flex flex-col gap-1 border border-rule bg-sheet p-5">
            <span className="label text-ink-muted">
              {t("kpiOvertime", { month: fmt.monthShort(m) })}
            </span>
            <span className="num-figure">{fmt.hours(hours.data.total_overtime_hours)}</span>
          </div>
          {fairness.data.distributions
            .filter((d) => d.metric === "weekends")
            .map((d) => (
              <div key={d.metric} className="flex flex-col gap-1 border border-rule bg-sheet p-5">
                <span className="label text-ink-muted">{t("kpiWeekends")}</span>
                <span className="num-figure">
                  {t("kpiMedian", { median: fmt.number(d.median, 1) })}
                </span>
                <span className="caption text-ink-muted">
                  {t("kpiRange", { min: d.minimum, max: d.maximum })}
                </span>
              </div>
            ))}
        </div>
      ) : null}
      <Section
        title={t("fairnessTitle", { year: y })}
        aside={
          <span className="flex items-center gap-2">
            <button
              type="button"
              className="dp-btn dp-btn--secondary label"
              onClick={() => {
                setYear(y - 1);
              }}
            >
              {y - 1}
            </button>
            <span className="body-strong">{y}</span>
            <button
              type="button"
              className="dp-btn dp-btn--secondary label"
              disabled={now !== null && y >= Number(now.slice(0, 4))}
              onClick={() => {
                setYear(y + 1);
              }}
            >
              {y + 1}
            </button>
          </span>
        }
      >
        <Async query={fairness}>
          {(f) =>
            f ? (
              <>
                <p className="caption m-0 text-ink-muted">
                  {f.people
                    ? t("asOf", { date: fmt.date(f.as_of) })
                    : t("anonymous", { date: fmt.date(f.as_of) })}
                </p>
                <div className="grid gap-6 [grid-template-columns:repeat(auto-fit,minmax(320px,1fr))]">
                  {f.distributions.map((d) => {
                    const name = METRICS.includes(d.metric as "nights")
                      ? t(`metric.${d.metric as "nights"}`)
                      : d.metric;
                    return (
                      <div
                        key={d.metric}
                        className="flex flex-col gap-2"
                        data-testid={`dist-${d.metric}`}
                      >
                        <h3 className="heading m-0">{name}</h3>
                        <DotStrip
                          values={d.values}
                          min={d.minimum}
                          max={d.maximum}
                          median={d.median}
                          mean={d.mean}
                          label={t("distLabel", {
                            name,
                            people: d.people,
                            min: d.minimum,
                            median: fmt.number(d.median, 1),
                            max: d.maximum,
                          })}
                        />
                        <p className="num-small m-0 text-ink-muted">
                          {t("distFacts", {
                            people: d.people,
                            mean: fmt.number(d.mean, 1),
                            median: fmt.number(d.median, 1),
                            min: d.minimum,
                            max: d.maximum,
                          })}
                        </p>
                      </div>
                    );
                  })}
                </div>
                {f.people ? (
                  <Table label={t("peopleLabel")}>
                    <thead>
                      <tr>
                        <th scope="col">{t("colPerson")}</th>
                        {METRICS.map((k) => (
                          <th key={k} scope="col" className="text-right">
                            {t(`metric.${k}`)}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {[...f.people]
                        .sort((a, b) => b.weekends - a.weekends)
                        .map((p) => (
                          <tr key={p.staff_id}>
                            <td>{p.display_name}</td>
                            <td className="num-time text-right">{p.nights}</td>
                            <td className="num-time text-right">{p.weekends}</td>
                            <td className="num-time text-right">{p.holidays}</td>
                          </tr>
                        ))}
                    </tbody>
                  </Table>
                ) : null}
              </>
            ) : null
          }
        </Async>
      </Section>
      <Section
        title={t("complianceTitle", { month: fmt.month(m) })}
        aside={<MonthSwitch month={m} onChange={setMonth} />}
      >
        <Async query={hours}>
          {(h) =>
            h ? (
              <>
                <p className="body m-0" data-testid="compliance-summary">
                  {t("complianceSummary", {
                    overtime: fmt.number(h.total_overtime_hours, 1),
                    violations: h.rest_violations_total,
                    people: h.people.length,
                  })}
                </p>
                {planner ? (
                  <Table label={t("hoursLabel")}>
                    <thead>
                      <tr>
                        <th scope="col">{t("colPerson")}</th>
                        <th scope="col" className="text-right">
                          {t("colContract")}
                        </th>
                        <th scope="col" className="text-right">
                          {t("colPlanned")}
                        </th>
                        <th scope="col" className="text-right">
                          {t("colOvertime")}
                        </th>
                        <th scope="col">{t("colRest")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...h.people]
                        .sort((a, b) => b.overtime_hours - a.overtime_hours)
                        .map((p) => (
                          <tr key={p.staff_id}>
                            <td>{p.display_name}</td>
                            <td className="num-time text-right">
                              {fmt.number(p.contract_hours, 1)}
                            </td>
                            <td className="num-time text-right">
                              {fmt.number(p.planned_hours, 1)}
                            </td>
                            <td className="num-time text-right">
                              {fmt.number(p.overtime_hours, 1)}
                            </td>
                            <td>
                              {p.rest_compliance
                                ? p.rest_compliance.compliant
                                  ? t("restOk")
                                  : t("restViolations", { count: p.rest_compliance.violations })
                                : "–"}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </Table>
                ) : (
                  <p className="caption m-0 text-ink-muted">{t("hoursOnW12")}</p>
                )}
                {h.people[0]?.rest_compliance ? (
                  <EngineBadge engine={h.people[0].rest_compliance.validator} />
                ) : null}
              </>
            ) : null
          }
        </Async>
      </Section>
      <Section title={t("trendTitle")}>
        <Async query={trend}>
          {(items) => (
            <>
              <Bars
                items={items.map((i) => ({
                  key: i.roster_month,
                  label: fmt.monthShort(i.roster_month),
                  value: i.overtime_hours,
                  text: fmt.number(i.overtime_hours, 0),
                }))}
                label={t("trendLabel")}
              />
              <Table label={t("trendLabel")}>
                <thead>
                  <tr>
                    <th scope="col">{t("colMonth")}</th>
                    <th scope="col" className="text-right">
                      {t("colOvertime")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((i) => (
                    <tr key={i.roster_month}>
                      <td>{fmt.month(i.roster_month)}</td>
                      <td className="num-time text-right">{fmt.number(i.overtime_hours, 1)}</td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </>
          )}
        </Async>
      </Section>
    </>
  );
}

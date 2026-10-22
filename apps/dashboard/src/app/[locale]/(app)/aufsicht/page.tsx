"use client";

import { unwrap } from "@dienstpilot/api-client";
import { Download, Eye } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";

import { AuditTable, ChainIndicator } from "@/components/AuditTable";
import { DotStrip } from "@/components/charts";
import { MonthEnd } from "@/components/MonthEnd";
import { MonthSwitch } from "@/components/MonthSwitch";
import { Async, Button, ICON, Loading, PageHeader, Section, Table } from "@/components/ui";
import { useFmt } from "@/lib/fmt";
import { useAction, useQuery } from "@/lib/hooks";
import { useSession } from "@/lib/session";

function Kpi({
  label,
  value,
  note,
  testId,
}: {
  label: string;
  value: string;
  note?: string | undefined;
  testId?: string | undefined;
}): ReactNode {
  return (
    <div className="flex flex-col gap-1 border border-rule bg-sheet p-4" data-testid={testId}>
      <span className="caption text-ink-muted">{label}</span>
      <span className="num-figure">{value}</span>
      {note ? <span className="caption text-ink-muted">{note}</span> : null}
    </div>
  );
}

/** W12: read-only view for Klinikleitung and Betriebsrat. Fairness only as anonymous statistics. */
export default function OversightPage(): ReactNode {
  const t = useTranslations("w12");
  const tf = useTranslations("w8");
  const fmt = useFmt();
  const { api } = useSession();
  const clock = useQuery((a) => unwrap(a.GET("/clock")), []);
  const [month, setMonth] = useState<string | null>(null);
  const m = month ?? clock.data?.now.slice(0, 7) ?? null;
  const q = useQuery(
    (a) =>
      m
        ? unwrap(a.GET("/oversight/summary", { params: { query: { month: m } } }))
        : Promise.resolve(null),
    [m],
  );
  const audit = useQuery(
    (a) => unwrap(a.GET("/audit/events", { params: { query: { limit: 8 } } })),
    [],
  );
  const exportLog = useAction(async () => {
    const data = await unwrap(api.GET("/audit/export", { params: { query: {} } }));
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "dienstpilot-protokoll.json";
    a.click();
    URL.revokeObjectURL(url);
  });
  if (!m) return <Loading />;
  return (
    <Async query={q}>
      {(s) => {
        if (!s) return null;
        const over = s.hours.people.filter((p) => p.overtime_hours > 0).length;
        const violations = s.hours.rest_violations_total;
        const weekends = s.fairness.find((d) => d.metric === "weekends");
        return (
          <>
            <span
              className="label inline-flex w-fit items-center gap-2 border border-rule-strong px-2 py-1"
              data-testid="read-only"
            >
              <Eye {...ICON} /> {t("readOnly")}
            </span>
            <PageHeader
              title={
                violations === 0
                  ? t("headlineOk", { month: fmt.month(m) })
                  : t("headlineBad", { month: fmt.month(m), count: violations })
              }
              status={t("sublineOversight", { date: fmt.date(clock.data?.now ?? `${m}-01`) })}
              actions={<MonthSwitch month={m} onChange={setMonth} />}
            />
            <div className="flex flex-wrap gap-2">
              <Button
                onClick={() => void exportLog.run()}
                disabled={exportLog.pending}
                icon={<Download {...ICON} />}
              >
                {t("export")}
              </Button>
            </div>
            <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(220px,1fr))]">
              <Kpi
                label={t("kpiRest")}
                value={
                  violations === 0 ? tf("restOk") : tf("restViolations", { count: violations })
                }
                note={t("kpiRestNote", { people: s.hours.people.length })}
              />
              <Kpi
                label={t("kpiOvertime")}
                value={fmt.hours(s.hours.total_overtime_hours)}
                note={t("kpiOvertimeNote", { over })}
              />
              <Kpi
                label={t("costTitle")}
                value="–"
                note={t("kpiCostNote")}
                testId="cost-placeholder"
              />
              <Kpi
                label={t("kpiWeekends")}
                value={weekends ? `${String(weekends.minimum)}–${String(weekends.maximum)}` : "–"}
                note={
                  weekends
                    ? t("kpiWeekendsNote", { median: fmt.number(weekends.median, 1) })
                    : undefined
                }
              />
            </div>
            <div className="grid items-start gap-6 [grid-template-columns:minmax(0,3fr)_minmax(320px,2fr)]">
              <Section title={t("hoursTitle", { month: fmt.month(m) })}>
                <Table label={t("hoursLabel")}>
                  <thead>
                    <tr>
                      <th scope="col">{tf("colPerson")}</th>
                      <th scope="col" className="text-right">
                        {tf("colContract")}
                      </th>
                      <th scope="col" className="text-right">
                        {tf("colPlanned")}
                      </th>
                      <th scope="col" className="text-right">
                        {tf("colOvertime")}
                      </th>
                      <th scope="col">{tf("colRest")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...s.hours.people]
                      .sort((a, b) => b.overtime_hours - a.overtime_hours)
                      .map((p) => (
                        <tr key={p.staff_id}>
                          <td>{p.display_name}</td>
                          <td className="num-time text-right">{fmt.number(p.contract_hours, 1)}</td>
                          <td className="num-time text-right">{fmt.number(p.planned_hours, 1)}</td>
                          <td className="num-time text-right">{fmt.number(p.overtime_hours, 1)}</td>
                          <td>
                            {p.rest_compliance
                              ? p.rest_compliance.compliant
                                ? tf("restOk")
                                : tf("restViolations", { count: p.rest_compliance.violations })
                              : "–"}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </Table>
              </Section>
              <div className="flex flex-col gap-6">
                <Section title={t("auditTitle")}>
                  <Async query={audit}>
                    {(d) => (
                      <>
                        <ChainIndicator chain={d.chain} />
                        <AuditTable events={d.events} />
                      </>
                    )}
                  </Async>
                </Section>
                <Section title={t("fairnessTitle")}>
                  <p className="caption m-0 text-ink-muted">{t("fairnessNote")}</p>
                  {s.fairness.map((d) => {
                    const name = tf(`metric.${d.metric as "nights"}`);
                    return (
                      <div key={d.metric} className="flex flex-col gap-1">
                        <h3 className="label m-0">{name}</h3>
                        <DotStrip
                          values={d.values}
                          min={d.minimum}
                          max={d.maximum}
                          median={d.median}
                          mean={d.mean}
                          label={tf("distLabel", {
                            name,
                            people: d.people,
                            min: d.minimum,
                            median: fmt.number(d.median, 1),
                            max: d.maximum,
                          })}
                        />
                        <p className="caption m-0 text-ink-muted">
                          {tf("distFacts", {
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
                </Section>
              </div>
            </div>
            <MonthEnd />
          </>
        );
      }}
    </Async>
  );
}

"use client";

import { unwrap } from "@dienstpilot/api-client";
import { Download, Eye } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";

import { AuditTable, ChainIndicator } from "@/components/AuditTable";
import { DotStrip } from "@/components/charts";
import { MonthSwitch } from "@/components/MonthSwitch";
import { Async, Button, ICON, Loading, PageHeader, Section, Table } from "@/components/ui";
import { useFmt } from "@/lib/fmt";
import { useAction, useQuery } from "@/lib/hooks";
import { useSession } from "@/lib/session";

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
    (a) => unwrap(a.GET("/audit/events", { params: { query: { limit: 20 } } })),
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
    <>
      <PageHeader
        title={t("title")}
        status={
          <span className="inline-flex items-center gap-2" data-testid="read-only">
            <Eye {...ICON} /> {t("readOnly")}
          </span>
        }
        actions={<MonthSwitch month={m} onChange={setMonth} />}
      />
      <Async query={q}>
        {(s) => {
          if (!s) return null;
          const over = s.hours.people.filter((p) => p.overtime_hours > 0).length;
          return (
            <>
              <Section title={t("hoursTitle", { month: fmt.month(m) })}>
                <p className="body m-0">
                  {t("hoursSummary", {
                    overtime: fmt.number(s.hours.total_overtime_hours, 1),
                    violations: s.hours.rest_violations_total,
                    over,
                  })}
                </p>
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
              <Section title={t("fairnessTitle")}>
                <p className="caption m-0 text-ink-muted">{t("fairnessNote")}</p>
                <div className="grid gap-6 [grid-template-columns:repeat(auto-fit,minmax(320px,1fr))]">
                  {s.fairness.map((d) => {
                    const name = tf(`metric.${d.metric as "nights"}`);
                    return (
                      <div key={d.metric} className="flex flex-col gap-2">
                        <h3 className="heading m-0">{name}</h3>
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
                        <p className="num-small m-0 text-ink-muted">
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
                </div>
              </Section>
              <Section title={t("costTitle")}>
                <p
                  className="body m-0 rounded-mark border border-dashed border-pencil bg-pencil-wash p-3 text-pencil"
                  data-testid="cost-placeholder"
                >
                  {t("costNone")}
                </p>
              </Section>
            </>
          );
        }}
      </Async>
      <Section
        title={t("auditTitle")}
        aside={
          <Button
            onClick={() => void exportLog.run()}
            disabled={exportLog.pending}
            icon={<Download {...ICON} />}
          >
            {t("export")}
          </Button>
        }
      >
        <Async query={audit}>
          {(d) => (
            <>
              <ChainIndicator
                verified={(d as { chain_verified?: boolean | null }).chain_verified ?? null}
                fromPhase={d.chain_available_from_phase}
              />
              <AuditTable events={d.events} />
            </>
          )}
        </Async>
      </Section>
    </>
  );
}

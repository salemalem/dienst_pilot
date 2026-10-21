"use client";

import { unwrap } from "@dienstpilot/api-client";
import { Check, CircleAlert, CircleCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { CoverageChart } from "@/components/charts";
import { EngineBadge } from "@/components/EngineBadge";
import { ShiftLabel } from "@/components/shift";
import { Async, ICON, PageHeader, Progress, Section } from "@/components/ui";
import { Link } from "@/i18n/navigation";
import { useFmt } from "@/lib/fmt";
import { useQuery } from "@/lib/hooks";

/** W1: status first (what needs a decision), then the window, the next 14 days and recent changes. */
export default function OverviewPage(): ReactNode {
  const t = useTranslations("w1");
  const ta = useTranslations("approval");
  const fmt = useFmt();
  const q = useQuery((api) => unwrap(api.GET("/planner/overview")), []);

  return (
    <Async query={q}>
      {(o) => {
        const open = o.escalations + o.pending_leave + o.open_proposals;
        const w = o.window;
        const today = o.now.slice(0, 10);
        const days = o.coverage.slice(0, 14);
        const short = days.filter((d) => d.short > 0);
        return (
          <>
            <PageHeader
              title={open === 0 ? t("statusNothing") : t("statusOpen", { count: open })}
              status={t("dateLine", {
                weekday: fmt.weekday(today),
                date: fmt.date(today),
                published: o.published_month ? fmt.month(o.published_month) : "–",
                planning: o.planning_month ? fmt.month(o.planning_month) : "–",
              })}
            />
            <div className="grid gap-6 [grid-template-columns:repeat(auto-fit,minmax(340px,1fr))]">
              <Section
                title={
                  w
                    ? t("window.titleMonth", { month: fmt.monthShort(w.roster_month) })
                    : t("window.title")
                }
                aside={
                  w ? (
                    <span className="label text-ink-muted">
                      {t("window.daysLeft", {
                        days: w.days_left,
                        date: fmt.dayMonth(w.closes_at.slice(0, 10)),
                      })}
                    </span>
                  ) : null
                }
              >
                {w ? (
                  <>
                    <p className="num-figure m-0" data-testid="window-progress">
                      {t("window.progress", { responded: w.responded, recipients: w.recipients })}
                    </p>
                    <Progress
                      value={w.responded}
                      max={w.recipients}
                      label={t("window.progress", {
                        responded: w.responded,
                        recipients: w.recipients,
                      })}
                    />
                    <p className="body m-0 text-ink-muted">
                      {t("window.missing", { count: w.recipients - w.responded })}
                    </p>
                    <Link href="/wunschphase" className="label text-action underline">
                      {t("window.open")}
                    </Link>
                  </>
                ) : (
                  <p className="body m-0">{t("window.none")}</p>
                )}
              </Section>
              <Section title={t("open.title")}>
                <p className="body-strong m-0 flex items-center gap-2" data-testid="escalations">
                  {o.escalations > 0 ? (
                    <CircleAlert
                      size={20}
                      strokeWidth={1.75}
                      absoluteStrokeWidth
                      className="text-alert"
                      aria-hidden
                    />
                  ) : (
                    <CircleCheck {...ICON} size={20} />
                  )}
                  {t("open.escalations", { count: o.escalations })}
                </p>
                <ul className="body m-0 flex list-none flex-col gap-2 border-t border-rule p-0 pt-3">
                  <li className="flex items-center gap-2">
                    <Check {...ICON} size={20} />
                    {t("open.leave", { count: o.pending_leave })}
                  </li>
                  <li className="flex items-center gap-2">
                    <Check {...ICON} size={20} />
                    {t("open.proposals", { count: o.open_proposals })}
                  </li>
                </ul>
                <Link href="/anfragen" className="label text-action underline">
                  {t("open.toRequests")}
                </Link>
              </Section>
            </div>
            <Section title={t("coverage.title")} aside={<EngineBadge engine={o.forecast_engine} />}>
              <p className="body m-0 text-ink-muted">
                {short.length === 0
                  ? t("coverage.allStaffed")
                  : t("coverage.someShort", { count: short.length })}{" "}
                {t("coverage.note")}
              </p>
              <div className="overflow-x-auto">
                <CoverageChart
                  label={t("coverage.chartLabel")}
                  todayLabel={t("coverage.today")}
                  axisLabel={t("coverage.axis")}
                  days={days.map((d) => ({
                    date: d.date,
                    short: d.short,
                    expected: d.expected_absences,
                    low: d.expected_low,
                    high: d.expected_high,
                    weekday: fmt.weekday(d.date),
                    label: fmt.dayMonth(d.date),
                    weekend: [5, 6].includes((new Date(`${d.date}T12:00:00Z`).getUTCDay() + 6) % 7),
                    today: d.date === today,
                    expectedText: fmt.number(d.expected_absences, 1),
                  }))}
                />
              </div>
              <details>
                <summary className="label cursor-pointer">{t("coverage.asTable")}</summary>
                <div className="overflow-x-auto">
                  <table
                    aria-label={t("coverage.title")}
                    className="w-full border-collapse text-center"
                    data-testid="coverage"
                  >
                    <thead>
                      <tr>
                        <th scope="row" className="label pr-3 text-left text-ink-muted">
                          {t("coverage.date")}
                        </th>
                        {days.map((d) => (
                          <th
                            key={d.date}
                            scope="col"
                            className="num-small min-w-[52px] border-b border-rule-strong p-1"
                          >
                            <span className="block text-ink-muted">{fmt.weekday(d.date)}</span>
                            {fmt.dayMonth(d.date).replace(/\.$/, "")}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <th scope="row" className="label pr-3 text-left">
                          {t("coverage.staffing")}
                        </th>
                        {days.map((d) => (
                          <td key={d.date} className="border-b border-rule p-1">
                            {d.short > 0 ? (
                              <span className="inline-flex items-center gap-1 text-alert">
                                <CircleAlert {...ICON} />
                                <span className="num-small">
                                  {t("coverage.short", { count: d.short })}
                                </span>
                              </span>
                            ) : (
                              <span className="inline-flex" title={t("coverage.ok")}>
                                <Check {...ICON} />
                                <span className="sr-only">{t("coverage.ok")}</span>
                              </span>
                            )}
                          </td>
                        ))}
                      </tr>
                      <tr>
                        <th scope="row" className="label pr-3 text-left">
                          {t("coverage.expected")}
                        </th>
                        {days.map((d) => (
                          <td key={d.date} className="num-small border-b border-rule p-1">
                            <span className="block">{fmt.number(d.expected_absences, 1)}</span>
                            <span className="block text-ink-muted">
                              {fmt.number(d.expected_low, 0)}–{fmt.number(d.expected_high, 0)}
                            </span>
                          </td>
                        ))}
                      </tr>
                    </tbody>
                  </table>
                </div>
              </details>
            </Section>
            <Section title={t("recent.title")}>
              {o.recent.length === 0 ? (
                <p className="body m-0">{t("recent.empty")}</p>
              ) : (
                <ul className="body m-0 flex list-none flex-col gap-3 p-0" data-testid="recent">
                  {o.recent.map((r) => (
                    <li
                      key={`${r.kind}-${r.at}-${r.date}-${r.shift_type}`}
                      className="flex flex-wrap items-center gap-3"
                    >
                      <CircleCheck {...ICON} size={20} />
                      <span className="body-strong">{t(`recent.${r.kind}`)}</span>
                      <span className="num-time">{fmt.dayMonth(r.date)}</span>
                      <ShiftLabel code={r.shift_type} />
                      {r.staff_name ? <span>{r.staff_name}</span> : null}
                      {r.approval === "policy" || r.approval === "planner" ? (
                        <span className="caption text-ink-muted">{ta(r.approval)}</span>
                      ) : null}
                      <span className="caption text-ink-muted">{fmt.dateTime(r.at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          </>
        );
      }}
    </Async>
  );
}

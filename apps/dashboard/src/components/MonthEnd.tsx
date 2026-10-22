"use client";

import { unwrap } from "@dienstpilot/api-client";
import { FileText } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";

import { Async, Button, ErrorState, ICON, Section } from "@/components/ui";
import { useFmt } from "@/lib/fmt";
import { useAction, useQuery } from "@/lib/hooks";
import { useSession } from "@/lib/session";

/**
 * W12: the month-end documentation. It is prepared by itself once the month is over (demo time);
 * the Planner confirms it with one click, which locks it and releases the payroll export.
 */
export function MonthEnd(): ReactNode {
  const t = useTranslations("w12.monthEnd");
  const fmt = useFmt();
  const { api, me } = useSession();
  const months = useQuery((a) => unwrap(a.GET("/oversight/months")), []);
  const [picked, setPicked] = useState<string | null>(null);
  const month = picked ?? months.data?.[0]?.roster_month.slice(0, 7) ?? null;
  const report = useQuery(
    (a) =>
      month
        ? unwrap(a.GET("/oversight/months/{month}/report", { params: { path: { month } } }))
        : Promise.resolve(null),
    [month],
  );
  const close = useAction(async () => {
    if (!month) return;
    await unwrap(api.POST("/planner/months/{month}/close", { params: { path: { month } } }));
    months.reload();
    report.reload();
  });
  const download = useAction(async () => {
    if (!month) return;
    const text = await unwrap(
      api.GET("/oversight/months/{month}/payroll", {
        params: { path: { month }, query: { format: "csv" } },
        parseAs: "text",
      }),
    );
    const url = URL.createObjectURL(new Blob([text as string], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `lohnexport-${month}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  });
  return (
    <Section title={t("title")}>
      <Async query={months}>
        {(list) =>
          list.length === 0 ? (
            <p className="body m-0 text-ink-muted" data-testid="month-end-none">
              {t("none")}
            </p>
          ) : (
            <div className="flex flex-col gap-3" data-testid="month-end">
              <label className="flex items-center gap-2">
                <span className="label">{t("month")}</span>
                <select
                  className="dp-input label !w-auto"
                  value={month ?? ""}
                  onChange={(e) => {
                    setPicked(e.target.value);
                  }}
                >
                  {list.map((m) => (
                    <option key={m.roster_month} value={m.roster_month.slice(0, 7)}>
                      {fmt.month(m.roster_month)} · {t(`status.${m.status as "prepared"}`)}
                    </option>
                  ))}
                </select>
              </label>
              <Async query={report}>
                {(r) =>
                  r ? (
                    <>
                      <p className="body m-0" data-testid="month-end-status">
                        {r.status === "closed"
                          ? t("closedAt", { at: fmt.dateTime(r.closed_at ?? r.prepared_at) })
                          : t("preparedAt", { at: fmt.dateTime(r.prepared_at) })}
                      </p>
                      <p className="body m-0">
                        {t("summary", {
                          overtime: fmt.number(r.total_overtime_hours, 1),
                          violations: r.rest_violations_total,
                          people: r.people.length,
                          entries: r.decision_trail.length,
                        })}
                      </p>
                      <p className="caption m-0 text-ink-muted" data-testid="month-end-narrative">
                        <strong>{t("narrativeLabel")}</strong> {r.narrative.text}
                      </p>
                      <div className="flex flex-wrap items-center gap-3">
                        {me.role === "planner" && r.status === "prepared" ? (
                          <Button
                            variant="primary"
                            onClick={() => void close.run()}
                            disabled={close.pending}
                            data-testid="close-month"
                          >
                            {t("close")}
                          </Button>
                        ) : null}
                        <Button
                          icon={<FileText {...ICON} size={18} />}
                          onClick={() => void download.run()}
                          disabled={!r.payroll_released || download.pending}
                          data-testid="payroll-export"
                        >
                          {t("payroll")}
                        </Button>
                        {!r.payroll_released ? (
                          <span className="caption text-ink-muted">{t("payrollLocked")}</span>
                        ) : null}
                      </div>
                      {close.error ? <ErrorState error={close.error} /> : null}
                      {download.error ? <ErrorState error={download.error} /> : null}
                      <p className="caption m-0 text-ink-muted">
                        {t("hash", { hash: r.report_hash.slice(0, 12) })}
                      </p>
                    </>
                  ) : null
                }
              </Async>
            </div>
          )
        }
      </Async>
    </Section>
  );
}

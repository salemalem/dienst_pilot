"use client";

import { unwrap } from "@dienstpilot/api-client";
import { Download } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";

import { AuditTable, ChainIndicator, actionKey } from "@/components/AuditTable";
import { Async, Button, Field, ICON, PageHeader, Section } from "@/components/ui";
import { AUDIT_ACTIONS } from "@/lib/audit";
import { useAction, useQuery } from "@/lib/hooks";
import { useSession } from "@/lib/session";

const PAGE = 50;

/** W10: filterable event log; who requested, what was proposed, who approved, when. */
export default function AuditPage(): ReactNode {
  const t = useTranslations("w10");
  const { api } = useSession();
  const [action, setAction] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [offset, setOffset] = useState(0);
  const q = useQuery(
    (a) =>
      unwrap(
        a.GET("/audit/events", {
          params: {
            query: {
              ...(action ? { action } : {}),
              ...(since ? { since: `${since}T00:00:00+02:00` } : {}),
              ...(until ? { until: `${until}T23:59:59+02:00` } : {}),
              limit: PAGE,
              offset,
            },
          },
        }),
      ),
    [action, since, until, offset],
  );
  const verify = useAction(async () => {
    await unwrap(api.POST("/audit/verify"));
    q.reload();
  });
  const exportLog = useAction(async () => {
    const data = await unwrap(api.GET("/audit/export", { params: { query: {} } }));
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "dienstpilot-protokoll.json";
    a.click();
    URL.revokeObjectURL(url);
  });

  return (
    <>
      <PageHeader
        title={t("title")}
        status={q.data ? t("status", { total: q.data.total }) : undefined}
        actions={
          <Button
            onClick={() => void exportLog.run()}
            disabled={exportLog.pending}
            icon={<Download {...ICON} />}
          >
            {t("export")}
          </Button>
        }
      />
      <div className="flex flex-wrap items-end gap-4" role="search" aria-label={t("filterTitle")}>
        {" "}
        <>
          <Field label={t("filterAction")}>
            {(p) => (
              <select
                {...p}
                className="dp-input"
                value={action}
                onChange={(e) => {
                  setAction(e.target.value);
                  setOffset(0);
                }}
              >
                <option value="">{t("all")}</option>
                {AUDIT_ACTIONS.map((a) => (
                  <option key={a} value={a}>
                    {t(`action.${actionKey(a) as "run_requested"}`)}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label={t("filterSince")}>
            {(p) => (
              <input
                {...p}
                type="date"
                className="dp-input"
                value={since}
                onChange={(e) => {
                  setSince(e.target.value);
                  setOffset(0);
                }}
              />
            )}
          </Field>
          <Field label={t("filterUntil")}>
            {(p) => (
              <input
                {...p}
                type="date"
                className="dp-input"
                value={until}
                onChange={(e) => {
                  setUntil(e.target.value);
                  setOffset(0);
                }}
              />
            )}
          </Field>
        </>
      </div>
      <Async query={q}>
        {(d) => (
          <Section
            title={t("eventsTitle")}
            aside={
              <ChainIndicator
                chain={d.chain}
                onVerify={() => void verify.run()}
                verifying={verify.pending}
              />
            }
          >
            <AuditTable events={d.events} />
            <div className="flex items-center gap-3">
              <Button
                disabled={offset === 0}
                onClick={() => {
                  setOffset(Math.max(0, offset - PAGE));
                }}
              >
                {t("prev")}
              </Button>
              <span className="num-small text-ink-muted">
                {t("range", {
                  from: d.total === 0 ? 0 : offset + 1,
                  to: Math.min(offset + PAGE, d.total),
                  total: d.total,
                })}
              </span>
              <Button
                disabled={offset + PAGE >= d.total}
                onClick={() => {
                  setOffset(offset + PAGE);
                }}
              >
                {t("next")}
              </Button>
            </div>
          </Section>
        )}
      </Async>
    </>
  );
}

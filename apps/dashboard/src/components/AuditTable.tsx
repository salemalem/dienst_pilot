"use client";

import type { components } from "@dienstpilot/api-client";
import { ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { ICON, Table } from "@/components/ui";
import { AUDIT_ACTIONS } from "@/lib/audit";
import { useFmt } from "@/lib/fmt";

type Event = components["schemas"]["AuditEventOut"];

/** Who did what, when; absences appear without a category for everyone but the Planner (the API decides). */
export function AuditTable({ events }: { events: Event[] }): ReactNode {
  const t = useTranslations("w10");
  const fmt = useFmt();
  const label = (a: string): string =>
    (AUDIT_ACTIONS as readonly string[]).includes(a) ? t(`action.${a as "run.requested"}`) : a;
  return (
    <Table label={t("tableLabel")}>
      <thead>
        <tr>
          <th scope="col">{t("colTime")}</th>
          <th scope="col">{t("colActor")}</th>
          <th scope="col">{t("colAction")}</th>
          <th scope="col">{t("colSubject")}</th>
        </tr>
      </thead>
      <tbody data-testid="audit-rows">
        {events.map((e) => (
          <tr key={e.id} data-action={e.action}>
            <td className="num-time whitespace-nowrap">{fmt.dateTime(e.occurred_at)}</td>
            <td>{e.actor}</td>
            <td>
              {label(e.action)}
              {e.payload.approval === "policy" ? (
                <span className="caption block text-ink-muted">{t("byPolicy")}</span>
              ) : null}
              {typeof e.payload.reason === "string" ? (
                <span className="caption block text-ink-muted">
                  {t("reason", { reason: e.payload.reason })}
                </span>
              ) : null}
            </td>
            <td>{e.staff_name ?? e.subject_type}</td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

/** The hash chain arrives in Phase 9; until then the indicator says so instead of showing a tick. */
export function ChainIndicator({
  verified,
  fromPhase,
}: {
  verified: boolean | null;
  fromPhase: number;
}): ReactNode {
  const t = useTranslations("w10");
  if (verified) {
    return (
      <p className="body-strong m-0 flex items-center gap-2" data-testid="chain">
        <ShieldCheck {...ICON} size={20} /> {t("chainOk")}
      </p>
    );
  }
  return (
    <p className="body m-0 text-ink-muted" data-testid="chain">
      {t("chainLater", { phase: fromPhase })}
    </p>
  );
}

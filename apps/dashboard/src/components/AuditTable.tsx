"use client";

import type { components } from "@dienstpilot/api-client";
import { ShieldAlert, ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { Button, ICON, Table } from "@/components/ui";
import { AUDIT_ACTIONS } from "@/lib/audit";
import { useFmt } from "@/lib/fmt";

/** Catalog keys cannot contain dots, so `run.requested` is `run_requested`. */
export const actionKey = (a: string): string => a.replace(".", "_");

type Event = components["schemas"]["AuditEventOut"];

/** Who did what, when; absences appear without a category for everyone but the Planner (the API decides). */
export function AuditTable({ events }: { events: Event[] }): ReactNode {
  const t = useTranslations("w10");
  const fmt = useFmt();
  const subject = (type: string): string =>
    t.has(`subject.${type}` as "subject.roster_variant")
      ? t(`subject.${type}` as "subject.roster_variant")
      : type;
  const label = (a: string): string =>
    (AUDIT_ACTIONS as readonly string[]).includes(a)
      ? t(`action.${actionKey(a) as "run_requested"}`)
      : a;
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
            <td>{e.staff_name ?? subject(e.subject_type)}</td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

type Chain = components["schemas"]["ChainOut"];

/**
 * What the log says about itself. The tick appears only when the last real verification passed
 * (and is recent); a broken chain, a stale check and "never checked" each say so.
 */
export function ChainIndicator({
  chain,
  onVerify,
  verifying = false,
}: {
  chain: Chain;
  onVerify?: () => void;
  verifying?: boolean;
}): ReactNode {
  const t = useTranslations("w10");
  const fmt = useFmt();
  const checked = chain.checked_at ? fmt.dateTime(chain.checked_at) : "";
  const headline =
    chain.state === "verified"
      ? t("chainOk")
      : chain.state === "stale"
        ? t("chainStale")
        : chain.state === "failed"
          ? t("chainFailed", { seq: chain.first_bad_seq ?? 0 })
          : t("chainNever");
  return (
    <div className="flex flex-col gap-1" data-testid="chain" data-state={chain.state}>
      <p
        className={`${chain.state === "verified" ? "body-strong" : "body"} m-0 flex items-center gap-2 ${
          chain.state === "failed" ? "text-danger" : ""
        }`}
        role={chain.state === "failed" ? "alert" : undefined}
      >
        {chain.state === "verified" ? (
          <ShieldCheck {...ICON} size={20} />
        ) : (
          <ShieldAlert {...ICON} size={20} />
        )}{" "}
        {headline}
      </p>
      {chain.checked_at && (
        <p className="caption m-0 text-ink-muted">
          {t("chainDetail", { time: checked, rows: chain.rows })}
          {chain.reason ? ` ${chain.reason}` : ""}
        </p>
      )}
      {onVerify && (
        <Button onClick={onVerify} disabled={verifying}>
          {t("chainVerify")}
        </Button>
      )}
    </div>
  );
}

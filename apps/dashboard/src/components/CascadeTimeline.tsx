"use client";

import type { components } from "@dienstpilot/api-client";
import {
  BellRing,
  CircleAlert,
  CircleCheck,
  CircleX,
  TimerOff,
  type LucideIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { ShiftLabel } from "@/components/shift";
import { ICON } from "@/components/ui";
import { useFmt } from "@/lib/fmt";

type Cascade = components["schemas"]["CascadeOut"];

const STEP: Record<
  string,
  { icon: LucideIcon; key: "asked" | "declined" | "timedOut" | "accepted" }
> = {
  pending: { icon: BellRing, key: "asked" },
  declined: { icon: CircleX, key: "declined" },
  no_response: { icon: TimerOff, key: "timedOut" },
  accepted: { icon: CircleCheck, key: "accepted" },
};

/** The sick-call cascade as a timeline: asked, declined, timed out, accepted (icon plus word). */
export function CascadeTimeline({ cascade }: { cascade: Cascade }): ReactNode {
  const t = useTranslations("w7");
  const fmt = useFmt();
  const closed = cascade.status === "closed" && cascade.outcome === "covered";
  const accepted = cascade.timeline.find((s) => s.response === "accepted");
  return (
    <div
      className="flex flex-col gap-3"
      data-testid="cascade"
      data-status={cascade.status}
      data-outcome={cascade.outcome ?? ""}
    >
      <div className="flex flex-wrap items-center gap-3">
        <span className="heading">{fmt.dayMonth(cascade.date)}</span>
        <ShiftLabel code={cascade.shift_type} />
        {cascade.absent_staff ? (
          <span className="body">{t("absent", { name: cascade.absent_staff })}</span>
        ) : null}
        <span className="caption text-ink-muted">
          {t("opened", { time: fmt.dateTime(cascade.opened_at) })}
        </span>
      </div>
      {closed && accepted ? (
        <p className="body-strong m-0 flex items-center gap-2" data-testid="gap-closed">
          <CircleCheck {...ICON} size={20} />
          {t("closed", {
            name: cascade.covered_by ?? accepted.staff_name ?? "",
            time: fmt.time(accepted.responded_at ?? cascade.opened_at),
          })}
        </p>
      ) : cascade.status === "pending_approval" ? (
        <p className="body-strong m-0 flex items-center gap-2 text-alert">
          <CircleAlert {...ICON} size={20} />
          {t("pendingApproval")}
        </p>
      ) : cascade.status === "closed" ? (
        <p className="body-strong m-0">
          {t(`outcome.${(cascade.outcome ?? "unfilled") as "unfilled"}`)}
        </p>
      ) : (
        <p className="body m-0">{t("open", { count: cascade.remaining_candidates })}</p>
      )}
      <ol className="m-0 flex list-none flex-col gap-2 p-0">
        {cascade.timeline.map((s) => {
          const step = STEP[s.response] ?? STEP.pending;
          if (!step) return null;
          const Icon = step.icon;
          return (
            <li key={`${s.rank}-${s.asked_at}`} className="body flex flex-wrap items-center gap-3">
              <Icon size={20} strokeWidth={1.75} absoluteStrokeWidth aria-hidden />
              <span className="label min-w-[9ch]">{t(`step.${step.key}`)}</span>
              <span>{s.staff_name ? s.staff_name : t("someone", { rank: s.rank })}</span>
              <span className="num-small text-ink-muted">
                {t("askedAt", { time: fmt.time(s.asked_at) })}
                {s.deadline_at && s.response === "pending"
                  ? `, ${t("replyBy", { time: fmt.time(s.deadline_at) })}`
                  : ""}
                {s.responded_at ? `, ${t("answeredAt", { time: fmt.time(s.responded_at) })}` : ""}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

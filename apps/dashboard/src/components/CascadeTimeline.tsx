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
type Step = Cascade["timeline"][number];

type Kind = "asked" | "declined" | "timedOut" | "accepted";

const ICONS: Record<Kind, LucideIcon> = {
  asked: BellRing,
  declined: CircleX,
  timedOut: TimerOff,
  accepted: CircleCheck,
};

interface Event {
  at: string;
  kind: Kind;
  step: Step;
}

/** Each offer is an "asked" event, then (once it is answered or has run out) a second event. */
function events(timeline: Step[]): Event[] {
  const out: Event[] = [];
  for (const s of timeline) {
    out.push({ at: s.asked_at, kind: "asked", step: s });
    if (s.response === "declined")
      out.push({ at: s.responded_at ?? s.asked_at, kind: "declined", step: s });
    else if (s.response === "no_response")
      out.push({ at: s.deadline_at ?? s.responded_at ?? s.asked_at, kind: "timedOut", step: s });
    else if (s.response === "accepted")
      out.push({ at: s.responded_at ?? s.asked_at, kind: "accepted", step: s });
  }
  return out.sort((a, b) => a.at.localeCompare(b.at));
}

/** The sick-call cascade as a timeline: time, icon and word per step (never colour alone). */
export function CascadeTimeline({ cascade }: { cascade: Cascade }): ReactNode {
  const t = useTranslations("w7");
  const fmt = useFmt();
  const closed = cascade.status === "closed" && cascade.outcome === "covered";
  const accepted = cascade.timeline.find((s) => s.response === "accepted");
  const name = (s: Step): string => s.staff_name ?? t("someone", { rank: s.rank });
  const line = (e: Event): string => {
    const who = name(e.step);
    if (e.kind === "asked")
      return e.step.deadline_at
        ? t("lineAsked", { name: who, time: fmt.time(e.step.deadline_at) })
        : t("lineAskedPlain", { name: who });
    if (e.kind === "timedOut") return t("lineTimedOut", { name: who });
    return t(e.kind === "declined" ? "lineDeclined" : "lineAccepted", { name: who });
  };
  return (
    <div
      className="flex flex-col gap-3"
      data-testid="cascade"
      data-status={cascade.status}
      data-outcome={cascade.outcome ?? ""}
    >
      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap items-center gap-3">
          <span className="label text-ink-muted">{fmt.dayMonth(cascade.date)}</span>
          <ShiftLabel code={cascade.shift_type} />
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
          <p className="body-strong m-0">{t("open", { count: cascade.remaining_candidates })}</p>
        )}
        {cascade.absent_staff ? (
          <p className="caption m-0 text-ink-muted">
            {t("absentSince", { name: cascade.absent_staff, time: fmt.time(cascade.opened_at) })}
          </p>
        ) : null}
      </div>
      <ol className="m-0 flex list-none flex-col gap-1 border-t border-rule p-0 pt-3">
        {events(cascade.timeline).map((e, i) => {
          const Icon = ICONS[e.kind];
          return (
            <li
              key={`${e.kind}-${e.step.rank}-${String(i)}`}
              className="body flex items-center gap-3 py-1"
            >
              <span className="num-small w-[4ch] text-ink-muted">{fmt.time(e.at)}</span>
              <Icon size={20} strokeWidth={1.75} absoluteStrokeWidth aria-hidden />
              <span>
                <strong>{t(`step.${e.kind}`)}</strong>: {line(e)}
              </span>
            </li>
          );
        })}
      </ol>
      {closed && accepted && cascade.escalation_reason === null ? (
        <p className="caption m-0 text-ink-muted">
          {t("noAction", { time: fmt.time(accepted.responded_at ?? cascade.opened_at) })}
        </p>
      ) : null}
    </div>
  );
}

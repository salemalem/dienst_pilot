"use client";

import { ApiError, unwrap, type components } from "@dienstpilot/api-client";
import { CircleAlert } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";

import { EngineBadge } from "@/components/EngineBadge";
import { RuleMessage } from "@/components/RuleMessage";
import { ShiftLabel } from "@/components/shift";
import { Suggestion } from "@/components/Suggestion";
import {
  Async,
  Button,
  Dialog,
  ErrorState,
  Field,
  PageHeader,
  Section,
  useToast,
} from "@/components/ui";
import { Link } from "@/i18n/navigation";
import { useFmt } from "@/lib/fmt";
import { useAction, useQuery } from "@/lib/hooks";
import { useSession } from "@/lib/session";

type Inbox = components["schemas"]["Inbox"];

interface Target {
  kind: "leave" | "swap";
  id: string;
  label: string;
}

function DeclineDialog({
  target,
  onClose,
  onDone,
}: {
  target: Target | null;
  onClose: () => void;
  onDone: () => void;
}): ReactNode {
  const t = useTranslations("w6");
  const { api } = useSession();
  const toast = useToast();
  const [reason, setReason] = useState("");
  const decline = useAction(async () => {
    if (!target) return;
    const body = { approve: false, reason: reason.trim() };
    if (target.kind === "leave")
      await unwrap(
        api.POST("/planner/leave/{request_id}/decision", {
          params: { path: { request_id: target.id } },
          body,
        }),
      );
    else
      await unwrap(
        api.POST("/planner/swaps/{swap_id}/decision", {
          params: { path: { swap_id: target.id } },
          body,
        }),
      );
    toast.show(t("declined"));
    setReason("");
    onDone();
    onClose();
  });
  return (
    <Dialog
      open={target !== null}
      title={target ? t("declineTitle", { label: target.label }) : ""}
      onClose={onClose}
      footer={
        <>
          <Button variant="quiet" onClick={onClose}>
            {t("cancel")}
          </Button>
          <Button
            variant="primary"
            disabled={decline.pending || reason.trim().length < 3}
            onClick={() => void decline.run()}
            data-testid="confirm-decline"
          >
            {t("decline")}
          </Button>
        </>
      }
    >
      <p className="body m-0">{t("declineBody")}</p>
      <Field label={t("reason")}>
        {(p) => (
          <textarea
            {...p}
            className="dp-input"
            value={reason}
            onChange={(e) => {
              setReason(e.target.value);
            }}
          />
        )}
      </Field>
      {decline.error ? <ErrorState error={decline.error} /> : null}
    </Dialog>
  );
}

/** W6: leave requests with their computed impact, escalated swaps and cover, copilot proposals. */
export default function RequestsPage(): ReactNode {
  const t = useTranslations("w6");
  const te = useTranslations("escalation");
  const fmt = useFmt();
  const toast = useToast();
  const { api } = useSession();
  const q = useQuery((a) => unwrap(a.GET("/planner/requests")), []);
  const [declining, setDeclining] = useState<Target | null>(null);
  const [blocked, setBlocked] = useState<Record<string, components["schemas"]["ViolationOut"][]>>(
    {},
  );

  const approve = useAction(async (kind: "leave" | "swap", id: string) => {
    try {
      const body = { approve: true, reason: null };
      if (kind === "leave")
        await unwrap(
          api.POST("/planner/leave/{request_id}/decision", {
            params: { path: { request_id: id } },
            body,
          }),
        );
      else
        await unwrap(
          api.POST("/planner/swaps/{swap_id}/decision", {
            params: { path: { swap_id: id } },
            body,
          }),
        );
      toast.show(t("approved"));
      q.reload();
    } catch (e) {
      if (e instanceof ApiError && e.violations.length > 0)
        setBlocked((b) => ({ ...b, [id]: e.violations }));
      else throw e;
    }
  });
  const decideProposal = useAction(async (id: string, accept: boolean) => {
    await unwrap(
      api.POST("/planner/proposals/{proposal_id}/decision", {
        params: { path: { proposal_id: id } },
        body: { accept },
      }),
    );
    toast.show(accept ? t("proposalAccepted") : t("proposalDismissed"));
    q.reload();
  });

  const reasonText = (r: string | null): string | null =>
    r && te.has(r as "overtime") ? te(r as "overtime") : r;

  const body = (d: Inbox): ReactNode => {
    const total = d.leave.length + d.swaps.length + d.cascades.length + d.proposals.length;
    return (
      <>
        <PageHeader
          title={t("title")}
          status={total === 0 ? t("statusNone") : t("statusOpen", { count: total })}
        />
        {approve.error ? <ErrorState error={approve.error} /> : null}
        <Section title={t("leaveTitle", { count: d.leave.length })}>
          {d.leave.length === 0 ? <p className="body m-0">{t("leaveNone")}</p> : null}
          <ul className="m-0 flex list-none flex-col gap-4 p-0">
            {d.leave.map((l) => (
              <li
                key={l.id}
                className="flex flex-col gap-2 border-b border-rule pb-4"
                data-testid="leave-request"
              >
                <div className="flex flex-wrap items-baseline gap-3">
                  <span className="heading">{l.display_name}</span>
                  <span className="num-time">
                    {fmt.range(l.start_date, l.end_date)} {l.end_date.slice(0, 4)}
                  </span>
                  <span className="caption text-ink-muted">
                    {t("submitted", { date: fmt.date(l.submitted_at) })}
                  </span>
                </div>
                <p className="body m-0" data-testid="leave-impact">
                  {t(
                    `hint.${l.impact.hint === "tight" || l.impact.hint === "not_coverable" ? l.impact.hint : "coverable"}`,
                  )}{" "}
                  {t("impact", { max: l.impact.max_on_leave_same_day, limit: l.impact.limit })}
                </p>
                <p className="body m-0 text-ink-muted">
                  {t("leaveTaken", {
                    days: l.impact.leave_days_taken_this_year,
                    mean: fmt.number(l.impact.department_mean_leave_days, 1),
                  })}{" "}
                  <EngineBadge engine={l.impact.engine} />
                </p>
                {blocked[l.id]?.map((v) => (
                  <RuleMessage key={`${v.rule}-${v.date}`} violation={v} live />
                ))}
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="primary"
                    disabled={approve.pending}
                    onClick={() => void approve.run("leave", l.id)}
                    data-testid="approve-leave"
                  >
                    {t("approve")}
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setDeclining({ kind: "leave", id: l.id, label: l.display_name });
                    }}
                  >
                    {t("declineWithReason")}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </Section>
        <Section title={t("swapsTitle", { count: d.swaps.length + d.cascades.length })}>
          {d.swaps.length + d.cascades.length === 0 ? (
            <p className="body m-0">{t("swapsNone")}</p>
          ) : null}
          <ul className="m-0 flex list-none flex-col gap-4 p-0">
            {d.swaps.map((s) => (
              <li
                key={s.id}
                className="flex flex-col gap-2 border-b border-rule pb-4"
                data-testid="swap-request"
              >
                <div className="flex flex-wrap items-center gap-3">
                  <CircleAlert size={20} strokeWidth={1.75} absoluteStrokeWidth aria-hidden />
                  <span className="body-strong">{t("swap")}</span>
                  <span className="num-time">{fmt.dayMonth(s.date)}</span>
                  <ShiftLabel code={s.shift_type} />
                  <span>
                    {s.offered_by && s.taken_by
                      ? t("swapBetween", { a: s.offered_by, b: s.taken_by })
                      : (s.offered_by ?? s.taken_by)}
                  </span>
                </div>
                {s.escalation_reason ? (
                  <p className="body m-0">{reasonText(s.escalation_reason)}</p>
                ) : null}
                {blocked[s.id]?.map((v) => (
                  <RuleMessage key={`${v.rule}-${v.date}`} violation={v} live />
                ))}
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="primary"
                    disabled={approve.pending}
                    onClick={() => void approve.run("swap", s.id)}
                  >
                    {t("approve")}
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setDeclining({ kind: "swap", id: s.id, label: fmt.dayMonth(s.date) });
                    }}
                  >
                    {t("declineWithReason")}
                  </Button>
                </div>
              </li>
            ))}
            {d.cascades.map((c) => (
              <li
                key={c.id}
                className="flex flex-col gap-2 border-b border-rule pb-4"
                data-testid="cascade-request"
              >
                <div className="flex flex-wrap items-center gap-3">
                  <CircleAlert size={20} strokeWidth={1.75} absoluteStrokeWidth aria-hidden />
                  <span className="body-strong">{t("cover")}</span>
                  <span className="num-time">{fmt.dayMonth(c.date)}</span>
                  <ShiftLabel code={c.shift_type} />
                  {c.accepted_by ? <span>{c.accepted_by}</span> : null}
                </div>
                {c.escalation_reason ? (
                  <p className="body m-0">{reasonText(c.escalation_reason)}</p>
                ) : null}
                <Link
                  href={`/ausfaelle/${c.id}`}
                  className="dp-btn dp-btn--primary label self-start no-underline"
                >
                  {t("decide")}
                </Link>
              </li>
            ))}
          </ul>
        </Section>
        <Section title={t("proposalsTitle", { count: d.proposals.length })}>
          {d.proposals.length === 0 ? <p className="body m-0">{t("proposalsNone")}</p> : null}
          <div className="flex flex-col gap-4">
            {d.proposals.map((p) => (
              <Suggestion
                key={p.id}
                text={
                  <>
                    <strong>{p.title}</strong> {p.body}
                  </>
                }
                reasons={[
                  { text: t("proposalWhy", { source: p.source, date: fmt.date(p.created_at) }) },
                  { text: t("proposalChangesNothing") },
                ]}
                accept={t("proposalAccept")}
                onAccept={() => void decideProposal.run(p.id, true)}
                dismiss={t("proposalDismiss")}
                onDismiss={() => void decideProposal.run(p.id, false)}
              />
            ))}
          </div>
        </Section>
        <DeclineDialog
          target={declining}
          onClose={() => {
            setDeclining(null);
          }}
          onDone={q.reload}
        />
      </>
    );
  };
  return <Async query={q}>{body}</Async>;
}

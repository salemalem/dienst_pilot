"use client";

import { ApiError, unwrap, type components } from "@dienstpilot/api-client";
import { CircleAlert, PencilLine } from "lucide-react";
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
  ICON,
  PageHeader,
  useToast,
} from "@/components/ui";
import { Link } from "@/i18n/navigation";
import { useFmt } from "@/lib/fmt";
import { useAction, useQuery } from "@/lib/hooks";
import { useSession } from "@/lib/session";

type Inbox = components["schemas"]["Inbox"];
type Violation = components["schemas"]["ViolationOut"];

type Item =
  | { kind: "leave"; id: string; urgent: boolean; at: string; data: Inbox["leave"][number] }
  | { kind: "swap"; id: string; urgent: boolean; at: string; data: Inbox["swaps"][number] }
  | { kind: "cascade"; id: string; urgent: boolean; at: string; data: Inbox["cascades"][number] }
  | { kind: "proposal"; id: string; urgent: boolean; at: string; data: Inbox["proposals"][number] };

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

/** W6: requests in a list, the selected one with its computed impact beside it. */
export default function RequestsPage(): ReactNode {
  const t = useTranslations("w6");
  const te = useTranslations("escalation");
  const fmt = useFmt();
  const toast = useToast();
  const { api } = useSession();
  const q = useQuery((a) => unwrap(a.GET("/planner/requests")), []);
  const [selected, setSelected] = useState<string | null>(null);
  const [declining, setDeclining] = useState<Target | null>(null);
  const [blocked, setBlocked] = useState<Record<string, Violation[]>>({});

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
      setSelected(null);
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
    setSelected(null);
    q.reload();
  });

  const applyProposal = useAction(async (id: string) => {
    try {
      await unwrap(
        api.POST("/planner/proposals/{proposal_id}/apply", {
          params: { path: { proposal_id: id } },
        }),
      );
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) {
        toast.show(t("proposalApplyRefused"));
        return;
      }
      throw e;
    }
    toast.show(t("proposalApplied"));
    setSelected(null);
    q.reload();
  });

  const reasonText = (r: string | null): string | null =>
    r && te.has(r as "overtime") ? te(r as "overtime") : r;

  const body = (d: Inbox): ReactNode => {
    const items: Item[] = [
      ...d.cascades.map((c) => ({
        kind: "cascade" as const,
        id: c.id,
        urgent: true,
        at: c.date,
        data: c,
      })),
      ...d.swaps.map((s) => ({
        kind: "swap" as const,
        id: s.id,
        urgent: true,
        at: s.date,
        data: s,
      })),
      ...d.leave.map((l) => ({
        kind: "leave" as const,
        id: l.id,
        urgent: false,
        at: l.submitted_at,
        data: l,
      })),
      ...d.proposals.map((p) => ({
        kind: "proposal" as const,
        id: p.id,
        urgent: false,
        at: p.created_at,
        data: p,
      })),
    ].sort((a, b) => Number(b.urgent) - Number(a.urgent) || b.at.localeCompare(a.at));
    const current = items.find((i) => i.id === selected) ?? items[0] ?? null;
    const urgent = items.filter((i) => i.urgent).length;
    const parts = [
      d.leave.length ? t("partLeave", { count: d.leave.length }) : null,
      d.swaps.length + d.cascades.length
        ? t("partSwap", { count: d.swaps.length + d.cascades.length })
        : null,
      d.proposals.length ? t("partProposal", { count: d.proposals.length }) : null,
    ].filter(Boolean);

    const heading = (i: Item): string =>
      i.kind === "leave"
        ? i.data.display_name
        : i.kind === "proposal"
          ? i.data.title
          : i.kind === "swap"
            ? t("swapAt", { date: fmt.dayMonth(i.data.date) })
            : t("coverAt", { date: fmt.dayMonth(i.data.date) });
    const kindLabel = (i: Item): string => t(`kind.${i.kind}`);
    const sub = (i: Item): ReactNode =>
      i.kind === "leave" ? (
        <span>
          {fmt.range(i.data.start_date, i.data.end_date)} {i.data.end_date.slice(0, 4)}
        </span>
      ) : i.kind === "proposal" ? (
        <span>{t("byCopilot")}</span>
      ) : (
        <ShiftLabel code={i.data.shift_type} />
      );

    return (
      <>
        <PageHeader
          title={
            items.length === 0 ? t("statusNone") : t("headline", { count: items.length, urgent })
          }
          status={parts.join(" · ") || undefined}
        />
        {approve.error ? <ErrorState error={approve.error} /> : null}
        {items.length > 0 ? (
          <div className="grid items-start gap-6 [grid-template-columns:minmax(260px,340px)_1fr]">
            <ul className="m-0 flex list-none flex-col gap-2 p-0" aria-label={t("listLabel")}>
              {items.map((i) => (
                <li key={`${i.kind}-${i.id}`}>
                  <button
                    type="button"
                    aria-current={current?.id === i.id ? "true" : undefined}
                    onClick={() => {
                      setSelected(i.id);
                    }}
                    data-testid={`${i.kind}-request`}
                    className={`flex w-full cursor-pointer flex-col gap-1 border p-3 text-left ${
                      current?.id === i.id
                        ? "border-2 border-action bg-sheet"
                        : "border-rule bg-sheet hover:bg-sheet-sunk"
                    } ${i.kind === "proposal" ? "border-dashed bg-pencil-wash" : ""}`}
                  >
                    <span className="caption flex items-center gap-1 text-ink-muted">
                      {i.kind === "proposal" ? <PencilLine {...ICON} size={12} /> : null}
                      {kindLabel(i)}
                    </span>
                    <span className="body-strong">{heading(i)}</span>
                    <span className="label text-ink-muted">{sub(i)}</span>
                    {i.urgent ? (
                      <span className="label flex items-center gap-1 text-alert">
                        <CircleAlert {...ICON} size={14} />
                        {t("urgent")}
                      </span>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
            <section
              aria-label={current ? heading(current) : undefined}
              className="flex min-w-0 flex-col gap-4 border border-rule bg-sheet p-5"
              data-testid="request-detail"
            >
              {current?.kind === "leave" ? (
                <>
                  <p className="caption m-0 text-ink-muted">
                    {kindLabel(current)} ·{" "}
                    {t("submitted", { date: fmt.date(current.data.submitted_at) })}
                  </p>
                  <h2 className="title m-0">
                    {current.data.display_name},{" "}
                    {fmt.range(current.data.start_date, current.data.end_date)}{" "}
                    {current.data.end_date.slice(0, 4)}
                  </h2>
                  <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(240px,1fr))]">
                    <div className="border border-rule p-4">
                      <h3 className="label m-0 text-ink-muted">{t("blockStaffing")}</h3>
                      <p className="body m-0" data-testid="leave-impact">
                        {t(
                          `hint.${current.data.impact.hint === "tight" || current.data.impact.hint === "not_coverable" ? current.data.impact.hint : "coverable"}`,
                        )}{" "}
                        {t("impact", {
                          max: current.data.impact.max_on_leave_same_day,
                          limit: current.data.impact.limit,
                        })}
                      </p>
                    </div>
                    <div className="border border-rule p-4">
                      <h3 className="label m-0 text-ink-muted">{t("blockLeave")}</h3>
                      <p className="body m-0">
                        {t("leaveTaken", {
                          days: current.data.impact.leave_days_taken_this_year,
                          mean: fmt.number(current.data.impact.department_mean_leave_days, 1),
                        })}
                      </p>
                    </div>
                  </div>
                  <EngineBadge engine={current.data.impact.engine} />
                  {blocked[current.id]?.map((v) => (
                    <RuleMessage key={`${v.rule}-${v.date}`} violation={v} live />
                  ))}
                  <div className="flex flex-wrap justify-end gap-2 border-t border-rule pt-4">
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setDeclining({
                          kind: "leave",
                          id: current.id,
                          label: current.data.display_name,
                        });
                      }}
                    >
                      {t("declineWithReason")}
                    </Button>
                    <Button
                      variant="primary"
                      disabled={approve.pending}
                      onClick={() => void approve.run("leave", current.id)}
                      data-testid="approve-leave"
                    >
                      {t("approve")}
                    </Button>
                  </div>
                </>
              ) : current?.kind === "swap" ? (
                <>
                  <p className="caption m-0 text-ink-muted">{kindLabel(current)}</p>
                  <h2 className="title m-0">{heading(current)}</h2>
                  <p className="body m-0">
                    {current.data.offered_by && current.data.taken_by
                      ? t("swapBetween", { a: current.data.offered_by, b: current.data.taken_by })
                      : (current.data.offered_by ?? current.data.taken_by)}
                  </p>
                  {current.data.escalation_reason ? (
                    <p className="body-strong m-0 flex items-start gap-2 text-alert">
                      <CircleAlert {...ICON} size={20} />
                      {reasonText(current.data.escalation_reason)}
                    </p>
                  ) : null}
                  {blocked[current.id]?.map((v) => (
                    <RuleMessage key={`${v.rule}-${v.date}`} violation={v} live />
                  ))}
                  <div className="flex flex-wrap justify-end gap-2 border-t border-rule pt-4">
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setDeclining({
                          kind: "swap",
                          id: current.id,
                          label: fmt.dayMonth(current.data.date),
                        });
                      }}
                    >
                      {t("declineWithReason")}
                    </Button>
                    <Button
                      variant="primary"
                      disabled={approve.pending}
                      onClick={() => void approve.run("swap", current.id)}
                    >
                      {t("approve")}
                    </Button>
                  </div>
                </>
              ) : current?.kind === "cascade" ? (
                <>
                  <p className="caption m-0 text-ink-muted">{kindLabel(current)}</p>
                  <h2 className="title m-0">{heading(current)}</h2>
                  {current.data.accepted_by ? (
                    <p className="body m-0">{current.data.accepted_by}</p>
                  ) : null}
                  {current.data.escalation_reason ? (
                    <p className="body-strong m-0 flex items-start gap-2 text-alert">
                      <CircleAlert {...ICON} size={20} />
                      {reasonText(current.data.escalation_reason)}
                    </p>
                  ) : null}
                  <div className="flex justify-end border-t border-rule pt-4">
                    <Link
                      href={`/ausfaelle/${current.id}`}
                      className="dp-btn dp-btn--primary label no-underline"
                    >
                      {t("decide")}
                    </Link>
                  </div>
                </>
              ) : current?.kind === "proposal" ? (
                <Suggestion
                  text={
                    <>
                      <strong>{current.data.title}</strong> {current.data.body}
                    </>
                  }
                  reasons={[
                    {
                      text: t("proposalWhy", {
                        source: current.data.source,
                        date: fmt.date(current.data.created_at),
                      }),
                    },
                    {
                      text: current.data.changes?.length
                        ? t("proposalChangesApply", { count: current.data.changes.length })
                        : t("proposalChangesNothing"),
                    },
                  ]}
                  actions={
                    current.data.changes?.length ? (
                      <Button
                        variant="primary"
                        disabled={applyProposal.pending}
                        onClick={() => void applyProposal.run(current.id)}
                      >
                        {t("proposalApply")}
                      </Button>
                    ) : undefined
                  }
                  accept={t("proposalAccept")}
                  onAccept={() => void decideProposal.run(current.id, true)}
                  dismiss={t("proposalDismiss")}
                  onDismiss={() => void decideProposal.run(current.id, false)}
                />
              ) : null}
            </section>
          </div>
        ) : null}
        <DeclineDialog
          target={declining}
          onClose={() => {
            setDeclining(null);
          }}
          onDone={() => {
            setSelected(null);
            q.reload();
          }}
        />
      </>
    );
  };
  return <Async query={q}>{body}</Async>;
}

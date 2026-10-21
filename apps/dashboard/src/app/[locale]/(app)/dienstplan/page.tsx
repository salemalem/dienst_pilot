"use client";

import { ApiError, unwrap, type components, type Violation } from "@dienstpilot/api-client";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Suspense, useCallback, useMemo, useState, type ReactNode } from "react";

import { EngineBadge } from "@/components/EngineBadge";
import { MonthSwitch } from "@/components/MonthSwitch";
import { PublishDialog } from "@/components/PublishDialog";
import { RosterGrid, type CellRef } from "@/components/RosterGrid";
import { RuleMessage } from "@/components/RuleMessage";
import { useShiftName } from "@/components/shift";
import { Suggestion } from "@/components/Suggestion";
import {
  Button,
  Dialog,
  ErrorState,
  Field,
  Loading,
  PageHeader,
  Section,
  useToast,
} from "@/components/ui";
import { usePathname, useRouter } from "@/i18n/navigation";
import { daysInMonth, useFmt } from "@/lib/fmt";
import { useAction, useQuery } from "@/lib/hooks";
import { usePlanning } from "@/lib/planning";
import { useSession } from "@/lib/session";

type Edit = components["schemas"]["AssignmentEdit"];

type Op =
  | {
      kind: "move";
      assignmentId: string;
      toStaffId: string;
      fromStaffId: string;
      day: string;
      shift: string;
    }
  | { kind: "remove"; assignmentId: string; staffId: string; day: string; shift: string }
  | { kind: "add"; staffId: string; day: string; shift: string };

const ADDABLE = ["frueh", "spaet", "nacht", "bereitschaft", "ruf"] as const;

function violationKey(v: Violation): string {
  return v.staff_id ? `${v.staff_id}|${v.date}` : `coverage|${v.date}`;
}

function Editor(): ReactNode {
  const t = useTranslations("w4");
  const tr = useTranslations("rules");
  const fmt = useFmt();
  const names = useShiftName();
  const toast = useToast();
  const { api } = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const planning = usePlanning();
  const overview = planning.overview.data;
  const month =
    params.get("month") ?? planning.month ?? overview?.published_month?.slice(0, 7) ?? null;
  const variantParam = params.get("variant");

  const runs = useQuery(
    (a) =>
      month
        ? unwrap(a.GET("/planner/runs", { params: { query: { month } } }))
        : Promise.resolve(null),
    [month],
  );
  const drafts = useMemo(() => {
    const done = runs.data?.runs.filter((r) => r.status === "done") ?? [];
    return done.flatMap((r) =>
      r.variants.filter((v) => v.status === "draft").map((v) => ({ ...v, runAt: r.created_at })),
    );
  }, [runs.data]);
  const published = Boolean(overview && month && overview.published_month?.slice(0, 7) === month);
  const variantId: string | null =
    variantParam !== null
      ? variantParam === "published"
        ? null
        : variantParam
      : published
        ? null
        : ((drafts.find((v) => v.recommended) ?? drafts[0])?.variant_id ?? null);

  const [selected, setSelected] = useState<CellRef | null>(null);
  const [reasonFor, setReasonFor] = useState<Op | null>(null);
  const [focusRequest, setFocusRequest] = useState<CellRef | null>(null);
  const [introduced, setIntroduced] = useState<Violation[]>([]);
  const [lastOp, setLastOp] = useState<Op | null>(null);
  const [blocked, setBlocked] = useState<Violation[]>([]);
  const [publish, setPublish] = useState(false);

  const q = useQuery(
    async (a) => {
      if (!month || !runs.data) return null;
      const [grid, validation] = await Promise.all([
        unwrap(
          a.GET("/roster", {
            params: { query: { month, ...(variantId ? { variant_id: variantId } : {}) } },
          }),
        ),
        unwrap(
          a.POST("/planner/validate", {
            body: { roster_month: month, ...(variantId ? { variant_id: variantId } : {}) },
          }),
        ),
      ]);
      return { grid, validation };
    },
    [month, variantId, Boolean(runs.data)],
  );

  const setQuery = useCallback(
    (next: { month?: string; variant?: string | null }) => {
      const p = new URLSearchParams(params.toString());
      if (next.month) p.set("month", next.month);
      if (next.month) p.delete("variant");
      if (next.variant !== undefined) {
        if (next.variant === null) p.set("variant", "published");
        else p.set("variant", next.variant);
      }
      router.replace(`${pathname}?${p.toString()}`);
    },
    [params, pathname, router],
  );

  const body = (op: Op, reason?: string): Edit => {
    const base: Edit = { variant_id: variantId, reason: reason ?? null };
    if (op.kind === "move")
      return { ...base, assignment_id: op.assignmentId, new_staff_id: op.toStaffId };
    if (op.kind === "remove") return { ...base, assignment_id: op.assignmentId };
    return { ...base, add: { date: op.day, shift_type: op.shift, staff_id: op.staffId } };
  };

  const send = useAction(async (op: Op, reason?: string, isUndo = false): Promise<boolean> => {
    try {
      const r = await unwrap(api.PATCH("/planner/roster/assignments", { body: body(op, reason) }));
      setBlocked([]);
      setIntroduced(r.introduced);
      setLastOp(isUndo ? null : op);
      setSelected(null);
      setReasonFor(null);
      q.reload();
      if (r.notified.length > 0) toast.show(t("notified", { count: r.notified.length }));
      return true;
    } catch (e) {
      if (e instanceof ApiError && e.violations.length > 0) {
        setBlocked(e.violations);
        return false;
      }
      throw e;
    }
  });

  const edit = (op: Op): void => {
    const status = q.data?.grid.status;
    if (status === "published") setReasonFor(op);
    else void send.run(op);
  };

  const undo = (): void => {
    if (!lastOp || !q.data) return;
    const grid = q.data.grid;
    // A reassignment creates a new assignment, so the way back looks it up in the refreshed grid.
    const idOf = (staffId: string, day: string, shift: string): string | undefined => {
      const cell = grid.rows.find((r) => r.staff_id === staffId)?.cells[day];
      const i = cell?.shifts.indexOf(shift) ?? -1;
      return i >= 0 ? cell?.assignment_ids[i] : undefined;
    };
    if (lastOp.kind === "move") {
      const id = idOf(lastOp.toStaffId, lastOp.day, lastOp.shift);
      if (id)
        edit({
          kind: "move",
          assignmentId: id,
          toStaffId: lastOp.fromStaffId,
          fromStaffId: lastOp.toStaffId,
          day: lastOp.day,
          shift: lastOp.shift,
        });
    } else if (lastOp.kind === "remove") {
      edit({ kind: "add", staffId: lastOp.staffId, day: lastOp.day, shift: lastOp.shift });
    } else {
      const cell = grid.rows.find((r) => r.staff_id === lastOp.staffId)?.cells[lastOp.day];
      const i = cell?.shifts.indexOf(lastOp.shift) ?? -1;
      const id = i >= 0 ? cell?.assignment_ids[i] : undefined;
      if (id)
        edit({
          kind: "remove",
          assignmentId: id,
          staffId: lastOp.staffId,
          day: lastOp.day,
          shift: lastOp.shift,
        });
    }
  };

  if (planning.overview.error)
    return <ErrorState error={planning.overview.error} onRetry={planning.overview.reload} />;
  if (!month || !overview) return <Loading />;
  if (q.error) return <ErrorState error={q.error} onRetry={q.reload} />;
  if (!q.data) return <Loading />;

  const { grid, validation } = q.data;
  const days = daysInMonth(month);
  const today = overview.now.slice(0, 10);
  const violations = new Map<string, string[]>();
  for (const v of validation.violations) {
    const k = violationKey(v);
    const label = tr.has(v.rule as "coverage") ? tr(v.rule as "coverage") : v.rule;
    violations.set(k, [...(violations.get(k) ?? []), label]);
  }
  const isPublished = grid.status === "published";
  const introducedKeys = new Set(
    introduced.map((v) => `${v.rule}|${violationKey(v)}|${JSON.stringify(v.params)}`),
  );
  const sorted = [...validation.violations].sort((a, b) => {
    const ai = introducedKeys.has(`${a.rule}|${violationKey(a)}|${JSON.stringify(a.params)}`)
      ? 0
      : 1;
    const bi = introducedKeys.has(`${b.rule}|${violationKey(b)}|${JSON.stringify(b.params)}`)
      ? 0
      : 1;
    return ai - bi;
  });
  const sel = selected ? grid.rows.find((r) => r.staff_id === selected.staffId) : null;
  const selCell = sel && selected ? sel.cells[selected.day] : undefined;
  const staffByName = new Map(grid.rows.map((r) => [r.display_name, r.staff_id]));

  const count = validation.violations.length;
  const published_at = grid.published_at;
  const draftLabel = drafts.find((d) => d.variant_id === variantId)?.label;
  const headline =
    grid.status === "not_planned"
      ? t("statusNotPlanned", { month: fmt.month(month) })
      : isPublished
        ? count === 0
          ? t("headlinePublishedOk", { month: fmt.month(month) })
          : t("headlinePublishedBad", { month: fmt.month(month), count })
        : count === 0
          ? planning.windowOpen
            ? t("headlineOkWindow")
            : t("headlineReady")
          : t("headlineLeft", { count });
  const subline = [
    t("sublineMonth", { month: fmt.month(month) }),
    isPublished
      ? published_at
        ? t("sublinePublished", { date: fmt.date(published_at) })
        : t("kind.published")
      : grid.status === "draft"
        ? t("sublineDraft", { label: draftLabel ?? "" })
        : null,
  ]
    .filter(Boolean)
    .join(" · ");
  const publishHint = planning.windowOpen ? t("hintWindowOpen") : count > 0 ? t("hintRules") : null;
  const rulePanel = (
    <Section
      title={t("rulesTitle", { count })}
      aside={<EngineBadge engine={validation.validator} />}
    >
      {count === 0 ? (
        <p className="body m-0" data-testid="rules-ok">
          {t("rulesOk")}
        </p>
      ) : (
        <div className="flex flex-col gap-3" data-testid="violations">
          {sorted.slice(0, 6).map((v) => (
            <RuleMessage
              key={`${v.rule}-${v.date}-${v.staff_id ?? ""}-${JSON.stringify(v.params)}`}
              violation={v}
              live={introducedKeys.has(`${v.rule}|${violationKey(v)}|${JSON.stringify(v.params)}`)}
            />
          ))}
          {sorted.length > 6 ? (
            <p className="caption m-0 text-ink-muted">{t("more", { count: sorted.length - 6 })}</p>
          ) : null}
        </div>
      )}
    </Section>
  );

  return (
    <>
      <PageHeader
        title={headline}
        status={subline}
        actions={
          <div className="flex flex-col items-end gap-1">
            <div className="flex flex-wrap items-center justify-end gap-2">
              <MonthSwitch
                month={month}
                onChange={(m) => {
                  setQuery({ month: m });
                }}
              />
              {!isPublished && drafts.length > 0 ? (
                <label className="flex items-center gap-2">
                  <span className="label">{t("variantPicker")}</span>
                  <select
                    className="dp-input label !w-auto"
                    value={variantId ?? ""}
                    onChange={(e) => {
                      setQuery({ variant: e.target.value || null });
                    }}
                  >
                    {drafts.map((v) => (
                      <option key={v.variant_id} value={v.variant_id}>
                        {t("variantOption", { label: v.label, time: fmt.dateTime(v.runAt) })}
                        {v.recommended ? ` · ${t("recommended")}` : ""}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <Button
                variant="secondary"
                disabled={!lastOp || send.pending}
                onClick={undo}
                data-testid="undo"
              >
                {t("undo")}
              </Button>
              {grid.status === "draft" && variantId ? (
                <Button
                  variant="primary"
                  disabled={planning.windowOpen || !validation.valid}
                  onClick={() => {
                    setPublish(true);
                  }}
                  data-testid="open-publish"
                >
                  {t("publish")}
                </Button>
              ) : null}
            </div>
            {grid.status === "draft" && publishHint ? (
              <span className="caption text-ink-muted" data-testid="publish-hint">
                {publishHint}
              </span>
            ) : null}
          </div>
        }
      />
      {isPublished ? <p className="caption m-0 text-ink-muted">{t("publishedNote")}</p> : null}
      {grid.status === "not_planned" ? (
        <p className="body m-0">{t("notPlanned")}</p>
      ) : (
        <>
          <div aria-live="polite" className="flex flex-col gap-3">
            {send.error && selected === null && reasonFor === null ? (
              <ErrorState error={send.error} />
            ) : null}
            {blocked.length > 0 ? (
              <Section title={t("blockedTitle")}>
                {blocked.map((v) => (
                  <RuleMessage key={`${v.rule}-${v.date}-${v.staff_id ?? ""}`} violation={v} live />
                ))}
              </Section>
            ) : null}
            <div className="grid items-start gap-6 [grid-template-columns:repeat(auto-fit,minmax(380px,1fr))]">
              {rulePanel}
              {grid.gaps.length > 0 ? (
                <Section title={t("gapsTitle")}>
                  {grid.gaps.map((g) => {
                    const name = g.candidates[0];
                    const staffId = name ? staffByName.get(name) : undefined;
                    return (
                      <Suggestion
                        key={`${g.date}-${g.shift_type}`}
                        text={
                          name
                            ? t("gapSuggestion", {
                                date: fmt.dayMonth(g.date),
                                shift: names.name(g.shift_type),
                                name,
                              })
                            : t("gapNone", {
                                date: fmt.dayMonth(g.date),
                                shift: names.name(g.shift_type),
                              })
                        }
                        reasons={[
                          { text: t("gapWhyChecked") },
                          { text: t("gapWhyRanked") },
                          ...(g.candidates.length > 1
                            ? [
                                {
                                  text: t("gapAlternatives", {
                                    names: g.candidates.slice(1).join(", "),
                                  }),
                                },
                              ]
                            : []),
                        ]}
                        badge={<EngineBadge engine={g.engine} />}
                        accept={name ? t("gapAccept", { name }) : undefined}
                        onAccept={
                          staffId
                            ? () => {
                                edit({ kind: "add", staffId, day: g.date, shift: g.shift_type });
                              }
                            : undefined
                        }
                      />
                    );
                  })}
                </Section>
              ) : null}
            </div>
          </div>
          <p className="caption m-0 text-ink-muted">{t("howTo")}</p>
          <RosterGrid
            rows={grid.rows}
            days={days}
            coverage={grid.coverage}
            today={today}
            violations={violations}
            focusRequest={focusRequest}
            onOpen={setSelected}
            onMove={(assignmentId, toStaffId, day) => {
              const from = grid.rows.find((r) =>
                r.cells[day]?.assignment_ids.includes(assignmentId),
              );
              const cell = from?.cells[day];
              const shift = cell?.shifts[cell.assignment_ids.indexOf(assignmentId)];
              if (from && shift)
                edit({
                  kind: "move",
                  assignmentId,
                  toStaffId,
                  fromStaffId: from.staff_id,
                  day,
                  shift,
                });
            }}
          />
        </>
      )}

      <Dialog
        open={selected !== null}
        title={
          sel && selected
            ? t("cellTitle", { name: sel.display_name, day: fmt.dayMonth(selected.day) })
            : ""
        }
        onClose={() => {
          setSelected(null);
        }}
      >
        {sel && selected ? (
          <CellActions
            key={`${selected.staffId}-${selected.day}`}
            row={sel}
            day={selected.day}
            others={grid.rows.filter((r) => r.staff_id !== sel.staff_id)}
            shifts={selCell?.shifts ?? []}
            ids={selCell?.assignment_ids ?? []}
            busy={send.pending}
            onOp={edit}
            onClose={() => {
              setSelected(null);
              setFocusRequest({ ...selected });
            }}
          />
        ) : null}
        {send.error ? <ErrorState error={send.error} /> : null}
      </Dialog>

      <ReasonDialog
        op={reasonFor}
        busy={send.pending}
        blocked={blocked}
        onClose={() => {
          setReasonFor(null);
          setBlocked([]);
        }}
        onConfirm={(reason) => {
          if (reasonFor) void send.run(reasonFor, reason);
        }}
      />

      <PublishDialog
        target={
          publish && variantId
            ? {
                month,
                variantId,
                label: drafts.find((d) => d.variant_id === variantId)?.label ?? "",
              }
            : null
        }
        onClose={() => {
          setPublish(false);
        }}
        onPublished={() => {
          planning.overview.reload();
          runs.reload();
          setQuery({ variant: null });
        }}
      />
    </>
  );
}

function CellActions({
  row,
  day,
  others,
  shifts,
  ids,
  busy,
  onOp,
  onClose,
}: {
  row: { staff_id: string; display_name: string };
  day: string;
  others: { staff_id: string; display_name: string }[];
  shifts: string[];
  ids: string[];
  busy: boolean;
  onOp: (op: Op) => void;
  onClose: () => void;
}): ReactNode {
  const t = useTranslations("w4");
  const names = useShiftName();
  const [to, setTo] = useState(others[0]?.staff_id ?? "");
  const [kind, setKind] = useState<string>("frueh");
  if (shifts.length === 0) {
    return (
      <div className="flex flex-col gap-3">
        <Field label={t("addShift")}>
          {(p) => (
            <select
              {...p}
              className="dp-input"
              value={kind}
              onChange={(e) => {
                setKind(e.target.value);
              }}
            >
              {ADDABLE.map((s) => (
                <option key={s} value={s}>
                  {names.name(s)}
                </option>
              ))}
            </select>
          )}
        </Field>
        <div className="flex justify-end gap-2">
          <Button variant="quiet" onClick={onClose}>
            {t("cancel")}
          </Button>
          <Button
            variant="primary"
            disabled={busy}
            onClick={() => {
              onOp({ kind: "add", staffId: row.staff_id, day, shift: kind });
            }}
            data-testid="add-shift"
          >
            {t("add")}
          </Button>
        </div>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      {shifts.map((s, i) => {
        const id = ids[i];
        if (!id) return null;
        return (
          <div
            key={id}
            className="flex flex-col gap-2 border-b border-rule pb-3"
            data-shift-action={s}
          >
            <p className="body-strong m-0">{names.name(s)}</p>
            <Field label={t("giveTo")}>
              {(p) => (
                <select
                  {...p}
                  className="dp-input"
                  value={to}
                  onChange={(e) => {
                    setTo(e.target.value);
                  }}
                  data-testid={`give-to-${s}`}
                >
                  {others.map((o) => (
                    <option key={o.staff_id} value={o.staff_id}>
                      {o.display_name}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="primary"
                disabled={busy || !to}
                onClick={() => {
                  onOp({
                    kind: "move",
                    assignmentId: id,
                    toStaffId: to,
                    fromStaffId: row.staff_id,
                    day,
                    shift: s,
                  });
                }}
                data-testid={`give-${s}`}
              >
                {t("give")}
              </Button>
              <Button
                variant="secondary"
                disabled={busy}
                onClick={() => {
                  onOp({ kind: "remove", assignmentId: id, staffId: row.staff_id, day, shift: s });
                }}
                data-testid={`remove-${s}`}
              >
                {t("remove")}
              </Button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ReasonDialog({
  op,
  busy,
  blocked,
  onClose,
  onConfirm,
}: {
  op: Op | null;
  busy: boolean;
  blocked: Violation[];
  onClose: () => void;
  onConfirm: (reason: string) => void;
}): ReactNode {
  const t = useTranslations("w4");
  const [reason, setReason] = useState("");
  return (
    <Dialog
      open={op !== null}
      title={t("reasonTitle")}
      onClose={onClose}
      footer={
        <>
          <Button variant="quiet" onClick={onClose}>
            {t("cancel")}
          </Button>
          <Button
            variant="primary"
            disabled={busy || reason.trim().length < 3}
            onClick={() => {
              onConfirm(reason.trim());
            }}
            data-testid="confirm-reason"
          >
            {t("reasonConfirm")}
          </Button>
        </>
      }
    >
      <p className="body m-0">{t("reasonBody")}</p>
      <Field label={t("reasonLabel")}>
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
      {blocked.map((v) => (
        <RuleMessage key={`${v.rule}-${v.date}-${v.staff_id ?? ""}`} violation={v} live />
      ))}
    </Dialog>
  );
}

/** W4: edit the draft or a published month; every change is checked by the validator at once. */
export default function RosterEditorPage(): ReactNode {
  return (
    <Suspense fallback={<Loading />}>
      <Editor />
    </Suspense>
  );
}

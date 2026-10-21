"use client";

import { unwrap, type components } from "@dienstpilot/api-client";
import { Info } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState, type ReactNode } from "react";

import { EngineBadge } from "@/components/EngineBadge";
import { MonthSwitch } from "@/components/MonthSwitch";
import { Suggestion } from "@/components/Suggestion";
import { Button, ErrorState, Loading, PageHeader, Section } from "@/components/ui";
import { Link } from "@/i18n/navigation";
import { useFmt } from "@/lib/fmt";
import { useAction, useQuery } from "@/lib/hooks";
import { usePlanning } from "@/lib/planning";
import { useSession } from "@/lib/session";
import { variantMetrics } from "@/lib/variants";
import { useKeyText } from "@/lib/violations";

type Run = components["schemas"]["RunOut"];
type Variant = components["schemas"]["VariantOut"];
type Profile = { name: string; wishes: number; overtime: number; spread: number };

const TERMINAL = ["done", "infeasible", "failed"];

function VariantCard({
  run,
  variant,
  month,
  violations,
}: {
  run: Run;
  variant: Variant;
  month: string;
  /** Rule violations C2 finds in this variant; null while the check runs. */
  violations: number | null;
}): ReactNode {
  const t = useTranslations("w3");
  const tp = useTranslations("profile");
  const fmt = useFmt();
  const text = useKeyText();
  const m = variantMetrics(variant.metrics);
  if (!m) return null;
  const profile = variant.profile ?? "";
  const weights = ((run.config?.profiles as Profile[] | undefined) ?? []).find(
    (p) => p.name === profile,
  );
  const name = ["wishes_first", "zero_overtime", "balanced"].includes(profile)
    ? tp(profile as "balanced")
    : profile;
  const reasons = [
    { text: t("why.profile", { profile: name }) },
    ...(weights
      ? [
          {
            text: t("why.weights", {
              wishes: weights.wishes,
              overtime: weights.overtime,
              spread: weights.spread,
            }),
          },
        ]
      : []),
    { text: t("why.important", { granted: m.importantGranted, total: m.importantTotal }) },
    { text: t("why.checked", { validator: run.validator_version ?? "" }) },
  ];
  return (
    <article
      className="flex min-w-0 flex-col gap-3"
      aria-label={t("variant", { label: variant.label })}
      data-testid={`variant-${variant.label}`}
    >
      <Suggestion
        badge={
          <span className="ml-auto flex items-center gap-2">
            {run.trial ? (
              <span className="label rounded-mark border border-dashed border-pencil px-2 text-pencil">
                {t("trial")}
              </span>
            ) : null}
            {variant.recommended ? (
              <span
                className="label rounded-mark border border-ink px-2 text-ink"
                data-testid="recommended"
              >
                {t("recommended")}
              </span>
            ) : null}
          </span>
        }
        title={
          <div className="flex flex-col">
            <h3 className="title m-0">{t("variant", { label: variant.label })}</h3>
            <span className="label text-ink-muted">{t("weighting", { profile: name })}</span>
          </div>
        }
        text={t("summary", {
          label: variant.label,
          rate: fmt.percent(m.wishRate),
          granted: m.wishesGranted,
          total: m.wishesTotal,
          overtime: fmt.number(m.overtimeHours, 1),
        })}
        reasons={reasons}
        actions={
          <Link
            href={`/dienstplan?month=${month}&variant=${variant.variant_id}`}
            className={`dp-btn ${variant.recommended ? "dp-btn--primary" : "dp-btn--secondary"} label no-underline`}
            data-testid={`open-${variant.label}`}
          >
            {t("openDraft")}
          </Link>
        }
      >
        <dl className="body m-0 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 border-y border-dashed border-pencil py-3">
          <dt>{t("m.wishes")}</dt>
          <dd className="num-time m-0 text-right">{fmt.percent(m.wishRate)}</dd>
          <dt>{t("m.important")}</dt>
          <dd className="num-time m-0 text-right">
            {t("m.ofTotal", { granted: m.importantGranted, total: m.importantTotal })}
          </dd>
          <dt>{t("m.spread")}</dt>
          <dd className="num-time m-0 text-right">{t("m.points", { count: m.burdenSpread })}</dd>
          <dt>{t("m.overtime")}</dt>
          <dd className="num-time m-0 text-right">{fmt.hours(m.overtimeHours)}</dd>
          <dt>{t("m.isolated")}</dt>
          <dd className="num-time m-0 text-right">{m.isolatedNights}</dd>
          <dt>{t("m.violations")}</dt>
          <dd className="num-time m-0 text-right" data-testid={`violations-${variant.label}`}>
            {violations === null ? "…" : violations}
          </dd>
        </dl>
      </Suggestion>
      {variant.recommended && variant.recommendation_key ? (
        <p className="body-strong m-0" data-testid="recommendation">
          {text(variant.recommendation_key, {})}
        </p>
      ) : null}
      {variant.status !== "draft" ? (
        <p className="label m-0 text-ink-muted">{t(`status.${variant.status}`)}</p>
      ) : null}
    </article>
  );
}

/** W3: start a real C1 run, poll it, compare the variants side by side. */
export default function VariantsPage(): ReactNode {
  const t = useTranslations("w3");
  const fmt = useFmt();
  const text = useKeyText();
  const { api } = useSession();
  const planning = usePlanning();
  const [picked, setPicked] = useState<string | null>(null);
  const month = picked ?? planning.month;
  const [runId, setRunId] = useState<string | null>(null);

  const runs = useQuery(
    (a) =>
      month
        ? unwrap(a.GET("/planner/runs", { params: { query: { month } } }))
        : Promise.resolve(null),
    [month],
  );
  const active = useQuery(
    (a) =>
      runId
        ? unwrap(a.GET("/planner/runs/{run_id}", { params: { path: { run_id: runId } } }))
        : Promise.resolve(null),
    [runId],
  );

  // Poll while the worker solves (a run takes seconds), then refresh the list.
  const status = active.data?.status;
  const reloadActive = active.reload;
  const reloadRuns = runs.reload;
  useEffect(() => {
    if (!status) return;
    if (TERMINAL.includes(status)) {
      reloadRuns();
      return;
    }
    const id = setTimeout(reloadActive, 1000);
    return () => {
      clearTimeout(id);
    };
  }, [status, active.data, reloadActive, reloadRuns]);

  const start = useAction(async () => {
    if (!month) return;
    const r = await unwrap(api.POST("/planner/runs", { body: { roster_month: month } }));
    setRunId(r.run_id);
  });

  const running = active.data !== null && !TERMINAL.includes(active.data.status);
  const waiting = runId !== null && active.data?.run_id !== runId && active.error === null;
  const pending = start.pending || running || waiting;
  const finished = runs.data?.runs.filter((r) => TERMINAL.includes(r.status)) ?? [];
  // While a new run is computing, the earlier run's variants are hidden so they are not mistaken for it.
  const shown: Run | null = pending
    ? null
    : ((active.data && TERMINAL.includes(active.data.status) ? active.data : null) ??
      finished[0] ??
      null);

  // Every variant is checked by the validator (C2) again, so the headline states what holds now.
  const checks = useQuery(
    async (a) => {
      if (!shown || shown.status !== "done" || !month) return {} as Record<string, number>;
      const entries = await Promise.all(
        shown.variants.map(async (v) => {
          const r = await unwrap(
            a.POST("/planner/validate", {
              body: { roster_month: month, variant_id: v.variant_id },
            }),
          );
          return [v.variant_id, r.violations.length] as const;
        }),
      );
      return Object.fromEntries(entries);
    },
    [shown?.run_id, month],
  );

  if (planning.overview.error)
    return <ErrorState error={planning.overview.error} onRetry={planning.overview.reload} />;
  if (!planning.overview.data || !month) return <Loading />;

  const responded = planning.overview.data.window?.responded;
  const valid = shown?.variants.filter((v) => checks.data?.[v.variant_id] === 0).length ?? 0;
  const total = shown?.variants.length ?? 0;
  const headline = pending
    ? t("running")
    : shown?.status === "done"
      ? checks.data && valid < total
        ? t("headlineSome", { valid, total })
        : t("headlineAll", { count: total, month: fmt.monthShort(month) })
      : shown
        ? t("noRosterTitle")
        : t("headlineNone", { month: fmt.monthShort(month) });
  const subline = shown
    ? [
        shown.trial
          ? t("sublineTrial", {
              date: fmt.date(shown.created_at),
              time: fmt.time(shown.created_at),
              responded: responded ?? 0,
            })
          : t("sublineRun", { date: fmt.date(shown.created_at), time: fmt.time(shown.created_at) }),
        shown.status === "done" && checks.data && valid === total
          ? t("sublineChecked", { validator: shown.validator_version ?? "" })
          : null,
      ]
        .filter(Boolean)
        .join(" · ")
    : t("empty");

  return (
    <>
      <PageHeader
        title={headline}
        status={subline}
        actions={
          <>
            <MonthSwitch month={month} onChange={setPicked} />
            <Button
              variant="primary"
              onClick={() => void start.run()}
              disabled={pending}
              data-testid="start-run"
            >
              {pending ? t("starting") : t("start")}
            </Button>
          </>
        }
      />
      {planning.windowOpen && month === planning.month ? (
        <div className="dp-rule !bg-action-wash" role="note" data-testid="trial-banner">
          <span className="dp-rule-icon !text-action">
            <Info size={20} strokeWidth={1.75} absoluteStrokeWidth aria-hidden />
          </span>
          <div className="dp-rule-text body">
            <strong className="!text-ink">{t("trialTitle")}</strong>
            <span>{t("trialBody")}</span>
          </div>
          <div className="dp-rule-actions">
            <Link href="/wunschphase" className="label text-action underline">
              {t("trialLink")}
            </Link>
          </div>
        </div>
      ) : null}
      <div aria-live="polite" className="contents">
        {running ? (
          <p role="status" className="body m-0" data-testid="run-progress">
            {t("progress", {
              status: t(`runStatus.${active.data?.status === "running" ? "running" : "queued"}`),
            })}
          </p>
        ) : null}
      </div>
      {start.error ? (
        <p role="alert" className="body m-0 text-alert">
          {start.error.message}
        </p>
      ) : null}
      {active.error ? <ErrorState error={active.error} onRetry={active.reload} /> : null}
      {runs.error ? <ErrorState error={runs.error} onRetry={runs.reload} /> : null}
      {finished.length > 1 ? (
        <label className="flex items-center gap-2">
          <span className="label">{t("runPicker")}</span>
          <select
            className="dp-input label !w-auto"
            value={shown?.run_id ?? ""}
            onChange={(e) => {
              setRunId(e.target.value);
            }}
          >
            {finished.map((r) => (
              <option key={r.run_id} value={r.run_id}>
                {fmt.dateTime(r.created_at)} · {r.planner_kind.toUpperCase()}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {shown?.status === "done" ? (
        <>
          <div className="grid items-start gap-6 [grid-template-columns:repeat(auto-fit,minmax(300px,1fr))]">
            {shown.variants.map((v) => (
              <VariantCard
                key={v.variant_id}
                run={shown}
                variant={v}
                month={month}
                violations={checks.data ? (checks.data[v.variant_id] ?? null) : null}
              />
            ))}
          </div>
          <p className="caption m-0 flex flex-wrap items-center gap-2 text-ink-muted">
            <EngineBadge
              engine={{
                component: "C1",
                implementation: "built",
                version: shown.solver_version ?? "",
                note: "",
              }}
            />
            {t("versions", {
              validator: shown.validator_version ?? "",
              rules: shown.rule_set_version,
            })}
          </p>
        </>
      ) : shown ? (
        <Section title={t("noRosterTitle")}>
          <p className="body m-0">{t("noRosterBody")}</p>
          <ul className="body m-0 list-disc pl-5">
            {shown.explanations.map((e, i) => (
              <li key={i}>{text(String(e.key), (e.params ?? {}) as Record<string, unknown>)}</li>
            ))}
          </ul>
        </Section>
      ) : null}
    </>
  );
}

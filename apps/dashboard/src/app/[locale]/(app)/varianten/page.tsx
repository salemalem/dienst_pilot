"use client";

import { unwrap, type components } from "@dienstpilot/api-client";
import { Info } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useId, useState, type ReactNode } from "react";

import { EngineBadge } from "@/components/EngineBadge";
import { PublishDialog, type PublishTarget } from "@/components/PublishDialog";
import { Suggestion } from "@/components/Suggestion";
import { Button, ErrorState, Loading, PageHeader, Section } from "@/components/ui";
import { Link } from "@/i18n/navigation";
import { useFmt } from "@/lib/fmt";
import { useAction, useQuery } from "@/lib/hooks";
import { usePlanning } from "@/lib/planning";
import { useKeyText } from "@/lib/violations";
import { variantMetrics } from "@/lib/variants";
import { useSession } from "@/lib/session";

type Run = components["schemas"]["RunOut"];
type Variant = components["schemas"]["VariantOut"];
type Profile = { name: string; wishes: number; overtime: number; spread: number };

const TERMINAL = ["done", "infeasible", "failed"];

function VariantCard({
  run,
  variant,
  month,
  windowOpen,
  onPublish,
}: {
  run: Run;
  variant: Variant;
  month: string;
  windowOpen: boolean;
  onPublish: (v: Variant) => void;
}): ReactNode {
  const t = useTranslations("w3");
  const tp = useTranslations("profile");
  const fmt = useFmt();
  const text = useKeyText();
  const hint = useId();
  const m = variantMetrics(variant.metrics);
  if (!m) return null;
  const profile = variant.profile ?? "";
  const weights = ((run.config?.profiles as Profile[] | undefined) ?? []).find(
    (p) => p.name === profile,
  );
  const name =
    profile && ["wishes_first", "zero_overtime", "balanced"].includes(profile)
      ? tp(profile as "balanced")
      : profile;
  const summary = t("summary", {
    label: variant.label,
    rate: fmt.percent(m.wishRate),
    granted: m.wishesGranted,
    total: m.wishesTotal,
    spread: m.burdenSpread,
    overtime: fmt.number(m.overtimeHours, 1),
  });
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
    ...(variant.recommendation_key ? [{ text: text(variant.recommendation_key, {}) }] : []),
  ];
  const draft = variant.status === "draft";
  return (
    <article
      className="flex min-w-0 flex-col gap-3"
      aria-label={t("variant", { label: variant.label })}
      data-testid={`variant-${variant.label}`}
    >
      <div className="flex items-baseline gap-3">
        <h3 className="heading m-0">{t("variant", { label: variant.label })}</h3>
        <span className="label text-ink-muted">{name}</span>
        {variant.recommended ? (
          <span className="label rounded-mark border border-ink px-2" data-testid="recommended">
            {t("recommended")}
          </span>
        ) : null}
        {run.trial ? (
          <span className="label rounded-mark border border-dashed border-pencil px-2 text-pencil">
            {t("trial")}
          </span>
        ) : null}
      </div>
      <Suggestion
        text={summary}
        reasons={reasons}
        badge={
          <EngineBadge
            engine={{
              component: "C1",
              implementation: "built",
              version: run.solver_version ?? "",
              note: "",
            }}
          />
        }
      />
      <dl className="body m-0 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1">
        <dt>{t("m.wishes")}</dt>
        <dd className="num-time m-0 text-right">
          {t("m.wishesValue", {
            rate: fmt.percent(m.wishRate),
            granted: m.wishesGranted,
            total: m.wishesTotal,
          })}
        </dd>
        <dt>{t("m.important")}</dt>
        <dd className="num-time m-0 text-right">
          {m.importantGranted} / {m.importantTotal}
        </dd>
        <dt>{t("m.spread")}</dt>
        <dd className="num-time m-0 text-right">
          {m.burdenSpread} ({m.burdenMin}–{m.burdenMax})
        </dd>
        <dt>{t("m.overtime")}</dt>
        <dd className="num-time m-0 text-right">{fmt.hours(m.overtimeHours)}</dd>
        <dt>{t("m.isolated")}</dt>
        <dd className="num-time m-0 text-right">{m.isolatedNights}</dd>
      </dl>
      {variant.status !== "draft" ? (
        <p className="label m-0 text-ink-muted">{t(`status.${variant.status}`)}</p>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        <Link
          href={`/dienstplan?month=${month}&variant=${variant.variant_id}`}
          className="dp-btn dp-btn--secondary label no-underline"
        >
          {t("openEditor")}
        </Link>
        <Button
          variant="primary"
          disabled={!draft || windowOpen}
          aria-describedby={windowOpen ? hint : undefined}
          onClick={() => {
            onPublish(variant);
          }}
          data-testid={`publish-${variant.label}`}
        >
          {t("publish")}
        </Button>
      </div>
      {windowOpen ? (
        <p id={hint} className="caption m-0 text-ink-muted">
          {t("publishBlocked")}
        </p>
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
  const month = planning.month;
  const [runId, setRunId] = useState<string | null>(null);
  const [publish, setPublish] = useState<PublishTarget | null>(null);

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

  if (planning.overview.error)
    return <ErrorState error={planning.overview.error} onRetry={planning.overview.reload} />;
  if (!planning.overview.data || !month) return <Loading />;

  const running = active.data !== null && !TERMINAL.includes(active.data.status);
  const finished = runs.data?.runs.filter((r) => TERMINAL.includes(r.status)) ?? [];
  const shown: Run | null =
    (active.data && TERMINAL.includes(active.data.status) ? active.data : null) ??
    finished[0] ??
    null;
  const pending = start.pending || running;

  return (
    <>
      <PageHeader
        title={t("title")}
        status={
          running
            ? t("running")
            : shown?.status === "done"
              ? t("statusDone", { count: shown.variants.length, month: fmt.month(month) })
              : t("statusNone", { month: fmt.month(month) })
        }
        actions={
          <Button
            variant="primary"
            onClick={() => void start.run()}
            disabled={pending}
            data-testid="start-run"
          >
            {pending ? t("starting") : t("start")}
          </Button>
        }
      />
      {planning.windowOpen ? (
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
        <Section
          title={t("comparison", { month: fmt.month(month) })}
          aside={
            <span className="caption text-ink-muted">
              {t("versions", {
                solver: shown.solver_version ?? "",
                validator: shown.validator_version ?? "",
                rules: shown.rule_set_version,
              })}
            </span>
          }
        >
          <div className="grid gap-6 [grid-template-columns:repeat(auto-fit,minmax(300px,1fr))]">
            {shown.variants.map((v) => (
              <VariantCard
                key={v.variant_id}
                run={shown}
                variant={v}
                month={month}
                windowOpen={planning.windowOpen}
                onPublish={(variant) => {
                  setPublish({ month, variantId: variant.variant_id, label: variant.label });
                }}
              />
            ))}
          </div>
        </Section>
      ) : shown ? (
        <Section title={t("noRosterTitle")}>
          <p className="body m-0">{t("noRosterBody")}</p>
          <ul className="body m-0 list-disc pl-5">
            {shown.explanations.map((e, i) => (
              <li key={i}>{text(String(e.key), (e.params ?? {}) as Record<string, unknown>)}</li>
            ))}
          </ul>
        </Section>
      ) : !running ? (
        <p className="body m-0 text-ink-muted">{t("empty")}</p>
      ) : null}
      <PublishDialog
        target={publish}
        onClose={() => {
          setPublish(null);
        }}
        onPublished={() => {
          reloadRuns();
          active.reload();
          planning.overview.reload();
        }}
      />
    </>
  );
}

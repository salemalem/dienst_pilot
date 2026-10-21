"use client";

import { unwrap, type components } from "@dienstpilot/api-client";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { EngineBadge } from "@/components/EngineBadge";
import { Async, PageHeader, Table } from "@/components/ui";
import { useFmt, type Fmt } from "@/lib/fmt";
import { useQuery } from "@/lib/hooks";

type Component = components["schemas"]["ComponentOut"];
type Metrics = Record<string, unknown>;

const num = (o: unknown, k: string): number | null => {
  const v = (o as Metrics | undefined)?.[k];
  return typeof v === "number" ? v : null;
};

function C1Metrics({ m, fmt }: { m: Metrics; fmt: Fmt }): ReactNode {
  const t = useTranslations("w13");
  const s = m.summary as { c1?: Metrics; baseline?: Metrics } | undefined;
  const rows: { key: string; label: string; c1: string; base: string }[] = [];
  const add = (
    key: "wishes_granted_rate" | "hard_violations" | "overtime_hours" | "burden_spread_mean",
    label: string,
    f: (n: number) => string,
  ): void => {
    const a = num(s?.c1, key);
    const b = num(s?.baseline, key);
    if (a !== null && b !== null) rows.push({ key, label, c1: f(a), base: f(b) });
  };
  add("wishes_granted_rate", t("m.wishes"), (n) => fmt.percent(n));
  add("hard_violations", t("m.hard"), (n) => fmt.number(n, 0));
  add("overtime_hours", t("m.overtime"), (n) => fmt.hours(n));
  add("burden_spread_mean", t("m.spread"), (n) => fmt.number(n, 1));
  const secs = num(m, "median_seconds_per_variant");
  return (
    <div className="flex flex-col gap-2" data-testid="c1-metrics">
      <p className="caption m-0 text-ink-muted">
        {t("evalSource", {
          source: String(m.source ?? ""),
          months: String(m.held_out_months ?? ""),
        })}
      </p>
      <Table label={t("m.label")}>
        <thead>
          <tr>
            <th scope="col">{t("m.metric")}</th>
            <th scope="col" className="text-right">
              C1
            </th>
            <th scope="col" className="text-right">
              {t("m.baseline")}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key}>
              <td>{r.label}</td>
              <td className="num-time text-right">{r.c1}</td>
              <td className="num-time text-right text-ink-muted">{r.base}</td>
            </tr>
          ))}
        </tbody>
      </Table>
      {secs !== null ? (
        <p className="caption m-0 text-ink-muted">
          {t("m.seconds", { seconds: fmt.number(secs, 2) })}
        </p>
      ) : null}
      {Array.isArray(m.limitations) ? (
        <details>
          <summary className="label cursor-pointer">{t("limitations")}</summary>
          <ul className="caption m-0 list-disc pl-5 text-ink-muted">
            {(m.limitations as string[]).map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

function C2Metrics({ m }: { m: Metrics }): ReactNode {
  const t = useTranslations("w13");
  const s = m.summary as Record<string, string> | undefined;
  return (
    <div className="flex flex-col gap-2" data-testid="c2-metrics">
      <p className="caption m-0 text-ink-muted">
        {t("evalSource", { source: "eval/results/c2.json", months: "" })}
      </p>
      <dl className="body m-0 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1">
        <dt>{t("m.agreePublished")}</dt>
        <dd className="num-time m-0 text-right">{s?.agreement_published_months ?? "–"}</dd>
        <dt>{t("m.agreeRandom")}</dt>
        <dd className="num-time m-0 text-right">{s?.agreement_random_changes ?? "–"}</dd>
      </dl>
    </div>
  );
}

function Card({ c }: { c: Component }): ReactNode {
  const t = useTranslations("w13");
  const fmt = useFmt();
  const known = ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"].includes(c.component);
  const standIn = c.implementation === "stand-in";
  const metrics = c.eval_metric as Metrics | null;
  return (
    <article
      className="flex flex-col gap-3 border border-rule bg-sheet p-5"
      data-testid={`component-${c.component}`}
      data-implementation={c.implementation}
      aria-label={c.component}
    >
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="heading m-0">
          {c.component} · {known ? t(`name.${c.component as "C1"}`) : c.component}
        </h3>
        <EngineBadge
          engine={{
            component: c.component,
            implementation: c.implementation,
            version: c.version,
            note: c.note,
          }}
        />
      </div>
      <p className="body m-0">{c.note}</p>
      <dl className="body m-0 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
        <dt className="text-ink-muted">{t("kind")}</dt>
        <dd className="m-0">{t(`kinds.${c.kind as "ml"}`)}</dd>
        <dt className="text-ink-muted">{t("version")}</dt>
        <dd className="num-time m-0">{c.version}</dd>
        <dt className="text-ink-muted">{t("lastTrained")}</dt>
        <dd className="m-0">{c.kind === "ml" ? t("notTrained") : t("notApplicable")}</dd>
        <dt className="text-ink-muted">{t("modelCard")}</dt>
        <dd className="m-0">{t("modelCardNone")}</dd>
        <dt className="text-ink-muted">{t("canChange")}</dt>
        <dd className="body-strong m-0" data-testid="can-change">
          {c.can_change_roster ? t("yes") : t("no")}
        </dd>
      </dl>
      {metrics && c.component === "C1" ? (
        <C1Metrics m={metrics} fmt={fmt} />
      ) : metrics && c.component === "C2" ? (
        <C2Metrics m={metrics} />
      ) : (
        <p
          className="body m-0 rounded-mark border border-dashed border-pencil bg-pencil-wash p-3 text-pencil"
          data-testid="metric-placeholder"
        >
          {standIn ? t("placeholder", { phase: c.planned_phase ?? 0 }) : t("noMetric")}
        </p>
      )}
    </article>
  );
}

const GROUPS = [
  { key: "rules", kinds: ["optimization", "deterministic"] },
  { key: "ml", kinds: ["ml"] },
  { key: "llm", kinds: ["llm"] },
] as const;

/** W13: one card per component with its real status; the portfolio's "how it works" screen. */
export default function TransparencyPage(): ReactNode {
  const t = useTranslations("w13");
  const q = useQuery((api) => unwrap(api.GET("/transparency/components")), []);
  return (
    <>
      <PageHeader
        title={t("title")}
        status={
          q.data
            ? t("status", {
                built: q.data.filter((c) => c.implementation === "built").length,
                standIn: q.data.filter((c) => c.implementation === "stand-in").length,
              })
            : undefined
        }
      />
      <p className="body m-0 max-w-[80ch]">{t("intro")}</p>
      <Async query={q}>
        {(list) => (
          <div className="flex flex-col gap-8">
            {GROUPS.map((g) => {
              const members = list.filter((c) => (g.kinds as readonly string[]).includes(c.kind));
              if (members.length === 0) return null;
              return (
                <section
                  key={g.key}
                  aria-labelledby={`group-${g.key}`}
                  className="flex flex-col gap-3"
                >
                  <div>
                    <h2 id={`group-${g.key}`} className="heading m-0">
                      {t(`group.${g.key}.title`)} · {members.map((c) => c.component).join(", ")}
                    </h2>
                    <p className="body m-0 text-ink-muted">{t(`group.${g.key}.tagline`)}</p>
                  </div>
                  <div className="grid items-start gap-6 [grid-template-columns:repeat(auto-fit,minmax(380px,1fr))]">
                    {members.map((c) => (
                      <Card key={c.component} c={c} />
                    ))}
                  </div>
                </section>
              );
            })}
          </div>
        )}
      </Async>
    </>
  );
}

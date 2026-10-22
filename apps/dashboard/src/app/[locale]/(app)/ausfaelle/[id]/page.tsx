"use client";

import { ApiError, unwrap, type components } from "@dienstpilot/api-client";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";

import { CascadeTimeline } from "@/components/CascadeTimeline";
import { EngineBadge } from "@/components/EngineBadge";
import { RuleMessage } from "@/components/RuleMessage";
import { Async, Button, PageHeader, Section, useToast } from "@/components/ui";
import { Link, useRouter } from "@/i18n/navigation";
import { useFmt } from "@/lib/fmt";
import { useAction, useQuery } from "@/lib/hooks";
import { useSession } from "@/lib/session";

type Option = components["schemas"]["Option"];

const optionKey = (o: Option, i: number): string => `${o.kind}-${o.staff_id ?? String(i)}`;

/** W7b: escalation with the ranked options and what each one costs. The Planner decides. */
export default function EscalationPage(): ReactNode {
  const t = useTranslations("w7b");
  const te = useTranslations("escalation");
  const fmt = useFmt();
  const toast = useToast();
  const router = useRouter();
  const { api } = useSession();
  const { id } = useParams<{ id: string }>();
  const [picked, setPicked] = useState<string | null>(null);
  const q = useQuery(
    (a) =>
      unwrap(a.GET("/planner/cascades/{cascade_id}", { params: { path: { cascade_id: id } } })),
    [id],
  );

  const decide = useAction(async (o: Option) => {
    await unwrap(
      api.POST("/planner/cascades/{cascade_id}/decision", {
        params: { path: { cascade_id: id } },
        body: { option: o.kind, staff_id: o.staff_id ?? null },
      }),
    );
    toast.show(t("decided"));
    router.push("/ausfaelle");
  });

  return (
    <Async query={q}>
      {(e) => {
        const reason = e.cascade.escalation_reason;
        const err = decide.error;
        const shift = t(`shiftName.${e.cascade.shift_type as "frueh"}`);
        const chosen = e.options.find((o, i) => optionKey(o, i) === picked) ?? null;
        return (
          <>
            <PageHeader
              title={t("headline", { shift, date: fmt.dayMonth(e.cascade.date) })}
              status={[
                `${shift} ${fmt.dayMonth(e.cascade.date)}`,
                e.cascade.absent_staff ? t("absent", { name: e.cascade.absent_staff }) : null,
                reason
                  ? te.has(reason as "overtime")
                    ? te(reason as "overtime")
                    : reason
                  : t("statusOpen"),
              ]
                .filter(Boolean)
                .join(" · ")}
              actions={
                <Link href="/ausfaelle" className="label text-action underline">
                  {t("back")}
                </Link>
              }
            />
            <div className="grid items-start gap-6 [grid-template-columns:minmax(300px,2fr)_minmax(0,3fr)]">
              <Section title={t("timeline")}>
                <CascadeTimeline cascade={e.cascade} />
              </Section>
              <div
                className="flex flex-col gap-3 rounded-panel border-[1.5px] border-dashed border-pencil bg-pencil-wash p-5"
                data-testid="options"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="label text-pencil">{t("suggestionTitle")}</span>
                  <EngineBadge engine={e.engine} />
                </div>
                <h2 className="heading m-0">{t("optionsQuestion", { shift })}</h2>
                {err instanceof ApiError && err.violations.length > 0
                  ? err.violations.map((v) => (
                      <RuleMessage key={`${v.rule}-${v.date}`} violation={v} live />
                    ))
                  : null}
                {err && !(err instanceof ApiError && err.violations.length > 0) ? (
                  <p role="alert" className="body m-0 text-alert">
                    {err.message}
                  </p>
                ) : null}
                <div
                  role="radiogroup"
                  aria-label={t("optionsTitle")}
                  className="flex flex-col gap-3"
                >
                  {e.options.map((o, i) => {
                    const key = optionKey(o, i);
                    const on = picked === key;
                    return (
                      <button
                        key={key}
                        type="button"
                        role="radio"
                        aria-checked={on}
                        onClick={() => {
                          setPicked(key);
                        }}
                        data-testid={`option-${o.kind}`}
                        className={`flex cursor-pointer flex-col gap-1 border bg-sheet p-4 text-left ${on ? "border-2 border-action" : "border-rule-strong"}`}
                      >
                        <span className="caption text-ink-muted">
                          {t("optionN", { n: i + 1, kind: t(`kind.${o.kind}`) })}
                        </span>
                        <span className="body-strong">
                          {t(`option.${o.kind}`, { name: o.staff_name ?? "" })}
                        </span>
                        <span className="caption">
                          <strong>{t("consequenceLabel")}</strong>{" "}
                          {o.hours_after != null && o.contract_hours != null
                            ? t("consequence", {
                                after: fmt.number(o.hours_after, 1),
                                contract: fmt.number(o.contract_hours, 1),
                                overtime: fmt.number(o.overtime_after ?? 0, 1),
                              })
                            : t(`noConsequenceFor.${o.kind}`)}
                        </span>
                      </button>
                    );
                  })}
                </div>
                <div className="flex flex-col gap-1 border-t border-dashed border-pencil pt-3">
                  <span className="caption text-ink-muted">{t("whyOrder")}</span>
                  <ul className="caption m-0 list-disc pl-5">
                    <li>{t("rank", { rank: 1 })}</li>
                    <li>{t("checked")}</li>
                  </ul>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="caption text-ink-muted">{t("aiNote")}</span>
                  <Button
                    variant="primary"
                    disabled={!chosen || decide.pending}
                    onClick={() => {
                      if (chosen) void decide.run(chosen);
                    }}
                    data-testid="run-option"
                  >
                    {t("runOption")}
                  </Button>
                </div>
              </div>
            </div>
          </>
        );
      }}
    </Async>
  );
}

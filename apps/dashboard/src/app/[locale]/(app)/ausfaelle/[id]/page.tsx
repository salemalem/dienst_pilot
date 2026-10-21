"use client";

import { ApiError, unwrap, type components } from "@dienstpilot/api-client";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { CascadeTimeline } from "@/components/CascadeTimeline";
import { EngineBadge } from "@/components/EngineBadge";
import { RuleMessage } from "@/components/RuleMessage";
import { Suggestion } from "@/components/Suggestion";
import { Async, PageHeader, Section, useToast } from "@/components/ui";
import { Link, useRouter } from "@/i18n/navigation";
import { useFmt } from "@/lib/fmt";
import { useAction, useQuery } from "@/lib/hooks";
import { useSession } from "@/lib/session";

type Option = components["schemas"]["Option"];

/** W7b: escalation with the ranked options and what each one costs. The Planner decides. */
export default function EscalationPage(): ReactNode {
  const t = useTranslations("w7b");
  const te = useTranslations("escalation");
  const fmt = useFmt();
  const toast = useToast();
  const router = useRouter();
  const { api } = useSession();
  const { id } = useParams<{ id: string }>();
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
        return (
          <>
            <PageHeader
              title={t("title")}
              status={
                reason
                  ? te.has(reason as "overtime")
                    ? te(reason as "overtime")
                    : reason
                  : t("statusOpen")
              }
              actions={
                <Link href="/ausfaelle" className="label text-action underline">
                  {t("back")}
                </Link>
              }
            />
            <Section title={t("timeline")}>
              <CascadeTimeline cascade={e.cascade} />
            </Section>
            <Section title={t("optionsTitle")} aside={<EngineBadge engine={e.engine} />}>
              <p className="body m-0 text-ink-muted">{t("optionsNote")}</p>
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
              <div className="flex flex-col gap-4">
                {e.options.map((o, i) => (
                  <Suggestion
                    key={`${o.kind}-${o.staff_id ?? i}`}
                    text={
                      <>
                        <strong>{t(`option.${o.kind}`, { name: o.staff_name ?? "" })}</strong>{" "}
                        {o.hours_after != null && o.contract_hours != null
                          ? t("consequence", {
                              after: fmt.number(o.hours_after, 1),
                              contract: fmt.number(o.contract_hours, 1),
                              overtime: fmt.number(o.overtime_after ?? 0, 1),
                            })
                          : t("noConsequence")}
                      </>
                    }
                    reasons={[{ text: t("rank", { rank: i + 1 }) }, { text: t("checked") }]}
                    accept={t(`choose.${o.kind}`)}
                    onAccept={() => void decide.run(o)}
                    busy={decide.pending}
                  />
                ))}
              </div>
            </Section>
          </>
        );
      }}
    </Async>
  );
}

"use client";

import { unwrap } from "@dienstpilot/api-client";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { CascadeTimeline } from "@/components/CascadeTimeline";
import { Async, PageHeader, Section } from "@/components/ui";
import { Link } from "@/i18n/navigation";
import { useQuery } from "@/lib/hooks";

/** W7: active cover cascades, escalations first. */
export default function AbsencesPage(): ReactNode {
  const t = useTranslations("w7");
  const q = useQuery((api) => unwrap(api.GET("/planner/cascades")), []);
  return (
    <Async query={q}>
      {(list) => {
        const escalated = list.filter((c) => c.status === "pending_approval");
        return (
          <>
            <PageHeader
              title={t("title")}
              status={
                list.length === 0
                  ? t("statusNone")
                  : escalated.length > 0
                    ? t("statusEscalated", { count: escalated.length })
                    : t("statusRunning", { count: list.length })
              }
            />
            {list.length === 0 ? <p className="body m-0">{t("none")}</p> : null}
            {[...list]
              .sort(
                (a, b) =>
                  Number(b.status === "pending_approval") -
                    Number(a.status === "pending_approval") ||
                  b.opened_at.localeCompare(a.opened_at),
              )
              .map((c) => (
                <Section
                  key={c.id}
                  title={t("cascadeTitle")}
                  aside={
                    c.status === "pending_approval" ? (
                      <Link
                        href={`/ausfaelle/${c.id}`}
                        className="dp-btn dp-btn--primary label no-underline"
                      >
                        {t("decide")}
                      </Link>
                    ) : null
                  }
                >
                  <CascadeTimeline cascade={c} />
                </Section>
              ))}
          </>
        );
      }}
    </Async>
  );
}

"use client";

import { unwrap } from "@dienstpilot/api-client";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { CascadeTimeline } from "@/components/CascadeTimeline";
import { Async, PageHeader } from "@/components/ui";
import { Link } from "@/i18n/navigation";
import { useFmt } from "@/lib/fmt";
import { useQuery } from "@/lib/hooks";

/** W7: cover cascades after sick reports, escalations first. */
export default function AbsencesPage(): ReactNode {
  const t = useTranslations("w7");
  const fmt = useFmt();
  const q = useQuery((api) => unwrap(api.GET("/planner/cascades")), []);
  return (
    <Async query={q}>
      {(list) => {
        const escalated = list.filter((c) => c.status === "pending_approval");
        const closed = list.filter((c) => c.status === "closed" && c.outcome === "covered");
        const running = list.filter((c) => c.status === "open");
        const parts = [
          closed.length ? t("partClosed", { count: closed.length }) : null,
          running.length ? t("partRunning", { count: running.length }) : null,
          escalated.length ? t("partEscalated", { count: escalated.length }) : null,
        ].filter(Boolean);
        const sorted = [...list].sort(
          (a, b) =>
            Number(b.status === "pending_approval") - Number(a.status === "pending_approval") ||
            b.opened_at.localeCompare(a.opened_at),
        );
        // The time each person gets is read from the offers themselves (deadline minus asked).
        const offer = list.flatMap((c) => c.timeline).find((s) => s.deadline_at);
        const minutes = offer?.deadline_at
          ? Math.round((Date.parse(offer.deadline_at) - Date.parse(offer.asked_at)) / 60000)
          : 0;
        return (
          <>
            <PageHeader
              title={list.length === 0 ? t("statusNone") : parts.join(", ")}
              status={
                list.length === 0
                  ? t("none")
                  : t("sublineAsking", {
                      date: fmt.dayMonth(sorted[0]?.opened_at.slice(0, 10) ?? ""),
                      minutes,
                    })
              }
            />
            <div className="grid items-start gap-6 [grid-template-columns:repeat(auto-fit,minmax(420px,1fr))]">
              {sorted.map((c) => (
                <section
                  key={c.id}
                  aria-label={t("cascadeTitle")}
                  className="flex min-w-0 flex-col gap-3 border border-rule bg-sheet p-5"
                >
                  <CascadeTimeline cascade={c} />
                  {c.status === "pending_approval" ? (
                    <Link
                      href={`/ausfaelle/${c.id}`}
                      className="dp-btn dp-btn--primary label self-start no-underline"
                    >
                      {t("decide")}
                    </Link>
                  ) : null}
                </section>
              ))}
            </div>
          </>
        );
      }}
    </Async>
  );
}

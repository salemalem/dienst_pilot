"use client";

import { unwrap } from "@dienstpilot/api-client";
import { BellRing, Check } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";

import {
  Async,
  Button,
  Dialog,
  ErrorState,
  ICON,
  Loading,
  PageHeader,
  Progress,
  Section,
  Table,
  useToast,
} from "@/components/ui";
import { useFmt } from "@/lib/fmt";
import { useAction, useQuery } from "@/lib/hooks";
import { usePlanning } from "@/lib/planning";
import { useSession } from "@/lib/session";

/** W2: who has answered the request window, remind the rest, close the window. */
export default function WindowPage(): ReactNode {
  const t = useTranslations("w2");
  const fmt = useFmt();
  const toast = useToast();
  const { api } = useSession();
  const planning = usePlanning();
  const month = planning.month;
  const q = useQuery(
    (a) =>
      month
        ? unwrap(a.GET("/planner/windows/{month}", { params: { path: { month } } }))
        : Promise.resolve(null),
    [month],
  );
  const [confirm, setConfirm] = useState(false);
  const [filter, setFilter] = useState<"all" | "open">("all");

  const remind = useAction(async () => {
    if (!month) return;
    const r = await unwrap(
      api.POST("/planner/windows/{month}/reminders", { params: { path: { month } } }),
    );
    toast.show(t("reminded", { count: r.reminded }));
  });
  const close = useAction(async () => {
    if (!month) return;
    await unwrap(api.POST("/planner/windows/{month}/close", { params: { path: { month } } }));
    setConfirm(false);
    toast.show(t("closed", { month: fmt.month(month) }));
    q.reload();
    planning.overview.reload();
  });

  if (planning.overview.error)
    return <ErrorState error={planning.overview.error} onRetry={planning.overview.reload} />;
  if (!planning.overview.data) return <Loading />;
  if (!month) return <PageHeader title={t("title")} status={t("none")} />;

  return (
    <Async query={q}>
      {(w) => {
        if (!w) return null;
        const open = w.status === "open";
        const waiting = w.people.filter((p) => !p.responded_at);
        const people = filter === "open" ? waiting : w.people;
        return (
          <>
            <PageHeader
              title={t("title")}
              status={`${t("progress", { responded: w.responded, recipients: w.recipients })} · ${open ? t("opensCloses", { opens: fmt.date(w.opens_at), closes: fmt.date(w.closes_at) }) : t("statusClosed")}`}
              actions={
                open ? (
                  <>
                    <Button
                      onClick={() => void remind.run()}
                      disabled={remind.pending || waiting.length === 0}
                      icon={<BellRing {...ICON} />}
                    >
                      {t("remind")}
                    </Button>
                    <Button
                      variant="primary"
                      onClick={() => {
                        setConfirm(true);
                      }}
                    >
                      {t("close")}
                    </Button>
                  </>
                ) : null
              }
            />
            <Section title={t("progressTitle", { month: fmt.month(month) })}>
              <Progress
                value={w.responded}
                max={w.recipients}
                label={t("progress", { responded: w.responded, recipients: w.recipients })}
              />
              <div className="flex gap-3">
                <Button
                  variant={filter === "all" ? "primary" : "secondary"}
                  aria-pressed={filter === "all"}
                  onClick={() => {
                    setFilter("all");
                  }}
                >
                  {t("filterAll", { count: w.people.length })}
                </Button>
                <Button
                  variant={filter === "open" ? "primary" : "secondary"}
                  aria-pressed={filter === "open"}
                  onClick={() => {
                    setFilter("open");
                  }}
                >
                  {t("filterOpen", { count: waiting.length })}
                </Button>
              </div>
              <Table label={t("listLabel")}>
                <thead>
                  <tr>
                    <th scope="col">{t("colPerson")}</th>
                    <th scope="col">{t("colStatus")}</th>
                  </tr>
                </thead>
                <tbody>
                  {people.map((p) => (
                    <tr key={p.staff_id}>
                      <td>{p.display_name}</td>
                      <td>
                        {p.responded_at ? (
                          <span className="inline-flex items-center gap-2">
                            <Check {...ICON} />
                            {t("answered", { date: fmt.dateTime(p.responded_at) })}
                          </span>
                        ) : (
                          <span className="text-ink-muted">{t("notAnswered")}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
              {remind.error ? <ErrorState error={remind.error} /> : null}
            </Section>
            <Dialog
              open={confirm}
              title={t("closeTitle", { month: fmt.month(month) })}
              onClose={() => {
                setConfirm(false);
              }}
              footer={
                <>
                  <Button
                    variant="quiet"
                    onClick={() => {
                      setConfirm(false);
                    }}
                  >
                    {t("cancel")}
                  </Button>
                  <Button
                    variant="primary"
                    disabled={close.pending}
                    onClick={() => void close.run()}
                  >
                    {t("close")}
                  </Button>
                </>
              }
            >
              <p className="body m-0">{t("closeBody", { open: waiting.length })}</p>
              {close.error ? <ErrorState error={close.error} /> : null}
            </Dialog>
          </>
        );
      }}
    </Async>
  );
}

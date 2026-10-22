"use client";

import { unwrap } from "@dienstpilot/api-client";
import { BellRing } from "lucide-react";
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
        return (
          <>
            <PageHeader
              title={t("progress", { responded: w.responded, recipients: w.recipients })}
              status={`${t("subline", { month: fmt.month(month) })} · ${open ? t("opensCloses", { opens: fmt.date(w.opens_at), closes: fmt.date(w.closes_at) }) : t("statusClosed")}`}
              actions={
                open ? (
                  <>
                    <Button
                      onClick={() => {
                        setConfirm(true);
                      }}
                    >
                      {t("close")}
                    </Button>
                    <Button
                      variant="primary"
                      onClick={() => void remind.run()}
                      disabled={remind.pending || waiting.length === 0}
                      icon={<BellRing {...ICON} />}
                    >
                      {t("remind")}
                    </Button>
                  </>
                ) : null
              }
            />
            <div className="flex flex-col gap-1">
              <Progress
                value={w.responded}
                max={w.recipients}
                label={t("progress", { responded: w.responded, recipients: w.recipients })}
              />
              <div className="flex items-baseline justify-between gap-4">
                <p className="caption m-0 text-ink-muted">
                  {open ? t("remindNote", { count: waiting.length }) : ""}
                </p>
                <span className="num-small text-ink-muted" data-testid="window-percent">
                  {fmt.percent(w.recipients > 0 ? w.responded / w.recipients : 0)}
                </span>
              </div>
            </div>
            {remind.error ? <ErrorState error={remind.error} /> : null}
            <div className="grid items-start gap-6 [grid-template-columns:repeat(auto-fit,minmax(380px,1fr))]">
              <Section
                title={t("waitingTitle")}
                aside={<span className="num-small">{waiting.length}</span>}
              >
                <Table label={t("waitingTitle")}>
                  <thead>
                    <tr>
                      <th scope="col">{t("colPerson")}</th>
                      <th scope="col">{t("colStatus")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {waiting.map((p) => (
                      <tr key={p.staff_id}>
                        <td>{p.display_name}</td>
                        <td className="text-ink-muted">{t("notAnswered")}</td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </Section>
              <Section
                title={t("answeredTitle")}
                aside={<span className="num-small">{w.people.length - waiting.length}</span>}
              >
                <Table label={t("answeredTitle")}>
                  <thead>
                    <tr>
                      <th scope="col">{t("colPerson")}</th>
                      <th scope="col">{t("colAnswered")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {w.people
                      .filter((p) => p.responded_at)
                      .map((p) => (
                        <tr key={p.staff_id}>
                          <td>{p.display_name}</td>
                          <td className="num-small">
                            {p.responded_at ? fmt.dateTime(p.responded_at) : ""}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </Table>
              </Section>
            </div>
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

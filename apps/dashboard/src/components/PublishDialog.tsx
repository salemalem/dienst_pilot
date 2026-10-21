"use client";

import { ApiError, unwrap } from "@dienstpilot/api-client";
import { CircleCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { EngineBadge } from "@/components/EngineBadge";
import { RuleMessage } from "@/components/RuleMessage";
import { Button, Dialog, ErrorState, ICON, Loading, useToast } from "@/components/ui";
import { useFmt } from "@/lib/fmt";
import { useAction, useQuery } from "@/lib/hooks";
import { useSession } from "@/lib/session";

export interface PublishTarget {
  month: string;
  variantId: string;
  label: string;
}

function Body({
  target,
  onClose,
  onPublished,
}: {
  target: PublishTarget;
  onClose: () => void;
  onPublished: () => void;
}): ReactNode {
  const t = useTranslations("w5");
  const fmt = useFmt();
  const toast = useToast();
  const { api } = useSession();
  const check = useQuery(
    async (a) => {
      const [validation, grid] = await Promise.all([
        unwrap(
          a.POST("/planner/validate", {
            body: { roster_month: target.month, variant_id: target.variantId },
          }),
        ),
        unwrap(
          a.GET("/roster", {
            params: { query: { month: target.month, variant_id: target.variantId } },
          }),
        ),
      ]);
      return { validation, people: grid.rows.length };
    },
    [target.variantId],
  );
  const publish = useAction(async () => {
    await unwrap(
      api.POST("/planner/variants/{variant_id}/publish", {
        params: { path: { variant_id: target.variantId } },
      }),
    );
    toast.show(t("published", { month: fmt.month(target.month) }));
    onPublished();
    onClose();
  });

  if (check.error) return <ErrorState error={check.error} onRetry={check.reload} />;
  if (!check.data) return <Loading />;
  const { validation, people } = check.data;
  const valid = validation.valid;
  const err = publish.error;
  return (
    <>
      <p className="body m-0">
        {t("summary", { month: fmt.month(target.month), label: target.label, people })}
      </p>
      <ul className="body m-0 list-disc pl-5">
        <li>{t("seeRoster")}</li>
        <li>{t("seeDeclined")}</li>
        <li>{t("seeFairness")}</li>
      </ul>
      <div className="flex flex-wrap items-center gap-2">
        {valid ? (
          <span className="label inline-flex items-center gap-2" data-testid="validation-ok">
            <CircleCheck {...ICON} size={20} /> {t("valid")}
          </span>
        ) : null}
        <EngineBadge engine={validation.validator} />
      </div>
      {!valid
        ? validation.violations
            .slice(0, 5)
            .map((v) => (
              <RuleMessage key={`${v.rule}-${v.date}-${v.staff_id ?? ""}`} violation={v} />
            ))
        : null}
      {err instanceof ApiError && err.violations.length > 0 ? (
        err.violations
          .slice(0, 5)
          .map((v) => (
            <RuleMessage key={`${v.rule}-${v.date}-${v.staff_id ?? ""}`} violation={v} live />
          ))
      ) : err ? (
        <p role="alert" className="body m-0 text-alert">
          {err instanceof ApiError && err.status === 409 ? t("conflict") : t("failed")}{" "}
          <span className="caption">({err.message})</span>
        </p>
      ) : null}
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="quiet" onClick={onClose}>
          {t("cancel")}
        </Button>
        <Button
          variant="primary"
          disabled={!valid || publish.pending}
          onClick={() => void publish.run()}
          data-testid="confirm-publish"
        >
          {t("confirm")}
        </Button>
      </div>
    </>
  );
}

/** W5: the only way a roster becomes visible to staff: the Planner's explicit approval. */
export function PublishDialog({
  target,
  onClose,
  onPublished,
}: {
  target: PublishTarget | null;
  onClose: () => void;
  onPublished: () => void;
}): ReactNode {
  const t = useTranslations("w5");
  return (
    <Dialog open={target !== null} title={t("title")} onClose={onClose} wide>
      {target ? <Body target={target} onClose={onClose} onPublished={onPublished} /> : null}
    </Dialog>
  );
}

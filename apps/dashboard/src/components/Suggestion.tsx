"use client";

import { CircleQuestionMark, PencilLine, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId, useState, type ReactNode } from "react";

import { Button, ICON } from "./ui";

export interface Reason {
  text: string;
  source?: string;
}

/**
 * Everything the system proposes is pencil until a person accepts it, always with "Warum? / Why?".
 * Never a publish or approve action in here.
 */
export function Suggestion({
  title,
  children,
  actions,
  text,
  reasons,
  accept,
  onAccept,
  dismiss,
  onDismiss,
  open = false,
  badge,
  busy,
}: {
  title?: ReactNode;
  children?: ReactNode;
  /** Extra actions before "Why?" (never publish or approve). */
  actions?: ReactNode;
  text: ReactNode;
  reasons: Reason[];
  accept?: string | undefined;
  onAccept?: (() => void) | undefined;
  dismiss?: string | undefined;
  onDismiss?: (() => void) | undefined;
  open?: boolean;
  badge?: ReactNode;
  busy?: boolean;
}): ReactNode {
  const t = useTranslations("common");
  const [shown, setShown] = useState(open);
  const whyId = useId();
  return (
    <div className="dp-sugg" data-testid="suggestion">
      <span className="dp-sugg-tag label">
        <PencilLine {...ICON} />
        {t("suggestion")}
        {badge}
      </span>
      {title}
      <p className="dp-sugg-body body">{text}</p>
      {children}
      <div className="dp-sugg-actions">
        {actions}
        {accept && onAccept ? (
          <Button variant="primary" onClick={onAccept} disabled={busy}>
            {accept}
          </Button>
        ) : null}
        {dismiss && onDismiss ? (
          <Button variant="quiet" onClick={onDismiss} icon={<X {...ICON} />}>
            {dismiss}
          </Button>
        ) : null}
        <Button
          variant="quiet"
          className="dp-sugg-why-btn"
          aria-expanded={shown}
          aria-controls={whyId}
          icon={<CircleQuestionMark {...ICON} />}
          onClick={() => {
            setShown((v) => !v);
          }}
        >
          {t("why")}
        </Button>
      </div>
      <div id={whyId} className="dp-sugg-why" hidden={!shown}>
        <ul className="body">
          {reasons.map((r) => (
            <li key={r.text}>
              {r.text}
              {r.source ? <cite> ({r.source})</cite> : null}
            </li>
          ))}
        </ul>
        <span className="dp-sugg-note caption">{t("suggestionNote")}</span>
      </div>
    </div>
  );
}

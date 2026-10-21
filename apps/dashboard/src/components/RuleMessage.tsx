"use client";

import type { Violation } from "@dienstpilot/api-client";
import { CircleAlert } from "lucide-react";
import type { ReactNode } from "react";

import { useViolationText } from "@/lib/violations";

/** A C2 rule violation: what is broken, where, and the fix. Red pen, icon, two sentences. */
export function RuleMessage({
  violation,
  live,
}: {
  violation: Violation;
  live?: boolean;
}): ReactNode {
  const text = useViolationText();
  const { title, detail } = text(violation);
  return (
    <div className="dp-rule" role={live ? "alert" : undefined} data-rule={violation.rule}>
      <span className="dp-rule-icon">
        <CircleAlert size={20} strokeWidth={1.75} absoluteStrokeWidth aria-hidden />
      </span>
      <div className="dp-rule-text body">
        <strong>{title}</strong>
        <span>{detail}</span>
      </div>
    </div>
  );
}

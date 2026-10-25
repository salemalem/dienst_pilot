"use client";

import { PencilLine } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { ICON } from "./ui";

export interface EngineLabel {
  component: string;
  implementation: string;
  version: string;
  note: string;
}

/** Tells whether an answer came from a built component or a stand-in, as the API reports it. */
export function EngineBadge({ engine }: { engine: EngineLabel }): ReactNode {
  const t = useTranslations("common");
  const standIn = engine.implementation === "stand-in";
  return (
    <span
      className={`caption inline-flex items-center gap-1 whitespace-nowrap rounded-mark border px-2 py-0.5 ${
        standIn
          ? "border-dashed border-pencil bg-pencil-wash text-pencil"
          : "border-rule-strong text-ink-muted"
      }`}
      title={engine.note}
      data-engine={engine.implementation}
    >
      {standIn ? <PencilLine {...ICON} size={12} /> : null}
      {engine.component} ·{" "}
      {standIn ? t("standIn") : engine.implementation === "partial" ? t("partial") : t("built")} ·{" "}
      {engine.version}
    </span>
  );
}

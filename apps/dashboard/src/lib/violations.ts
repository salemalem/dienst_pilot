"use client";

import type { Violation } from "@dienstpilot/api-client";
import { useTranslations } from "next-intl";

import { useFmt } from "./fmt";

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

/** Render an API i18n key with its parameters (days, shifts and rule names become words). */
export function useKeyText(): (key: string, raw: Record<string, unknown>) => string {
  const t = useTranslations();
  const shifts = useTranslations("shift");
  const rules = useTranslations("rules");
  const fmt = useFmt();
  return (key, raw) => {
    const out: Record<string, string | number> = {};
    for (const [k, v] of Object.entries(raw)) {
      if (typeof v === "string" && ISO_DAY.test(v)) out[k] = fmt.dayMonth(v);
      else if (k === "shift" && typeof v === "string") out[k] = shifts(`${v as "frueh"}.name`);
      else if (k === "rule" && typeof v === "string")
        out[k] = rules.has(v as "coverage") ? rules(v as "coverage") : v;
      else if (typeof v === "number") out[k] = Number.isInteger(v) ? v : fmt.number(v);
      else if (typeof v === "string") out[k] = v;
    }
    return t(key as "violation.coverage", out as never);
  };
}

/** Turn an API violation ({key, params, fix_key, fix_params}) into the two sentences of a rule message. */
export function useViolationText(): (v: Violation) => { title: string; detail: string } {
  const text = useKeyText();
  return (v) => ({
    title: `${v.display_name ? `${v.display_name}: ` : ""}${text(v.key, v.params)}`,
    detail: text(v.fix_key, v.fix_params),
  });
}

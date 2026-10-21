import { useTranslation } from "react-i18next";

import { useFmt } from "./fmt";

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

/** Render an API i18n key with its parameters (days, shifts and rule names become words). */
export function useKeyText(): (key: string, raw: Record<string, unknown>) => string {
  const { t } = useTranslation();
  const fmt = useFmt();
  return (key, raw) => {
    const out: Record<string, string | number> = {};
    for (const [k, v] of Object.entries(raw)) {
      if (typeof v === "string" && ISO_DAY.test(v)) out[k] = fmt.dayMonth(v);
      else if (k === "shift" && typeof v === "string") out[k] = t(`shift.${v as "frueh"}.name`);
      else if (k === "rule" && typeof v === "string")
        out[k] = t(`rules.${v as "coverage"}`, { defaultValue: v });
      else if (k === "qualification" && typeof v === "string")
        out[k] = t(`qualification.${v as "any"}`, { defaultValue: v });
      else if (typeof v === "number") out[k] = Number.isInteger(v) ? v : fmt.number(v);
      else if (typeof v === "string") out[k] = v;
    }
    return t(key, out).replace(/(\d)\.\.(?!\.)/g, "$1.");
  };
}

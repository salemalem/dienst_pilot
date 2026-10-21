"use client";

import { buildFmt, type Fmt } from "@dienstpilot/i18n";
import type { Locale } from "@dienstpilot/i18n";
import { useLocale } from "next-intl";
import { useMemo } from "react";

export {
  addMonths,
  buildFmt,
  dayToDate,
  daysInMonth,
  isWeekend,
  monthStart,
  weekdayIndex,
  type Fmt,
} from "@dienstpilot/i18n";

/** Locale formatting for the current language (CLAUDE.md: dates, 24 h, "91 %", German decimals). */
export function useFmt(): Fmt {
  const locale = useLocale() as Locale;
  return useMemo(() => buildFmt(locale), [locale]);
}

import { buildFmt, type Fmt, type Locale } from "@dienstpilot/i18n";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

/** Locale formatting for the current language (shared with the dashboard). */
export function useFmt(): Fmt {
  const { i18n } = useTranslation();
  const locale = (i18n.language === "en" ? "en" : "de") satisfies Locale;
  return useMemo(() => buildFmt(locale), [locale]);
}

/**
 * Locale formatting per CLAUDE.md: dates dd.MM.yyyy (DE) and d MMM yyyy (EN), 24-hour clock in
 * both, weeks start Monday, German percentages with a (non-breaking) space: "91 %".
 * Calendar values are read in the department's time zone.
 */
type Locale = "de" | "en";

export const TIME_ZONE = "Europe/Berlin";
/** ISO weekday of the first day of the week (1 = Monday). */
export const WEEK_STARTS_ON = 1;

const EN_MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];
const TAG: Record<Locale, string> = { de: "de-DE", en: "en-GB" };

function parts(date: Date): {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
} {
  const f = new Intl.DateTimeFormat("en-GB", {
    timeZone: TIME_ZONE,
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "numeric",
    minute: "numeric",
    hourCycle: "h23",
  });
  const get = (type: Intl.DateTimeFormatPartTypes): number =>
    Number(f.formatToParts(date).find((p) => p.type === type)?.value);
  return {
    year: get("year"),
    month: get("month"),
    day: get("day"),
    hour: get("hour"),
    minute: get("minute"),
  };
}

const pad = (n: number): string => String(n).padStart(2, "0");

/** 20.10.2026 / 20 Oct 2026 */
export function formatDate(date: Date, locale: Locale): string {
  const p = parts(date);
  return locale === "de"
    ? `${pad(p.day)}.${pad(p.month)}.${p.year}`
    : `${p.day} ${EN_MONTHS[p.month - 1] ?? ""} ${p.year}`;
}

/** 07:30 in both locales. */
export function formatTime(date: Date): string {
  const p = parts(date);
  return `${pad(p.hour)}:${pad(p.minute)}`;
}

/** 9,75 / 9.75 */
export function formatNumber(value: number, locale: Locale, maximumFractionDigits = 2): string {
  return new Intl.NumberFormat(TAG[locale], { maximumFractionDigits }).format(value);
}

/** 91 % / 91% (value is a fraction: 0.91). */
export function formatPercent(value: number, locale: Locale, maximumFractionDigits = 0): string {
  return new Intl.NumberFormat(TAG[locale], { style: "percent", maximumFractionDigits }).format(
    value,
  );
}

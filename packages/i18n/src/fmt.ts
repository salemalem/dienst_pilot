/**
 * Calendar-day helpers and the locale formatters both apps share (dd.MM.yyyy / d MMM yyyy,
 * "14./15.12." for two consecutive days, an en dash for a range, 24-hour times, "91 %").
 */
import { formatDate, formatNumber, formatPercent, formatTime } from "./format.ts";

type Locale = "de" | "en";

const MONTHS_DE = [
  "Januar",
  "Februar",
  "März",
  "April",
  "Mai",
  "Juni",
  "Juli",
  "August",
  "September",
  "Oktober",
  "November",
  "Dezember",
];
const MONTHS_EN = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];
const WEEKDAYS: Record<Locale, string[]> = {
  de: ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"],
  en: ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"],
};

/** A calendar day ("2026-12-14") as a Date at noon UTC, so the Berlin calendar day is the same. */
export function dayToDate(day: string): Date {
  return new Date(`${day.slice(0, 10)}T12:00:00Z`);
}

/** ISO weekday index, Monday = 0. */
export function weekdayIndex(day: string): number {
  return (dayToDate(day).getUTCDay() + 6) % 7;
}

/** A calendar day moved by whole days ("2026-10-20" + 2 = "2026-10-22"). */
export function addDays(day: string, delta: number): string {
  return new Date(dayToDate(day).getTime() + delta * 86_400_000).toISOString().slice(0, 10);
}

export function isWeekend(day: string): boolean {
  return weekdayIndex(day) >= 5;
}

/** First day of a month ("2026-12") as "2026-12-01"; accepts a full date too. */
export function monthStart(month: string): string {
  return `${month.slice(0, 7)}-01`;
}

export function addMonths(month: string, delta: number): string {
  const [y, m] = month.slice(0, 7).split("-").map(Number);
  const total = (y ?? 0) * 12 + (m ?? 1) - 1 + delta;
  return `${String(Math.floor(total / 12))}-${String((total % 12) + 1).padStart(2, "0")}`;
}

export function daysInMonth(month: string): string[] {
  const [y, m] = month.slice(0, 7).split("-").map(Number);
  const n = new Date(Date.UTC(y ?? 2026, m ?? 1, 0)).getUTCDate();
  return Array.from(
    { length: n },
    (_, i) => `${month.slice(0, 7)}-${String(i + 1).padStart(2, "0")}`,
  );
}

export interface Fmt {
  locale: Locale;
  /** 14.12.2026 / 14 Dec 2026 */
  date: (day: string | Date) => string;
  /** 14.12. / 14 Dec */
  dayMonth: (day: string) => string;
  /** 14./15.12. or 14/15 Dec: two consecutive days. */
  daySpan: (from: string, to: string) => string;
  /** 14.–27.07. / 14–27 Jul: a longer range. */
  range: (from: string, to: string) => string;
  time: (instant: string | Date) => string;
  dateTime: (instant: string | Date) => string;
  number: (value: number, digits?: number) => string;
  /** A rate between 0 and 1 as "91 %" (DE) or "91%" (EN). */
  percent: (rate: number) => string;
  hours: (value: number) => string;
  month: (month: string) => string;
  monthShort: (month: string) => string;
  weekday: (day: string) => string;
}

/** The formatters for a locale (also used directly by tests). */
export function buildFmt(locale: Locale): Fmt {
  const enMonth = (d: Date): string => MONTHS_EN[d.getUTCMonth()]?.slice(0, 3) ?? "";
  const toDate = (v: string | Date): Date =>
    typeof v === "string" ? new Date(v.length === 10 ? `${v}T12:00:00Z` : v) : v;
  const pad = (n: number): string => String(n).padStart(2, "0");
  const dayMonth = (day: string): string => {
    const d = dayToDate(day);
    return locale === "de"
      ? `${pad(d.getUTCDate())}.${pad(d.getUTCMonth() + 1)}.`
      : `${String(d.getUTCDate())} ${enMonth(d)}`;
  };
  return {
    locale,
    date: (day) => formatDate(toDate(day), locale),
    dayMonth,
    daySpan: (from, to) => {
      const a = dayToDate(from);
      const b = dayToDate(to);
      if (locale === "de") {
        return a.getUTCMonth() === b.getUTCMonth()
          ? `${pad(a.getUTCDate())}./${pad(b.getUTCDate())}.${pad(b.getUTCMonth() + 1)}.`
          : `${dayMonth(from)}/${dayMonth(to)}`;
      }
      return a.getUTCMonth() === b.getUTCMonth()
        ? `${String(a.getUTCDate())}/${String(b.getUTCDate())} ${enMonth(b)}`
        : `${dayMonth(from)}/${dayMonth(to)}`;
    },
    range: (from, to) => {
      const a = dayToDate(from);
      const b = dayToDate(to);
      if (locale === "de") {
        return a.getUTCMonth() === b.getUTCMonth()
          ? `${pad(a.getUTCDate())}.–${pad(b.getUTCDate())}.${pad(b.getUTCMonth() + 1)}.`
          : `${dayMonth(from)}–${dayMonth(to)}`;
      }
      return a.getUTCMonth() === b.getUTCMonth()
        ? `${String(a.getUTCDate())}–${String(b.getUTCDate())} ${enMonth(b)}`
        : `${dayMonth(from)}–${dayMonth(to)}`;
    },
    time: (instant) => formatTime(toDate(instant)),
    dateTime: (instant) => `${formatDate(toDate(instant), locale)}, ${formatTime(toDate(instant))}`,
    number: (value, digits = 2) => formatNumber(value, locale, digits),
    percent: (rate) => formatPercent(rate, locale),
    hours: (value) => `${formatNumber(value, locale, 2)} h`,
    month: (month) => {
      const m = Number(month.slice(5, 7)) - 1;
      return `${(locale === "de" ? MONTHS_DE : MONTHS_EN)[m] ?? ""} ${month.slice(0, 4)}`;
    },
    monthShort: (month) => {
      const m = Number(month.slice(5, 7)) - 1;
      return (locale === "de" ? MONTHS_DE : MONTHS_EN)[m] ?? "";
    },
    weekday: (day) => WEEKDAYS[locale][weekdayIndex(day)] ?? "",
  };
}

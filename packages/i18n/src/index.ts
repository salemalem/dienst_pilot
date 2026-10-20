/** The one message catalog for the dashboard and the staff app, plus locale formatting. */
import de from "../de.json";
import en from "../en.json";

export const locales = ["de", "en"] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = "de";

export type Messages = typeof de;
export const messages: Record<Locale, Messages> = { de, en };

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (locales as readonly string[]).includes(value);
}

export * from "./format.ts";

import { defaultLocale, locales, messages, type Locale } from "@dienstpilot/i18n";
import i18next from "i18next";
import ICU from "i18next-icu";
import { initReactI18next } from "react-i18next";

import { storage } from "./lib/storage";

const LANG_KEY = "dp-lang";

function initial(): Locale {
  const stored = storage.get(LANG_KEY);
  return locales.find((l) => l === stored) ?? defaultLocale;
}

// One catalog for both apps, in ICU syntax: i18next-icu reads it the way next-intl does.
// German is the default; the DE | EN switch (M1, M12) changes it at runtime and is remembered.
void i18next
  .use(ICU)
  .use(initReactI18next)
  .init({
    lng: initial(),
    fallbackLng: defaultLocale,
    supportedLngs: [...locales],
    resources: Object.fromEntries(locales.map((l) => [l, { translation: messages[l] }])),
    interpolation: { escapeValue: false },
    returnNull: false,
  });

export function setLanguage(locale: Locale): void {
  storage.set(LANG_KEY, locale);
  void i18next.changeLanguage(locale);
}

export default i18next;

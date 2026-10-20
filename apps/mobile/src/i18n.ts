import { defaultLocale, locales, messages } from "@dienstpilot/i18n";
import i18next from "i18next";
import ICU from "i18next-icu";
import { initReactI18next } from "react-i18next";

// One catalog for both apps, in ICU syntax: i18next-icu reads it the way next-intl does.
// The app starts in German (the default locale); the DE | EN switch changes it at runtime.
void i18next
  .use(ICU)
  .use(initReactI18next)
  .init({
    lng: defaultLocale,
    fallbackLng: defaultLocale,
    supportedLngs: [...locales],
    resources: Object.fromEntries(locales.map((l) => [l, { translation: messages[l] }])),
    interpolation: { escapeValue: false },
    returnNull: false,
  });

export default i18next;

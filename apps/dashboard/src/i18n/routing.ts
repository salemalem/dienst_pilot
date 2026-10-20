import { defaultLocale, locales } from "@dienstpilot/i18n";
import { defineRouting } from "next-intl/routing";

export const routing = defineRouting({ locales, defaultLocale, localePrefix: "always" });

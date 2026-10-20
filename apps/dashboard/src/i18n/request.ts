import { isLocale, messages } from "@dienstpilot/i18n";
import { getRequestConfig } from "next-intl/server";

import { routing } from "./routing";

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = isLocale(requested) ? requested : routing.defaultLocale;
  return { locale, messages: messages[locale], timeZone: "Europe/Berlin" };
});

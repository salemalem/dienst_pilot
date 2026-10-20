import type { Locale, Messages } from "@dienstpilot/i18n";

declare module "next-intl" {
  interface AppConfig {
    Locale: Locale;
    Messages: Messages;
  }
}

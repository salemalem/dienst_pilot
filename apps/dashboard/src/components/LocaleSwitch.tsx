"use client";

import { locales } from "@dienstpilot/i18n";
import { useLocale, useTranslations } from "next-intl";
import { useTransition, type ReactNode } from "react";

import { usePathname, useRouter } from "@/i18n/navigation";

/** DE | EN toggle. Switches the language at runtime without leaving the page. */
export function LocaleSwitch(): ReactNode {
  const t = useTranslations("locale");
  const active = useLocale();
  const router = useRouter();
  const pathname = usePathname();
  const [pending, startTransition] = useTransition();

  return (
    <div
      role="group"
      aria-label={t("label")}
      className="inline-flex gap-0.5 rounded-control border border-rule-strong bg-sheet p-0.5"
    >
      {locales.map((locale) => {
        const on = locale === active;
        return (
          <button
            key={locale}
            type="button"
            lang={locale}
            aria-pressed={on}
            aria-label={t(locale)}
            disabled={pending}
            onClick={() => {
              startTransition(() => router.replace(pathname, { locale }));
            }}
            className={`label h-8 cursor-pointer rounded border-0 px-2.5 ${
              on ? "bg-action text-on-action" : "bg-transparent text-ink"
            }`}
          >
            {locale.toUpperCase()}
          </button>
        );
      })}
    </div>
  );
}

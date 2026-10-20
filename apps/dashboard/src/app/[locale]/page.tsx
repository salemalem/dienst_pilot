import { isLocale } from "@dienstpilot/i18n";
import { notFound } from "next/navigation";
import { useTranslations } from "next-intl";
import { setRequestLocale } from "next-intl/server";
import { use, type ReactNode } from "react";

import { EnvBadge } from "@/components/EnvBadge";
import { LocaleSwitch } from "@/components/LocaleSwitch";
import { ShiftLegend } from "@/components/ShiftLegend";

export default function HomePage({ params }: PageProps<"/[locale]">): ReactNode {
  const { locale } = use(params);
  if (!isLocale(locale)) notFound();
  setRequestLocale(locale);
  const t = useTranslations();
  return (
    <>
      <header className="flex min-h-14 flex-wrap items-center gap-4 border-b border-rule bg-sheet px-6 py-2">
        <span className="title">{t("app.name")}</span>
        <span className="label text-ink-muted">{t("app.department")}</span>
        <span className="flex-1" />
        <EnvBadge />
        <LocaleSwitch />
      </header>
      <main className="flex flex-col gap-6 px-10 py-8">
        <h1 className="display m-0">{t("shell.dashboardTitle")}</h1>
        <p className="body m-0 text-ink-muted">{t("shell.scaffold")}</p>
        <ShiftLegend />
      </main>
    </>
  );
}

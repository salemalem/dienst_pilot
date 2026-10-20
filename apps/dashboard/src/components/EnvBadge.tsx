import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

/** "Demo-Umgebung, synthetische Daten": required on every screen, never dismissible. */
export function EnvBadge(): ReactNode {
  const t = useTranslations("app");
  return (
    <span
      role="status"
      className="caption inline-flex h-[26px] items-center whitespace-nowrap rounded-mark border border-env bg-env-wash px-2 text-env"
    >
      {t("env")}
    </span>
  );
}

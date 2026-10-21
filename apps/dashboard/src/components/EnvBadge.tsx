import { FlaskConical } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

/** "Demo-Umgebung, synthetische Daten": required on every screen, never dismissible. */
export function EnvBadge(): ReactNode {
  const t = useTranslations("app");
  return (
    <span role="status" className="dp-env caption">
      <FlaskConical size={14} strokeWidth={1.75} absoluteStrokeWidth aria-hidden />
      {t("env")}
    </span>
  );
}

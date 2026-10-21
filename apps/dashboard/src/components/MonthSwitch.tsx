"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { Button, ICON } from "@/components/ui";
import { addMonths, useFmt } from "@/lib/fmt";

/** Previous / next month around the month's name (W3, W4, W8). */
export function MonthSwitch({
  month,
  onChange,
}: {
  month: string;
  onChange: (month: string) => void;
}): ReactNode {
  const t = useTranslations("common");
  const fmt = useFmt();
  return (
    <div className="flex items-center gap-1" role="group" aria-label={t("month")}>
      <Button
        variant="secondary"
        className="dp-iconbtn"
        aria-label={t("prevMonth")}
        icon={<ChevronLeft {...ICON} />}
        onClick={() => {
          onChange(addMonths(month, -1));
        }}
      />
      <span className="body-strong min-w-[9ch] px-2 text-center" aria-live="polite">
        {fmt.month(month)}
      </span>
      <Button
        variant="secondary"
        className="dp-iconbtn"
        aria-label={t("nextMonth")}
        icon={<ChevronRight {...ICON} />}
        onClick={() => {
          onChange(addMonths(month, 1));
        }}
      />
    </div>
  );
}

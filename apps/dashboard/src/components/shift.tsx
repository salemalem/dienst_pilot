"use client";

import { shiftTypes, type ShiftType } from "@dienstpilot/design-tokens";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

/** API shift codes map to the six token names (`frueh`, `spaet`, `nacht`, `bereitschaft`, `ruf`, `frei`). */
export function asShift(code: string): ShiftType | null {
  return (shiftTypes as readonly string[]).includes(code) ? (code as ShiftType) : null;
}

/** The letter in the current language, alongside the colour, never colour alone. */
export function useShiftName(): {
  letter: (code: string) => string;
  name: (code: string) => string;
  short: (code: string) => string;
} {
  const t = useTranslations("shift");
  return {
    letter: (c) => {
      const s = asShift(c);
      return s ? t(`${s}.letter`) : c;
    },
    name: (c) => {
      const s = asShift(c);
      return s ? t(`${s}.name`) : c;
    },
    short: (c) => {
      const s = asShift(c);
      return s ? t(`${s}.short`) : c;
    },
  };
}

export function ShiftChip({
  code,
  size = "md",
}: {
  code: string;
  size?: "sm" | "md" | "lg";
}): ReactNode {
  const { letter } = useShiftName();
  const s = asShift(code) ?? "frei";
  return (
    <span
      className={`dp-chip dp-shift--${s} ${size === "lg" ? "dp-chip--lg" : size === "sm" ? "dp-chip--sm" : ""}`}
      aria-hidden="true"
    >
      {s === "frei" ? <span>{letter(code)}</span> : letter(code)}
    </span>
  );
}

/** Chip plus the shift's name, for lists. */
export function ShiftLabel({ code }: { code: string }): ReactNode {
  const { name } = useShiftName();
  return (
    <span className="inline-flex items-center gap-2">
      <ShiftChip code={code} size="sm" />
      <span>{name(code)}</span>
    </span>
  );
}

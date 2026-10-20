import { shiftTypes, type ShiftType } from "@dienstpilot/design-tokens";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

// Literal class names so Tailwind can see them. Colour is never the only cue: each chip carries
// its letter; leave is hatched and Rufbereitschaft has the dotted off-site edge.
const CHIP: Record<ShiftType, string> = {
  frueh: "bg-shift-frueh text-on-shift-frueh",
  spaet: "bg-shift-spaet text-on-shift-spaet",
  nacht: "bg-shift-nacht text-on-shift-nacht ring-1 ring-inset ring-shift-nacht-edge",
  bereitschaft: "bg-shift-bereitschaft text-on-shift-bereitschaft",
  ruf: "bg-shift-ruf text-on-shift-ruf outline-[1.5px] outline-dotted -outline-offset-4 outline-on-shift-ruf",
  frei: "text-on-shift-frei ring-1 ring-inset ring-shift-frei bg-[repeating-linear-gradient(135deg,var(--shift-frei)_0_2px,var(--shift-frei-wash)_2px_5px)]",
};

/** The six shift types with their letters in the current language. */
export function ShiftLegend(): ReactNode {
  const t = useTranslations("shift");
  const heading = useTranslations("shell");
  return (
    <section aria-labelledby="shift-types" className="flex flex-col gap-3">
      <h2 id="shift-types" className="heading m-0">
        {heading("shiftTypes")}
      </h2>
      <ul className="m-0 flex list-none flex-wrap gap-x-6 gap-y-3 p-0">
        {shiftTypes.map((shift) => (
          <li key={shift} className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className={`grid h-8 min-w-8 place-items-center rounded-mark text-base font-[750] ${CHIP[shift]}`}
            >
              {shift === "frei" ? (
                <span className="rounded-sm bg-shift-frei px-0.5">{t(`${shift}.letter`)}</span>
              ) : (
                t(`${shift}.letter`)
              )}
            </span>
            <span className="body">{t(`${shift}.name`)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

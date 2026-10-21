import type { Page } from "@playwright/test";

import { makeApi } from "../../../scripts/e2e/api.ts";
import { API_URL } from "../playwright.config.ts";

export const { login, api } = makeApi(API_URL);

/** Open the dashboard as a persona, in a theme, before any script runs. */
export async function asPersona(
  page: Page,
  persona: "brandt" | "vogel" | "it-admin",
  theme: "light" | "dark" = "light",
): Promise<void> {
  await page.addInitScript(
    ([p, t]) => {
      sessionStorage.setItem("dp-persona", String(p));
      localStorage.setItem("dp-theme", String(t));
    },
    [persona, theme],
  );
}

export interface DraftShift {
  staffId: string;
  day: string;
  assignmentId: string;
}

type Grid = {
  rows: {
    staff_id: string;
    cells: Record<string, { shifts: string[]; assignment_ids: string[]; on_leave: boolean }>;
  }[];
};

const next = (day: string): string =>
  new Date(Date.parse(`${day}T12:00:00Z`) + 86_400_000).toISOString().slice(0, 10);

/**
 * A change that breaks the 11-hour rest rule: someone with a Spätdienst (ends 22:00) takes a
 * colleague's Frühdienst (07:30) on the next day. Returns the shift to move and who gets it.
 */
export function restBreakingMove(grid: Grid): {
  from: DraftShift;
  to: { staffId: string; day: string };
} {
  for (const p of grid.rows) {
    for (const [day, cell] of Object.entries(p.cells)) {
      if (!cell.shifts.includes("spaet") || cell.shifts.length !== 1) continue;
      const d2 = next(day);
      const free = !p.cells[d2] || (p.cells[d2].shifts.length === 0 && !p.cells[d2].on_leave);
      if (!free) continue;
      for (const q of grid.rows) {
        const c = q.cells[d2];
        const i = c?.shifts.indexOf("frueh") ?? -1;
        if (q.staff_id !== p.staff_id && c && i >= 0 && c.shifts.length === 1) {
          const id = c.assignment_ids[i];
          if (id)
            return {
              from: { staffId: q.staff_id, day: d2, assignmentId: id },
              to: { staffId: p.staff_id, day: d2 },
            };
        }
      }
    }
  }
  throw new Error("no rest-breaking move found in the draft");
}

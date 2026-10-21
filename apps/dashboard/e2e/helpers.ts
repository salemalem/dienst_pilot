import type { Page } from "@playwright/test";

import { API_URL } from "../playwright.config.ts";

/** Scripted API calls play the other personas' parts (staff, admin); the checks run in the UI. */
export async function login(persona: string): Promise<string> {
  const r = await fetch(`${API_URL}/auth/demo-login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ persona }),
  });
  if (!r.ok) throw new Error(`login ${persona}: ${String(r.status)}`);
  return ((await r.json()) as { access_token: string }).access_token;
}

export async function api<T = unknown>(
  token: string,
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const r = await fetch(`${API_URL}${path}`, {
    method,
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!r.ok) throw new Error(`${method} ${path}: ${String(r.status)} ${await r.text()}`);
  return (await r.json()) as T;
}

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

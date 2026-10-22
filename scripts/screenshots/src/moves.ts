/**
 * A change that breaks the 11-hour rest rule: someone with a Spätdienst (ends 22:00) takes a
 * colleague's Frühdienst (07:30) on the next day. Used to show the editor with a rule message.
 */
type Cell = { shifts: string[]; assignment_ids: string[]; on_leave: boolean };
export type Grid = { rows: { staff_id: string; cells: Record<string, Cell> }[] };

const next = (day: string): string =>
  new Date(Date.parse(`${day}T12:00:00Z`) + 86_400_000).toISOString().slice(0, 10);

export function restBreakingMove(grid: Grid): { assignmentId: string; toStaffId: string } {
  for (const p of grid.rows) {
    for (const [day, cell] of Object.entries(p.cells)) {
      if (!cell.shifts.includes("spaet") || cell.shifts.length !== 1) continue;
      const d2 = next(day);
      const own = p.cells[d2];
      if (own && (own.shifts.length > 0 || own.on_leave)) continue;
      for (const q of grid.rows) {
        const c = q.cells[d2];
        const i = c?.shifts.indexOf("frueh") ?? -1;
        if (q.staff_id !== p.staff_id && c && i >= 0 && c.shifts.length === 1) {
          const id = c.assignment_ids[i];
          if (id) return { assignmentId: id, toStaffId: p.staff_id };
        }
      }
    }
  }
  throw new Error("no rest-breaking move found in the draft");
}

"use client";

import type { components } from "@dienstpilot/api-client";
import { Check, CircleAlert, CircleSlash2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import {
  useEffect,
  useRef,
  useState,
  type DragEvent,
  type KeyboardEvent,
  type ReactNode,
} from "react";

import { asShift, useShiftName } from "@/components/shift";
import { useFmt, isWeekend } from "@/lib/fmt";

type Row = components["schemas"]["RosterRow"];
type Cell = components["schemas"]["Cell"];
type Coverage = components["schemas"]["CoverageRow"];

export interface CellRef {
  staffId: string;
  day: string;
}

/** The shift a cell shows first: the in-house or day shift, then on-call from home. */
export function primaryIndex(cell: Cell): number {
  const i = cell.shifts.findIndex((s) => s !== "ruf");
  return i >= 0 ? i : 0;
}

const ICON = { strokeWidth: 1.75, absoluteStrokeWidth: true, "aria-hidden": true } as const;

/**
 * W4's grid: physicians × days on the paper sheet. Roving tabindex (arrows), drag a shift onto a
 * colleague's cell on the same day, or Space to pick up, ↑/↓ to choose the person, Space to drop.
 */
export function RosterGrid({
  rows,
  days,
  coverage,
  today,
  violations,
  readOnly,
  onOpen,
  onMove,
  focusRequest,
}: {
  rows: Row[];
  days: string[];
  coverage: Coverage[];
  today: string;
  /** staff|day → rule names, and day → coverage rule. */
  violations: Map<string, string[]>;
  readOnly?: boolean;
  onOpen: (cell: CellRef) => void;
  onMove: (assignmentId: string, toStaffId: string, day: string) => void;
  focusRequest?: CellRef | null;
}): ReactNode {
  const t = useTranslations("w4");
  const locale = useLocale();
  const fmt = useFmt();
  const names = useShiftName();
  const [focus, setFocus] = useState<{ r: number; d: number }>({
    r: 0,
    d: Math.max(0, days.indexOf(today)),
  });
  const [picked, setPicked] = useState<{
    staffId: string;
    day: string;
    assignmentId: string;
  } | null>(null);
  const [announce, setAnnounce] = useState("");
  const [dragOver, setDragOver] = useState<string | null>(null);
  const refs = useRef(new Map<string, HTMLTableCellElement>());

  useEffect(() => {
    if (focusRequest) refs.current.get(`${focusRequest.staffId}|${focusRequest.day}`)?.focus();
  }, [focusRequest]);

  const missing = (day: string): Coverage[] =>
    coverage.filter((c) => c.date === day && c.assigned < c.required);
  const key = (staffId: string, day: string): string => `${staffId}|${day}`;

  const focusCell = (r: number, d: number): void => {
    const rr = Math.min(Math.max(r, 0), rows.length - 1);
    const dd = Math.min(Math.max(d, 0), days.length - 1);
    setFocus({ r: rr, d: dd });
    const row = rows[rr];
    const day = days[dd];
    if (row && day) refs.current.get(key(row.staff_id, day))?.focus();
  };

  const describe = (row: Row, day: string, cell: Cell | undefined): string => {
    const parts = [`${row.display_name}, ${fmt.dayMonth(day)}`];
    if (cell?.shifts.length) parts.push(cell.shifts.map((s) => names.name(s)).join(" + "));
    else if (cell?.on_leave) parts.push(t("cell.leave"));
    else if (cell?.absence) parts.push(t("cell.absent"));
    else parts.push(t("cell.free"));
    if (cell?.wish === "granted") parts.push(t("cell.wishGranted"));
    if (cell?.wish === "missed") parts.push(t("cell.wishMissed"));
    const v = violations.get(key(row.staff_id, day));
    if (v?.length) parts.push(`${t("cell.violation")}: ${v.join(", ")}`);
    return parts.join(", ");
  };

  const onKey = (
    e: KeyboardEvent<HTMLTableCellElement>,
    row: Row,
    ri: number,
    di: number,
    cell: Cell | undefined,
  ): void => {
    const day = days[di];
    if (!day) return;
    const move = (dr: number, dd: number): void => {
      e.preventDefault();
      focusCell(ri + dr, di + dd);
    };
    switch (e.key) {
      case "ArrowRight":
        return move(0, 1);
      case "ArrowLeft":
        return move(0, -1);
      case "ArrowDown":
        return move(1, 0);
      case "ArrowUp":
        return move(-1, 0);
      case "Home":
        return move(0, -di);
      case "End":
        return move(0, days.length);
      case "Escape":
        if (picked) {
          e.preventDefault();
          setPicked(null);
          setAnnounce(t("kbd.cancelled"));
        }
        return;
      case "Enter":
        e.preventDefault();
        if (picked) drop(row, day);
        else if (!readOnly) onOpen({ staffId: row.staff_id, day });
        return;
      case " ":
        e.preventDefault();
        if (readOnly) return;
        if (picked) drop(row, day);
        else if (cell?.shifts.length) {
          const id = cell.assignment_ids[primaryIndex(cell)];
          if (id) {
            setPicked({ staffId: row.staff_id, day, assignmentId: id });
            setAnnounce(t("kbd.picked", { name: row.display_name, day: fmt.dayMonth(day) }));
          }
        }
        return;
    }
  };

  const drop = (row: Row, day: string): void => {
    if (!picked) return;
    if (picked.day !== day) {
      setAnnounce(t("kbd.sameDay"));
      return;
    }
    if (picked.staffId !== row.staff_id) onMove(picked.assignmentId, row.staff_id, day);
    setPicked(null);
  };

  const onDragStart = (e: DragEvent, row: Row, day: string, cell: Cell): void => {
    const id = cell.assignment_ids[primaryIndex(cell)];
    if (!id || readOnly) return e.preventDefault();
    e.dataTransfer.setData("text/plain", JSON.stringify({ id, staffId: row.staff_id, day }));
    e.dataTransfer.effectAllowed = "move";
  };

  return (
    <div className="dp-sheet" style={{ display: "block" }}>
      <p className="sr-only" aria-live="assertive">
        {announce}
      </p>
      <table
        className="dp-grid"
        role="grid"
        aria-label={t("gridLabel")}
        aria-rowcount={rows.length + 2}
        data-testid="roster-grid"
      >
        <thead>
          <tr>
            <th scope="col" className="dp-rowhead grid-name">
              {t("colPhysician")}
            </th>
            {days.map((d) => (
              <th
                key={d}
                scope="col"
                className={`num-small ${isWeekend(d) ? "is-weekend" : ""} ${d === today ? "is-today" : ""}`}
                aria-current={d === today ? "date" : undefined}
              >
                <span className="dp-day">
                  <span>{fmt.weekday(d)}</span>
                  <b>{Number(d.slice(8))}</b>
                </span>
              </th>
            ))}
            <th scope="col" className="dp-total num-small">
              {t("colShifts")}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={row.staff_id}>
              <th scope="row" className="dp-rowhead">
                <span className="grid-name block">{row.display_name}</span>
                <small>{locale === "de" ? row.title_de : row.title_en}</small>
              </th>
              {days.map((d, di) => {
                const cell = row.cells[d];
                const shift = cell?.shifts.length
                  ? asShift(cell.shifts[primaryIndex(cell)] ?? "")
                  : null;
                const v = violations.get(key(row.staff_id, d));
                const selected = picked?.staffId === row.staff_id && picked.day === d;
                const target =
                  picked &&
                  picked.day === d &&
                  picked.staffId !== row.staff_id &&
                  focus.r === ri &&
                  focus.d === di;
                const leave = !shift && (cell?.on_leave || cell?.absence);
                return (
                  <td
                    key={d}
                    ref={(el) => {
                      if (el) refs.current.set(key(row.staff_id, d), el);
                      else refs.current.delete(key(row.staff_id, d));
                    }}
                    role="gridcell"
                    tabIndex={focus.r === ri && focus.d === di ? 0 : -1}
                    aria-label={describe(row, d, cell)}
                    aria-selected={selected || undefined}
                    draggable={Boolean(shift) && !readOnly}
                    data-staff={row.staff_id}
                    data-day={d}
                    data-shift={cell?.shifts.join(",") ?? ""}
                    data-violation={v ? v.join(" ") : undefined}
                    className={`dp-cell-td ${isWeekend(d) ? "is-weekend-col" : ""} ${d === today ? "is-today-col" : ""}`}
                    onFocus={() => {
                      setFocus({ r: ri, d: di });
                    }}
                    onClick={() => {
                      setFocus({ r: ri, d: di });
                      if (!readOnly) onOpen({ staffId: row.staff_id, day: d });
                    }}
                    onKeyDown={(e) => {
                      onKey(e, row, ri, di, cell);
                    }}
                    onDragStart={(e) => {
                      if (cell) onDragStart(e, row, d, cell);
                    }}
                    onDragOver={(e) => {
                      e.preventDefault();
                      setDragOver(key(row.staff_id, d));
                    }}
                    onDragLeave={() => {
                      setDragOver(null);
                    }}
                    onDrop={(e) => {
                      e.preventDefault();
                      setDragOver(null);
                      try {
                        const data = JSON.parse(e.dataTransfer.getData("text/plain")) as {
                          id: string;
                          staffId: string;
                          day: string;
                        };
                        if (data.day !== d) setAnnounce(t("kbd.sameDay"));
                        else if (data.staffId !== row.staff_id) onMove(data.id, row.staff_id, d);
                      } catch {
                        // Not one of our drags.
                      }
                    }}
                  >
                    <div
                      className={`dp-cell ${shift ? `has-shift dp-shift--${shift}` : ""} ${leave ? "is-leave" : ""} ${v ? "is-violation" : ""} ${selected || dragOver === key(row.staff_id, d) || target ? "is-selected" : ""} ${cell?.changed ? "is-changed" : ""}`}
                    >
                      {v ? (
                        <span className="dp-bang">
                          <CircleAlert size={14} {...ICON} />
                        </span>
                      ) : null}
                      {cell?.wish ? (
                        <span className={`dp-mark dp-mark--${cell.wish}`}>
                          {cell.wish === "granted" ? (
                            <Check size={12} {...ICON} />
                          ) : (
                            <CircleSlash2 size={12} {...ICON} />
                          )}
                        </span>
                      ) : null}
                      {cell?.shifts.length ? (
                        <span className="dp-letter grid-letter">
                          {cell.shifts.map((s) => names.letter(s)).join("/")}
                        </span>
                      ) : leave ? (
                        <span className="dp-letter grid-letter">
                          {cell?.on_leave ? names.letter("frei") : t("cell.absentLetter")}
                        </span>
                      ) : null}
                    </div>
                  </td>
                );
              })}
              <td className="dp-total num-small" data-testid={`total-${row.staff_id}`}>
                {Object.values(row.cells).reduce((n, c) => n + c.shifts.length, 0)}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row" className="dp-rowhead grid-name">
              {t("coverage")}
            </th>
            {days.map((d) => {
              const gaps = missing(d);
              const kinds = [...new Set(gaps.map((g) => g.shift_type))];
              return (
                <td
                  key={d}
                  className={`${isWeekend(d) ? "is-weekend-col" : ""}`}
                  data-testid={`coverage-${d}`}
                  data-gap={kinds.length ? kinds.join(",") : undefined}
                >
                  <div
                    className={`dp-cell ${kinds.length ? "is-gap" : ""}`}
                    role="img"
                    aria-label={
                      kinds.length
                        ? `${t("gap")}: ${kinds.map((k) => names.name(k)).join(", ")}, ${fmt.dayMonth(d)}`
                        : `${t("staffed")}, ${fmt.dayMonth(d)}`
                    }
                  >
                    {kinds.length ? (
                      <span className="dp-letter grid-letter">
                        {kinds.map((k) => names.letter(k)).join("")}
                      </span>
                    ) : (
                      <span className="dp-cov dp-cov-ok">
                        <Check size={14} {...ICON} />
                      </span>
                    )}
                  </div>
                </td>
              );
            })}
            <td className="dp-total" />
          </tr>
        </tfoot>
      </table>
      <GridLegend />
    </div>
  );
}

/** Shift letters with colour and the shape-coded marks; always visible under the grid. */
export function GridLegend(): ReactNode {
  const t = useTranslations("w4.legend");
  const names = useShiftName();
  const shifts = ["frueh", "spaet", "nacht", "bereitschaft", "ruf", "frei"] as const;
  return (
    <div className="dp-legend caption" aria-label={t("label")} role="group">
      {shifts.map((s) => (
        <span key={s} className="dp-legend-item">
          <span className={`dp-cell has-shift dp-shift--${s} ${s === "frei" ? "is-leave" : ""}`}>
            <span className="dp-letter grid-letter">{names.letter(s)}</span>
          </span>
          {names.name(s)}
        </span>
      ))}
      <span className="dp-legend-item">
        <Check size={14} {...ICON} /> {t("granted")}
      </span>
      <span className="dp-legend-item">
        <CircleSlash2 size={14} {...ICON} /> {t("missed")}
      </span>
      <span className="dp-legend-item text-alert">
        <CircleAlert size={14} {...ICON} /> {t("violation")}
      </span>
    </div>
  );
}

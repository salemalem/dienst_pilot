"""Scripted demo scenarios (ASSUMPTIONS §19): small, listed edits to the demo seed's output.

The simulation runs unchanged; these edits are applied to the finished tables, only for the
default seed, so the three situations of PROCESS.md §4 can be played with the real engines.
Every edit checks its precondition and fails loudly if the simulated data no longer fits.
"""

from datetime import date, datetime
from typing import Any

from synthdata.config import TZ
from synthdata.ids import uid

Rows = list[dict[str, Any]]
OCTOBER = date(2026, 10, 1)


class ScenarioDataError(RuntimeError):
    """The simulated data no longer matches what a scripted scenario expects."""


def _staff(tables: dict[str, Rows], name: str) -> Any:
    ids = [r["id"] for r in tables["organization/staff"] if r["display_name"] == name]
    if len(ids) != 1:
        raise ScenarioDataError(f"expected one staff member called {name!r}")
    return ids[0]


def _one(rows: Rows, what: str, **match: Any) -> dict[str, Any]:
    found = [r for r in rows if all(r[k] == v for k, v in match.items())]
    if len(found) != 1:
        raise ScenarioDataError(f"{what}: expected one row matching {match}, found {len(found)}")
    return found[0]


def _referenced(tables: dict[str, Rows]) -> set[Any]:
    """Return the assignments a swap or cover search points at (never edited)."""
    return {r["assignment_id"] for r in tables["operations/swap_offer"]} | {
        r["assignment_id"] for r in tables["operations/cover_cascade"]
    }


def _move(tables: dict[str, Rows], row: dict[str, Any], **change: Any) -> None:
    if row["id"] in _referenced(tables):
        raise ScenarioDataError(f"assignment {row['id']} is referenced by a swap or cover search")
    row.update(change)
    row["id"] = uid(
        "assignment", OCTOBER, "scenario", row["staff_id"], row["date"], row["shift_type"]
    )


def apply(tables: dict[str, Rows]) -> None:
    """Apply the scripted scenarios in place (default seed only)."""
    _sick_call(tables)
    _july_leave(tables)


def _sick_call(tables: dict[str, Rows]) -> None:
    """Situation C: Dr. Weber works the Frühdienst of Tuesday 20 October 2026.

    Dr. Alvarez is then the colleague C5 ranks first among those C2 allows to cover it.
    """
    weber = _staff(tables, "Dr. Jonas Weber")
    kaiser = _staff(tables, "Dr. Nadia Kaiser")
    wagner = _staff(tables, "Dr. Felix Wagner")
    okafor = _staff(tables, "Dr. Mira Okafor")
    run = _one(tables["planning/roster_run"], "October run", roster_month=OCTOBER)
    variant = _one(tables["planning/roster_variant"], "October variant", run_id=run["id"])["id"]
    rows = [r for r in tables["planning/assignment"] if r["variant_id"] == variant]

    # 1. Weber's autumn leave ends on Monday 19 October instead of Friday 23 October.
    leave = _one(
        tables["requests/leave_request"],
        "Weber's autumn leave",
        staff_id=weber,
        start_date=date(2026, 10, 12),
        end_date=date(2026, 10, 23),
        status="approved",
    )
    leave["end_date"] = date(2026, 10, 19)
    # 2. ... and he works Frühdienst from Tuesday to Friday, on top of the minimum demand, so his
    #    hours stay as they were and nobody else loses a shift.
    for d in range(20, 24):
        day = date(2026, 10, d)
        if any(r["staff_id"] == weber and r["date"] == day for r in rows):
            raise ScenarioDataError(f"Weber already has a shift on {day}")
        tables["planning/assignment"].append(
            {
                "id": uid("assignment", OCTOBER, "scenario", weber, day, "frueh"),
                "variant_id": variant,
                "staff_id": weber,
                "date": day,
                "shift_type": "frueh",
            }
        )
    # 3. Dr. Kaiser works her Frühdienst of Thursday 22 October on Tuesday 20 October instead.
    _move(
        tables,
        _one(
            rows,
            "Kaiser's Frühdienst",
            staff_id=kaiser,
            date=date(2026, 10, 22),
            shift_type="frueh",
        ),
        date=date(2026, 10, 20),
    )
    # 4. Dr. Wagner and Dr. Okafor exchange Spätdienste: Wagner 20 October, Okafor 27 October.
    w = _one(
        rows, "Wagner's Spätdienst", staff_id=wagner, date=date(2026, 10, 27), shift_type="spaet"
    )
    o = _one(
        rows, "Okafor's Spätdienst", staff_id=okafor, date=date(2026, 10, 20), shift_type="spaet"
    )
    _move(tables, w, staff_id=okafor)
    _move(tables, o, staff_id=wagner)


def _july_leave(tables: dict[str, Rows]) -> None:
    """Situation A: two colleagues have already requested leave overlapping 14–27 July 2027."""
    for name, start, end, submitted in (
        (
            "Dr. Carla Franke",
            date(2027, 7, 12),
            date(2027, 7, 23),
            datetime(2026, 10, 14, 9, 12, tzinfo=TZ),
        ),
        (
            "Dr. Niklas Stein",
            date(2027, 7, 19),
            date(2027, 7, 30),
            datetime(2026, 10, 16, 18, 47, tzinfo=TZ),
        ),
    ):
        staff = _staff(tables, name)
        tables["requests/leave_request"].append(
            {
                "id": uid("leave", "scenario", staff, start, end),
                "staff_id": staff,
                "start_date": start,
                "end_date": end,
                "submitted_at": submitted,
                "status": "pending",
                "decided_at": None,
                "decided_by": None,
                "decision_reason_code": None,
                "decision_reason": None,
                "previous_request_id": None,
            }
        )

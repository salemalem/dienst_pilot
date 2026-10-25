"""Ground truth for the C8 tasks: plain SQL on the seeded database, never the API or MCP tools.

Each function answers one kind of question from ``planning.assignment`` of the published
variants (the seed has no later changes to a published roster). The task generator
(``c8_tasks.py``) stores the results in ``c8_tasks.json``; a database test re-computes them, so a
change to the seed or to these definitions cannot go unnoticed.

Definitions the questions rely on (the same as the application's):
* nights: shifts of type ``nacht``;
* weekend duty: a weekend (Saturday and Sunday of one calendar week) with at least one shift;
* holiday duty: a public holiday with a working shift (frueh, spaet, nacht, bereitschaft);
* "this year so far": 1 January up to and including the ledger's ``as_of`` date.
"""

from datetime import date
from typing import Any

from c8_harness import World

WORKING = ("frueh", "spaet", "nacht", "bereitschaft")


def effective(w: World, first: date, last: date) -> list[tuple[str, str | None, date, str]]:
    """Return (assignment id, holder, day, shift type) of the published roster as it stands.

    Raw SQL, written independently of the application: the published variant's assignments, then
    accepted swaps and cover cascades applied in time order (the last one wins). A cascade that
    closed without a covering colleague, or is still open, leaves the shift without a holder.
    """
    base = w.sql(
        "SELECT a.id, a.staff_id, a.date, a.shift_type FROM planning.assignment a"
        " JOIN planning.roster_variant v ON v.id = a.variant_id AND v.status = 'published'"
        " WHERE a.date BETWEEN :a AND :b",
        a=first,
        b=last,
    )
    holder = {str(r[0]): str(r[1]) for r in base}
    ids = list(holder)
    events: list[tuple[Any, str, str, str | None]] = []
    for s in w.sql(
        "SELECT assignment_id, counter_assignment_id, offered_by, accepted_by,"
        " coalesce(decided_at, accepted_at, offered_at) FROM operations.swap_offer"
        " WHERE status IN ('accepted', 'approved') AND accepted_by IS NOT NULL"
    ):
        if str(s[0]) in holder:
            events.append((s[4], str(s[0]), "a", str(s[3])))
        if s[1] is not None and str(s[1]) in holder:
            events.append((s[4], str(s[1]), "a", str(s[2])))
    for c in w.sql(
        "SELECT assignment_id, opened_at, status, covered_by FROM operations.cover_cascade"
    ):
        if str(c[0]) in holder:
            who = str(c[3]) if c[2] == "closed" and c[3] is not None else None
            events.append((c[1], str(c[0]), "b", who))
    for _, aid, _, who in sorted(events, key=lambda e: (e[0], e[1])):
        holder[aid] = who  # type: ignore[assignment]
    del ids
    return [(str(r[0]), holder[str(r[0])], r[2], str(r[3])) for r in base]


def staff_id(w: World, name: str) -> str:
    """Return the id of the physician with this exact display name."""
    return str(w.sql("SELECT id FROM organization.staff WHERE display_name = :n", n=name)[0][0])


def shifts_of(w: World, staff: str, first: date, last: date, kind: str | None = None) -> int:
    """Count one physician's shifts (optionally of one type) in a date range."""
    return sum(
        1 for _, h, _, k in effective(w, first, last) if h == staff and (kind is None or k == kind)
    )


def weekend_shifts_of(w: World, staff: str, first: date, last: date) -> int:
    """Count shifts on a Saturday or Sunday in a date range."""
    return sum(1 for _, h, d, _ in effective(w, first, last) if h == staff and d.weekday() >= 5)


def working_days_of(w: World, staff: str, first: date, last: date) -> int:
    """Count distinct days with at least one shift."""
    return len({d for _, h, d, _ in effective(w, first, last) if h == staff})


def first_night(w: World, staff: str, first: date, last: date) -> str | None:
    """Return the first date with a night shift in a range."""
    days = sorted(d for _, h, d, k in effective(w, first, last) if h == staff and k == "nacht")
    return days[0].isoformat() if days else None


def on_day(w: World, day: date, kind: str) -> int:
    """Count shifts of this type held by a physician on a day (a shift without holder: none)."""
    return sum(1 for _, h, d, k in effective(w, day, day) if h and k == kind)


def weekend_shifts_total(w: World, first: date, last: date) -> int:
    """Count all held shifts on Saturdays and Sundays in a date range."""
    return sum(1 for _, h, d, _ in effective(w, first, last) if h and d.weekday() >= 5)


def burden(w: World, year: int, as_of: date) -> dict[str, dict[str, int]]:
    """Return nights, weekends and holiday duty per physician from 1 January to ``as_of``."""
    out: dict[str, dict[str, int]] = {}
    holidays = {r[0] for r in w.sql("SELECT date FROM organization.holiday")}
    weekends: dict[str, set[int]] = {}
    hol: dict[str, set[date]] = {}
    for _, who, day, kind in effective(w, date(year, 1, 1), as_of):
        if who is None:
            continue
        row = out.setdefault(who, {"nights": 0, "weekends": 0, "holidays": 0})
        if kind == "nacht":
            row["nights"] += 1
        if day.weekday() >= 5:
            weekends.setdefault(who, set()).add(day.toordinal() - day.weekday())
        if day in holidays and kind in WORKING:
            hol.setdefault(who, set()).add(day)
    for who, row in out.items():
        row["weekends"] = len(weekends.get(who, ()))
        row["holidays"] = len(hol.get(who, ()))
    return out


def ledger_people(w: World, day: date) -> set[str]:
    """Return the physicians the fairness ledger counts: a resident or specialist contract valid on
    ``day`` and no rotation to another department that day (independent of the application)."""
    rows = w.sql(
        "SELECT DISTINCT c.staff_id FROM organization.contract c"
        " WHERE c.role IN ('assistenzarzt', 'facharzt') AND c.valid_from <= :d"
        " AND (c.valid_to IS NULL OR c.valid_to >= :d)"
        " AND NOT EXISTS (SELECT 1 FROM organization.staff_rotation r WHERE r.staff_id = c.staff_id"
        " AND r.start_date <= :d AND r.end_date >= :d)",
        d=day,
    )
    return {str(r[0]) for r in rows}


def as_of(w: World) -> Any:
    """Return the ledger's ``as_of`` date as the API states it (a fact of the seed, not a count)."""
    r = w.client.get("/fairness", headers={"Authorization": "Bearer " + w.token("brandt")})
    return date.fromisoformat(r.json()["as_of"])

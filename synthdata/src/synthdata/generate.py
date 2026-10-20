"""Run the whole simulation and return every table as rows, plus the latent truth."""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from synthdata import GENERATOR_VERSION
from synthdata.behaviour import Latent, draw_latents, sickness_wave
from synthdata.calendar import (
    Holiday,
    days,
    month_end,
    month_starts,
    public_holidays,
    school_holiday_periods,
)
from synthdata.config import (
    DEMO_NOW,
    DEPARTMENT_NAME,
    DEPARTMENT_SHORT,
    HISTORY_START,
    LAST_PUBLISHED_MONTH,
    OPEN_WINDOW_MONTH,
    PARAMS,
)
from synthdata.demand import template_for
from synthdata.ids import uid
from synthdata.leave import LeaveRequest, generate_leave
from synthdata.operations import OpsContext, OpsLog, cover_shift, simulate_sickness, simulate_swaps
from synthdata.planner import PlanInput, plan_month
from synthdata.rng import Streams
from synthdata.roster import Schedule
from synthdata.rules import RULE_SETS, rules_for
from synthdata.shifts import SHIFT_TYPES
from synthdata.staff import NEUTRAL_TITLE_DE, TITLE_EN, Person, build_staff
from synthdata.windows import Window, build_window, publish_time

Rows = list[dict[str, object]]
PLANNER_KEY = "brandt"


class DemoRosterInvalidError(RuntimeError):
    """The November 2026 demo roster breaks a hard rule; the generator refuses to output it."""


@dataclass
class Dataset:
    """All visible tables (by context) and the ground truth."""

    tables: dict[str, Rows] = field(default_factory=dict)
    truth: dict[str, Rows] = field(default_factory=dict)


def generate(seed: int) -> Dataset:
    """Build the full dataset for one seed. Deterministic: same seed, same rows."""
    streams = Streams(seed)
    people = build_staff(streams)
    pmap = {p.key: p for p in people}
    latents = draw_latents(streams, people)
    years = range(2021, 2027)
    holiday_rows = [h for y in range(2020, 2028) for h in public_holidays(y)]
    holidays = {h.day for h in holiday_rows}
    last_day = date(2026, 12, 31)
    template = {
        d: template_for(d, holidays) for d in days(HISTORY_START - timedelta(days=7), last_day)
    }
    leave_reqs, leave = generate_leave(streams, people, latents, years)
    waves = {y: sickness_wave(streams.get("wave", y)) for y in range(2020, 2027)}

    ds = Dataset()
    ops = OpsLog()
    effective: Schedule = {}
    sick: dict[str, set[date]] = {}
    absences_open: list[tuple[str, date, date, datetime, object]] = []
    windows: list[Window] = []
    roster_runs: Rows = []
    variants: Rows = []
    approvals: Rows = []
    assignments: Rows = []
    published_v: Rows = []

    for month in month_starts(HISTORY_START, OPEN_WINDOW_MONTH):
        windows.append(build_window(streams, month, people, latents))
        if month > LAST_PUBLISHED_MONTH:
            continue
        rules = rules_for(month)
        published = publish_time(month)
        window = windows[-1]
        blocked: dict[str, set[date]] = {k: set(v) for k, v in leave.items()}
        for k, ws in window.wishes.items():
            for w in ws:
                if w.kind == "unavailable":
                    blocked.setdefault(k, set()).add(w.day)
        for k, a, b, reported, _ in absences_open:
            if reported <= published:
                blocked.setdefault(k, set()).update(days(a, b))
        is_demo = month == LAST_PUBLISHED_MONTH
        attempts = PARAMS.planner_attempts_demo if is_demo else PARAMS.planner_attempts_history
        result = plan_month(
            PlanInput(
                month,
                rules,
                pmap,
                latents,
                holidays,
                leave,
                blocked,
                window.wishes,
                effective,
                template,
            ),
            [streams.get("planner", month.isoformat(), i) for i in range(attempts)],
        )
        if is_demo and (result.gaps or result.person_violations):
            problems = [*result.gaps, *result.person_violations][:10]
            raise DemoRosterInvalidError(f"November 2026 roster breaks hard rules: {problems}")
        for v in [*result.gaps, *result.person_violations]:
            published_v.append(
                {
                    "roster_month": month,
                    "date": v.day,
                    "staff_id": None if v.person is None else pmap[v.person].id,
                    "rule": v.rule,
                    "detail": v.detail,
                }
            )

        run_id, variant_id = uid("roster-run", month), uid("roster-variant", month, "A")
        created = published - timedelta(days=2, hours=4)
        roster_runs.append(
            {
                "id": run_id,
                "roster_month": month,
                "rule_set_version": rules.version,
                "planner_kind": "manual-heuristic",
                "generator_version": GENERATOR_VERSION,
                "created_at": created,
            }
        )
        variants.append(
            {
                "id": variant_id,
                "run_id": run_id,
                "label": "A",
                "status": "published",
                "published_at": published,
            }
        )
        approvals.append(
            {
                "id": uid("approval", variant_id),
                "variant_id": variant_id,
                "approved_by": pmap[PLANNER_KEY].id,
                "approved_at": published - timedelta(minutes=30),
                "kind": "planner",
            }
        )
        ids: dict[tuple[str, date, str], object] = {}
        for k, sp in sorted(result.schedule.items()):
            for d, codes in sorted(sp.items()):
                for c in sorted(codes):
                    aid = uid("assignment", month, k, d, c)
                    ids[(k, d, c)] = aid
                    assignments.append(
                        {
                            "id": aid,
                            "variant_id": variant_id,
                            "staff_id": pmap[k].id,
                            "date": d,
                            "shift_type": c,
                        }
                    )
                    effective.setdefault(k, {}).setdefault(d, set()).add(c)

        if is_demo:
            continue
        # In-month changes, up to the demo date.
        ctx = OpsContext(
            month, rules, pmap, latents, holidays, leave, sick, effective, ids, published, waves
        )
        simulate_swaps(ctx, ops, streams.get("swaps", month.isoformat()))
        cover_rng = streams.get("cover-carry", month.isoformat())
        for k, a, b, reported, absence_id in absences_open:
            for sd in days(max(a, month), min(b, month_end(month))):
                if reported > published:
                    for shift in sorted(effective.get(k, {}).get(sd, set())):
                        cover_shift(ctx, ops, cover_rng, k, sd, shift, reported, absence_id)

        new_absences: list[tuple[str, date, date, datetime, object]] = []

        def on_new(
            k: str,
            a: date,
            b: date,
            reported: datetime,
            absence_id: object,
            sink: list[tuple[str, date, date, datetime, object]] = new_absences,
        ) -> None:
            sick.setdefault(k, set()).update(days(a, b))
            sink.append((k, a, b, reported, absence_id))

        stop = min(month_end(month), DEMO_NOW.date() - timedelta(days=2))
        simulate_sickness(ctx, ops, streams.get("sickness", month.isoformat()), stop, on_new)
        absences_open += [x for x in new_absences if x[2] > month_end(month)]
        absences_open = [x for x in absences_open if x[2] > month_end(month)]

    ds.tables = _organization(people, holiday_rows, template)
    ds.tables.update(_requests(windows, leave_reqs, pmap))
    ds.tables.update(
        {
            "planning/roster_run": roster_runs,
            "planning/roster_variant": variants,
            "planning/approval": approvals,
            "planning/assignment": assignments,
            "operations/absence": ops.absences,
            "operations/swap_offer": ops.swaps,
            "operations/cover_cascade": ops.cascades,
            "operations/cover_offer": ops.offers,
        }
    )
    ds.truth = {
        "staff_latent": _latent_rows(people, latents),
        "sickness_wave": [
            {
                "season_start_year": y,
                "peak_offset_days": w[0],
                "width_days": w[1],
                "amplitude": w[2],
                "autumn_bump": w[3],
            }
            for y, w in sorted(waves.items())
        ],
        "department_sickness_hazard": ops.hazard,
        "published_violations": published_v,
        "in_month_breaches": ops.breaches,
    }
    return ds


def _organization(
    people: list[Person],
    holiday_rows: list[Holiday],
    template: dict[date, list[tuple[str, str, int]]],
) -> dict[str, Rows]:
    dept_id = uid("department", "innere")
    staff: Rows = []
    contracts: Rows = []
    quals: Rows = []
    rotations: Rows = []
    for p in people:
        staff.append({"id": p.id, "department_id": dept_id, "display_name": p.display_name})
        for i, r in enumerate(p.periods):
            contracts.append(
                {
                    "id": uid("contract", p.key, i),
                    "staff_id": p.id,
                    "role": r.role,
                    "title_de": r.title_de or NEUTRAL_TITLE_DE[r.role],
                    "title_en": TITLE_EN[r.role],
                    "weekly_hours": r.weekly_hours,
                    "valid_from": r.start,
                    "valid_to": r.end,
                }
            )
        quals += _qualification_rows(p)
        for a, b, target in p.rotations:
            rotations.append(
                {
                    "id": uid("rotation", p.key, a),
                    "staff_id": p.id,
                    "target": target,
                    "start_date": a,
                    "end_date": b,
                }
            )
    demand: Rows = [
        {"date": d, "shift_type": s, "qualification": q, "required_count": c}
        for d, rows in sorted(template.items())
        if d >= HISTORY_START
        for s, q, c in rows
    ]
    school: Rows = [
        {
            "id": uid("school-holiday", a),
            "start_date": a,
            "end_date": b,
            "name_de": de,
            "name_en": en,
        }
        for y in range(2021, 2028)
        for a, b, de, en in school_holiday_periods(y)
    ]
    return {
        "organization/department": [
            {"id": dept_id, "name": DEPARTMENT_NAME, "short_name": DEPARTMENT_SHORT}
        ],
        "organization/staff": staff,
        "organization/contract": contracts,
        "organization/qualification": [
            {
                "code": "facharzt",
                "name_de": "Facharztstatus Innere Medizin",
                "name_en": "Specialist in internal medicine",
            },
            {
                "code": "nachtdienstfaehig",
                "name_de": "Freigabe für Nacht- und Bereitschaftsdienst",
                "name_en": "Cleared for night and on-call duty",
            },
            {
                "code": "oberarzt",
                "name_de": "Oberarzt-Hintergrund (Rufbereitschaft)",
                "name_en": "Senior back-up (on-call from home)",
            },
        ],
        "organization/staff_qualification": quals,
        "organization/staff_rotation": rotations,
        "organization/shift_type": [
            {
                "code": s.code,
                "letter_de": s.letter_de,
                "letter_en": s.letter_en,
                "name_de": s.name_de,
                "name_en": s.name_en,
                "start_time": s.start,
                "end_time": s.end,
                "ends_next_day": s.ends_next_day,
                "break_minutes": s.break_minutes,
                "net_hours": s.net_hours,
                "kind": s.kind,
                "counts_as_working_time": s.counts_as_working_time,
                "burden_weight": s.burden_weight,
            }
            for s in SHIFT_TYPES.values()
        ],
        "organization/shift_demand": demand,
        "organization/holiday": [
            {"date": h.day, "name_de": h.name_de, "name_en": h.name_en}
            for h in holiday_rows
            if 2021 <= h.day.year <= 2027
        ],
        "organization/school_holiday": school,
        "organization/rule_set": [
            {
                "id": uid("rule-set", r.version),
                "version": r.version,
                "effective_from": r.effective_from,
                "rules": r.as_json(),
                "change_note_de": r.change_note_de,
                "change_note_en": r.change_note_en,
            }
            for r in RULE_SETS
        ],
    }


def _qualification_rows(p: Person) -> Rows:
    """Return validity periods of each qualification, derived from the role history."""
    out: Rows = []
    end = p.end
    first = p.start
    night_from = first if p.periods[0].role != "assistenzarzt" else first + timedelta(days=365)
    if end is None or night_from <= end:
        out.append(
            {
                "staff_id": p.id,
                "qualification": "nachtdienstfaehig",
                "valid_from": night_from,
                "valid_to": end,
            }
        )
    fa = p.first_role_start(("facharzt", "oberarzt", "chefaerztin"))
    if fa is not None:
        out.append(
            {"staff_id": p.id, "qualification": "facharzt", "valid_from": fa, "valid_to": end}
        )
    oa = p.first_role_start(("oberarzt", "chefaerztin"))
    if oa is not None:
        out.append(
            {"staff_id": p.id, "qualification": "oberarzt", "valid_from": oa, "valid_to": end}
        )
    return out


def _requests(
    windows: list[Window], leave_reqs: list[LeaveRequest], pmap: dict[str, Person]
) -> dict[str, Rows]:
    win_rows: Rows = []
    responses: Rows = []
    prefs: Rows = []
    for w in windows:
        win_rows.append(
            {
                "id": w.id,
                "roster_month": w.month,
                "opens_at": w.opens_at,
                "closes_at": w.closes_at,
                "status": w.status,
                "recipient_count": len(w.recipients),
            }
        )
        for k, at in sorted(w.responses.items()):
            responses.append({"window_id": w.id, "staff_id": pmap[k].id, "submitted_at": at})
            for i, wish in enumerate(w.wishes.get(k, [])):
                prefs.append(
                    {
                        "id": uid("preference", w.id, k, i),
                        "window_id": w.id,
                        "staff_id": pmap[k].id,
                        "date": wish.day,
                        "kind": wish.kind,
                        "shift_type": wish.shift,
                        "important": wish.important,
                    }
                )
    leave_rows: Rows = [
        {
            "id": r.id,
            "staff_id": pmap[r.staff_key].id,
            "start_date": r.start,
            "end_date": r.end,
            "submitted_at": r.submitted_at,
            "status": r.status,
            "decided_at": r.decided_at,
            "decided_by": None if r.decided_at is None else pmap[PLANNER_KEY].id,
            "decision_reason_code": r.decision_reason_code,
            "decision_reason": r.decision_reason,
        }
        for r in leave_reqs
    ]
    return {
        "requests/request_window": win_rows,
        "requests/window_response": responses,
        "requests/preference": prefs,
        "requests/leave_request": leave_rows,
    }


def _latent_rows(people: list[Person], latents: dict[str, Latent]) -> Rows:
    rows: Rows = []
    weekdays = ("mo", "di", "mi", "do", "fr", "sa", "so")
    shifts = ("frueh", "spaet", "nacht", "bereitschaft")
    for p in people:
        lat = latents[p.key]
        row: dict[str, object] = {"staff_id": p.id}
        for i, wd in enumerate(weekdays):
            for j, s in enumerate(shifts):
                row[f"pref_{wd}_{s}"] = float(lat.preference[i, j])
        for name in (
            "night_tolerance",
            "weekend_aversion",
            "holiday_period_affinity",
            "cover_willingness",
            "cover_load_decay",
            "swap_propensity",
            "responsiveness",
            "planner_favour",
            "sickness_frailty",
        ):
            row[name] = float(getattr(lat, name))
        rows.append(row)
    return rows

"""Contract tests of the event schemas (ADR-016): files, pins, versions, producers."""

import hashlib
import json
from typing import Any

import jsonschema
import pytest

from dienstpilot import recording
from dienstpilot.shared.events import schemas

U = "0fa0e226-bbae-5a54-b05a-db82a17ca3d0"
EXAMPLES: dict[str, dict[str, Any]] = {
    "PreferencesSubmitted": {"window_id": U, "staff_id": U, "entries": 3},
    "LeaveRequested": {
        "leave_request_id": U,
        "staff_id": U,
        "start_date": "2026-12-01",
        "end_date": "2026-12-05",
    },
    "LeaveDecided": {"leave_request_id": U, "staff_id": U, "decision": "approved"},
    "RosterGenerated": {"run_id": U, "roster_month": "2026-12-01", "status": "done"},
    "RosterPublished": {"variant_id": U},
    "RosterChanged": {"change_id": U},
    "SwapOffered": {"swap_id": U, "staff_id": U},
    "SwapAccepted": {"swap_id": U, "staff_id": U, "escalation_reason": None},
    "SwapAutoApproved": {"swap_id": U},
    "SwapEscalated": {"swap_id": U, "reason": "hours_band"},
    "SwapDecided": {"swap_id": U, "decision": "declined"},
    "SicknessReported": {
        "absence_id": U,
        "staff_id": U,
        "start_date": "2026-10-20",
        "end_date": "2026-10-20",
    },
    "CoverRequested": {"cascade_id": U, "staff_id": U},
    "CoverAccepted": {"cascade_id": U, "staff_id": U},
    "CoverEscalated": {"cascade_id": U, "reason": "list_exhausted"},
    "CoverDecided": {"cascade_id": U, "approval": "policy"},
    "WindowClosed": {"window_id": U},
    "MonthReportPrepared": {"roster_month": "2026-10-01"},
    "MonthClosed": {"roster_month": "2026-10-01"},
}
FORBIDDEN = ("category", "name", "display_name", "diagnos", "reason_text")


def test_every_schema_is_valid_json_schema_and_has_an_example() -> None:
    loaded = schemas.load()
    assert {t for t, _ in loaded} == set(EXAMPLES)
    for (name, version), schema in loaded.items():
        jsonschema.Draft202012Validator.check_schema(schema)
        assert schema["title"] == name and schema["$id"].endswith(f"{name}.v{version}")
        schemas.validate(name, version, EXAMPLES[name])


def test_published_schema_files_never_change() -> None:
    """A change needs a new version (a new file), not an edit: the pins catch edits."""
    pins = json.loads((schemas.DIR / "MANIFEST.json").read_text())
    files = {p.name for p in schemas.DIR.glob("*.v*.json")}
    assert set(pins) == files, "every schema file is pinned in MANIFEST.json, and vice versa"
    for name, digest in pins.items():
        assert hashlib.sha256((schemas.DIR / name).read_bytes()).hexdigest() == digest, (
            f"{name} changed after it was pinned: add a new version instead"
        )


@pytest.mark.parametrize("name", sorted(EXAMPLES))
def test_payloads_must_match_exactly(name: str) -> None:
    ok = EXAMPLES[name]
    with pytest.raises(jsonschema.ValidationError):
        schemas.validate(name, 1, {**ok, "extra": 1})  # no additional properties
    missing = dict(ok)
    missing.pop(next(iter(missing)))
    with pytest.raises(jsonschema.ValidationError):
        schemas.validate(name, 1, missing)


def test_payloads_carry_ids_only_never_names_or_the_absence_category() -> None:
    for name, schema in ((t, s) for (t, _), s in schemas.load().items()):
        for prop in schema["properties"]:
            assert not any(f in prop for f in FORBIDDEN), f"{name}.{prop}"


def test_an_unknown_type_or_version_is_refused() -> None:
    with pytest.raises(schemas.UnknownEventError):
        schemas.validate("Nope", 1, {})
    with pytest.raises(schemas.UnknownEventError):
        schemas.validate("MonthClosed", 2, EXAMPLES["MonthClosed"])


def test_a_new_version_is_consumed_next_to_the_old_one(tmp_path: Any, monkeypatch: Any) -> None:
    """Both versions stay loadable: the registry is keyed by (type, version)."""
    schemas.load.cache_clear()
    extra = json.loads((schemas.DIR / "MonthClosed.v1.json").read_text())
    extra["properties"]["note"] = {"type": "string"}
    (tmp_path / "MonthClosed.v2.json").write_text(json.dumps(extra))
    (tmp_path / "MonthClosed.v1.json").write_text((schemas.DIR / "MonthClosed.v1.json").read_text())
    monkeypatch.setattr(schemas, "DIR", tmp_path)
    schemas.load.cache_clear()
    try:
        assert schemas.latest("MonthClosed") == 2
        schemas.validate("MonthClosed", 1, EXAMPLES["MonthClosed"])
        schemas.validate("MonthClosed", 2, {**EXAMPLES["MonthClosed"], "note": "x"})
    finally:
        monkeypatch.undo()
        schemas.load.cache_clear()


ACTIONS = {
    "preferences.submitted": {"entries": 2},
    "leave.requested": {"start_date": "2026-12-01", "end_date": "2026-12-02"},
    "leave.approved": {},
    "leave.declined": {},
    "roster.published": {},
    "roster.changed": {},
    "swap.offered": {},
    "swap.taken": {"escalation_reason": "rule_violation"},
    "swap.approved": {"approval": "policy"},
    "swap.declined": {},
    "absence.reported": {"start_date": "2026-10-20", "end_date": "2026-10-20", "category": "sick"},
    "cover.search_started": {},
    "cover.accepted": {},
    "cover.decided": {"approval": "policy"},
    "window.closed": {},
    "month.report_prepared": {"roster_month": "2026-10-01"},
    "month.closed": {"roster_month": "2026-10-01"},
}


def test_every_event_a_producer_can_make_has_a_valid_payload() -> None:
    made = set()
    for action, payload in ACTIONS.items():
        for event_type, body in recording._map(action, U, U, payload):
            schemas.validate(event_type, schemas.latest(event_type), body)
            made.add(event_type)
    assert "category" not in json.dumps(
        recording._map("absence.reported", U, U, ACTIONS["absence.reported"])
    )
    # RosterGenerated and CoverEscalated are published directly (jobs, timers, respond route).
    assert made | {"RosterGenerated", "CoverEscalated"} == set(EXAMPLES)

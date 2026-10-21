"""Helpers shared by the routes: department lookups, audit recording, engine labels."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel

from dienstpilot.app.deps import Ctx
from dienstpilot.audit import service as audit
from dienstpilot.organization import service as organization
from dienstpilot.organization.service import StaffMember
from dienstpilot.shared.ports import EngineInfo


class EngineLabel(BaseModel):
    """Which component produced a value, and whether it is a stand-in."""

    component: str
    implementation: str
    version: str
    note: str


def label(info: EngineInfo) -> EngineLabel:
    """Return the label for API responses."""
    return EngineLabel(
        component=info.component,
        implementation=info.implementation,
        version=info.version,
        note=info.note,
    )


@dataclass(frozen=True)
class Department:
    """The signed-in user's department, loaded once per request."""

    id: str
    staff: dict[str, StaffMember]

    def name(self, staff_id: str | None) -> str | None:
        """Return a physician's display name."""
        return (
            None
            if staff_id is None or staff_id not in self.staff
            else self.staff[staff_id].display_name
        )

    def rostered(self, d: date) -> list[StaffMember]:
        """Return the physicians on the department's roster on d."""
        return [s for s in self.staff.values() if s.rostered_on(d)]


def department(ctx: Ctx) -> Department:
    """Return the user's department with its physicians (department scope)."""
    members = organization.staff(ctx.session, ctx.user.department_id)
    return Department(ctx.user.department_id, {s.id: s for s in members})


def in_department(dep: Department, staff_id: str) -> None:
    """Raise 404 unless the physician belongs to the user's department."""
    if staff_id not in dep.staff:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")


def record(
    ctx: Ctx,
    action: str,
    subject_type: str,
    subject_id: str | None = None,
    staff_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Record an audit event for a write by the signed-in user."""
    audit.record(
        ctx.session,
        occurred_at=ctx.clock.now(),
        department_id=ctx.user.department_id,
        actor_user_id=ctx.user.id,
        actor_label=ctx.user.display_name,
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        staff_id=staff_id,
        payload=payload,
    )


def jsonable(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe copy (dates as ISO strings)."""
    return {k: (v.isoformat() if isinstance(v, date) else v) for k, v in payload.items()}

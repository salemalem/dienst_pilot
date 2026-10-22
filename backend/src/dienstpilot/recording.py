"""Record an audit event and publish its domain event in the same transaction.

Every write path calls ``record``: the audit trail (hash chain) and the event outbox get their
rows together, so the log and the event stream can never disagree about what happened. Which
audit action becomes which event, and what the event may carry (ids only), is decided here.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from dienstpilot.audit import service as audit
from dienstpilot.shared.events import outbox

Payload = dict[str, Any]
Mapper = Callable[[str | None, str | None, Payload], tuple[str, Payload] | None]


def _event(name: str, **fields: str | None) -> tuple[str, Payload]:
    return name, fields


def _map(
    action: str, subject: str | None, staff: str | None, p: Payload
) -> list[tuple[str, Payload]]:
    """Return the events an audit action produces (usually one, none for most)."""
    match action:
        case "preferences.submitted":
            return [
                (
                    "PreferencesSubmitted",
                    {"window_id": subject, "staff_id": staff, "entries": int(p.get("entries", 0))},
                )
            ]
        case "leave.requested":
            return [
                (
                    "LeaveRequested",
                    {
                        "leave_request_id": subject,
                        "staff_id": staff,
                        "start_date": p.get("start_date"),
                        "end_date": p.get("end_date"),
                    },
                )
            ]
        case "leave.approved" | "leave.declined":
            return [
                (
                    "LeaveDecided",
                    {
                        "leave_request_id": subject,
                        "staff_id": staff,
                        "decision": action.split(".")[1],
                    },
                )
            ]
        case "roster.published":
            return [("RosterPublished", {"variant_id": subject})]
        case "roster.changed":
            return [("RosterChanged", {"change_id": subject})]
        case "swap.offered":
            return [("SwapOffered", {"swap_id": subject, "staff_id": staff})]
        case "swap.taken":
            out = [
                (
                    "SwapAccepted",
                    {
                        "swap_id": subject,
                        "staff_id": staff,
                        "escalation_reason": p.get("escalation_reason"),
                    },
                )
            ]
            if p.get("escalation_reason"):
                out.append(
                    ("SwapEscalated", {"swap_id": subject, "reason": p["escalation_reason"]})
                )
            return out
        case "swap.approved" | "swap.declined":
            if p.get("approval") == "policy":
                return [("SwapAutoApproved", {"swap_id": subject})]
            return [("SwapDecided", {"swap_id": subject, "decision": action.split(".")[1]})]
        case "absence.reported":
            return [
                (
                    "SicknessReported",
                    {
                        "absence_id": subject,
                        "staff_id": staff,
                        "start_date": p.get("start_date"),
                        "end_date": p.get("end_date"),
                    },
                )
            ]
        case "cover.search_started":
            return [("CoverRequested", {"cascade_id": subject, "staff_id": staff})]
        case "cover.accepted":
            return [("CoverAccepted", {"cascade_id": subject, "staff_id": staff})]
        case "cover.decided":
            return [
                (
                    "CoverDecided",
                    {
                        "cascade_id": subject,
                        "approval": "policy" if p.get("approval") == "policy" else "planner",
                    },
                )
            ]
        case "window.closed":
            return [("WindowClosed", {"window_id": subject})]
        case "month.report_prepared":
            return [("MonthReportPrepared", {"roster_month": p.get("roster_month")})]
        case "month.closed":
            return [("MonthClosed", {"roster_month": p.get("roster_month")})]
    return []


def record(
    session: Session,
    *,
    occurred_at: datetime,
    department_id: str | None,
    actor_user_id: str | None,
    actor_label: str,
    action: str,
    subject_type: str,
    subject_id: str | None = None,
    staff_id: str | None = None,
    payload: Payload | None = None,
) -> str:
    """Append the audit event; publish the domain event it stands for (if it has one)."""
    event_id = audit.record(
        session,
        occurred_at=occurred_at,
        department_id=department_id,
        actor_user_id=actor_user_id,
        actor_label=actor_label,
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        staff_id=staff_id,
        payload=payload,
    )
    for event_type, body in _map(action, subject_id, staff_id, payload or {}):
        outbox.publish(
            session, event_type, body, occurred_at=occurred_at, department_id=department_id
        )
    return event_id

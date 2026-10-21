"""Privacy rules applied in the API layer (CLAUDE.md, privacy rules).

- Only the Planner sees an absence's category; everyone else sees "absent" ("abwesend").
- A person's hours and fairness detail go to themselves, the Planner and (hours only) Oversight.
- No endpoint returns a diagnosis or a requester's leave reason: neither is ever stored.
"""

from typing import Any

from dienstpilot.identity.service import UserView

ABSENT = "absent"  # the UI shows "abwesend" / "absent"


def sees_absence_category(user: UserView) -> bool:
    """Return whether the user may see why someone is absent."""
    return user.role == "planner"


def absence_for(user: UserView, category: str) -> dict[str, Any]:
    """Return how an absence is shown to the user."""
    return (
        {"status": ABSENT, "category": category}
        if sees_absence_category(user)
        else {"status": ABSENT}
    )


def audit_payload_for(user: UserView, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Strip what the user may not see from an audit event's payload."""
    if sees_absence_category(user):
        return payload
    return {k: v for k, v in payload.items() if k != "category"}

"""Public interface of the identity context."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from dienstpilot.identity.models import User, UserSettings
from dienstpilot.identity.personas import PERSONAS

SETTINGS_FIELDS = ("language", "theme", "notifications", "calendar_sync", "preference_suggestions")


@dataclass(frozen=True)
class UserView:
    """A user as other parts of the application see it."""

    id: str
    persona_key: str
    display_name: str
    role: str
    department_id: str
    staff_id: str | None


def _view(u: User) -> UserView:
    return UserView(
        str(u.id),
        u.persona_key,
        u.display_name,
        u.role,
        str(u.department_id),
        None if u.staff_id is None else str(u.staff_id),
    )


def personas(session: Session) -> list[UserView]:
    """Return the demo personas in UI_SPEC order."""
    users = {u.persona_key: u for u in session.scalars(select(User))}
    return [_view(users[p.key]) for p in PERSONAS if p.key in users]


def by_persona(session: Session, key: str) -> UserView | None:
    """Return the user for a persona key."""
    u = session.scalar(select(User).where(User.persona_key == key))
    return None if u is None else _view(u)


def by_id(session: Session, user_id: str) -> UserView | None:
    """Return the user with this id."""
    u = session.get(User, uuid.UUID(user_id))
    return None if u is None else _view(u)


def users_by_staff(session: Session) -> dict[str, UserView]:
    """Return users that are physicians, keyed by staff id."""
    return {
        str(u.staff_id): _view(u)
        for u in session.scalars(select(User).where(User.staff_id.is_not(None)))
    }


def get_settings(session: Session, user_id: str) -> dict[str, object]:
    """Return a user's app settings (defaults if never saved)."""
    s = session.get(UserSettings, uuid.UUID(user_id))
    if s is None:
        s = UserSettings(
            user_id=uuid.UUID(user_id),
            language="de",
            theme="auto",
            notifications=True,
            calendar_sync=False,
            preference_suggestions=True,
        )
    return {f: getattr(s, f) for f in SETTINGS_FIELDS}


def update_settings(
    session: Session, user_id: str, changes: dict[str, object]
) -> dict[str, object]:
    """Save changed settings and return all of them."""
    current = get_settings(session, user_id)
    current.update({k: v for k, v in changes.items() if k in SETTINGS_FIELDS and v is not None})
    session.merge(UserSettings(user_id=uuid.UUID(user_id), **current))
    session.flush()
    return current

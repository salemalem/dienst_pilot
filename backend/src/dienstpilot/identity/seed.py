"""Seed the demo personas (UI_SPEC §1) for a department."""

import uuid

from sqlalchemy import Connection, Table, insert

from dienstpilot.identity import models  # noqa: F401  (registers the tables)
from dienstpilot.identity.models import User
from dienstpilot.identity.personas import PERSONAS
from dienstpilot.shared.db import IdentityBase as Base

TABLES: list[Table] = list(Base.metadata.sorted_tables)


def persona_id(key: str) -> uuid.UUID:
    """Return the stable user id of a persona."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dienstpilot/persona/{key}")


def load_personas(conn: Connection, department_id: str, staff_by_name: dict[str, str]) -> int:
    """Insert the personas; physicians are linked to their staff record by display name."""
    rows = []
    for p in PERSONAS:
        staff_id = staff_by_name.get(p.display_name) if p.is_physician else None
        if p.is_physician and staff_id is None:
            raise ValueError(f"persona {p.key}: no physician named {p.display_name}")
        rows.append(
            {
                "id": persona_id(p.key),
                "persona_key": p.key,
                "display_name": p.display_name,
                "role": p.role,
                "department_id": uuid.UUID(department_id),
                "staff_id": None if staff_id is None else uuid.UUID(staff_id),
            }
        )
    conn.execute(insert(User), rows)
    return len(rows)

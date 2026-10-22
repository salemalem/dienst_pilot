"""Alembic environment. The database URL comes from application settings."""

from alembic import context
from sqlalchemy import MetaData, create_engine, pool

from dienstpilot.audit import models as _audit  # noqa: F401
from dienstpilot.fairness import models as _fairness  # noqa: F401
from dienstpilot.identity import models as _identity  # noqa: F401
from dienstpilot.notifications import models as _notifications  # noqa: F401
from dienstpilot.operations import models as _operations  # noqa: F401
from dienstpilot.organization import models as _organization  # noqa: F401
from dienstpilot.planning import models as _planning  # noqa: F401
from dienstpilot.requests import models as _requests  # noqa: F401
from dienstpilot.shared.db import (
    AuditBase,
    EventsBase,
    FairnessBase,
    IdentityBase,
    NotificationsBase,
    OperationsBase,
    OrganizationBase,
    PlanningBase,
    RequestsBase,
    WorkflowBase,
)
from dienstpilot.shared.events import models as _events  # noqa: F401
from dienstpilot.shared.settings import get_settings
from dienstpilot.shared.workflows import models as _workflows  # noqa: F401

# One schema per bounded context.
TARGET: list[MetaData] = [
    b.metadata
    for b in (
        OrganizationBase,
        RequestsBase,
        PlanningBase,
        OperationsBase,
        IdentityBase,
        AuditBase,
        EventsBase,
        FairnessBase,
        WorkflowBase,
        NotificationsBase,
    )
]
SCHEMAS = {m.schema for m in TARGET}


def include_name(name: str | None, type_: str, parent_names: object) -> bool:
    if type_ == "schema":
        return name in SCHEMAS
    return True


def run_migrations_offline() -> None:
    context.configure(url=get_settings().database_url, literal_binds=True, target_metadata=TARGET)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(get_settings().database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=TARGET,
            include_schemas=True,
            include_name=include_name,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

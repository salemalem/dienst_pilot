"""Alembic environment. The database URL comes from application settings."""

from alembic import context
from sqlalchemy import MetaData, create_engine, pool

from dienstpilot.operations import models as _operations  # noqa: F401
from dienstpilot.organization import models as _organization  # noqa: F401
from dienstpilot.planning import models as _planning  # noqa: F401
from dienstpilot.requests import models as _requests  # noqa: F401
from dienstpilot.shared.db import OperationsBase, OrganizationBase, PlanningBase, RequestsBase
from dienstpilot.shared.settings import get_settings

# One schema per bounded context.
TARGET: list[MetaData] = [
    b.metadata for b in (OrganizationBase, RequestsBase, PlanningBase, OperationsBase)
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

"""Database helpers shared by all contexts: one declarative base per context, one schema each."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def context_metadata(schema: str) -> MetaData:
    """Return metadata whose tables live in the context's own Postgres schema."""
    return MetaData(schema=schema, naming_convention=NAMING)


class OrganizationBase(DeclarativeBase):
    """Base for the organization context."""

    metadata = context_metadata("organization")


class RequestsBase(DeclarativeBase):
    """Base for the requests context."""

    metadata = context_metadata("requests")


class PlanningBase(DeclarativeBase):
    """Base for the planning context."""

    metadata = context_metadata("planning")


class OperationsBase(DeclarativeBase):
    """Base for the operations context."""

    metadata = context_metadata("operations")


class IdentityBase(DeclarativeBase):
    """Base for the identity context."""

    metadata = context_metadata("identity")


class AuditBase(DeclarativeBase):
    """Base for the audit context."""

    metadata = context_metadata("audit")

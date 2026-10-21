"""Database engine and sessions (one engine per process)."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from dienstpilot.shared.settings import get_settings


@lru_cache
def get_engine() -> Engine:
    """Return the process-wide engine."""
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def get_session() -> Iterator[Session]:
    """Yield a session that commits on success and rolls back on error."""
    factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    with factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

"""The arq worker: runs solver runs and leave checks outside the API process.

Start with ``arq dienstpilot.worker.WorkerSettings`` (the ``worker`` service in the compose file).
"""

import asyncio
from typing import Any, ClassVar

from arq.connections import RedisSettings
from sqlalchemy.orm import Session, sessionmaker

from dienstpilot.app.jobs import JOBS
from dienstpilot.app.queue import QUEUE_NAME
from dienstpilot.engines.registry import default_engines
from dienstpilot.shared.clock import RedisClock
from dienstpilot.shared.database import get_engine
from dienstpilot.shared.settings import get_settings


def _run(name: str, kwargs: dict[str, str]) -> None:
    import redis

    settings = get_settings()
    clock = RedisClock(redis.Redis.from_url(settings.redis_url), settings.demo_now)
    factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    session: Session
    with factory() as session:
        JOBS[name](session, ENGINES, clock, **kwargs)


ENGINES = default_engines()


async def run_roster(ctx: dict[str, Any], run_id: str, department_id: str) -> None:
    """Solve a month (C1) and store the C2-checked variants."""
    await asyncio.to_thread(_run, "run_roster", {"run_id": run_id, "department_id": department_id})


async def check_leave(ctx: dict[str, Any], check_id: str, department_id: str) -> None:
    """M5: check whether a leave is coverable and whether it needs a trade-off."""
    await asyncio.to_thread(
        _run, "check_leave", {"check_id": check_id, "department_id": department_id}
    )


class WorkerSettings:
    """arq settings."""

    functions: ClassVar[list[Any]] = [run_roster, check_leave]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    queue_name = QUEUE_NAME
    job_timeout = 900
    max_jobs = 2

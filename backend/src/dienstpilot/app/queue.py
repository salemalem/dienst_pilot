"""The job queue: arq on Redis in the running system, an inline runner in tests.

A route commits its transaction before it enqueues, so the worker always finds the row.
"""

import asyncio
from functools import lru_cache
from typing import Annotated, Protocol

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import Depends

from dienstpilot.shared.settings import get_settings

QUEUE_NAME = "dienstpilot:jobs"


class JobQueue(Protocol):
    """Puts a job on the queue."""

    def enqueue(self, job: str, **kwargs: str) -> None:
        """Queue ``job`` (a name in ``app.jobs.JOBS``) with string arguments, in order."""


class ArqQueue:
    """Enqueues on Redis for the arq worker (``dienstpilot.worker``)."""

    def __init__(self, redis_url: str, queue_name: str = QUEUE_NAME) -> None:
        """Remember where Redis is."""
        self._settings = RedisSettings.from_dsn(redis_url)
        self._queue = queue_name

    def enqueue(self, job: str, **kwargs: str) -> None:
        """Queue a job; the job id makes a re-sent request idempotent."""

        async def put() -> None:
            pool = await create_pool(self._settings, default_queue_name=self._queue)
            try:
                # a bearer token travels as an argument but is never part of the job id
                ident = [v for k, v in kwargs.items() if k != "token"]
                job_id = f"{job}:{':'.join(ident)}"
                await pool.enqueue_job(job, *kwargs.values(), _job_id=job_id)
            finally:
                await pool.aclose()

        asyncio.run(put())


@lru_cache
def get_queue() -> JobQueue:
    """Return the queue (overridden in tests)."""
    return ArqQueue(get_settings().redis_url)


QueueDep = Annotated[JobQueue, Depends(get_queue)]

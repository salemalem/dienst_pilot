"""The arq worker: solver runs, leave checks, due timers and the event pipeline.

Start with ``arq dienstpilot.worker.WorkerSettings`` (the ``worker`` service in the compose file).

Besides jobs, a one-second tick (a) fires every timer that is due on the demo clock, (b) relays
the outbox to the Redis stream, (c) lets each consumer handle what is waiting for it. All state
is in Postgres; the tick only wakes things up, so a restart loses nothing (ADR-016, ADR-017).
"""

import asyncio
import logging
from typing import Any, ClassVar

import redis
from arq import cron
from arq.connections import RedisSettings
from sqlalchemy.orm import Session, sessionmaker

from dienstpilot.app.jobs import JOBS
from dienstpilot.app.queue import QUEUE_NAME
from dienstpilot.engines.registry import default_engines
from dienstpilot.planning import service as planning
from dienstpilot.shared.clock import RedisClock
from dienstpilot.shared.database import get_engine
from dienstpilot.shared.events.consumer import consume
from dienstpilot.shared.events.relay import relay
from dienstpilot.shared.events.stream import RedisStream
from dienstpilot.shared.settings import get_settings
from dienstpilot.workflows.handlers import CONSUMERS
from dienstpilot.workflows.runtime import settle

log = logging.getLogger(__name__)
ENGINES = default_engines()


def _clock() -> RedisClock:
    settings = get_settings()
    return RedisClock(redis.Redis.from_url(settings.redis_url), settings.demo_now)


def _factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def _run(name: str, kwargs: dict[str, str]) -> None:
    with _factory()() as session:
        JOBS[name](session, ENGINES, _clock(), **kwargs)


def _fail_run(run_id: str, error: str) -> None:
    """Mark a run the job timeout cut off as failed (the thread may still be running)."""
    with _factory()() as session:
        r = planning.run(session, run_id)
        if r is not None and r.status in ("queued", "running"):
            planning.set_run_status(session, run_id, "failed", now=_clock().now(), error=error)
            session.commit()


async def run_roster(ctx: dict[str, Any], run_id: str, department_id: str) -> None:
    """Solve a month (C1) and store the C2-checked variants."""
    try:
        await asyncio.to_thread(
            _run, "run_roster", {"run_id": run_id, "department_id": department_id}
        )
    except asyncio.CancelledError:  # arq's job timeout
        await asyncio.to_thread(_fail_run, run_id, planning.JOB_TIMEOUT)
        raise


async def check_leave(ctx: dict[str, Any], check_id: str, department_id: str) -> None:
    """M5: check whether a leave is coverable and whether it needs a trade-off."""
    await asyncio.to_thread(
        _run, "check_leave", {"check_id": check_id, "department_id": department_id}
    )


async def run_copilot(ctx: dict[str, Any], run_id: str, role: str, token: str) -> None:
    """C8: answer a planner's question with the agent (tools through MCP, as that user)."""
    await asyncio.to_thread(_run, "run_copilot", {"run_id": run_id, "role": role, "token": token})


def _tick() -> None:
    clock = _clock()
    factory = _factory()
    stream = RedisStream(redis.Redis.from_url(get_settings().redis_url))
    for step in ("timers", "relay", "consumers"):
        try:
            with factory() as session:
                if step == "timers":
                    settle(session, clock, ENGINES)
                elif step == "relay":
                    relay(session, stream, clock.now())
                else:
                    for consumer in CONSUMERS:
                        consume(session, stream, consumer, clock.now())
                session.commit()
        except Exception:
            log.exception("worker tick: %s failed", step)


async def tick(ctx: dict[str, Any]) -> None:
    """Fire due timers, relay events, run consumers."""
    await asyncio.to_thread(_tick)


def _recover(live_runs: set[str]) -> list[str]:
    with _factory()() as session:
        failed = planning.fail_interrupted(session, _clock().now(), keep=live_runs)
        session.commit()
        return failed


async def startup(ctx: dict[str, Any]) -> None:
    """Mark runs a dead worker left in ``queued`` or ``running`` as failed (no job is waiting)."""
    queued = await ctx["redis"].zrange(QUEUE_NAME, 0, -1)
    live = set()
    for raw in queued:
        parts = (raw.decode() if isinstance(raw, bytes) else str(raw)).split(":")
        if parts[0] == "run_roster" and len(parts) > 1:
            live.add(parts[1])
    failed = await asyncio.to_thread(_recover, live)
    if failed:
        log.warning("marked %d interrupted roster runs as failed: %s", len(failed), failed)


class WorkerSettings:
    """arq settings."""

    functions: ClassVar[list[Any]] = [run_roster, check_leave, run_copilot]
    cron_jobs: ClassVar[list[Any]] = [
        cron(tick, second=set(range(60)), run_at_startup=True, unique=True, timeout=30)
    ]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    queue_name = QUEUE_NAME
    job_timeout = 900  # arq cancels a job after this long; run_roster then marks its run failed
    max_jobs = 2

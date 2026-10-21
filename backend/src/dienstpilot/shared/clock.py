"""The demo clock. Every "today", deadline and countdown comes from here, never the system time.

The default is the demo moment from settings. In DEMO_MODE an Administrator can move the clock;
the setting lives in Redis so it survives API reloads.
"""

from datetime import datetime

import redis

from dienstpilot.shared.ports import Clock
from dienstpilot.shared.settings import TZ

REDIS_KEY = "dienstpilot:demo:clock"


class FixedClock(Clock):
    """A clock that always shows the same instant (tests, and the default demo moment)."""

    def __init__(self, now: datetime) -> None:
        """Create a clock fixed at ``now`` (must be timezone-aware)."""
        if now.tzinfo is None:
            raise ValueError("the clock needs a timezone-aware datetime")
        self._now = now

    def now(self) -> datetime:
        """Return the fixed instant in Europe/Berlin."""
        return self._now.astimezone(TZ)


class RedisClock(Clock):
    """The demo clock: an Administrator's setting from Redis, else the default demo moment."""

    def __init__(self, client: redis.Redis, default: datetime) -> None:
        """Read overrides from ``client``; fall back to ``default``."""
        self._client = client
        self._default = default

    def now(self) -> datetime:
        """Return the current demo instant in Europe/Berlin."""
        raw = self._client.get(REDIS_KEY)
        text = raw.decode() if isinstance(raw, bytes) else raw
        value = datetime.fromisoformat(text) if text else self._default
        return value.astimezone(TZ)

    def set(self, value: datetime) -> None:
        """Move the demo clock (timezone-aware)."""
        if value.tzinfo is None:
            raise ValueError("the clock needs a timezone-aware datetime")
        self._client.set(REDIS_KEY, value.isoformat())

    def reset(self) -> None:
        """Return to the default demo moment."""
        self._client.delete(REDIS_KEY)

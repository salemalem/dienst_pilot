"""The stream port: Redis Streams in the running system, an in-memory stand-in in unit tests."""

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Protocol

STREAM = "dienstpilot:events"


@dataclass(frozen=True)
class Message:
    """One delivered stream entry."""

    id: str
    fields: dict[str, str]


class EventStream(Protocol):
    """What the relay and the consumers need from a stream."""

    def add(self, fields: dict[str, str]) -> str:
        """Append an entry; return its stream id."""

    def read(self, group: str, consumer: str, count: int) -> list[Message]:
        """Return entries not yet delivered to the group, plus its unacknowledged ones."""

    def ack(self, group: str, message_id: str) -> None:
        """Mark an entry as handled by the group."""


class RedisStream:
    """Redis Streams with one consumer group per consumer."""

    def __init__(self, client: Any, name: str = STREAM) -> None:
        """Wrap a redis-py client."""
        self._r, self._name = client, name
        self._groups: set[str] = set()

    def add(self, fields: dict[str, str]) -> str:
        """XADD."""
        return str(self._r.xadd(self._name, fields).decode())

    def _group(self, group: str) -> None:
        if group in self._groups:
            return
        try:
            self._r.xgroup_create(self._name, group, id="0", mkstream=True)
        except Exception as e:  # BUSYGROUP: it exists already
            if "BUSYGROUP" not in str(e):
                raise
        self._groups.add(group)

    def read(self, group: str, consumer: str, count: int) -> list[Message]:
        """XREADGROUP: own pending entries first (a crash before XACK), then new ones."""
        self._group(group)
        out: list[Message] = []
        for start in ("0", ">"):
            res = self._r.xreadgroup(group, consumer, {self._name: start}, count=count)
            for _, entries in res:
                out += [
                    Message(
                        i.decode(),
                        {k.decode(): v.decode() for k, v in f.items()},
                    )
                    for i, f in entries
                ]
            if out:
                break
        return out

    def ack(self, group: str, message_id: str) -> None:
        """XACK."""
        self._r.xack(self._name, group, message_id)


class MemoryStream:
    """An in-memory stream with the same delivery rules (tests)."""

    def __init__(self) -> None:
        """Start empty."""
        self.entries: list[Message] = []
        self._next: dict[str, int] = defaultdict(int)
        self._pending: dict[str, dict[str, Message]] = defaultdict(dict)

    def add(self, fields: dict[str, str]) -> str:
        """Append."""
        mid = f"{len(self.entries) + 1}-0"
        self.entries.append(Message(mid, dict(fields)))
        return mid

    def read(self, group: str, consumer: str, count: int) -> list[Message]:
        """Pending first, then undelivered."""
        if self._pending[group]:
            return list(self._pending[group].values())[:count]
        i = self._next[group]
        batch = self.entries[i : i + count]
        self._next[group] = i + len(batch)
        for m in batch:
            self._pending[group][m.id] = m
        return batch

    def ack(self, group: str, message_id: str) -> None:
        """Forget the pending entry."""
        self._pending[group].pop(message_id, None)


def encode(
    event_id: str,
    event_type: str,
    version: int,
    department_id: str | None,
    occurred_at: str,
    payload: dict[str, Any],
) -> dict[str, str]:
    """Return the fields of a stream entry (all strings)."""
    return {
        "event_id": event_id,
        "event_type": event_type,
        "version": str(version),
        "department_id": department_id or "",
        "occurred_at": occurred_at,
        "payload": json.dumps(payload, sort_keys=True, separators=(",", ":")),
    }

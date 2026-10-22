r"""The hash chain of the audit trail (ARCHITECTURE §8, ADR-016).

Every event stores ``hash = sha256(prev_hash ‖ canonical_json(event))`` where ``‖`` is the
concatenation of the previous hash as 64 lower-case hex characters and the UTF-8 bytes of the
canonical JSON. Events are ordered by ``seq`` (1, 2, 3 ... without gaps) inside one *chain*:
one chain per department plus one ``system`` chain for events that belong to no department. The
first event of a chain has the previous hash ``GENESIS``.

Canonical JSON (format version 1): the keys listed in ``canonical`` below, sorted, no
whitespace, UTF-8 without ``\\u`` escapes, timestamps as UTC with microseconds and a trailing
``Z``, ids as lower-case UUID strings. ``hash`` and ``prev_hash`` are not part of it. The
format is frozen: migration 0007 carries its own copy, and a test checks that the two agree.
"""

import hashlib
import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

SYSTEM_CHAIN = "system"
GENESIS = "0" * 64
FORMAT_VERSION = 1


def chain_key(department_id: str | uuid.UUID | None) -> str:
    """Return the chain an event belongs to."""
    return SYSTEM_CHAIN if department_id is None else str(department_id)


def _id(value: str | uuid.UUID | None) -> str | None:
    return None if value is None else str(value).lower()


def normalise_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return the payload as JSON stores it (what a read from the database gives back)."""
    out: dict[str, Any] = json.loads(json.dumps(payload or {}, default=str))
    return out


def canonical(
    *,
    chain: str,
    seq: int,
    event_id: str | uuid.UUID,
    occurred_at: datetime,
    department_id: str | uuid.UUID | None,
    actor_user_id: str | uuid.UUID | None,
    actor_label: str,
    action: str,
    subject_type: str,
    subject_id: str | uuid.UUID | None,
    staff_id: str | uuid.UUID | None,
    payload: Mapping[str, Any],
) -> bytes:
    """Return the canonical JSON of an event as bytes."""
    doc = {
        "v": FORMAT_VERSION,
        "chain": chain,
        "seq": seq,
        "id": _id(event_id),
        "at": occurred_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "department_id": _id(department_id),
        "actor_user_id": _id(actor_user_id),
        "actor": actor_label,
        "action": action,
        "subject_type": subject_type,
        "subject_id": _id(subject_id),
        "staff_id": _id(staff_id),
        "payload": dict(payload),
    }
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def link(prev_hash: str, canonical_json: bytes) -> str:
    """Return ``sha256(prev_hash ‖ canonical_json)`` as hex."""
    return hashlib.sha256(prev_hash.encode("ascii") + canonical_json).hexdigest()

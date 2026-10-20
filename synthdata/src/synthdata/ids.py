"""Deterministic identifiers: UUIDv5 from stable keys, never random."""

import uuid

NAMESPACE = uuid.UUID("6b1f3c2e-8d4a-5e7b-9c10-d1e570110710")


def uid(*parts: object) -> uuid.UUID:
    """Return the UUIDv5 for a key such as ``uid("staff", "kaya")``."""
    return uuid.uuid5(NAMESPACE, "/".join(str(p) for p in parts))

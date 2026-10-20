"""Named random streams.

Each part of the simulation draws from its own stream, so changing one part never shifts the
numbers another part sees.
"""

import hashlib

import numpy as np


class Streams:
    """Factory for independent, reproducible random generators keyed by name."""

    def __init__(self, seed: int) -> None:
        """Create a factory for the given master seed."""
        self.seed = seed

    def get(self, *key: str | int) -> np.random.Generator:
        """Return a fresh generator for the stream named by ``key``."""
        digest = hashlib.sha256("/".join(str(k) for k in key).encode()).digest()
        words = [int.from_bytes(digest[i : i + 4], "little") for i in range(0, 16, 4)]
        return np.random.Generator(np.random.PCG64(np.random.SeedSequence([self.seed, *words])))

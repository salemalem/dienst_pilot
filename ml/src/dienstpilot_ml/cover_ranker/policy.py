"""The cover ordering policy, separate from the model (ARCHITECTURE C5, PROMOTION_RULE.md).

Candidates come from the validator (C2). They are bucketed by cover burden, least burdened first;
P(accept) orders people only within a bucket. A model can never move a person across a bucket.
"""

from collections.abc import Callable
from dataclasses import dataclass

BUCKET_WIDTH = 2  # covers in the last 90 days: 0-1, 2-3, 4-5, ...
P_DECIMALS = 4  # probabilities equal to this many decimals are tied


@dataclass(frozen=True)
class Ranked:
    """A candidate with what the policy uses."""

    staff_id: str
    covers_last_90_days: int
    hours_ratio: float
    p_accept: float


def bucket(covers_last_90_days: int, width: int = BUCKET_WIDTH) -> int:
    """Return the burden bucket of a cover count (0 is the least burdened)."""
    return covers_last_90_days // width


def order(candidates: list[Ranked], width: int = BUCKET_WIDTH) -> list[Ranked]:
    """Return the candidates in asking order: bucket, then P(accept) high to low, then ties."""
    return sorted(
        candidates,
        key=lambda c: (
            bucket(c.covers_last_90_days, width),
            -round(c.p_accept, P_DECIMALS),
            c.hours_ratio,
            c.staff_id,
        ),
    )


Policy = Callable[[list[Ranked]], list[Ranked]]

"""The state machines of the four workflows (ARCHITECTURE §9.1), as data.

A transition not listed here is refused, so a workflow can never skip a state.
"""

from dataclasses import dataclass

SICK_CASCADE = "sick_cascade"
SWAP_APPROVAL = "swap_approval"
REQUEST_WINDOW = "request_window"
MONTH_END = "month_end"


@dataclass(frozen=True)
class Machine:
    """States and the transitions allowed between them."""

    kind: str
    initial: str
    transitions: dict[str, frozenset[str]]

    def allows(self, current: str, to: str) -> bool:
        """Tell whether ``current`` may move to ``to``."""
        return to in self.transitions.get(current, frozenset())


def _m(kind: str, initial: str, **t: set[str]) -> Machine:
    return Machine(kind, initial, {k: frozenset(v) for k, v in t.items()})


MACHINES: dict[str, Machine] = {
    m.kind: m
    for m in (
        _m(
            SICK_CASCADE,
            "finding_candidates",
            finding_candidates={"asking", "escalated"},
            asking={"asking", "filled", "escalated"},
            escalated={"filled", "unfilled"},
        ),
        _m(
            SWAP_APPROVAL,
            "offered",
            offered={"auto_approved", "escalated"},
            escalated={"approved", "declined"},
        ),
        _m(
            REQUEST_WINDOW,
            "open",
            open={"reminded_7d", "reminded_2d", "closed"},
            reminded_7d={"reminded_2d", "closed"},
            reminded_2d={"closed"},
        ),
        _m(MONTH_END, "waiting", waiting={"prepared"}, prepared={"prepared", "closed"}),
    )
}

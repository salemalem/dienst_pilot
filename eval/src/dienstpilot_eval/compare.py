"""Reduce the validator's and the Phase 2 checker's findings to comparable keys."""

from collections import Counter
from datetime import date
from typing import Any

from dienstpilot_validator import Violation

Key = tuple[str, str | None, date, str]


def from_validator(vs: list[Violation]) -> Counter[Key]:
    out: Counter[Key] = Counter()
    for v in vs:
        extra = ""
        if v.rule == "coverage":
            extra = f"{v.params['shift']}/{v.params['qualification']}"
        elif v.rule == "qualification":
            extra = str(v.params["shift"])
        out[(v.rule, v.staff_id, v.day, extra)] += 1
    return out


def from_checker(problems: list[Any]) -> Counter[Key]:
    out: Counter[Key] = Counter()
    for p in problems:
        extra = p.detail if p.rule in ("coverage", "qualification") else ""
        out[(p.rule, p.staff, p.day, extra)] += 1
    return out

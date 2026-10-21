"""C2: the rule and compliance validator (ARCHITECTURE §9).

A pure function of a month's inputs: it reads the declarative rules, shift times and
qualifications it is given and returns every violation as an i18n key with parameters and a
suggested fix. It is implemented independently of the solver (C1) and imports nothing from it.
"""

from dienstpilot_validator.model import Assignment, MonthInput, Person, ShiftType, Violation
from dienstpilot_validator.validate import VERSION, RULE_KEYS, validate, validate_change

__all__ = ["RULE_KEYS", "VERSION", "Assignment", "MonthInput", "Person", "ShiftType", "Violation", "validate",
           "validate_change"]

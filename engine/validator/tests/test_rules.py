from datetime import date, timedelta

from dienstpilot_validator import validate, validate_change
from dienstpilot_validator.model import Assignment

from validator_builder import RULES, month_input, person, rules

NOV = date(2026, 11, 1)


def test_a_clean_week_has_no_violation() -> None:
    days = [NOV + timedelta(days=i) for i in range(1, 6)]  # Mon 2 – Fri 6 November
    shifts = [("a", d, "frueh") for d in days] + [("b", d, "spaet") for d in days]
    v = validate(month_input(NOV, shifts, rules={**RULES, "contract_hours_band_min_days": 99}))
    assert v == []


def test_rest_period_late_then_early() -> None:
    v = validate(month_input(NOV, [("a", date(2026, 11, 2), "spaet"), ("a", date(2026, 11, 3), "frueh")]))
    rest = [x for x in v if x.rule == "min_rest"]
    assert rest and rest[0].params["hours"] == 9.5 and rest[0].fix_key == "fix.min_rest"


def test_rest_period_is_measured_in_real_time_across_dst() -> None:
    # 25 Oct 2026: clocks go back. A night 24→25 Oct lasts 11.5 h; the early shift 25 Oct at
    # 19:00 local would be 11 h after 08:00 only on the wall clock.
    late = month_input(date(2026, 10, 1), [("a", date(2026, 10, 24), "nacht"), ("a", date(2026, 10, 25), "nacht")])
    assert "min_rest" not in rules(validate(late))


def test_rest_continues_across_the_month_boundary() -> None:
    v = validate(month_input(NOV, [("a", date(2026, 10, 31), "spaet"), ("a", NOV, "frueh")]))
    assert any(x.rule == "min_rest" and x.day == NOV for x in v)


def test_one_shift_per_day_and_ruf_with_early_is_allowed() -> None:
    assert "one_shift_per_day" in rules(validate(month_input(NOV, [("a", NOV, "frueh"), ("a", NOV, "spaet")])))
    assert "one_shift_per_day" not in rules(validate(month_input(NOV, [("s", NOV, "frueh"), ("s", NOV, "ruf")])))
    assert "one_shift_per_day" in rules(validate(month_input(NOV, [("s", date(2026, 11, 2), "spaet"),
                                                                  ("s", date(2026, 11, 2), "ruf")])))


def test_consecutive_nights_follow_the_rule_set() -> None:
    four = [("a", NOV + timedelta(days=i), "nacht") for i in range(4)]
    v = validate(month_input(NOV, four))
    nights = [x for x in v if x.rule == "max_consecutive_nights"]
    assert len(nights) == 1 and nights[0].params == {"nights": 4, "max": 3, "date": "2026-11-04"}
    assert "max_consecutive_nights" not in rules(validate(month_input(NOV, four, rules={**RULES,
                                                                                         "max_consecutive_nights": 4})))


def test_weekend_on_call_and_ruf_limits() -> None:
    sats = [date(2026, 11, 7), date(2026, 11, 14), date(2026, 11, 21)]
    assert "max_weekends" in rules(validate(month_input(NOV, [("a", d, "frueh") for d in sats])))
    b = [("a", date(2026, 11, d), "bereitschaft") for d in (1, 7, 14, 21, 28)]
    assert "max_on_call" in rules(validate(month_input(NOV, b)))
    r = [("s", date(2026, 11, d), "ruf") for d in range(1, 12)]
    assert "max_on_call_home" in rules(validate(month_input(NOV, r)))


def test_free_day_after_on_call() -> None:
    v = validate(month_input(NOV, [("a", date(2026, 11, 7), "bereitschaft"), ("a", date(2026, 11, 8), "nacht")]))
    assert "free_day_after_on_call" in rules(v)


def test_hours_band_with_min_days() -> None:
    few = validate(month_input(NOV, [("a", date(2026, 11, 2), "frueh")]))
    assert any(x.rule == "contract_hours_band" and x.staff_id == "a" for x in few)
    short = validate(month_input(NOV, [], people={"a": person("a", rotations=((date(2026, 11, 4), date(2026, 11, 30)),))}))
    assert "contract_hours_band" not in rules(short)  # only 3 rostered workdays: the band does not apply


def test_qualification_role_leave_unavailable_and_not_rostered() -> None:
    people = {"new": person("new", quals=()), "s": person("s", "oberarzt", quals=("oberarzt",)),
              "rot": person("rot", rotations=((NOV, date(2026, 11, 30)),))}
    d = date(2026, 11, 3)
    v = validate(month_input(NOV, [("new", d, "nacht"), ("s", d, "spaet"), ("rot", d, "frueh")], people=people,
                             leave={"s": frozenset({d})}))
    found = {(x.rule, x.staff_id) for x in v}
    assert ("qualification", "new") in found
    assert ("role", "s") in found
    assert ("unavailable", "s") in found
    assert ("not_rostered", "rot") in found
    blocked = validate(month_input(NOV, [("a", d, "frueh")], blocked={"a": frozenset({d})}))
    assert any(x.rule == "unavailable" and x.params["reason"] == "unavailable" for x in blocked)


def test_coverage_counts_qualifications() -> None:
    d = date(2026, 11, 7)
    demand = {d: [("bereitschaft", "any", 2), ("bereitschaft", "facharzt", 1)]}
    v = validate(month_input(NOV, [("a", d, "bereitschaft"), ("b", d, "bereitschaft")], demand=demand))
    cov = [x for x in v if x.rule == "coverage"]
    assert len(cov) == 1 and cov[0].params["qualification"] == "facharzt" and cov[0].params["assigned"] == 0


def test_validate_change_reports_only_what_the_change_introduces() -> None:
    base = month_input(NOV, [("a", date(2026, 11, 2), "spaet")])
    after, new = validate_change(base, add=[Assignment("a", date(2026, 11, 3), "frueh")])
    assert {x.rule for x in new} >= {"min_rest"}
    _, none = validate_change(base, add=[Assignment("b", date(2026, 11, 3), "frueh")])
    assert not any(x.rule == "min_rest" for x in none)
    assert after

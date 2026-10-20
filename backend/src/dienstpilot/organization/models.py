"""Organization and rules: departments, staff, contracts, qualifications, shift types, rules."""

import uuid
from datetime import date, time
from typing import Any

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, String, Time
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from dienstpilot.shared.db import OrganizationBase as Base

ROLES = "('chefaerztin','oberarzt','facharzt','assistenzarzt')"


class Department(Base):
    """A hospital department."""

    __tablename__ = "department"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    short_name: Mapped[str] = mapped_column(String(80))


class Staff(Base):
    """A physician. Display name only; no protected attributes are stored."""

    __tablename__ = "staff"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    department_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("department.id"))
    display_name: Mapped[str] = mapped_column(String(200))


class Contract(Base):
    """A contract period: role, weekly hours and the display title for that period."""

    __tablename__ = "contract"
    __table_args__ = (CheckConstraint(f"role IN {ROLES}", name="role"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    staff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("staff.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    title_de: Mapped[str] = mapped_column(String(80))
    title_en: Mapped[str] = mapped_column(String(80))
    weekly_hours: Mapped[float] = mapped_column(Numeric(4, 1))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)


class Qualification(Base):
    """A qualification a shift can require."""

    __tablename__ = "qualification"
    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    name_de: Mapped[str] = mapped_column(String(120))
    name_en: Mapped[str] = mapped_column(String(120))


class StaffQualification(Base):
    """A qualification held by a physician over a validity period."""

    __tablename__ = "staff_qualification"
    staff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("staff.id"), primary_key=True)
    qualification: Mapped[str] = mapped_column(ForeignKey("qualification.code"), primary_key=True)
    valid_from: Mapped[date] = mapped_column(Date, primary_key=True)
    valid_to: Mapped[date | None] = mapped_column(Date)


class StaffRotation(Base):
    """An external rotation: employed, but not on the department's roster."""

    __tablename__ = "staff_rotation"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    staff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("staff.id"), index=True)
    target: Mapped[str] = mapped_column(String(80))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)


class ShiftType(Base):
    """A shift type with clock times, break, net hours and burden weight (UI_SPEC §5)."""

    __tablename__ = "shift_type"
    __table_args__ = (
        CheckConstraint("kind IN ('work','on_call','on_call_home','leave')", name="kind"),
    )
    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    letter_de: Mapped[str] = mapped_column(String(2))
    letter_en: Mapped[str] = mapped_column(String(2))
    name_de: Mapped[str] = mapped_column(String(80))
    name_en: Mapped[str] = mapped_column(String(80))
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    ends_next_day: Mapped[bool]
    break_minutes: Mapped[int]
    net_hours: Mapped[float] = mapped_column(Numeric(5, 2))
    kind: Mapped[str] = mapped_column(String(20))
    counts_as_working_time: Mapped[bool]
    burden_weight: Mapped[float] = mapped_column(Numeric(4, 2))


class ShiftDemand(Base):
    """Required count per date, shift type and qualification ('any' = the shift's total)."""

    __tablename__ = "shift_demand"
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    shift_type: Mapped[str] = mapped_column(ForeignKey("shift_type.code"), primary_key=True)
    qualification: Mapped[str] = mapped_column(String(40), primary_key=True)
    required_count: Mapped[int]


class Holiday(Base):
    """A public holiday."""

    __tablename__ = "holiday"
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    name_de: Mapped[str] = mapped_column(String(80))
    name_en: Mapped[str] = mapped_column(String(80))


class SchoolHoliday(Base):
    """A school-holiday period (approximate, synthetic)."""

    __tablename__ = "school_holiday"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    name_de: Mapped[str] = mapped_column(String(80))
    name_en: Mapped[str] = mapped_column(String(80))


class RuleSet(Base):
    """A versioned rule set: typed, declarative rules stored as data."""

    __tablename__ = "rule_set"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(String(20), unique=True)
    effective_from: Mapped[date] = mapped_column(Date)
    rules: Mapped[dict[str, Any]] = mapped_column(JSONB)
    change_note_de: Mapped[str] = mapped_column(String(300))
    change_note_en: Mapped[str] = mapped_column(String(300))

"""Month-end reports (the payroll export and the Oversight report are read from them)."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from dienstpilot.shared.db import FairnessBase as Base


class MonthReport(Base):
    """The documentation of one month: prepared automatically, closed by the Planner."""

    __tablename__ = "month_report"
    __table_args__ = (CheckConstraint("status IN ('prepared','closed')", name="status"),)
    department_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    roster_month: Mapped[date] = mapped_column(Date, primary_key=True)
    status: Mapped[str] = mapped_column(String(10))
    prepared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[uuid.UUID | None]
    report_hash: Mapped[str] = mapped_column(String(64))  # sha256 of the canonical payload
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)

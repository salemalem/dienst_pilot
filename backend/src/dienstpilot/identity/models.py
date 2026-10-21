"""Users (demo personas) and their app settings."""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from dienstpilot.shared.db import IdentityBase as Base

ROLES = "('staff','staff_plus','planner','oversight','admin')"


class User(Base):
    """A user of the apps. Physicians link to their staff record; HR and IT do not."""

    __tablename__ = "user"
    __table_args__ = (CheckConstraint(f"role IN {ROLES}", name="role"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    persona_key: Mapped[str] = mapped_column(String(40), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))
    department_id: Mapped[uuid.UUID]
    staff_id: Mapped[uuid.UUID | None] = mapped_column(unique=True)


class UserSettings(Base):
    """Personal app settings (M12)."""

    __tablename__ = "user_settings"
    __table_args__ = (
        CheckConstraint("language IN ('de','en')", name="language"),
        CheckConstraint("theme IN ('auto','light','dark')", name="theme"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), primary_key=True)
    language: Mapped[str] = mapped_column(String(2), default="de")
    theme: Mapped[str] = mapped_column(String(5), default="auto")
    notifications: Mapped[bool] = mapped_column(default=True)
    calendar_sync: Mapped[bool] = mapped_column(default=False)
    preference_suggestions: Mapped[bool] = mapped_column(default=True)

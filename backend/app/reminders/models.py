import uuid
from datetime import date, datetime, time

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, String, Time, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, utcnow


class Reminder(Base):
    """'Did you log lunch?' at 12:30 on weekdays, in the user's own time zone."""

    __tablename__ = "reminders"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(16))  # breakfast | lunch | dinner | snack | custom
    at_time: Mapped[time] = mapped_column(Time)  # local time
    days: Mapped[list] = mapped_column(JSON)  # 0=Mon ... 6=Sun
    channels: Mapped[list] = mapped_column(JSON)  # ["in_app"] or ["in_app","sms"]
    message: Mapped[str | None] = mapped_column(String(160), nullable=True)
    skip_if_logged: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sent_on: Mapped[date | None] = mapped_column(Date, nullable=True)  # local date
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (Index("ix_reminders_user", "user_id"),)

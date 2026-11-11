import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)  # stored lower-case
    password_hash: Mapped[str] = mapped_column(String(100))
    display_name: Mapped[str] = mapped_column(String(80))
    timezone: Mapped[str] = mapped_column(String(64), default="America/Chicago")  # IANA name
    preferred_language: Mapped[str] = mapped_column(String(16), default="en")  # BCP-47 tag
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Phone + text-message consent. A number only counts after the user types the code we texted.
    phone_e164: Mapped[str | None] = mapped_column(String(20), nullable=True)  # e.g. +16125550100
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pending_phone_e164: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phone_code_hash: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone_code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    phone_code_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    sms_opt_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sms_opted_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("phone_e164", name="uq_users_phone_e164"),)

    @property
    def can_receive_sms(self) -> bool:
        return bool(self.phone_e164 and self.phone_verified_at and self.sms_opt_in_at and not self.sms_opted_out_at)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, utcnow


class NutritionTarget(Base):
    """The user's current daily targets. One row per user; every change is in audit_events."""

    __tablename__ = "nutrition_targets"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    calories_kcal: Mapped[Decimal] = mapped_column(Numeric(7, 1))
    protein_g: Mapped[Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)
    carbs_g: Mapped[Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)
    fat_g: Mapped[Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)
    fiber_g: Mapped[Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

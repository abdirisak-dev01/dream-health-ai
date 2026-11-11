import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, utcnow


class Food(Base):
    """A food record. All nutrient values are per 100 g of the food in the stated state (raw / cooked)."""

    __tablename__ = "foods"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True)  # stable ID from the data source/seed
    name: Mapped[str] = mapped_column(String(200))
    search_text: Mapped[str] = mapped_column(Text)  # normalized name + aliases, used for lookup
    display_names: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {"en": "Rice (cooked)", "so": ..., "es": ...}
    state: Mapped[str] = mapped_column(String(16))  # raw | cooked | prepared | n/a

    kcal_per_100g: Mapped[Decimal] = mapped_column(Numeric(7, 2))
    protein_g_per_100g: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    carbs_g_per_100g: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    fat_g_per_100g: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    fiber_g_per_100g: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)

    # Provenance: where these numbers came from, and whether a qualified reviewer checked them.
    source: Mapped[str] = mapped_column(String(64))
    source_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    data_version: Mapped[str] = mapped_column(String(32))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    portions: Mapped[list["FoodPortion"]] = relationship(back_populates="food", cascade="all, delete-orphan",
                                                          lazy="selectin")

    __table_args__ = (
        CheckConstraint("kcal_per_100g >= 0 AND protein_g_per_100g >= 0 AND carbs_g_per_100g >= 0 "
                        "AND fat_g_per_100g >= 0", name="ck_foods_nonnegative"),
        CheckConstraint("state IN ('raw','cooked','prepared','n/a')", name="ck_foods_state"),
    )


class FoodPortion(Base):
    """A named household measure for one food, e.g. 1 cup cooked rice = 158 g."""

    __tablename__ = "food_portions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    food_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("foods.id", ondelete="CASCADE"), index=True)
    unit: Mapped[str] = mapped_column(String(32))  # singular, lower-case: cup, tbsp, slice, large, medium
    grams: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)  # used for "2 eggs" (no unit given)

    food: Mapped[Food] = relationship(back_populates="portions")

    __table_args__ = (
        UniqueConstraint("food_id", "unit", name="uq_food_portion_unit"),
        CheckConstraint("grams > 0", name="ck_food_portion_grams_positive"),
    )

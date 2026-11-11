"""Meals are saved in two steps, so nothing reaches a user's log without their OK:

1. MealProposal  - a draft built from structured items or typed text (status: pending | needs_input)
2. Meal          - created only when the user confirms the proposal. Item values are copied
                   (snapshot), so later food-data corrections never silently rewrite history.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, utcnow

MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack", "other")


class _NutritionCols:
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    unit: Mapped[str] = mapped_column(String(32))
    grams: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    kcal: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    protein_g: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    carbs_g: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    fat_g: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    fiber_g: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    # provenance copied from the food record at the time of logging
    food_name: Mapped[str] = mapped_column(String(200))
    food_source: Mapped[str] = mapped_column(String(64))
    food_data_version: Mapped[str] = mapped_column(String(32))
    food_verified: Mapped[bool] = mapped_column()
    basis: Mapped[str] = mapped_column(String(16), default="confirmed")  # confirmed | estimated (future photos)
    position: Mapped[int] = mapped_column(Integer)


class MealProposal(Base):
    __tablename__ = "meal_proposals"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16))  # pending | needs_input | confirmed | discarded
    input_mode: Mapped[str] = mapped_column(String(16))  # items | text
    meal_type: Mapped[str] = mapped_column(String(16))
    eaten_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    nutrition_date: Mapped[date] = mapped_column(Date)  # eaten_at in the user's time zone
    timezone: Mapped[str] = mapped_column(String(64))
    unresolved: Mapped[list | None] = mapped_column(JSON, nullable=True)  # text lines that need the user's help
    meal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    items: Mapped[list["MealProposalItem"]] = relationship(
        back_populates="proposal", cascade="all, delete-orphan", order_by="MealProposalItem.position",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_meal_proposals_user", "user_id", "created_at"),
        CheckConstraint("status IN ('pending','needs_input','confirmed','discarded')", name="ck_proposal_status"),
    )


class MealProposalItem(_NutritionCols, Base):
    __tablename__ = "meal_proposal_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    proposal_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("meal_proposals.id", ondelete="CASCADE"),
                                                   index=True)
    food_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("foods.id"))

    proposal: Mapped[MealProposal] = relationship(back_populates="items")


class Meal(Base):
    __tablename__ = "meals"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    # unique: confirming the same proposal twice can never create two meals
    proposal_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("meal_proposals.id"), unique=True)
    meal_type: Mapped[str] = mapped_column(String(16))
    eaten_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    nutrition_date: Mapped[date] = mapped_column(Date)
    timezone: Mapped[str] = mapped_column(String(64))
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["MealItem"]] = relationship(
        back_populates="meal", cascade="all, delete-orphan", order_by="MealItem.position", lazy="selectin",
    )

    __table_args__ = (Index("ix_meals_user_date", "user_id", "nutrition_date"),)


class MealItem(_NutritionCols, Base):
    __tablename__ = "meal_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    meal_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("meals.id", ondelete="CASCADE"), index=True)
    food_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("foods.id"))

    meal: Mapped[Meal] = relationship(back_populates="items")

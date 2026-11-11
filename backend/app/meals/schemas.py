import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MealType = Literal["breakfast", "lunch", "dinner", "snack", "other"]


class ItemIn(BaseModel):
    food_id: uuid.UUID
    quantity: Decimal = Field(gt=0, le=10000)
    unit: str = Field(min_length=1, max_length=32)


class ProposalIn(BaseModel):
    """Send either `items` (picked from food search) or `text` (typed meal). Not both."""

    meal_type: MealType = "other"
    eaten_at: datetime | None = Field(default=None, description="When you ate. Defaults to now. Needs a time zone.")
    items: list[ItemIn] | None = Field(default=None, min_length=1, max_length=30)
    text: str | None = Field(default=None, min_length=1, max_length=1000,
                             examples=["150 g roasted chicken breast, 1 cup rice, 2 eggs"])

    @field_validator("eaten_at")
    @classmethod
    def _aware(cls, v):
        if v is not None and v.tzinfo is None:
            raise ValueError("must include a time zone offset, e.g. 2026-11-06T12:30:00-06:00")
        return v

    @model_validator(mode="after")
    def _one_input(self):
        if (self.items is None) == (self.text is None):
            raise ValueError("send exactly one of `items` or `text`")
        return self


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    food_id: uuid.UUID
    food_name: str
    food_labels: dict | None = None  # {"en": "Rice (cooked)", "so": "Bariis (la karsaday)", "es": "Arroz blanco (cocido)"}
    quantity: Decimal
    unit: str
    grams: Decimal
    kcal: Decimal
    protein_g: Decimal
    carbs_g: Decimal
    fat_g: Decimal
    fiber_g: Decimal | None
    basis: str
    food_source: str
    food_data_version: str
    food_verified: bool


class Candidate(BaseModel):
    food_id: uuid.UUID
    name: str
    allowed_units: list[str]


class UnresolvedLine(BaseModel):
    text: str
    problem: str  # quantity_missing | quantity_invalid | food_missing | food_not_found | food_ambiguous | food_typo | unit_invalid | too_large
    message: str
    candidates: list[Candidate] = []


class Totals(BaseModel):
    kcal: Decimal
    protein_g: Decimal
    carbs_g: Decimal
    fat_g: Decimal
    fiber_g: Decimal


class ProposalOut(BaseModel):
    id: uuid.UUID
    status: str
    meal_type: str
    eaten_at: datetime
    nutrition_date: date
    items: list[ItemOut]
    unresolved: list[UnresolvedLine]
    totals: Totals
    includes_unverified_food_data: bool
    meal_id: uuid.UUID | None
    next_step: str


class MealOut(BaseModel):
    id: uuid.UUID
    meal_type: str
    eaten_at: datetime
    nutrition_date: date
    confirmed_at: datetime
    items: list[ItemOut]
    totals: Totals
    includes_unverified_food_data: bool


class TargetCompare(BaseModel):
    target: Decimal | None
    eaten: Decimal
    remaining: Decimal | None


class DaySummary(BaseModel):
    date: date
    timezone: str
    meal_count: int
    totals: Totals
    targets_set: bool
    vs_targets: dict[str, TargetCompare]
    includes_unverified_food_data: bool
    note: str

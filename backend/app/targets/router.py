"""Editable daily nutrition targets.

The user sets their own numbers. The app does not calculate or recommend targets in Phase 1;
that needs a policy approved by the Nutrition reviewer. The bounds below only catch typos.
"""
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.db import get_db
from app.core.errors import not_found
from app.core.security import get_current_user
from app.targets.models import NutritionTarget

router = APIRouter(prefix="/v1/me/targets", tags=["targets"])


class TargetsIn(BaseModel):
    calories_kcal: Decimal = Field(gt=0, le=10000, decimal_places=1)
    protein_g: Decimal | None = Field(default=None, ge=0, le=1000, decimal_places=1)
    carbs_g: Decimal | None = Field(default=None, ge=0, le=2000, decimal_places=1)
    fat_g: Decimal | None = Field(default=None, ge=0, le=1000, decimal_places=1)
    fiber_g: Decimal | None = Field(default=None, ge=0, le=300, decimal_places=1)


class TargetsOut(TargetsIn):
    model_config = ConfigDict(from_attributes=True)
    updated_at: datetime


FIELDS = ("calories_kcal", "protein_g", "carbs_g", "fat_g", "fiber_g")


def _snapshot(t: NutritionTarget | None) -> dict | None:
    if t is None:
        return None
    return {f: (None if getattr(t, f) is None else f"{Decimal(getattr(t, f)):.1f}") for f in FIELDS}


@router.get("", response_model=TargetsOut, summary="My daily targets")
def get_targets(user=Depends(get_current_user), db: Session = Depends(get_db)):
    t = db.get(NutritionTarget, user.id)
    if t is None:
        raise not_found("Targets")
    return t


@router.put("", response_model=TargetsOut, summary="Set or replace my daily targets")
def put_targets(body: TargetsIn, user=Depends(get_current_user), db: Session = Depends(get_db)):
    t = db.get(NutritionTarget, user.id)
    before = _snapshot(t)
    if t is None:
        t = NutritionTarget(user_id=user.id)
        db.add(t)
    for f in FIELDS:
        setattr(t, f, getattr(body, f))
    db.flush()
    audit.record(db, user_id=user.id, action="targets.updated", entity_type="nutrition_targets",
                 entity_id=user.id, before=before, after=_snapshot(t))
    db.commit()
    db.refresh(t)
    return t

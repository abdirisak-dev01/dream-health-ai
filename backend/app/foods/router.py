import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import not_found
from app.core.security import get_current_user
from app.foods.models import Food
from app.foods.service import search_foods

router = APIRouter(prefix="/v1/foods", tags=["foods"])


class PortionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    unit: str
    grams: Decimal
    is_default: bool


class FoodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    state: str
    kcal_per_100g: Decimal
    protein_g_per_100g: Decimal
    carbs_g_per_100g: Decimal
    fat_g_per_100g: Decimal
    fiber_g_per_100g: Decimal | None
    source: str
    data_version: str
    verified: bool
    portions: list[PortionOut]
    allowed_units: list[str]


def food_out(f: Food) -> FoodOut:
    from app.meals.nutrition import MASS_UNITS_G

    return FoodOut.model_validate(
        {**{k: getattr(f, k) for k in FoodOut.model_fields if k not in ("portions", "allowed_units")},
         "portions": f.portions,
         "allowed_units": sorted(MASS_UNITS_G) + sorted(p.unit for p in f.portions)}
    )


@router.get("", response_model=list[FoodOut], summary="Search foods by name (e.g. 'rice', 'chicken cooked')")
def list_foods(
    q: str = Query(min_length=1, max_length=100),
    limit: int = Query(20, ge=1, le=50),
    _user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return [food_out(f) for f in search_foods(db, q, limit)]


@router.get("/{food_id}", response_model=FoodOut, summary="One food record")
def get_food(food_id: uuid.UUID, _user=Depends(get_current_user), db: Session = Depends(get_db)):
    f = db.get(Food, food_id)
    if f is None:
        raise not_found("Food")
    return food_out(f)

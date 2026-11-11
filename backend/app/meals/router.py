import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from app.core.db import get_db, utcnow
from app.core.security import get_current_user
from app.foods.models import Food
from app.meals import service
from app.meals.models import Meal, MealProposal
from app.meals.nutrition import NUTRIENTS, sum_items
from app.meals.schemas import (
    DaySummary, ItemOut, MealOut, ProposalIn, ProposalOut, TargetCompare, Totals, UnresolvedLine,
)
from app.targets.models import NutritionTarget

meals_router = APIRouter(prefix="/v1/meals", tags=["meals"])
days_router = APIRouter(prefix="/v1/days", tags=["daily totals"])

NEXT_STEP = {
    "pending": "Check the items and totals, then POST /v1/meals/proposals/{id}/confirm to save.",
    "needs_input": "Some lines need help. Fix them (pick a candidate food or unit) and send a new proposal.",
    "confirmed": "Saved to your log.",
    "discarded": "Discarded. Nothing was saved.",
}


def _items(objs) -> list[ItemOut]:
    objs = list(objs)
    if not objs:
        return []
    db = object_session(objs[0])
    ids = {i.food_id for i in objs}
    labels = dict(db.execute(select(Food.id, Food.display_names).where(Food.id.in_(ids))).all()) if db else {}
    out = []
    for i in objs:
        item = ItemOut.model_validate(i)
        item.food_labels = labels.get(i.food_id)
        out.append(item)
    return out


def proposal_out(p: MealProposal) -> ProposalOut:
    return ProposalOut(
        id=p.id, status=p.status, meal_type=p.meal_type, eaten_at=p.eaten_at, nutrition_date=p.nutrition_date,
        items=_items(p.items), unresolved=[UnresolvedLine(**u) for u in (p.unresolved or [])],
        totals=Totals(**sum_items(p.items)),
        includes_unverified_food_data=any(not i.food_verified for i in p.items),
        meal_id=p.meal_id, next_step=NEXT_STEP[p.status].replace("{id}", str(p.id)),
    )


def meal_out(m: Meal) -> MealOut:
    return MealOut(
        id=m.id, meal_type=m.meal_type, eaten_at=m.eaten_at, nutrition_date=m.nutrition_date,
        confirmed_at=m.confirmed_at, items=_items(m.items), totals=Totals(**sum_items(m.items)),
        includes_unverified_food_data=any(not i.food_verified for i in m.items),
    )


# ---- proposals (draft, nothing saved to the log yet) --------------------------

@meals_router.post("/proposals", response_model=ProposalOut, status_code=201,
                   summary="Step 1: draft a meal from food items or typed text")
def create_proposal(body: ProposalIn, user=Depends(get_current_user), db: Session = Depends(get_db)):
    return proposal_out(service.create_proposal(db, user, body))


@meals_router.get("/proposals/{proposal_id}", response_model=ProposalOut, summary="See a draft")
def get_proposal(proposal_id: uuid.UUID, user=Depends(get_current_user), db: Session = Depends(get_db)):
    return proposal_out(service.get_own_proposal(db, user, proposal_id))


@meals_router.post("/proposals/{proposal_id}/confirm", response_model=MealOut,
                   summary="Step 2: confirm the draft and save it to your log (safe to repeat)")
def confirm_proposal(proposal_id: uuid.UUID, response: Response, user=Depends(get_current_user),
                     db: Session = Depends(get_db)):
    meal, created = service.confirm_proposal(db, user, proposal_id)
    response.status_code = 201 if created else 200
    return meal_out(meal)


@meals_router.post("/proposals/{proposal_id}/discard", response_model=ProposalOut, summary="Throw a draft away")
def discard_proposal(proposal_id: uuid.UUID, user=Depends(get_current_user), db: Session = Depends(get_db)):
    return proposal_out(service.discard_proposal(db, user, proposal_id))


# ---- confirmed meals -------------------------------------------------------------

@meals_router.get("", response_model=list[MealOut], summary="My confirmed meals for one day")
def list_meals(
    day: date | None = Query(None, alias="date", description="YYYY-MM-DD in your time zone. Default: today."),
    user=Depends(get_current_user), db: Session = Depends(get_db),
):
    day = day or service.local_date(utcnow(), user.timezone)
    return [meal_out(m) for m in service.list_meals(db, user, day)]


@meals_router.get("/{meal_id}", response_model=MealOut, summary="One confirmed meal")
def get_meal(meal_id: uuid.UUID, user=Depends(get_current_user), db: Session = Depends(get_db)):
    return meal_out(service.get_own_meal(db, user, meal_id))


@meals_router.delete("/{meal_id}", status_code=204, summary="Remove a meal from my log (kept in audit history)")
def delete_meal(meal_id: uuid.UUID, user=Depends(get_current_user), db: Session = Depends(get_db)):
    service.delete_meal(db, user, meal_id)
    return Response(status_code=204)


# ---- running totals ----------------------------------------------------------------

TARGET_FIELDS = {"kcal": "calories_kcal", "protein_g": "protein_g", "carbs_g": "carbs_g",
                 "fat_g": "fat_g", "fiber_g": "fiber_g"}


@days_router.get("/today/summary", response_model=DaySummary, summary="Today's running totals vs my targets")
def today_summary(user=Depends(get_current_user), db: Session = Depends(get_db)):
    return _summary(service.local_date(utcnow(), user.timezone), user, db)


@days_router.get("/{day}/summary", response_model=DaySummary, summary="Running totals vs my targets for a day")
def day_summary(day: date, user=Depends(get_current_user), db: Session = Depends(get_db)):
    return _summary(day, user, db)


def _summary(day: date, user, db: Session) -> DaySummary:
    meals = service.list_meals(db, user, day)
    items = [i for m in meals for i in m.items]
    totals = sum_items(items)
    target = db.get(NutritionTarget, user.id)
    compare = {}
    for key in NUTRIENTS:
        t = None if target is None else getattr(target, TARGET_FIELDS[key])
        compare[key] = TargetCompare(target=t, eaten=totals[key], remaining=None if t is None else t - totals[key])
    unverified = any(not i.food_verified for i in items)
    note = "Totals count confirmed meals only."
    if unverified:
        note += " Some food values are development placeholders and are not yet verified."
    return DaySummary(date=day, timezone=user.timezone, meal_count=len(meals), totals=Totals(**totals),
                      targets_set=target is not None, vs_targets=compare,
                      includes_unverified_food_data=unverified, note=note)

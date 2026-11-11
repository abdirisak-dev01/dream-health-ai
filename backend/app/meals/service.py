"""Meal business rules. Routers stay thin; everything testable lives here."""
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.config import get_settings
from app.core.db import utcnow
from app.core.errors import AppError, not_found
from app.foods.models import Food
from app.foods.service import exact_matches, search_foods, suggest_foods
from app.meals import text_parser
from app.meals.models import Meal, MealItem, MealProposal, MealProposalItem
from app.meals.nutrition import (
    MASS_UNITS_G, NUTRIENTS, UnitError, calculate_item, default_portion_unit, normalize_unit, sum_items,
)
from app.meals.schemas import Candidate, ProposalIn, UnresolvedLine
from app.users.models import User

PROBLEM_MESSAGES = {
    "quantity_missing": "Add an amount, e.g. '150 g rice' or '1 cup rice'.",
    "quantity_invalid": "The amount could not be read. Use a number like 150, 1.5 or 1/2.",
    "food_missing": "Add the food name after the amount.",
    "food_not_found": "No matching food found. Try a different name or search foods.",
    "food_ambiguous": "More than one food matches. Pick one of the candidates.",
    "food_typo": "Did you mean one of these? Send it again with the right name.",
    "unit_invalid": "This unit can't be used for this food. Use one of the allowed units.",
    "too_large": "This amount is unusually large. Check for a typo.",
}


def local_date(dt: datetime, tz_name: str) -> date:
    return dt.astimezone(ZoneInfo(tz_name)).date()


def _candidate(f: Food) -> Candidate:
    return Candidate(food_id=f.id, name=f.name,
                     allowed_units=sorted(MASS_UNITS_G) + sorted(p.unit for p in f.portions))


def _unresolved(text: str, problem: str, candidates: list[Food] | None = None, message: str | None = None) -> dict:
    return UnresolvedLine(
        text=text, problem=problem, message=message or PROBLEM_MESSAGES[problem],
        candidates=[_candidate(f) for f in (candidates or [])],
    ).model_dump(mode="json")


def _make_item(food: Food, quantity: Decimal, unit: str, position: int) -> MealProposalItem:
    n = calculate_item(food, quantity, unit)  # raises UnitError
    if n.grams > get_settings().max_item_grams:
        raise OverflowError
    return MealProposalItem(
        food_id=food.id, food_name=food.name, quantity=quantity, unit=normalize_unit(unit),
        grams=n.grams, kcal=n.kcal, protein_g=n.protein_g, carbs_g=n.carbs_g, fat_g=n.fat_g, fiber_g=n.fiber_g,
        food_source=food.source, food_data_version=food.data_version, food_verified=food.verified,
        basis="confirmed", position=position,
    )


def _resolve_food(db: Session, query: str) -> tuple[Food | None, str | None, list[Food]]:
    exact = exact_matches(db, query)
    if len(exact) == 1:
        return exact[0], None, []
    if len(exact) > 1:
        return None, "food_ambiguous", exact[:6]
    found = search_foods(db, query, limit=6)
    if len(found) == 1:
        return found[0], None, []
    if not found:
        guesses = suggest_foods(db, query)
        return (None, "food_typo", guesses) if guesses else (None, "food_not_found", [])
    return None, "food_ambiguous", found


def create_proposal(db: Session, user: User, body: ProposalIn) -> MealProposal:
    eaten_at = body.eaten_at or utcnow()
    if eaten_at > utcnow() + timedelta(minutes=5):
        raise AppError(422, "eaten_at_in_future", "eaten_at can't be in the future")
    proposal = MealProposal(
        user_id=user.id, meal_type=body.meal_type, eaten_at=eaten_at,
        nutrition_date=local_date(eaten_at, user.timezone), timezone=user.timezone,
        input_mode="items" if body.items is not None else "text",
    )
    unresolved: list[dict] = []

    if body.items is not None:
        # Structured input must be exactly right: reject the whole request on any bad item.
        for i, it in enumerate(body.items):
            food = db.get(Food, it.food_id)
            if food is None:
                raise AppError(422, "food_not_found", f"items[{i}]: food not found")
            try:
                proposal.items.append(_make_item(food, it.quantity, it.unit, i))
            except UnitError as e:
                raise AppError(422, "unit_invalid", f"items[{i}]: {e}")
            except OverflowError:
                raise AppError(422, "too_large", f"items[{i}]: {PROBLEM_MESSAGES['too_large']}")
    else:
        lines = text_parser.split_lines(body.text or "")
        if not lines:
            raise AppError(422, "text_empty", "Type at least one food, e.g. '1 cup rice'")
        if len(lines) > text_parser.MAX_TEXT_LINES:
            raise AppError(422, "text_too_long", f"Up to {text_parser.MAX_TEXT_LINES} foods per meal")
        pos = 0
        for line in lines:
            parsed = text_parser.parse_line(line)
            if parsed.problem:
                unresolved.append(_unresolved(line, parsed.problem))
                continue
            food, problem, cands = _resolve_food(db, parsed.food_query)
            if food is None:
                unresolved.append(_unresolved(line, problem, cands))
                continue
            unit = parsed.unit or default_portion_unit(food)
            if unit is None:
                unresolved.append(_unresolved(line, "unit_invalid", [food],
                                              f"Add a unit for '{food.name}', e.g. '150 g'."))
                continue
            try:
                proposal.items.append(_make_item(food, parsed.quantity, unit, pos))
                pos += 1
            except UnitError as e:
                unresolved.append(_unresolved(line, "unit_invalid", [food], str(e)))
            except OverflowError:
                unresolved.append(_unresolved(line, "too_large"))

    proposal.unresolved = unresolved or None
    proposal.status = "needs_input" if unresolved or not proposal.items else "pending"
    db.add(proposal)
    db.flush()
    audit.record(db, user_id=user.id, action="meal_proposal.created", entity_type="meal_proposal",
                 entity_id=proposal.id,
                 after={"input_mode": proposal.input_mode, "status": proposal.status,
                        "item_count": len(proposal.items), "unresolved_count": len(unresolved)})
    db.commit()
    return proposal


def get_own_proposal(db: Session, user: User, proposal_id: uuid.UUID, lock: bool = False) -> MealProposal:
    stmt = select(MealProposal).where(MealProposal.id == proposal_id, MealProposal.user_id == user.id)
    if lock:
        stmt = stmt.with_for_update()
    p = db.scalar(stmt)
    if p is None:
        raise not_found("Meal proposal")
    return p


def confirm_proposal(db: Session, user: User, proposal_id: uuid.UUID) -> tuple[Meal, bool]:
    """Returns (meal, created). Confirming twice returns the same meal (idempotent)."""
    p = get_own_proposal(db, user, proposal_id, lock=True)
    if p.status == "confirmed":
        return get_own_meal(db, user, p.meal_id, include_deleted=True), False
    if p.status == "discarded":
        raise AppError(409, "proposal_discarded", "This proposal was discarded")
    if p.status == "needs_input" or not p.items:
        raise AppError(409, "proposal_needs_input",
                       "Some lines need your help first. Send a new proposal with those foods fixed.")

    meal = Meal(user_id=user.id, proposal_id=p.id, meal_type=p.meal_type, eaten_at=p.eaten_at,
                nutrition_date=p.nutrition_date, timezone=p.timezone)
    copy_cols = ["food_id", "food_name", "quantity", "unit", "grams", *NUTRIENTS, "food_source",
                 "food_data_version", "food_verified", "basis", "position"]
    for it in p.items:
        meal.items.append(MealItem(**{c: getattr(it, c) for c in copy_cols}))
    db.add(meal)
    try:
        db.flush()
    except IntegrityError:  # someone confirmed it at the same moment
        db.rollback()
        p = get_own_proposal(db, user, proposal_id)
        return get_own_meal(db, user, p.meal_id, include_deleted=True), False
    p.status = "confirmed"
    p.meal_id = meal.id
    totals = sum_items(meal.items)
    audit.record(db, user_id=user.id, action="meal.confirmed", entity_type="meal", entity_id=meal.id,
                 after={"proposal_id": str(p.id), "nutrition_date": p.nutrition_date.isoformat(),
                        "item_count": len(meal.items), "kcal": str(totals["kcal"])})
    db.commit()
    return meal, True


def discard_proposal(db: Session, user: User, proposal_id: uuid.UUID) -> MealProposal:
    p = get_own_proposal(db, user, proposal_id, lock=True)
    if p.status == "confirmed":
        raise AppError(409, "proposal_confirmed", "Already confirmed. Delete the meal instead.")
    if p.status != "discarded":
        before = {"status": p.status}
        p.status = "discarded"
        audit.record(db, user_id=user.id, action="meal_proposal.discarded", entity_type="meal_proposal",
                     entity_id=p.id, before=before, after={"status": "discarded"})
        db.commit()
    return p


def get_own_meal(db: Session, user: User, meal_id: uuid.UUID | None, include_deleted: bool = False) -> Meal:
    stmt = select(Meal).where(Meal.id == meal_id, Meal.user_id == user.id)
    if not include_deleted:
        stmt = stmt.where(Meal.deleted_at.is_(None))
    m = db.scalar(stmt)
    if m is None:
        raise not_found("Meal")
    return m


def list_meals(db: Session, user: User, day: date) -> list[Meal]:
    stmt = (select(Meal)
            .where(Meal.user_id == user.id, Meal.nutrition_date == day, Meal.deleted_at.is_(None))
            .order_by(Meal.eaten_at, Meal.id))
    return list(db.scalars(stmt).all())


def delete_meal(db: Session, user: User, meal_id: uuid.UUID) -> None:
    m = get_own_meal(db, user, meal_id)
    m.deleted_at = utcnow()
    totals = sum_items(m.items)
    audit.record(db, user_id=user.id, action="meal.deleted", entity_type="meal", entity_id=m.id,
                 before={"nutrition_date": m.nutrition_date.isoformat(), "item_count": len(m.items),
                         "kcal": str(totals["kcal"])},
                 after={"deleted": True})
    db.commit()

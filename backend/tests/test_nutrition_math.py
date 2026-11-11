"""Pure calculation tests (test vectors). No database needed."""
from decimal import Decimal

import pytest

from app.foods.models import Food, FoodPortion
from app.meals.nutrition import UnitError, calculate_item, r2, sum_items


def make_food(kcal, p, c, f, fiber=None, portions=()):
    food = Food(name="Test food", kcal_per_100g=Decimal(kcal), protein_g_per_100g=Decimal(p),
                carbs_g_per_100g=Decimal(c), fat_g_per_100g=Decimal(f),
                fiber_g_per_100g=None if fiber is None else Decimal(fiber))
    food.portions = [FoodPortion(unit=u, grams=Decimal(g), is_default=d) for u, g, d in portions]
    return food


CHICKEN_RAW = make_food("120", "22.5", "0", "2.6", "0")
CHICKEN_COOKED = make_food("165", "31.0", "0", "3.6", "0")
RICE_COOKED = make_food("130", "2.7", "28.2", "0.3", "0.4", [("cup", "158", False)])


def test_n101_raw_vs_cooked_chicken_are_different():
    raw = calculate_item(CHICKEN_RAW, Decimal("150"), "g")
    cooked = calculate_item(CHICKEN_COOKED, Decimal("150"), "g")
    assert raw.kcal == Decimal("180.00") and raw.protein_g == Decimal("33.75")
    assert cooked.kcal == Decimal("247.50") and cooked.protein_g == Decimal("46.50")


def test_named_portion_cup_of_rice():
    n = calculate_item(RICE_COOKED, Decimal("1"), "cups")
    assert n.grams == Decimal("158.00")
    assert n.kcal == Decimal("205.40")
    assert n.carbs_g == Decimal("44.56")
    assert n.fiber_g == Decimal("0.63")


def test_fraction_of_portion():
    n = calculate_item(RICE_COOKED, Decimal("0.5"), "cup")
    assert n.grams == Decimal("79.00") and n.kcal == Decimal("102.70")


@pytest.mark.parametrize("qty,unit,grams", [
    ("1", "kg", "1000.00"), ("4", "oz", "113.40"), ("1", "lb", "453.59"), ("200", "grams", "200.00"),
])
def test_mass_units(qty, unit, grams):
    assert calculate_item(CHICKEN_RAW, Decimal(qty), unit).grams == Decimal(grams)


@pytest.mark.parametrize("unit", ["cup", "ml", "handful", "bowl"])
def test_undefined_units_are_rejected_not_guessed(unit):
    with pytest.raises(UnitError):
        calculate_item(CHICKEN_RAW, Decimal("1"), unit)


def test_zero_or_negative_quantity_rejected():
    with pytest.raises(UnitError):
        calculate_item(CHICKEN_RAW, Decimal("0"), "g")


def test_rounding_is_half_up():
    assert r2(Decimal("1.005")) == Decimal("1.01")
    assert r2(Decimal("2.675")) == Decimal("2.68")


def test_missing_fiber_stays_missing_per_item():
    food = make_food("100", "1", "1", "1", None)
    assert calculate_item(food, Decimal("100"), "g").fiber_g is None


def test_sum_items():
    a = calculate_item(CHICKEN_COOKED, Decimal("150"), "g")
    b = calculate_item(RICE_COOKED, Decimal("1"), "cup")
    t = sum_items([a, b])
    assert t["kcal"] == Decimal("452.90")
    assert t["protein_g"] == Decimal("50.77")

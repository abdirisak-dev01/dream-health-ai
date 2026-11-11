"""Deterministic nutrition math. No AI, no guessing.

grams      = quantity x (grams per unit)
nutrient   = (nutrient per 100 g) x grams / 100
Rounding   = 2 decimals, half-up, on every stored item value.

Units allowed:
  * mass units (g, kg, oz, lb) for every food
  * named portions defined for that specific food (cup, tbsp, slice, large, ...)
Anything else (e.g. "ml" for a food with no volume portion, "handful") is rejected, never guessed.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.foods.models import Food

MASS_UNITS_G: dict[str, Decimal] = {
    "g": Decimal("1"),
    "kg": Decimal("1000"),
    "oz": Decimal("28.349523125"),
    "lb": Decimal("453.59237"),
}

UNIT_ALIASES = {
    "gram": "g", "grams": "g", "gr": "g", "gm": "g",
    "kilogram": "kg", "kilograms": "kg", "kgs": "kg",
    "ounce": "oz", "ounces": "oz",
    "pound": "lb", "pounds": "lb", "lbs": "lb",
    "cups": "cup",
    "tablespoon": "tbsp", "tablespoons": "tbsp", "tbsps": "tbsp",
    "teaspoon": "tsp", "teaspoons": "tsp", "tsps": "tsp",
    "slices": "slice", "pieces": "piece",
    # Spanish
    "gramo": "g", "gramos": "g", "kilo": "kg", "kilos": "kg", "onza": "oz", "onzas": "oz", "libra": "lb", "libras": "lb",
    "taza": "cup", "tazas": "cup", "cucharada": "tbsp", "cucharadas": "tbsp", "cucharadita": "tsp",
    "cucharaditas": "tsp", "rebanada": "slice", "rebanadas": "slice", "pieza": "piece", "piezas": "piece",
    "grande": "large", "grandes": "large", "mediano": "medium", "mediana": "medium", "pequeño": "small",
    "pequeno": "small", "pequeña": "small",
    # Somali
    "garaam": "g", "garaamka": "g", "kiilo": "kg", "koob": "cup", "koobab": "cup", "jeex": "slice",
    "xabbo": "piece", "weyn": "large",
}

# Words that are units only when a food defines them as a portion
PORTION_WORDS = {"cup", "tbsp", "tsp", "slice", "piece", "large", "medium", "small", "ml", "l"}

TWO_PLACES = Decimal("0.01")
NUTRIENTS = ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g")


class UnitError(ValueError):
    pass


def normalize_unit(unit: str) -> str:
    u = unit.strip().lower().rstrip(".")
    return UNIT_ALIASES.get(u, u)


def grams_per_unit(food: Food, unit: str) -> Decimal:
    u = normalize_unit(unit)
    if u in MASS_UNITS_G:
        return MASS_UNITS_G[u]
    for p in food.portions:
        if p.unit == u:
            return Decimal(p.grams)
    allowed = sorted(MASS_UNITS_G) + sorted(p.unit for p in food.portions)
    raise UnitError(f"Unit '{unit}' is not defined for '{food.name}'. Allowed: {', '.join(allowed)}")


def default_portion_unit(food: Food) -> str | None:
    for p in food.portions:
        if p.is_default:
            return p.unit
    return None


def r2(x: Decimal) -> Decimal:
    return x.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class ItemNutrition:
    grams: Decimal
    kcal: Decimal
    protein_g: Decimal
    carbs_g: Decimal
    fat_g: Decimal
    fiber_g: Decimal | None


def calculate_item(food: Food, quantity: Decimal, unit: str) -> ItemNutrition:
    if quantity <= 0:
        raise UnitError("Quantity must be greater than zero")
    grams = Decimal(quantity) * grams_per_unit(food, unit)
    factor = grams / Decimal(100)
    fiber = None if food.fiber_g_per_100g is None else r2(Decimal(food.fiber_g_per_100g) * factor)
    return ItemNutrition(
        grams=r2(grams),
        kcal=r2(Decimal(food.kcal_per_100g) * factor),
        protein_g=r2(Decimal(food.protein_g_per_100g) * factor),
        carbs_g=r2(Decimal(food.carbs_g_per_100g) * factor),
        fat_g=r2(Decimal(food.fat_g_per_100g) * factor),
        fiber_g=fiber,
    )


def sum_items(items) -> dict[str, Decimal]:
    """Sum stored item values. fiber_g treats missing values as 0 and the caller can flag it."""
    totals = {k: Decimal("0") for k in NUTRIENTS}
    for it in items:
        for k in NUTRIENTS:
            v = getattr(it, k)
            if v is not None:
                totals[k] += Decimal(v)
    return {k: r2(v) for k, v in totals.items()}

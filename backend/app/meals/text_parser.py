"""Turn plain text like "150 g chicken breast cooked, 1 cup rice, 2 eggs" into lines of
(quantity, unit, food words). This is a simple rule-based parser, not AI: if a line is unclear,
it says so and the user picks the food or unit themselves.
"""
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.meals.nutrition import MASS_UNITS_G, PORTION_WORDS, normalize_unit

MAX_TEXT_LINES = 20

# Commas split foods, except a decimal comma between digits ("1,5 cups").
# "and" in English, "y/con" in Spanish, "iyo/iyo" in Somali also split.
_SPLIT = re.compile(r"\s*(?:(?<!\d),|,(?!\d)|;|\n|\+|\band\b|\bwith\b|\by\b|\bcon\b|\biyo\b)\s*",
                    re.IGNORECASE)
_NUMBER_WORDS = {
    # English
    "a": "1", "an": "1", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "half": "0.5", "quarter": "0.25",
    # Spanish
    "un": "1", "una": "1", "uno": "1", "dos": "2", "tres": "3", "cuatro": "4", "cinco": "5", "seis": "6",
    "medio": "0.5", "media": "0.5",
    # Somali
    "hal": "1", "laba": "2", "saddex": "3", "afar": "4", "shan": "5", "lix": "6", "badh": "0.5", "nus": "0.5",
}
# "150g", "1.5 cups", "1/2 cup", "2 eggs", "half cup"
_QTY = re.compile(r"^(?P<qty>\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?)\s*(?P<rest>.*)$")


@dataclass
class ParsedLine:
    text: str
    quantity: Decimal | None
    unit: str | None  # normalized; None means "count" (use the food's default portion)
    food_query: str
    problem: str | None = None


def _to_decimal(s: str) -> Decimal:
    s = s.replace(",", ".").strip()
    if " " in s:  # mixed number "1 1/2"
        whole, frac = s.split()
        return Decimal(whole) + _to_decimal(frac)
    if "/" in s:
        n, d = s.split("/")
        if Decimal(d) == 0:
            raise InvalidOperation
        return Decimal(n) / Decimal(d)
    return Decimal(s)


# Everyday words people put around a meal: "i ate ...", "for lunch i had ...", "today".
_FILLER = re.compile(
    r"^(?:(?:for|at|para el|para la|en el|en la|de)\s+(?:breakfast|lunch|dinner|supper|desayuno|almuerzo|cena|merienda)"
    r"\s*,?\s*)?"
    r"(?:(?:today|hoy|maanta)\s*,?\s*)?"
    r"(?:"
    r"(?:i|we)\s+(?:just\s+|also\s+)?(?:ate|eat|eaten|had|have|drank|drink|got)\s+"  # English
    r"|(?:yo\s+)?(?:com[ií]|desayun[eé]|almorc[eé]|cen[eé]|tom[eé]|beb[ií])\s+"  # Spanish
    r"|(?:waxaan|waan|waxa)\s+(?:cunay|cabbay|cabay)\s+"  # Somali
    r")?",
    re.IGNORECASE,
)
# A new amount after a word starts a new food: "150g chicken 200g rice" -> two foods.
_NEW_ITEM = re.compile(r"(?<=[A-Za-z])\s+(?=\d)")


def clean_line(text: str) -> str:
    return _FILLER.sub("", text.strip(), count=1).strip()


def split_lines(text: str) -> list[str]:
    out = []
    for part in _SPLIT.split(text or ""):
        part = clean_line(part or "")
        if not part:
            continue
        out.extend(p.strip() for p in _NEW_ITEM.split(part) if p.strip())
    return out


def has_any_amount(text: str) -> bool:
    """True if any line starts with a number or a number word (so it looks like food)."""
    for line in split_lines(text):
        first = line.split()[0].lower() if line.split() else ""
        if first in _NUMBER_WORDS or _QTY.match(line):
            return True
    return False


def parse_line(text: str) -> ParsedLine:
    raw = text.strip()
    words = raw.split()
    if words and words[0].lower() in _NUMBER_WORDS:
        raw = _NUMBER_WORDS[words[0].lower()] + " " + " ".join(words[1:])

    m = _QTY.match(raw)
    if not m:
        return ParsedLine(text, None, None, raw, problem="quantity_missing")
    try:
        qty = _to_decimal(m.group("qty"))
    except (InvalidOperation, ValueError):
        return ParsedLine(text, None, None, raw, problem="quantity_invalid")

    rest = m.group("rest").strip()
    rest_words = rest.split()
    unit = None
    if rest_words:
        cand = normalize_unit(rest_words[0])
        if cand in MASS_UNITS_G or cand in PORTION_WORDS:
            unit = cand
            rest_words = rest_words[1:]
    if rest_words and rest_words[0].lower() in ("of", "de"):
        rest_words = rest_words[1:]
    food_query = " ".join(rest_words)
    if not food_query:
        return ParsedLine(text, qty, unit, "", problem="food_missing")
    return ParsedLine(text, qty, unit, food_query)

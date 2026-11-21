"""Turn plain text like "150 g chicken breast cooked, 1 cup rice, 2 eggs" into lines of
(quantity, unit, food words). Works for English, Spanish, French, Arabic and Mandarin.
© 2026 Abdirisak Omar. All rights reserved.

This is a simple rule-based parser, not AI: if a line is unclear, it says so and the user picks the food
or unit themselves.
"""
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.meals.nutrition import MASS_UNITS_G, PORTION_WORDS, normalize_unit

MAX_TEXT_LINES = 20

CJK = r"㐀-鿿"
_HAS_CJK = re.compile(f"[{CJK}]")
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

# Units written as two words, turned into one token before reading.
_MULTIWORD_UNITS = [
    (re.compile(r"\b(?:cuill[eè]res?|c\.)\s+(?:à|a)\s+soupe\b", re.IGNORECASE), "tbsp"),
    (re.compile(r"\b(?:cuill[eè]res?|c\.)\s+(?:à|a)\s+caf[eé]\b", re.IGNORECASE), "tsp"),
    (re.compile(r"(?:ملعقة|ملاعق)\s+كبير[ةه]"), "tbsp"),
    (re.compile(r"(?:ملعقة|ملاعق)\s+صغير[ةه]"), "tsp"),
]

# Commas split foods, except a decimal comma between digits ("1,5 cups").
# Also: and/with (English), y/con (Spanish), et/avec (French), و (Arabic), 和/还有/以及/跟 (Chinese).
_SPLIT = re.compile(
    r"\s*(?:(?<!\d),|,(?!\d)|;|\n|\+|、|\band\b|\bwith\b|\by\b|\bcon\b|\bet\b|\bavec\b|\s+و\s+|\s+و(?=\d)|和|还有|以及|跟)\s*",
    re.IGNORECASE)

_NUMBER_WORDS = {
    # English
    "a": "1", "an": "1", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "half": "0.5", "quarter": "0.25",
    # Spanish
    "un": "1", "una": "1", "uno": "1", "dos": "2", "tres": "3", "cuatro": "4", "cinco": "5", "seis": "6",
    "medio": "0.5", "media": "0.5",
    # French ("un/une" shared with Spanish above)
    "une": "1", "deux": "2", "trois": "3", "quatre": "4", "cinq": "5", "demi": "0.5", "demie": "0.5",
    # Arabic
    "واحد": "1", "واحدة": "1", "اثنين": "2", "اثنان": "2", "ثلاثة": "3", "ثلاث": "3", "أربعة": "4", "اربعة": "4",
    "خمسة": "5", "نصف": "0.5", "ربع": "0.25",
}
# "150g", "1.5 cups", "1/2 cup", "2 eggs", "half cup"
_QTY = re.compile(r"^(?P<qty>\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?)\s*(?P<rest>.*)$")

# Words that mean "this many pieces" (use the food's default portion): حبة (Arabic)
_COUNT_WORDS = {"حبة", "حبات", "حبه"}
# Words between the unit and the food: "150 g of chicken", "1 taza de arroz", "150 غ من الدجاج"
_LINK_WORDS = {"of", "de", "du", "des", "من"}


@dataclass
class ParsedLine:
    text: str
    quantity: Decimal | None
    unit: str | None  # normalized; None means "count" (use the food's default portion)
    food_query: str
    problem: str | None = None


def prepare(text: str) -> str:
    """Same characters for everyone: full-width -> normal, Arabic-Indic digits -> 0-9, Arabic/Chinese punctuation."""
    text = unicodedata.normalize("NFKC", text or "").translate(_ARABIC_DIGITS)
    text = text.replace("،", ",").replace("٫", ".").replace("؛", ";").replace("。", ",").replace("’", "'")
    for pattern, token in _MULTIWORD_UNITS:
        text = pattern.sub(token, text)
    return text


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


# Everyday words people put around a meal: "i ate ...", "for lunch i had ...", "j'ai mangé ...", "أكلت ...".
_FILLER = re.compile(
    r"^(?:(?:for|at|para el|para la|en el|en la|de|pour le|pour la|au|à la|على|في|لل)\s*"
    r"(?:breakfast|lunch|dinner|supper|desayuno|almuerzo|cena|merienda|petit[- ]d[ée]jeuner|d[ée]jeuner|d[îi]ner|"
    r"collation|go[ûu]ter|الفطور|الإفطار|الغداء|العشاء)\s*,?\s*)?"
    r"(?:(?:today|hoy|aujourd'hui|ce midi|ce soir|اليوم)\s*,?\s*)?"
    r"(?:"
    r"(?:i|we)\s+(?:just\s+|also\s+)?(?:ate|eat|eaten|had|have|drank|drink|got)\s+"  # English
    r"|(?:yo\s+)?(?:com[ií]|desayun[eé]|almorc[eé]|cen[eé]|tom[eé]|beb[ií])\s+"  # Spanish
    r"|(?:j'ai|on a|nous avons)\s+(?:mang[ée]|pris|bu)\s+"  # French
    r"|(?:أكلت|اكلت|تناولت|شربت|أكلنا|اكلنا)\s+"  # Arabic
    r")?",
    re.IGNORECASE,
)
# Chinese: "我今天午餐吃了 ..." -> "..."
_ZH_FILLER = re.compile(r"^(?:我们?)?(?:今天)?(?:早上|中午|晚上)?(?:早餐|早饭|午餐|午饭|晚餐|晚饭|加餐)?(?:我们?)?"
                        r"(?:吃了|吃的|喝了|吃|喝)?[:\s]*")
# A new amount after a word starts a new food: "150g chicken 200g rice" -> two foods.
_NEW_ITEM = re.compile(r"(?<=[A-Za-zÀ-ɏ؀-ۿ])\s+(?=\d)|(?<=[㐀-鿿])\s*(?=\d)")


def clean_line(text: str) -> str:
    text = _FILLER.sub("", text.strip(), count=1).strip()
    if _HAS_CJK.search(text):
        text = _ZH_FILLER.sub("", text, count=1).strip()
    return text


def split_lines(text: str) -> list[str]:
    out = []
    for part in _SPLIT.split(prepare(text)):
        part = clean_line(part or "")
        if not part:
            continue
        out.extend(p.strip() for p in _NEW_ITEM.split(part) if p.strip())
    return out


# ---- Chinese: "150克烤鸡胸肉", "两个鸡蛋", "一杯米饭" (no spaces) ------------------------------------------
_ZH_DIGIT = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_ZH_UNITS = {
    "公斤": "kg", "千克": "kg", "克": "g", "杯": "cup", "片": "slice", "块": "piece", "汤匙": "tbsp", "大勺": "tbsp",
    "勺": "tbsp", "茶匙": "tsp", "小勺": "tsp", "盎司": "oz", "磅": "lb",
    "个": None, "颗": None, "只": None, "根": None, "条": None,  # counters: use the food's default portion
    "碗": "碗", "份": "份", "盘": "盘",  # no fixed size: the user is asked for grams
}
_ZH_LINE = re.compile(
    r"^(?P<qty>\d+(?:[.,]\d+)?|\d+/\d+|[零一二两三四五六七八九十]+半?|半)\s*"
    r"(?P<unit>" + "|".join(sorted(_ZH_UNITS, key=len, reverse=True)) + r")?\s*(?:的)?\s*(?P<food>.*)$")


def _zh_number(s: str) -> Decimal:
    if re.fullmatch(r"\d+(?:[.,]\d+)?|\d+/\d+", s):
        return _to_decimal(s)
    half = Decimal("0.5") if s.endswith("半") else Decimal(0)
    s = s.rstrip("半")
    if not s:
        return half
    if "十" in s:
        tens, _, ones = s.partition("十")
        value = (_ZH_DIGIT.get(tens, 1) if tens else 1) * 10 + (_ZH_DIGIT.get(ones, 0) if ones else 0)
    else:
        value = _ZH_DIGIT[s]
    return Decimal(value) + half


def _parse_zh(text: str, line: str) -> ParsedLine | None:
    m = _ZH_LINE.match(line)
    if not m or not m.group("qty"):
        return None
    try:
        qty = _zh_number(m.group("qty"))
    except (KeyError, InvalidOperation, ValueError):
        return ParsedLine(text, None, None, line, problem="quantity_invalid")
    unit = _ZH_UNITS.get(m.group("unit")) if m.group("unit") else None
    food = m.group("food").strip()
    if not food:
        return ParsedLine(text, qty, unit, "", problem="food_missing")
    return ParsedLine(text, qty, unit, food)


# ---- every other language ------------------------------------------------------------------------------
def _first_is_unit(word: str) -> bool:
    u = normalize_unit(word)
    return u in PORTION_WORDS or u in MASS_UNITS_G and u != "g"


def has_any_amount(text: str) -> bool:
    """True if any line starts with an amount (so it looks like food, not a question)."""
    for line in split_lines(text):
        if _HAS_CJK.search(line) and _ZH_LINE.match(line) and _ZH_LINE.match(line).group("qty"):
            return True
        words = line.split()
        first = words[0].lower() if words else ""
        if first in _NUMBER_WORDS or _QTY.match(line) or (len(words) > 1 and _first_is_unit(first)):
            return True
    return False


def parse_line(text: str) -> ParsedLine:
    raw = prepare(text).strip()
    if _HAS_CJK.search(raw):
        zh = _parse_zh(text, raw)
        if zh is not None:
            return zh
    words = raw.split()
    if words and words[0].lower() in _NUMBER_WORDS:
        raw = _NUMBER_WORDS[words[0].lower()] + " " + " ".join(words[1:])
    elif len(words) > 1 and _first_is_unit(words[0]):  # "كوب أرز" / "cup rice" = one cup
        raw = "1 " + raw

    m = _QTY.match(raw)
    if not m:
        return ParsedLine(text, None, None, raw, problem="quantity_missing")
    try:
        qty = _to_decimal(m.group("qty"))
    except (InvalidOperation, ValueError):
        return ParsedLine(text, None, None, raw, problem="quantity_invalid")

    rest_words = m.group("rest").strip().split()
    unit = None
    if rest_words:
        if rest_words[0] in _COUNT_WORDS:
            rest_words = rest_words[1:]
        else:
            cand = normalize_unit(rest_words[0])
            if cand in MASS_UNITS_G or cand in PORTION_WORDS:
                unit = cand
                rest_words = rest_words[1:]
    if rest_words and rest_words[0].lower() in _LINK_WORDS:
        rest_words = rest_words[1:]
    if rest_words and re.match(r"^[dl]'", rest_words[0], re.IGNORECASE):  # French "d'avoine", "l'huile"
        rest_words[0] = rest_words[0][2:]
    food_query = " ".join(rest_words)
    if not food_query:
        return ParsedLine(text, qty, unit, "", problem="food_missing")
    return ParsedLine(text, qty, unit, food_query)

"""Food lookup and seed loading."""
import csv
import re
import unicodedata
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.foods.models import Food, FoodPortion

SEED_FILE = Path(__file__).parent / "data" / "dev_seed_foods.csv"
SEED_SOURCE = "DEV_SEED_UNVERIFIED"
SEED_VERSION = "dev-2026-11-06"


def normalize(text: str) -> str:
    """lower-case, strip accents, keep letters/digits/apostrophes, single spaces."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9' ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def build_search_text(terms: list[str]) -> str:
    """'| chicken breast skinless raw | chicken |' - padded so lookups can match whole words and exact terms."""
    return "|" + "|".join(f" {t} " for t in terms if t) + "|"


def _terms(search_text: str) -> list[str]:
    return [t.strip() for t in search_text.split("|") if t.strip()]


def _token_variants(tok: str) -> list[str]:
    out = [tok]
    if len(tok) > 3 and tok.endswith("es"):
        out.append(tok[:-2])
    if len(tok) > 2 and tok.endswith("s"):
        out.append(tok[:-1])
    return out


def search_foods(db: Session, query: str, limit: int = 20) -> list[Food]:
    """Every word in the query must start a word in the food's name or aliases (simple plural handling).
    Word-start matching means "oil" finds olive oil but not "boiled" lentils."""
    tokens = normalize(query).split()
    if not tokens:
        return []
    stmt = select(Food)
    for tok in tokens:
        variants = _token_variants(tok)
        cond = Food.search_text.contains(f" {variants[0]}")
        for v in variants[1:]:
            cond = cond | Food.search_text.contains(f" {v}")
        stmt = stmt.where(cond)
    foods = list(db.scalars(stmt.order_by(Food.name).limit(200)).all())

    # Rank: exact alias/name hit first, then shorter names.
    q = " ".join(tokens)

    def rank(f: Food):
        exact = q in _terms(f.search_text)
        return (0 if exact else 1, len(f.name))

    foods.sort(key=rank)
    return foods[:limit]


def exact_matches(db: Session, query: str) -> list[Food]:
    """Foods whose name or one alias equals the query exactly (after normalizing)."""
    q = normalize(query)
    hits = []
    for f in search_foods(db, query, limit=50):
        if q in _terms(f.search_text):
            hits.append(f)
    return hits


def _state_word(state: str) -> str:
    # lets "chicken cooked" or "raw chicken" find the right record
    return f" {state}" if state in ("raw", "cooked") else ""


def suggest_foods(db: Session, query: str, limit: int = 6) -> list[Food]:
    """Typo help: 'chicj' -> foods with 'chicken'. Only used to ASK the user, never to save silently."""
    import difflib

    vocab = set()
    for text in db.scalars(select(Food.search_text)).all():
        for term in _terms(text):
            vocab.update(term.split())
    fixed = []
    changed = False
    for tok in normalize(query).split():
        if any(v in vocab for v in _token_variants(tok)):
            fixed.append(tok)
            continue
        match = difflib.get_close_matches(tok, vocab, n=1, cutoff=0.6)
        if match:
            fixed.append(match[0])
            changed = True
        else:
            fixed.append(tok)
    if not changed:
        return []
    return search_foods(db, " ".join(fixed), limit)


def _parse_portions(spec: str) -> list[tuple[str, Decimal, bool]]:
    out = []
    for part in filter(None, (spec or "").split("|")):
        unit, grams = part.split(":")
        default = grams.endswith("*")
        out.append((unit.strip().lower(), Decimal(grams.rstrip("*")), default))
    return out


def _seed_terms(row: dict) -> str:
    aliases = [normalize(a) for a in row["aliases"].split("|") if a.strip()]
    labels = [normalize(row[k]) for k in ("label_en", "label_so", "label_es") if row.get(k)]
    return build_search_text([normalize(row["name"]) + _state_word(row["state"])] + aliases + labels)


def _seed_labels(row: dict) -> dict:
    return {lang: row[f"label_{lang}"] for lang in ("en", "so", "es") if row.get(f"label_{lang}")}


def load_seed_foods(db: Session, path: Path = SEED_FILE) -> int:
    """Insert seed foods that aren't present yet (matched by code). Safe to run many times.
    For foods already there, refresh names and search words only; nutrient values are never changed here."""
    existing = {f.code: f for f in db.scalars(select(Food)).all()}
    added = 0
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["code"] in existing:
                f = existing[row["code"]]
                f.search_text = _seed_terms(row)
                f.display_names = _seed_labels(row)
                continue
            food = Food(
                code=row["code"],
                name=row["name"],
                search_text=_seed_terms(row),
                display_names=_seed_labels(row),
                state=row["state"],
                kcal_per_100g=Decimal(row["kcal"]),
                protein_g_per_100g=Decimal(row["protein_g"]),
                carbs_g_per_100g=Decimal(row["carbs_g"]),
                fat_g_per_100g=Decimal(row["fat_g"]),
                fiber_g_per_100g=Decimal(row["fiber_g"]) if row["fiber_g"] else None,
                source=SEED_SOURCE,
                source_ref="Development placeholder values; replace with a reviewed USDA FoodData Central import",
                data_version=SEED_VERSION,
                verified=False,
            )
            for unit, grams, default in _parse_portions(row["portions"]):
                food.portions.append(FoodPortion(unit=unit, grams=grams, is_default=default))
            db.add(food)
            added += 1
    db.commit()
    return added


if __name__ == "__main__":  # python -m app.foods.service
    from app.core.db import get_sessionmaker

    with get_sessionmaker()() as session:
        n = load_seed_foods(session)
        print(f"seed foods: {n} added")

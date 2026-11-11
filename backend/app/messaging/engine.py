"""The conversation engine: one brain for the in-app chat and for text messages.

What a user can send (English / Somali / Spanish):
    "lunch: 1 cup rice, 2 eggs"     -> a meal DRAFT with calories, nothing saved yet
    YES  / HAA   / SI               -> save the latest draft
    NO   / MAYA  / NO               -> throw the draft away
    TODAY/ MAANTA/ HOY              -> today's totals vs goal
    UNDO / TIRTIR/ DESHACER         -> remove the last saved meal from today
    HELP / CAAWI / AYUDA            -> how to use it
    STOP / START                    -> (text messages only) turn texts off / on. Carriers require English words.

Replies come from app/i18n.py in the user's language.
Rule-based, no AI: unclear foods are flagged and the user is asked, never guessed.
"""
import re
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.core.errors import AppError
from app.foods.models import Food
from app.i18n import lang_of, meal_name, t, unit_name
from app.meals import service as meals
from app.meals.models import MealProposal
from app.meals.nutrition import sum_items
from app.meals.schemas import ProposalIn
from app.meals.text_parser import has_any_amount
from app.targets.models import NutritionTarget
from app.users.models import User

YES = {"yes", "y", "ok", "okay", "save", "confirm", "haa", "ha", "haye", "si", "sí", "vale", "guardar"}
NO = {"no", "n", "nope", "discard", "maya", "may", "cancelar"}
TODAY = {"today", "total", "totals", "summary", "maanta", "hoy", "resumen"}
HELP = {"help", "?", "commands", "caawi", "caawimaad", "ayuda"}
UNDO = {"undo", "tirtir", "deshacer", "borrar"}
GREETINGS = {
    "hi", "hello", "hey", "how", "how are you", "good morning", "good evening", "thanks", "thank you", "ok thanks",
    "salaam", "salam", "asc", "salaan", "assalamu alaikum", "iska warran", "nabad", "mahadsanid", "subax wanaagsan",
    "hola", "buenos dias", "buenos días", "buenas", "buenas tardes", "buenas noches", "gracias", "que tal", "qué tal",
}
# Standard US carrier opt-out words. On SMS, CANCEL means STOP (industry rule), not "cancel draft".
STOP = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit", "jooji", "parar", "alto"}
START = {"start", "unstop", "subscribe", "bilow", "iniciar"}

DRAFT_MAX_AGE = timedelta(hours=3)
_MEALS_RE = r"breakfast|lunch|dinner|supper|snack|quraac|qado|casho|desayuno|almuerzo|cena|merienda"
_MEAL_PREFIX = re.compile(rf"^\s*({_MEALS_RE})\s*[:\-]\s*", re.IGNORECASE)
_MEAL_WORD = re.compile(rf"\b({_MEALS_RE})\b", re.IGNORECASE)
_MEAL_WORDS = {"supper": "dinner", "quraac": "breakfast", "qado": "lunch", "casho": "dinner",
               "desayuno": "breakfast", "almuerzo": "lunch", "cena": "dinner", "merienda": "snack"}


def _n(x) -> str:
    """Short number: 205.40 -> 205, 18.62 -> 18.6"""
    d = Decimal(x)
    return f"{d:.0f}" if abs(d) >= 100 else f"{d:.1f}".rstrip("0").rstrip(".")


def _meal_type_for(now_local: datetime) -> str:
    h = now_local.hour + now_local.minute / 60
    if 4 <= h < 10.5:
        return "breakfast"
    if 10.5 <= h < 15:
        return "lunch"
    if 17 <= h < 21.5:
        return "dinner"
    return "snack"


def food_label(food: Food | None, lang: str, fallback: str) -> str:
    names = (food.display_names if food is not None else None) or {}
    return names.get(lang) or names.get("en") or fallback


def _latest_draft(db: Session, user: User) -> MealProposal | None:
    stmt = (select(MealProposal)
            .where(MealProposal.user_id == user.id, MealProposal.status.in_(("pending", "needs_input")),
                   MealProposal.created_at > utcnow() - DRAFT_MAX_AGE)
            .order_by(MealProposal.created_at.desc()).limit(1))
    return db.scalar(stmt)


def _qty_text(lang: str, qty, unit: str) -> str:
    many = Decimal(qty) != 1
    return f"{_n(qty)} {unit_name(lang, unit, many)}"


def draft_text(db: Session, p: MealProposal, lang: str) -> str:
    lines = []
    if p.items:
        lines.append(t(lang, "draft_head", meal=meal_name(lang, p.meal_type)))
        for it in p.items:
            label = food_label(db.get(Food, it.food_id), lang, it.food_name)
            lines.append(t(lang, "item", food=label, qty=_qty_text(lang, it.quantity, it.unit), kcal=_n(it.kcal)))
        tot = sum_items(p.items)
        lines.append(t(lang, "total", kcal=_n(tot["kcal"]), protein=_n(tot["protein_g"])))
    if p.unresolved:
        if lines:
            lines.append("")
        lines.append(t(lang, "need_help"))
        for u in p.unresolved:
            names = [food_label(db.get(Food, c["food_id"]), lang, c["name"]) for c in u.get("candidates", [])[:3]]
            options = t(lang, "or").join(names)
            key = f"p_{u['problem']}"
            if u["problem"] in ("food_ambiguous", "food_typo") and not names:
                key = "p_food_not_found"
            lines.append("- " + t(lang, key, text=u["text"], options=options))
        lines.append(t(lang, "resend"))
    elif p.status == "pending":
        lines.append(t(lang, "ask_save"))
    return "\n".join(lines)


def today_text(db: Session, user: User) -> str:
    lang = lang_of(user)
    day = meals.local_date(utcnow(), user.timezone)
    rows = meals.list_meals(db, user, day)
    tot = sum_items([i for m in rows for i in m.items])
    lines = [t(lang, "today", n=len(rows), meals=t(lang, "meals_one" if len(rows) == 1 else "meals_many"),
               kcal=_n(tot["kcal"]), protein=_n(tot["protein_g"]))]
    target = db.get(NutritionTarget, user.id)
    if target is None:
        lines.append(t(lang, "no_goal"))
        return "\n".join(lines)
    left = Decimal(target.calories_kcal) - tot["kcal"]
    if left >= 0:
        lines.append(t(lang, "goal_left", goal=_n(target.calories_kcal), left=_n(left)))
    else:
        lines.append(t(lang, "goal_over", goal=_n(target.calories_kcal), over=_n(-left)))
    if target.protein_g is not None:
        p_left = max(Decimal(0), Decimal(target.protein_g) - tot["protein_g"])
        lines.append(t(lang, "protein_left", left=_n(p_left), goal=_n(target.protein_g)))
    return "\n".join(lines)


def handle(db: Session, user: User, text: str, channel: str) -> str:
    """Return the reply text. Caller records messages and commits."""
    lang = lang_of(user)
    raw = (text or "").strip()
    word = re.sub(r"\s+", " ", raw.lower()).strip(" .!¡?¿,")

    if not word or word in HELP or raw.strip() == "?":
        return t(lang, "help")

    if channel == "sms" and word in STOP:
        user.sms_opted_out_at = utcnow()
        return t(lang, "stop")
    if channel == "sms" and word in START:
        user.sms_opted_out_at = None
        if user.sms_opt_in_at is None:
            user.sms_opt_in_at = utcnow()
        return t(lang, "start")

    if word in YES:
        draft = _latest_draft(db, user)
        if draft is None:
            return t(lang, "nothing_to_save")
        try:
            meal, _ = meals.confirm_proposal(db, user, draft.id)
        except AppError:
            return t(lang, "cant_save")
        tot = sum_items(meal.items)
        saved = t(lang, "saved", meal=meal_name(lang, meal.meal_type).capitalize(), kcal=_n(tot["kcal"]))
        return saved + "\n" + today_text(db, user)

    if word in NO:
        draft = _latest_draft(db, user)
        if draft is None:
            return t(lang, "no_draft")
        meals.discard_proposal(db, user, draft.id)
        return t(lang, "cancelled")

    if word in TODAY:
        return today_text(db, user)

    if word in GREETINGS:
        return t(lang, "greet", name=user.display_name)

    if word in UNDO:
        day = meals.local_date(utcnow(), user.timezone)
        rows = meals.list_meals(db, user, day)
        if not rows:
            return t(lang, "undo_none")
        last = max(rows, key=lambda m: m.confirmed_at)
        meals.delete_meal(db, user, last.id)
        return t(lang, "undo_done", meal=meal_name(lang, last.meal_type)) + "\n" + today_text(db, user)

    # Anything else: treat it as a meal description.
    meal_type = None
    m = _MEAL_PREFIX.match(raw)
    if m:
        w = m.group(1).lower()
        meal_type = _MEAL_WORDS.get(w, w)
        raw = raw[m.end():]
    if meal_type is None:
        found = _MEAL_WORD.search(raw)  # "for lunch I had ...", "en el almuerzo comí ..."
        if found:
            w = found.group(1).lower()
            meal_type = _MEAL_WORDS.get(w, w)
    if meal_type is None:
        meal_type = _meal_type_for(utcnow().astimezone(ZoneInfo(user.timezone)))

    # No amount anywhere: probably a question or a chat, not a meal. Don't make an empty draft.
    if not has_any_amount(raw):
        return t(lang, "no_amount")

    # A new meal replaces any older draft, so YES always means the latest thing the user saw.
    old = _latest_draft(db, user)
    if old is not None:
        meals.discard_proposal(db, user, old.id)
    try:
        p = meals.create_proposal(db, user, ProposalIn(meal_type=meal_type, text=raw[:1000]))
    except (AppError, ValueError):
        return t(lang, "cant_read")
    return draft_text(db, p, lang)

"""Decide which reminders are due and send them.

A reminder is due when, in the user's time zone:
  * today is one of its days, and
  * the time is at or after at_time but less than 2 hours after it (no 3 a.m. surprises after downtime), and
  * it hasn't been sent today.
If skip_if_logged is on and a meal of that type is already saved today, it's marked done without sending.
"""
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.i18n import lang_of, t
from app.meals.models import Meal
from app.messaging import service as msg
from app.reminders.models import Reminder
from app.users.models import User

log = logging.getLogger("dhai.reminders")
SEND_WINDOW = timedelta(hours=2)



def reminder_text(r: Reminder, lang: str = "en") -> str:
    return r.message or t(lang, f"rem_{r.label}" if r.label in ("breakfast", "lunch", "dinner", "snack") else "rem_custom")


def is_due(r: Reminder, now_local: datetime) -> bool:
    if not r.enabled or now_local.weekday() not in (r.days or []):
        return False
    if r.last_sent_on == now_local.date():
        return False
    start = datetime.combine(now_local.date(), r.at_time, tzinfo=now_local.tzinfo)
    return start <= now_local < start + SEND_WINDOW


def already_logged(db: Session, user: User, r: Reminder, day: date) -> bool:
    if r.label not in ("breakfast", "lunch", "dinner", "snack"):
        return False
    return db.scalar(select(Meal.id).where(Meal.user_id == user.id, Meal.nutrition_date == day,
                                           Meal.meal_type == r.label, Meal.deleted_at.is_(None)).limit(1)) is not None


def deliver(db: Session, user: User, r: Reminder) -> list[str]:
    """Send on each channel the user allows. Returns channels actually used."""
    used = []
    text = reminder_text(r, lang_of(user))
    for ch in r.channels or ["in_app"]:
        try:
            msg.send(db, user, ch, text, kind="reminder")
            used.append(ch)
        except msg.NotAllowed:
            continue  # e.g. texts turned off: skip SMS quietly, in-app still goes out
    return used


def run_due(db: Session, now: datetime | None = None) -> int:
    """Check all reminders once. Returns how many were sent."""
    now = now or utcnow()
    sent = 0
    # SKIP LOCKED: if two API containers ever run, they never send the same reminder twice.
    rows = db.execute(select(Reminder, User).join(User, User.id == Reminder.user_id)
                      .where(Reminder.enabled.is_(True), User.is_active.is_(True))
                      .with_for_update(of=Reminder, skip_locked=True)).all()
    for r, user in rows:
        now_local = now.astimezone(ZoneInfo(user.timezone))
        if not is_due(r, now_local):
            continue
        r.last_sent_on = now_local.date()
        if r.skip_if_logged and already_logged(db, user, r, now_local.date()):
            continue
        if deliver(db, user, r):
            sent += 1
    db.commit()
    return sent

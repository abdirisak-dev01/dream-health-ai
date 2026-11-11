import uuid
from datetime import time
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.db import get_db
from app.core.errors import AppError, not_found
from app.core.security import get_current_user
from app.i18n import lang_of
from app.reminders import service
from app.reminders.models import Reminder
from app.users.models import User

router = APIRouter(prefix="/v1/reminders", tags=["reminders"])
MAX_REMINDERS = 10


class ReminderIn(BaseModel):
    label: Literal["breakfast", "lunch", "dinner", "snack", "custom"]
    at_time: time = Field(examples=["12:30"])
    days: list[int] = Field(default=[0, 1, 2, 3, 4, 5, 6], min_length=1, max_length=7,
                            description="0=Monday ... 6=Sunday")
    channels: list[Literal["in_app", "sms"]] = Field(default=["in_app"], min_length=1, max_length=2)
    message: str | None = Field(default=None, max_length=160)
    skip_if_logged: bool = True
    enabled: bool = True

    @field_validator("days")
    @classmethod
    def _days(cls, v):
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("days must be 0 (Mon) to 6 (Sun)")
        return sorted(set(v))

    @field_validator("channels")
    @classmethod
    def _channels(cls, v):
        return list(dict.fromkeys(v))

    @field_validator("at_time")
    @classmethod
    def _minute(cls, v: time):
        return v.replace(second=0, microsecond=0, tzinfo=None)


class ReminderOut(ReminderIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    text: str


def _out(r: Reminder, lang: str = "en") -> ReminderOut:
    return ReminderOut(id=r.id, label=r.label, at_time=r.at_time, days=r.days, channels=r.channels,
                       message=r.message, skip_if_logged=r.skip_if_logged, enabled=r.enabled,
                       text=service.reminder_text(r, lang))


def _own(db: Session, user: User, rid: uuid.UUID) -> Reminder:
    r = db.scalar(select(Reminder).where(Reminder.id == rid, Reminder.user_id == user.id))
    if r is None:
        raise not_found("Reminder")
    return r


def _check_sms(user: User, body: ReminderIn):
    if "sms" in body.channels and not user.can_receive_sms:
        raise AppError(409, "texts_off", "Turn on text messages in Settings (verify your phone) to use SMS reminders")


@router.get("", response_model=list[ReminderOut], summary="My reminders")
def list_reminders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Reminder).where(Reminder.user_id == user.id).order_by(Reminder.at_time)).all()
    return [_out(r, lang_of(user)) for r in rows]


@router.post("", response_model=ReminderOut, status_code=201, summary="Add a reminder")
def create_reminder(body: ReminderIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _check_sms(user, body)
    count = len(db.scalars(select(Reminder.id).where(Reminder.user_id == user.id)).all())
    if count >= MAX_REMINDERS:
        raise AppError(409, "too_many_reminders", f"Up to {MAX_REMINDERS} reminders")
    r = Reminder(user_id=user.id, **body.model_dump())
    db.add(r)
    db.flush()
    audit.record(db, user_id=user.id, action="reminder.created", entity_type="reminder", entity_id=r.id,
                 after={"label": r.label, "at_time": r.at_time.isoformat(), "channels": r.channels})
    db.commit()
    return _out(r, lang_of(user))


@router.put("/{reminder_id}", response_model=ReminderOut, summary="Change a reminder")
def update_reminder(reminder_id: uuid.UUID, body: ReminderIn, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    r = _own(db, user, reminder_id)
    _check_sms(user, body)
    for k, v in body.model_dump().items():
        setattr(r, k, v)
    r.last_sent_on = None
    audit.record(db, user_id=user.id, action="reminder.updated", entity_type="reminder", entity_id=r.id,
                 after={"label": r.label, "at_time": r.at_time.isoformat(), "enabled": r.enabled})
    db.commit()
    return _out(r, lang_of(user))


@router.delete("/{reminder_id}", status_code=204, summary="Delete a reminder")
def delete_reminder(reminder_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _own(db, user, reminder_id)
    db.delete(r)
    audit.record(db, user_id=user.id, action="reminder.deleted", entity_type="reminder", entity_id=reminder_id)
    db.commit()
    return Response(status_code=204)


@router.post("/{reminder_id}/send-now", summary="Send this reminder right now (for testing)")
def send_now(reminder_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _own(db, user, reminder_id)
    used = service.deliver(db, user, r)
    db.commit()
    return {"sent_on": used}

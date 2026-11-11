import hashlib
import hmac
import re
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.config import get_settings
from app.core.db import get_db, utcnow
from app.core.errors import AppError
from app.core.security import get_current_user
from app.messaging import engine
from app.messaging import service as msg
from app.messaging.engine import START
from app.i18n import lang_of, t
from app.users.models import User

chat_router = APIRouter(prefix="/v1", tags=["chat & messages"])
phone_router = APIRouter(prefix="/v1/me/phone", tags=["phone & text consent"])
dev_router = APIRouter(prefix="/v1/dev", tags=["test mode (fake phone)"])


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    channel: str
    direction: str
    kind: str
    body: str
    status: str
    created_at: datetime


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class ChatOut(BaseModel):
    reply: str
    messages: list[MessageOut]


# ---- in-app chat -------------------------------------------------------------------

@chat_router.post("/chat", response_model=ChatOut, summary="Talk to the app (same brain as text messages)")
def chat(body: ChatIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m_in = msg.record_in(db, user, "in_app", body.text)
    db.flush()
    reply = engine.handle(db, user, body.text, "in_app")
    m_out = msg.send(db, user, "in_app", reply)
    db.commit()
    return ChatOut(reply=reply, messages=[MessageOut.model_validate(m_in), MessageOut.model_validate(m_out)])


@chat_router.get("/messages", response_model=list[MessageOut], summary="My messages on one channel")
def list_messages(channel: Literal["in_app", "sms"] = "in_app", after: uuid.UUID | None = None,
                  limit: int = Query(100, ge=1, le=200),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return msg.list_messages(db, user, channel, after, limit)


# ---- phone number + consent --------------------------------------------------------------

_E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_phone(raw: str) -> str:
    s = re.sub(r"[\s\-().]", "", raw or "")
    if s.startswith("00"):
        s = "+" + s[2:]
    if re.fullmatch(r"\d{10}", s):  # US number without country code
        s = "+1" + s
    if re.fullmatch(r"1\d{10}", s):
        s = "+" + s
    if not _E164.match(s):
        raise AppError(422, "phone_invalid", "Use international format, e.g. +16125550100 or +252612345678")
    return s


def _code_hash(user_id: uuid.UUID, phone: str, code: str) -> str:
    key = get_settings().jwt_secret.encode()
    return hmac.new(key, f"{user_id}|{phone}|{code}".encode(), hashlib.sha256).hexdigest()


class PhoneIn(BaseModel):
    phone: str = Field(min_length=6, max_length=32, examples=["+16125550100"])


class VerifyIn(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")
    agree_to_texts: bool = Field(description="User agrees to get texts (meal replies and reminders). Reply STOP any time.")


class ConsentIn(BaseModel):
    agree_to_texts: bool


class PhoneStatus(BaseModel):
    phone: str | None
    verified: bool
    pending_phone: str | None
    texts_on: bool
    opted_out: bool
    test_mode: bool
    app_number: str


def _status(user: User) -> PhoneStatus:
    s = get_settings()
    return PhoneStatus(phone=user.phone_e164, verified=user.phone_verified_at is not None,
                       pending_phone=user.pending_phone_e164, texts_on=user.can_receive_sms,
                       opted_out=user.sms_opted_out_at is not None, test_mode=s.is_test_mode_messaging,
                       app_number=s.sms_app_number)


@phone_router.get("", response_model=PhoneStatus, summary="My phone and text settings")
def phone_status(user: User = Depends(get_current_user)):
    return _status(user)


@phone_router.post("", response_model=PhoneStatus, summary="Step 1: add a phone number (we text you a 6-digit code)")
def start_phone(body: PhoneIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    phone = normalize_phone(body.phone)
    taken = db.scalar(select(User.id).where(User.phone_e164 == phone, User.id != user.id))
    if taken:
        raise AppError(409, "phone_taken", "This number is linked to another account")
    code = f"{secrets.randbelow(10**6):06d}"
    user.pending_phone_e164 = phone
    user.phone_code_hash = _code_hash(user.id, phone, code)
    user.phone_code_expires_at = utcnow() + timedelta(minutes=get_settings().phone_code_minutes)
    user.phone_code_attempts = 0
    msg.send(db, user, "sms", t(lang_of(user), "code", code=code, minutes=get_settings().phone_code_minutes),
             kind="verification", to_override=phone)
    audit.record(db, user_id=user.id, action="phone.code_sent", entity_type="user", entity_id=user.id)
    db.commit()
    return _status(user)


@phone_router.post("/verify", response_model=PhoneStatus, summary="Step 2: type the code to confirm the number")
def verify_phone(body: VerifyIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.pending_phone_e164 or not user.phone_code_hash:
        raise AppError(409, "no_code", "Ask for a code first")
    if user.phone_code_expires_at is None or user.phone_code_expires_at < utcnow():
        raise AppError(409, "code_expired", "The code expired. Ask for a new one.")
    if user.phone_code_attempts >= 5:
        raise AppError(429, "too_many_attempts", "Too many wrong codes. Ask for a new one.")
    if not hmac.compare_digest(_code_hash(user.id, user.pending_phone_e164, body.code), user.phone_code_hash):
        user.phone_code_attempts += 1
        db.commit()
        raise AppError(422, "code_wrong", "That code is not right")
    if db.scalar(select(User.id).where(User.phone_e164 == user.pending_phone_e164, User.id != user.id)):
        raise AppError(409, "phone_taken", "This number is linked to another account")
    now = utcnow()
    user.phone_e164 = user.pending_phone_e164
    user.phone_verified_at = now
    user.pending_phone_e164 = user.phone_code_hash = user.phone_code_expires_at = None
    user.phone_code_attempts = 0
    user.sms_opted_out_at = None
    user.sms_opt_in_at = now if body.agree_to_texts else None
    audit.record(db, user_id=user.id, action="phone.verified", entity_type="user", entity_id=user.id,
                 after={"texts_on": body.agree_to_texts})
    if body.agree_to_texts:
        msg.send(db, user, "sms", t(lang_of(user), "texts_on"), kind="system")
    db.commit()
    return _status(user)


@phone_router.put("/consent", response_model=PhoneStatus, summary="Turn text messages on or off")
def set_consent(body: ConsentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.phone_verified_at is None:
        raise AppError(409, "phone_not_verified", "Verify a phone number first")
    before = {"texts_on": user.can_receive_sms}
    if body.agree_to_texts:
        user.sms_opt_in_at = utcnow()
        user.sms_opted_out_at = None
    else:
        user.sms_opt_in_at = None
    audit.record(db, user_id=user.id, action="phone.consent_changed", entity_type="user", entity_id=user.id,
                 before=before, after={"texts_on": user.can_receive_sms})
    db.commit()
    return _status(user)


@phone_router.delete("", response_model=PhoneStatus, summary="Remove my phone number")
def remove_phone(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.phone_e164 = user.phone_verified_at = user.sms_opt_in_at = user.sms_opted_out_at = None
    user.pending_phone_e164 = user.phone_code_hash = user.phone_code_expires_at = None
    audit.record(db, user_id=user.id, action="phone.removed", entity_type="user", entity_id=user.id)
    db.commit()
    return _status(user)


# ---- test mode: the fake phone ----------------------------------------------------------------

class FakeTextIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


def handle_incoming_sms(db: Session, user: User, text: str) -> None:
    """What happens when a text arrives from a user's verified number.
    Used by the fake phone now, and by the real provider webhook at launch."""
    msg.record_in(db, user, "sms", text, from_address=user.phone_e164)
    db.flush()
    word = text.strip().lower().strip(" .!")
    if user.sms_opted_out_at is not None and word not in START:
        db.commit()  # after STOP: stay silent until START
        return
    reply = engine.handle(db, user, text, "sms")
    if user.sms_opted_out_at is not None:  # they just sent STOP: one final confirmation is allowed
        msg.send(db, user, "sms", reply, kind="system")
    elif user.can_receive_sms:
        msg.send(db, user, "sms", reply)
    else:
        msg.send(db, user, "sms", t(lang_of(user), "start_needed"), kind="system")
    db.commit()


def _require_test_mode():
    if not get_settings().is_test_mode_messaging:
        raise AppError(404, "not_found", "Not found")


@dev_router.post("/fake-phone/send", response_model=list[MessageOut],
                 summary="TEST MODE: text the app from your fake phone")
def fake_phone_send(body: FakeTextIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_test_mode()
    if user.phone_e164 is None:
        raise AppError(409, "phone_not_verified", "Add and verify a phone number in Settings first")
    last = db.scalar(select(msg.Message.id).where(msg.Message.user_id == user.id, msg.Message.channel == "sms")
                     .order_by(msg.Message.created_at.desc()).limit(1))
    handle_incoming_sms(db, user, body.text)
    return msg.list_messages(db, user, "sms", after=last)

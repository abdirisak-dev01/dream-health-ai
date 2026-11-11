"""Send and record messages. Every send goes through here, so consent rules live in one place."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.i18n import sms_safe
from app.messaging.models import Message
from app.messaging.providers import get_sms_provider
from app.users.models import User


class NotAllowed(Exception):
    pass


def record_in(db: Session, user: User | None, channel: str, body: str, from_address: str | None = None) -> Message:
    m = Message(user_id=user.id if user else None, channel=channel, direction="in", kind="chat", body=body,
                from_address=from_address, to_address=get_settings().sms_app_number if channel == "sms" else None,
                status="received")
    db.add(m)
    return m


def send(db: Session, user: User, channel: str, body: str, kind: str = "chat",
         to_override: str | None = None) -> Message:
    """Send one message to a user.

    SMS rules: only to a verified, opted-in, not-opted-out number. Two exceptions:
      * kind="verification" goes to the number being verified (to_override)
      * kind="system" confirms a STOP to the number that just sent it
    """
    if channel == "in_app":
        m = Message(user_id=user.id, channel="in_app", direction="out", kind=kind, body=body, status="sent")
        db.add(m)
        return m

    if channel == "sms":
        if kind in ("verification", "system"):
            to = to_override or user.phone_e164
        else:
            if not user.can_receive_sms:
                raise NotAllowed("User has not verified a phone and agreed to texts, or replied STOP")
            to = user.phone_e164
        if not to:
            raise NotAllowed("No phone number")
        body = sms_safe(body)  # keep every text in the cheap GSM-7 alphabet
        result = get_sms_provider().send(to, body)
        m = Message(user_id=user.id, channel="sms", direction="out", kind=kind, body=body, to_address=to,
                    from_address=get_settings().sms_app_number, status=result.status, provider=result.provider,
                    provider_message_id=result.provider_message_id, error=result.error)
        db.add(m)
        return m

    raise NotAllowed(f"Channel {channel} is not available yet")


def list_messages(db: Session, user: User, channel: str, after: uuid.UUID | None = None, limit: int = 100):
    stmt = select(Message).where(Message.user_id == user.id, Message.channel == channel)
    if after is not None:
        pivot = db.scalar(select(Message.created_at).where(Message.id == after, Message.user_id == user.id))
        if pivot is not None:
            stmt = stmt.where(Message.created_at > pivot)
    rows = db.scalars(stmt.order_by(Message.created_at.desc(), Message.id).limit(limit)).all()
    return list(reversed(rows))

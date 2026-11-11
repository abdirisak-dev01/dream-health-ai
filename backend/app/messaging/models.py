import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, utcnow

CHANNELS = ("in_app", "sms", "whatsapp")


class Message(Base):
    """Every message the app sends or receives, on any channel.

    in_app  - the chat box inside the web app
    sms     - text messages (in testing they go to the 'outbox' = the fake phone)
    whatsapp- reserved for launch
    """

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    channel: Mapped[str] = mapped_column(String(16))
    direction: Mapped[str] = mapped_column(String(8))  # in | out
    kind: Mapped[str] = mapped_column(String(16), default="chat")  # chat | reminder | verification | system
    body: Mapped[str] = mapped_column(Text)
    to_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    from_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # simulated = delivered to the fake phone; queued/sent/failed = real provider states
    status: Mapped[str] = mapped_column(String(16), default="sent")
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_messages_user_channel_created", "user_id", "channel", "created_at"),
        CheckConstraint("direction IN ('in','out')", name="ck_messages_direction"),
        CheckConstraint("channel IN ('in_app','sms','whatsapp')", name="ck_messages_channel"),
    )

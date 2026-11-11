"""Write audit events in the same database transaction as the change they describe.

Keep payloads minimal: IDs, numbers and field names. Never passwords, tokens or free-text meal notes.
"""
import uuid
from contextvars import ContextVar
from typing import Any

from sqlalchemy.orm import Session

from app.audit.models import AuditEvent

current_request_id: ContextVar[str | None] = ContextVar("current_request_id", default=None)


def record(
    db: Session,
    *,
    user_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: Any = None,
    before: dict | None = None,
    after: dict | None = None,
) -> AuditEvent:
    ev = AuditEvent(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=None if entity_id is None else str(entity_id),
        before=before,
        after=after,
        request_id=current_request_id.get(),
    )
    db.add(ev)
    return ev

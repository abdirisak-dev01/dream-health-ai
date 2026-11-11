"""Passwords, access tokens, current-user dependency and a simple login limiter."""
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import timedelta

import bcrypt
import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db, utcnow
from app.core.errors import AppError

# ---- passwords -------------------------------------------------------------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


# Used when the email is unknown, so a login attempt takes the same time either way.
_DUMMY_HASH = bcrypt.hashpw(b"timing-equalizer", bcrypt.gensalt(rounds=12)).decode("ascii")


def burn_password_check(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


# ---- tokens ----------------------------------------------------------------

def create_access_token(user_id: uuid.UUID) -> tuple[str, int]:
    s = get_settings()
    now = utcnow()
    expires_in = s.access_token_minutes * 60
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
        "typ": "access",
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm), expires_in


_bearer = HTTPBearer(auto_error=False)


def _unauthorized(msg: str = "Not authenticated") -> AppError:
    return AppError(401, "unauthorized", msg)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
):
    from app.users.models import User  # local import avoids a cycle

    if creds is None or creds.scheme.lower() != "bearer":
        raise _unauthorized()
    s = get_settings()
    try:
        payload = jwt.decode(
            creds.credentials, s.jwt_secret, algorithms=[s.jwt_algorithm], options={"require": ["exp", "sub"]}
        )
        if payload.get("typ") != "access":
            raise _unauthorized("Invalid token")
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError):
        raise _unauthorized("Invalid or expired token")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized("Invalid or expired token")
    return user


# ---- login limiter -----------------------------------------------------------

class LoginLimiter:
    """Counts failed logins per (email, ip). In-memory: resets on restart and is
    per-process. Replace with Redis or DB-backed storage before running more than one API container."""

    def __init__(self):
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _trim(self, key: str, now: float) -> deque[float]:
        window = get_settings().login_window_seconds
        q = self._failures[key]
        while q and now - q[0] > window:
            q.popleft()
        return q

    def is_blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._trim(key, time.monotonic())) >= get_settings().login_max_failures

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            self._trim(key, now).append(now)

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._failures.clear()
            else:
                self._failures.pop(key, None)


login_limiter = LoginLimiter()

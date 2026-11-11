from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.db import get_db
from app.core.errors import AppError
from app.core.security import (
    burn_password_check,
    create_access_token,
    get_current_user,
    hash_password,
    login_limiter,
    verify_password,
)
from app.users.models import User
from app.users.schemas import LoginIn, RegisterIn, TokenOut, UserOut, UserUpdateIn

auth_router = APIRouter(prefix="/v1/auth", tags=["auth"])
me_router = APIRouter(prefix="/v1/me", tags=["me"])


@auth_router.post("/register", response_model=UserOut, status_code=201, summary="Create an account")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise AppError(409, "email_taken", "An account with this email already exists")
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        display_name=body.display_name.strip(),
        timezone=body.timezone,
        preferred_language=body.preferred_language,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "email_taken", "An account with this email already exists")
    audit.record(
        db, user_id=user.id, action="user.registered", entity_type="user", entity_id=user.id,
        after={"timezone": user.timezone, "preferred_language": user.preferred_language},
    )
    db.commit()
    return user


@auth_router.post("/login", response_model=TokenOut, summary="Log in and get an access token")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    email = body.email.lower()
    ip = request.client.host if request.client else "unknown"
    key = f"{email}|{ip}"
    if login_limiter.is_blocked(key):
        raise AppError(429, "too_many_attempts", "Too many failed logins. Try again later.")

    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        burn_password_check(body.password)
        login_limiter.record_failure(key)
        raise AppError(401, "invalid_credentials", "Email or password is incorrect")
    if not verify_password(body.password, user.password_hash) or not user.is_active:
        login_limiter.record_failure(key)
        audit.record(db, user_id=user.id, action="auth.login_failed", entity_type="user", entity_id=user.id)
        db.commit()
        raise AppError(401, "invalid_credentials", "Email or password is incorrect")

    login_limiter.reset(key)
    audit.record(db, user_id=user.id, action="auth.login_succeeded", entity_type="user", entity_id=user.id)
    db.commit()
    token, expires_in = create_access_token(user.id)
    return TokenOut(access_token=token, expires_in=expires_in)


@me_router.get("", response_model=UserOut, summary="My profile")
def get_me(user: User = Depends(get_current_user)):
    return user


@me_router.patch("", response_model=UserOut, summary="Update my profile (name, time zone, language)")
def update_me(body: UserUpdateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        return user
    before = {k: getattr(user, k) for k in changes}
    for k, v in changes.items():
        setattr(user, k, v.strip() if isinstance(v, str) else v)
    audit.record(db, user_id=user.id, action="user.updated", entity_type="user", entity_id=user.id,
                 before=before, after=changes)
    db.commit()
    db.refresh(user)
    return user

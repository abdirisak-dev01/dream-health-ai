import re
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# Languages planned for early pilots. Adding one is a product + localization decision, not a code tweak.
SUPPORTED_LANGUAGES = {"en", "es", "so"}
_LANG_RE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")


def _check_timezone(v: str) -> str:
    try:
        ZoneInfo(v)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("must be an IANA time zone name, e.g. America/Chicago")
    return v


def _check_language(v: str) -> str:
    if not _LANG_RE.match(v) or v.split("-")[0] not in SUPPORTED_LANGUAGES:
        raise ValueError(f"must be one of: {', '.join(sorted(SUPPORTED_LANGUAGES))} (optionally with a region)")
    return v


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)
    timezone: str = "America/Chicago"
    preferred_language: str = "en"

    _tz = field_validator("timezone")(_check_timezone)
    _lang = field_validator("preferred_language")(_check_language)

    @field_validator("password")
    @classmethod
    def _pw_bytes(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 72:
            raise ValueError("must be at most 72 bytes")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    timezone: str
    preferred_language: str
    created_at: datetime


class UserUpdateIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    timezone: str | None = None
    preferred_language: str | None = None

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v):
        return None if v is None else _check_timezone(v)

    @field_validator("preferred_language")
    @classmethod
    def _lang(cls, v):
        return None if v is None else _check_language(v)

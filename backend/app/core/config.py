"""App settings, read from environment variables (see .env.example)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_DEFAULT_SECRET = "dev-only-change-me-dev-only-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"  # development | test | production
    database_url: str = "postgresql+psycopg://dhai:dhai@localhost:5432/dhai"

    jwt_secret: str = DEV_DEFAULT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30

    # Login throttling (simple in-process limiter, good enough for a single-container pilot)
    login_max_failures: int = 5
    login_window_seconds: int = 15 * 60

    # Safety bound: a single meal item above this many grams is rejected as a likely typo
    max_item_grams: int = 5000

    # Text messages. "outbox" = free test mode (fake phone). "twilio" = real texts.
    sms_provider: str = "outbox"
    sms_app_number: str = "+15550001000"  # the number users text in test mode
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from: str = ""
    phone_code_minutes: int = 10

    # Reminders: how often the background checker runs (0 = off, e.g. in tests)
    reminder_tick_seconds: int = 30

    @property
    def is_test_mode_messaging(self) -> bool:
        return self.sms_provider == "outbox" and self.app_env != "production"

    def check_safe_for_env(self) -> None:
        if self.app_env == "production" and self.jwt_secret == DEV_DEFAULT_SECRET:
            raise RuntimeError("JWT_SECRET must be set to a strong random value in production")
        if len(self.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET must be at least 32 characters")


@lru_cache
def get_settings() -> Settings:
    return Settings()

"""Tests run against a real PostgreSQL database (TEST_DATABASE_URL), built with the real migration."""
import os
import uuid

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://dhai:dhai@localhost:5432/dhai_test"
)
os.environ.setdefault("APP_ENV", "test")
os.environ["REMINDER_TICK_SECONDS"] = "0"  # tests run the reminder check by hand
os.environ["SMS_PROVIDER"] = "outbox"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.db import get_engine, get_sessionmaker  # noqa: E402
from app.core.security import login_limiter  # noqa: E402
from app.foods.service import load_seed_foods  # noqa: E402
from app.main import app  # noqa: E402

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USER_TABLES = "messages, reminders, audit_events, meal_items, meals, meal_proposal_items, meal_proposals, nutrition_targets, users"


@pytest.fixture(scope="session", autouse=True)
def database():
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    with get_sessionmaker()() as db:
        load_seed_foods(db)
    yield
    get_engine().dispose()


@pytest.fixture(autouse=True)
def clean_tables():
    with get_engine().begin() as conn:
        conn.execute(text(f"TRUNCATE {USER_TABLES} CASCADE"))
    login_limiter.reset()
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    with get_sessionmaker()() as s:
        yield s


PASSWORD = "correct-horse-battery"


@pytest.fixture
def make_user(client):
    def _make(tz: str = "America/Chicago", lang: str = "en") -> dict:
        email = f"user-{uuid.uuid4().hex[:8]}@example.com"
        r = client.post("/v1/auth/register", json={
            "email": email, "password": PASSWORD, "display_name": "Test", "timezone": tz,
            "preferred_language": lang,
        })
        assert r.status_code == 201, r.text
        r = client.post("/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 200, r.text
        return {"email": email, "id": r.json(), "headers": {"Authorization": f"Bearer {r.json()['access_token']}"}}
    return _make


@pytest.fixture
def food_id(client, make_user):
    """Look up a seed food by its code."""
    from app.foods.models import Food

    def _get(code: str) -> str:
        with get_sessionmaker()() as s:
            return str(s.query(Food).filter_by(code=code).one().id)
    return _get

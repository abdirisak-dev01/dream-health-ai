"""SEC-102 style horizontal access tests: user B must never read or change user A's records.
Every answer is 404 (not 403) so B can't even learn that A's record exists."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.db import get_engine


@pytest.fixture
def two_users_and_a_meal(client, make_user):
    a, b = make_user(), make_user()
    pending = client.post("/v1/meals/proposals", headers=a["headers"], json={"text": "1 apple"}).json()
    confirmed = client.post("/v1/meals/proposals", headers=a["headers"], json={"text": "1 banana"}).json()
    meal = client.post(f"/v1/meals/proposals/{confirmed['id']}/confirm", headers=a["headers"]).json()
    client.put("/v1/me/targets", headers=a["headers"], json={"calories_kcal": 1800})
    return a, b, pending, meal


def test_other_users_records_are_invisible(client, two_users_and_a_meal):
    a, b, pending, meal = two_users_and_a_meal
    hb = b["headers"]
    attempts = [
        client.get(f"/v1/meals/proposals/{pending['id']}", headers=hb),
        client.post(f"/v1/meals/proposals/{pending['id']}/confirm", headers=hb),
        client.post(f"/v1/meals/proposals/{pending['id']}/discard", headers=hb),
        client.get(f"/v1/meals/{meal['id']}", headers=hb),
        client.delete(f"/v1/meals/{meal['id']}", headers=hb),
    ]
    for r in attempts:
        assert r.status_code == 404, r.request.url

    assert client.get("/v1/meals", headers=hb).json() == []
    assert client.get("/v1/days/today/summary", headers=hb).json()["meal_count"] == 0
    assert client.get("/v1/me/targets", headers=hb).status_code == 404
    assert all(e["action"].startswith(("user.", "auth.")) for e in client.get("/v1/audit", headers=hb).json())

    # A's data is untouched
    ha = a["headers"]
    assert client.get(f"/v1/meals/proposals/{pending['id']}", headers=ha).json()["status"] == "pending"
    assert client.get(f"/v1/meals/{meal['id']}", headers=ha).status_code == 200


def test_audit_history_cannot_be_edited_or_deleted(client, make_user):
    make_user()
    for sql in ("UPDATE audit_events SET action = 'tampered'", "DELETE FROM audit_events"):
        with pytest.raises(DBAPIError, match="append-only"):
            with get_engine().begin() as conn:
                conn.execute(text(sql))


def test_audit_never_stores_passwords_or_meal_text(client, make_user):
    u = make_user()
    client.post("/v1/meals/proposals", headers=u["headers"], json={"text": "1 apple secret-note"})
    with get_engine().connect() as conn:
        dump = " ".join(str(r) for r in conn.execute(text("SELECT before, after FROM audit_events")))
    assert "correct-horse" not in dump and "secret-note" not in dump and "$2b$" not in dump

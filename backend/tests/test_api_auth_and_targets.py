from datetime import timedelta

import jwt

from app.core.config import get_settings
from tests.conftest import PASSWORD


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["database"] == "ok"
    assert "X-Request-ID" in r.headers


def test_register_login_me(client, make_user):
    u = make_user(tz="Africa/Mogadishu", lang="so")
    r = client.get("/v1/me", headers=u["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == u["email"]
    assert body["timezone"] == "Africa/Mogadishu"
    assert body["preferred_language"] == "so"
    assert "password_hash" not in body


def test_register_duplicate_email_case_insensitive(client, make_user):
    u = make_user()
    r = client.post("/v1/auth/register", json={"email": u["email"].upper(), "password": PASSWORD,
                                               "display_name": "x"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "email_taken"


def test_register_validation(client):
    bad = [
        {"email": "a@example.com", "password": "short", "display_name": "x"},
        {"email": "not-an-email", "password": PASSWORD, "display_name": "x"},
        {"email": "a@example.com", "password": PASSWORD, "display_name": "x", "timezone": "Mars/Base"},
        {"email": "a@example.com", "password": PASSWORD, "display_name": "x", "preferred_language": "xx"},
    ]
    for body in bad:
        r = client.post("/v1/auth/register", json=body)
        assert r.status_code == 422, body
        assert r.json()["error"]["code"] == "validation_error"


def test_wrong_password_and_unknown_email_look_the_same(client, make_user):
    u = make_user()
    r1 = client.post("/v1/auth/login", json={"email": u["email"], "password": "wrong-password-123"})
    r2 = client.post("/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong-password-123"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json()["error"]["message"] == r2.json()["error"]["message"]


def test_login_throttled_after_repeated_failures(client, make_user):
    u = make_user()
    for _ in range(get_settings().login_max_failures):
        assert client.post("/v1/auth/login", json={"email": u["email"], "password": "wrong-password-1"}
                           ).status_code == 401
    r = client.post("/v1/auth/login", json={"email": u["email"], "password": PASSWORD})
    assert r.status_code == 429


def test_requests_without_or_with_bad_tokens_are_rejected(client, make_user):
    u = make_user()
    s = get_settings()
    assert client.get("/v1/me").status_code == 401
    assert client.get("/v1/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401
    forged = jwt.encode({"sub": u["id"]["access_token"][:5], "exp": 9999999999, "typ": "access"},
                        "another-secret-another-secret-another", algorithm="HS256")
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    me = client.get("/v1/me", headers=u["headers"]).json()
    from app.core.db import utcnow
    expired = jwt.encode({"sub": me["id"], "exp": utcnow() - timedelta(minutes=1), "typ": "access"},
                         s.jwt_secret, algorithm=s.jwt_algorithm)
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_update_profile(client, make_user):
    u = make_user()
    r = client.patch("/v1/me", headers=u["headers"], json={"timezone": "America/New_York", "preferred_language": "es"})
    assert r.status_code == 200
    assert r.json()["timezone"] == "America/New_York"
    assert client.patch("/v1/me", headers=u["headers"], json={"timezone": "Nope/Nope"}).status_code == 422


def test_targets_set_edit_and_audit(client, make_user):
    u = make_user()
    h = u["headers"]
    assert client.get("/v1/me/targets", headers=h).status_code == 404
    r = client.put("/v1/me/targets", headers=h, json={"calories_kcal": 2200, "protein_g": 140})
    assert r.status_code == 200
    assert r.json()["calories_kcal"] == "2200.0"
    r = client.put("/v1/me/targets", headers=h, json={"calories_kcal": 2000, "protein_g": 150, "fiber_g": 30})
    assert r.json()["protein_g"] == "150.0"
    assert client.get("/v1/me/targets", headers=h).json()["fiber_g"] == "30.0"

    events = [e for e in client.get("/v1/audit", headers=h).json() if e["action"] == "targets.updated"]
    assert len(events) == 2
    latest = events[0]
    assert latest["before"]["calories_kcal"] == "2200.0"
    assert latest["after"]["calories_kcal"] == "2000.0"


def test_targets_reject_typos(client, make_user):
    h = make_user()["headers"]
    for body in ({"calories_kcal": 0}, {"calories_kcal": 220000}, {"calories_kcal": 2000, "protein_g": -5}):
        assert client.put("/v1/me/targets", headers=h, json=body).status_code == 422

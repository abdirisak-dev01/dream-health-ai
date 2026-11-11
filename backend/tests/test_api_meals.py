from datetime import datetime, timedelta, timezone


def propose(client, h, **body):
    return client.post("/v1/meals/proposals", headers=h, json=body)


def test_food_search(client, make_user):
    h = make_user()["headers"]
    names = [f["name"] for f in client.get("/v1/foods", params={"q": "chicken"}, headers=h).json()]
    assert len(names) == 2  # raw and roasted: the user must pick
    names = [f["name"] for f in client.get("/v1/foods", params={"q": "oil"}, headers=h).json()]
    assert names == ["Oil, olive"]  # whole-word match: no "boiled" lentils
    assert client.get("/v1/foods", params={"q": "bariis"}, headers=h).json()[0]["name"].startswith("Rice")
    assert client.get("/v1/foods", params={"q": "chicken"}).status_code == 401


def test_text_meal_full_flow(client, make_user):
    h = make_user()["headers"]
    client.put("/v1/me/targets", headers=h, json={"calories_kcal": 2000, "protein_g": 120})

    r = propose(client, h, meal_type="lunch", text="150 g roasted chicken breast, 1 cup rice, 2 eggs")
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["status"] == "pending"
    assert [i["food_name"] for i in p["items"]] == [
        "Chicken breast, skinless, roasted", "Rice, white, long-grain, cooked", "Egg, whole, raw"]
    assert p["items"][2]["unit"] == "large" and p["items"][2]["grams"] == "100.00"  # default portion
    # 247.50 + 205.40 + 143.00
    assert p["totals"]["kcal"] == "595.90"
    assert p["includes_unverified_food_data"] is True

    # Nothing counts until confirmed
    assert client.get("/v1/days/today/summary", headers=h).json()["meal_count"] == 0

    r = client.post(f"/v1/meals/proposals/{p['id']}/confirm", headers=h)
    assert r.status_code == 201
    meal = r.json()

    s = client.get("/v1/days/today/summary", headers=h).json()
    assert s["meal_count"] == 1
    assert s["totals"]["kcal"] == "595.90"
    assert s["vs_targets"]["kcal"]["remaining"] == "1404.10"
    assert s["vs_targets"]["fat_g"]["target"] is None
    assert "not yet verified" in s["note"]

    assert [m["id"] for m in client.get("/v1/meals", headers=h).json()] == [meal["id"]]


def test_confirm_twice_creates_one_meal(client, make_user):
    h = make_user()["headers"]
    p = propose(client, h, text="1 banana").json()
    r1 = client.post(f"/v1/meals/proposals/{p['id']}/confirm", headers=h)
    r2 = client.post(f"/v1/meals/proposals/{p['id']}/confirm", headers=h)
    assert (r1.status_code, r2.status_code) == (201, 200)
    assert r1.json()["id"] == r2.json()["id"]
    assert client.get("/v1/days/today/summary", headers=h).json()["meal_count"] == 1


def test_unclear_text_needs_input_and_cannot_be_confirmed(client, make_user):
    h = make_user()["headers"]
    p = propose(client, h, text="150 g chicken, 1 cup roasted chicken breast, rice, 2 pizza, 1 banana").json()
    assert p["status"] == "needs_input"
    assert [i["food_name"] for i in p["items"]] == ["Banana, raw"]
    problems = {u["text"]: u for u in p["unresolved"]}
    assert problems["150 g chicken"]["problem"] == "food_ambiguous"
    assert len(problems["150 g chicken"]["candidates"]) == 2
    assert problems["1 cup roasted chicken breast"]["problem"] == "unit_invalid"
    assert problems["rice"]["problem"] == "quantity_missing"
    assert problems["2 pizza"]["problem"] == "food_not_found"

    r = client.post(f"/v1/meals/proposals/{p['id']}/confirm", headers=h)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "proposal_needs_input"


def test_structured_items_flow_and_validation(client, make_user, food_id):
    h = make_user()["headers"]
    rice = food_id("dev-rice-white-cooked")
    r = propose(client, h, items=[{"food_id": rice, "quantity": 0.5, "unit": "cup"}])
    assert r.status_code == 201 and r.json()["totals"]["kcal"] == "102.70"

    r = propose(client, h, items=[{"food_id": rice, "quantity": 1, "unit": "handful"}])
    assert r.status_code == 422 and r.json()["error"]["code"] == "unit_invalid"
    r = propose(client, h, items=[{"food_id": "00000000-0000-0000-0000-000000000000", "quantity": 1, "unit": "g"}])
    assert r.status_code == 422 and r.json()["error"]["code"] == "food_not_found"
    r = propose(client, h, items=[{"food_id": rice, "quantity": 9000, "unit": "g"}])
    assert r.status_code == 422 and r.json()["error"]["code"] == "too_large"
    assert propose(client, h, text="1 apple", items=[{"food_id": rice, "quantity": 1, "unit": "g"}]
                   ).status_code == 422
    assert propose(client, h).status_code == 422


def test_discard(client, make_user):
    h = make_user()["headers"]
    p = propose(client, h, text="1 apple").json()
    assert client.post(f"/v1/meals/proposals/{p['id']}/discard", headers=h).json()["status"] == "discarded"
    assert client.post(f"/v1/meals/proposals/{p['id']}/confirm", headers=h).status_code == 409


def test_delete_meal_removes_it_from_totals(client, make_user):
    h = make_user()["headers"]
    p = propose(client, h, text="1 apple").json()
    meal = client.post(f"/v1/meals/proposals/{p['id']}/confirm", headers=h).json()
    assert client.delete(f"/v1/meals/{meal['id']}", headers=h).status_code == 204
    assert client.get(f"/v1/meals/{meal['id']}", headers=h).status_code == 404
    assert client.get("/v1/days/today/summary", headers=h).json()["meal_count"] == 0
    actions = [e["action"] for e in client.get("/v1/audit", headers=h).json()]
    assert "meal.deleted" in actions and "meal.confirmed" in actions


def test_nutrition_day_uses_users_time_zone(client, make_user):
    # 23:30 in Chicago on 5 Nov is already 6 Nov in UTC. It must count for 5 Nov.
    h = make_user(tz="America/Chicago")["headers"]
    p = propose(client, h, text="1 banana", eaten_at="2026-11-05T23:30:00-06:00").json()
    assert p["nutrition_date"] == "2026-11-05"
    client.post(f"/v1/meals/proposals/{p['id']}/confirm", headers=h)
    assert client.get("/v1/days/2026-11-05/summary", headers=h).json()["meal_count"] == 1
    assert client.get("/v1/days/2026-11-06/summary", headers=h).json()["meal_count"] == 0


def test_eaten_at_rules(client, make_user):
    h = make_user()["headers"]
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    r = propose(client, h, text="1 apple", eaten_at=future)
    assert r.status_code == 422 and r.json()["error"]["code"] == "eaten_at_in_future"
    assert propose(client, h, text="1 apple", eaten_at="2026-11-05T12:00:00").status_code == 422  # no zone


def test_text_limits(client, make_user):
    h = make_user()["headers"]
    assert propose(client, h, text=", , ;").status_code == 422
    assert propose(client, h, text=", ".join(["1 apple"] * 21)).status_code == 422

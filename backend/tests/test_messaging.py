"""Chat, phone verification, fake-phone texting, STOP/START."""
import re

import pytest

from app.core.config import get_settings
from app.messaging.router import normalize_phone
from app.core.errors import AppError


def chat(client, h, text):
    r = client.post("/v1/chat", headers=h, json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()["reply"]


def sms_inbox(client, h):
    return client.get("/v1/messages", params={"channel": "sms"}, headers=h).json()


def verify_phone(client, h, phone="+16125550100", agree=True):
    assert client.post("/v1/me/phone", headers=h, json={"phone": phone}).status_code == 200
    code = re.search(r"\b(\d{6})\b", sms_inbox(client, h)[-1]["body"]).group(1)
    r = client.post("/v1/me/phone/verify", headers=h, json={"code": code, "agree_to_texts": agree})
    assert r.status_code == 200, r.text
    return r.json()


def text(client, h, body):
    r = client.post("/v1/dev/fake-phone/send", headers=h, json={"text": body})
    assert r.status_code == 200, r.text
    return [m for m in r.json() if m["direction"] == "out"]


# ---- chat ------------------------------------------------------------------------------

def test_chat_meal_yes_today(client, make_user):
    h = make_user()["headers"]
    client.put("/v1/me/targets", headers=h, json={"calories_kcal": 2000, "protein_g": 120})
    reply = chat(client, h, "lunch: 1 cup rice, 150 g roasted chicken breast")
    assert "Here's your lunch:" in reply and "Total: 453 kcal" in reply and "Reply YES or NO" in reply
    assert client.get("/v1/days/today/summary", headers=h).json()["meal_count"] == 0  # not saved yet

    reply = chat(client, h, "yes")
    assert reply.startswith("Saved! Lunch: 453 kcal.")
    assert "1547 kcal left" in reply
    assert client.get("/v1/days/today/summary", headers=h).json()["meal_count"] == 1
    assert "Today: 1 meal, 453 kcal" in chat(client, h, "TODAY")


def test_chat_no_cancels_and_new_meal_replaces_draft(client, make_user):
    h = make_user()["headers"]
    chat(client, h, "1 apple")
    chat(client, h, "2 eggs")  # replaces the apple draft
    assert chat(client, h, "yes").startswith("Saved!")
    meals = client.get("/v1/meals", headers=h).json()
    assert [i["food_name"] for i in meals[0]["items"]] == ["Egg, whole, raw"]
    assert meals[0]["items"][0]["food_labels"] == {"en": "Egg", "so": "Ukun", "es": "Huevo"}
    chat(client, h, "1 banana")
    assert "Nothing was saved" in chat(client, h, "no")
    assert "nothing to save" in chat(client, h, "yes")


def test_chat_unclear_lines_ask_instead_of_guess(client, make_user):
    h = make_user()["headers"]
    reply = chat(client, h, "150 g chicken")
    assert "which one?" in reply and "Chicken breast (roasted)" in reply
    assert "needs a fix" in chat(client, h, "yes")


def test_chat_undo_and_help(client, make_user):
    h = make_user()["headers"]
    chat(client, h, "1 apple")
    chat(client, h, "yes")
    assert "Removed your last meal" in chat(client, h, "undo")
    assert "Tell me what you ate" in chat(client, h, "help")
    assert "No meals saved today" in chat(client, h, "undo")


def test_chat_history_is_private(client, make_user):
    a, b = make_user(), make_user()
    chat(client, a["headers"], "1 apple")
    assert client.get("/v1/messages", headers=b["headers"]).json() == []
    assert len(client.get("/v1/messages", headers=a["headers"]).json()) == 2


# ---- phone + consent ---------------------------------------------------------------------

@pytest.mark.parametrize("raw,out", [
    ("+1 (612) 555-0100", "+16125550100"), ("6125550100", "+16125550100"), ("16125550100", "+16125550100"),
    ("00252612345678", "+252612345678"), ("+44 7700 900123", "+447700900123"),
])
def test_normalize_phone(raw, out):
    assert normalize_phone(raw) == out


@pytest.mark.parametrize("raw", ["12345", "+0123456789", "phone", "+1234567890123456"])
def test_normalize_phone_rejects(raw):
    with pytest.raises(AppError):
        normalize_phone(raw)


def test_phone_verify_flow(client, make_user):
    h = make_user()["headers"]
    s = verify_phone(client, h)
    assert s["verified"] and s["texts_on"] and s["test_mode"]
    assert "texts are on" in sms_inbox(client, h)[-1]["body"]


def test_wrong_code_limit(client, make_user):
    h = make_user()["headers"]
    client.post("/v1/me/phone", headers=h, json={"phone": "+16125550111"})
    for _ in range(5):
        r = client.post("/v1/me/phone/verify", headers=h, json={"code": "000000", "agree_to_texts": True})
        assert r.status_code in (422, 200)
        if r.status_code == 200:  # astronomically unlikely
            return
    r = client.post("/v1/me/phone/verify", headers=h, json={"code": "000000", "agree_to_texts": True})
    assert r.status_code == 429


def test_one_number_one_account(client, make_user):
    a, b = make_user(), make_user()
    verify_phone(client, a["headers"], "+16125550122")
    r = client.post("/v1/me/phone", headers=b["headers"], json={"phone": "+16125550122"})
    assert r.status_code == 409


# ---- fake phone texting ---------------------------------------------------------------------

def test_text_a_meal_and_save_it(client, make_user):
    h = make_user()["headers"]
    verify_phone(client, h)
    out = text(client, h, "dinner: 1 cup lentils")
    assert "Here's your dinner:" in out[0]["body"]
    out = text(client, h, "YES")
    assert out[0]["body"].startswith("Saved! Dinner")
    assert client.get("/v1/days/today/summary", headers=h).json()["meal_count"] == 1


@pytest.mark.parametrize("lang", ["en", "so", "es"])
def test_sms_replies_stay_in_cheap_text_alphabet(client, make_user, lang):
    from app.i18n import is_gsm7
    h = make_user(lang=lang)["headers"]
    verify_phone(client, h)
    for m in text(client, h, "1 cup rice, 2 eggs") + text(client, h, "help") + text(client, h, "today"):
        assert is_gsm7(m["body"]), m["body"]  # other characters would make each text cost 2-3x


def test_stop_start(client, make_user):
    h = make_user()["headers"]
    verify_phone(client, h)
    out = text(client, h, "STOP")
    assert "won't get more texts" in out[0]["body"]
    assert client.get("/v1/me/phone", headers=h).json()["texts_on"] is False
    assert text(client, h, "1 apple") == []  # silence after STOP
    out = text(client, h, "start")
    assert "back on" in out[0]["body"]
    assert client.get("/v1/me/phone", headers=h).json()["texts_on"] is True


def test_cancel_means_stop_on_sms(client, make_user):
    h = make_user()["headers"]
    verify_phone(client, h)
    text(client, h, "CANCEL")
    assert client.get("/v1/me/phone", headers=h).json()["opted_out"] is True


def test_verified_but_no_consent_gets_no_replies(client, make_user):
    h = make_user()["headers"]
    verify_phone(client, h, agree=False)
    out = text(client, h, "1 apple")
    assert out[0]["body"] == "Dream Health: reply START to get text replies."


def test_fake_phone_needs_verified_number(client, make_user):
    h = make_user()["headers"]
    r = client.post("/v1/dev/fake-phone/send", headers=h, json={"text": "hi"})
    assert r.status_code == 409


def test_fake_phone_is_off_in_production(client, make_user, monkeypatch):
    h = make_user()["headers"]
    monkeypatch.setattr(get_settings(), "app_env", "production")
    r = client.post("/v1/dev/fake-phone/send", headers=h, json={"text": "hi"})
    assert r.status_code == 404


def test_everyday_sentence_with_typo_asks_instead_of_guessing(client, make_user):
    h = make_user()["headers"]
    reply = chat(client, h, "i eat 150g of chicj 200g of rice")
    assert "did you mean" in reply.lower() and "Chicken" in reply  # typo is suggested, not saved
    assert "Rice (cooked)" in reply  # the clear line is understood
    assert "needs a fix" in chat(client, h, "yes")
    reply = chat(client, h, "i eat 150g of roasted chicken 200g of rice")
    assert "Reply YES" in reply
    assert chat(client, h, "yes").startswith("Saved!")


def test_greetings_and_questions_are_not_meals(client, make_user):
    h = make_user()["headers"]
    assert chat(client, h, "hi").startswith("Hi Test!")
    assert "didn't see an amount" in chat(client, h, "what should I eat for dinner")
    assert client.get("/v1/messages", headers=h).status_code == 200
    # no drafts were created by chit-chat
    assert "nothing to save" in chat(client, h, "yes")


def test_meal_word_in_sentence_sets_meal_type(client, make_user):
    h = make_user()["headers"]
    assert chat(client, h, "for breakfast I had 1 cup oats").startswith("Here's your breakfast:")


# ---- Somali and Spanish ----------------------------------------------------------------------

def test_somali_conversation(client, make_user):
    h = make_user(lang="so")["headers"]
    client.put("/v1/me/targets", headers=h, json={"calories_kcal": 2000})
    assert chat(client, h, "salaan").startswith("Salaan Test!")
    reply = chat(client, h, "qado: waxaan cunay 1 koob bariis iyo 2 ukun")
    assert "Bariis (la karsaday), 1 koob: 205 kcal" in reply
    assert "Ukun, 2 weyn: 143 kcal" in reply
    assert "HAA ama MAYA" in reply
    reply = chat(client, h, "haa")
    assert reply.startswith("Waa la kaydiyay! Qado: 348 kcal.") and "1652 kcal ayaa haray" in reply
    assert chat(client, h, "maanta").startswith("Maanta: 1 cunto, 348 kcal")
    reply = chat(client, h, "150 g digaag")
    assert "midkee?" in reply and "Naas digaag (la dubay)" in reply


def test_spanish_conversation(client, make_user):
    h = make_user(lang="es")["headers"]
    assert chat(client, h, "hola").startswith("¡Hola Test!")
    reply = chat(client, h, "almuerzo: comí 150 g de pollo asado y 1 taza de arroz")
    assert "Pechuga de pollo (asada), 150 g: 248 kcal" in reply
    assert "Arroz blanco (cocido), 1 taza: 205 kcal" in reply
    assert "¿Lo guardo?" in reply
    assert chat(client, h, "sí").startswith("¡Guardado! Almuerzo: 453 kcal.")
    assert chat(client, h, "hoy").startswith("Hoy: 1 comida, 453 kcal")
    assert chat(client, h, "deshacer").startswith("Se borró tu última comida")
    assert "Dime qué comiste" in chat(client, h, "ayuda")


def test_spanish_sms_drops_costly_accents(client, make_user):
    h = make_user(lang="es")["headers"]
    verify_phone(client, h)
    body = text(client, h, "ayuda")[0]["body"]
    assert "SI para guardar" in body and "tu ultima comida" in body  # í and ú swapped; é is allowed in GSM-7
    assert "Código" not in body


def test_reminder_in_users_language(client, make_user):
    h = make_user(lang="so")["headers"]
    rem = client.post("/v1/reminders", headers=h, json={"label": "lunch", "at_time": "12:30"}).json()
    assert rem["text"].startswith("Dream Health: waa waqtigii qadada")

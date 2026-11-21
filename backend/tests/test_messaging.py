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
    assert meals[0]["items"][0]["food_labels"] == {"en": "Egg", "es": "Huevo", "fr": "Œuf", "ar": "بيضة", "zh": "鸡蛋"}
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


@pytest.mark.parametrize("lang", ["en", "es", "fr"])
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


# ---- Spanish, French, Arabic, Mandarin --------------------------------------------------------------

def test_french_conversation(client, make_user):
    h = make_user(lang="fr")["headers"]
    client.put("/v1/me/targets", headers=h, json={"calories_kcal": 2000})
    assert chat(client, h, "bonjour").startswith("Bonjour Test !")
    reply = chat(client, h, "déjeuner : j'ai mangé 150 g de poulet rôti et 1 tasse de riz")
    assert reply.startswith("Ton repas (déjeuner) :")
    assert "Blanc de poulet (rôti), 150 g : 248 kcal" in reply
    assert "Riz blanc (cuit), 1 tasse : 205 kcal" in reply
    assert "Réponds OUI ou NON" in reply
    reply = chat(client, h, "oui")
    assert reply.startswith("Enregistré ! Déjeuner : 453 kcal.") and "il te reste 1547 kcal" in reply
    assert chat(client, h, "aujourd'hui").startswith("Aujourd'hui : 1 repas, 453 kcal")
    reply = chat(client, h, "2 tranches de pain avec 1 c. à soupe d'huile d'olive")
    assert "Pain complet, 2 tranches : 161 kcal" in reply and "Huile d'olive, 1 c. à soupe : 119 kcal" in reply
    assert "lequel ?" in chat(client, h, "150 g de poulet")


def test_arabic_conversation(client, make_user):
    h = make_user(lang="ar")["headers"]
    client.put("/v1/me/targets", headers=h, json={"calories_kcal": 2000})
    assert chat(client, h, "مرحبا").startswith("مرحبًا Test!")
    reply = chat(client, h, "الغداء: أكلت 150 غ دجاج مشوي و كوب أرز")
    assert reply.startswith("وجبتك (غداء):")
    assert "صدر دجاج (مشوي)، 150 غ: 248 سعرة" in reply
    assert "أرز أبيض (مطبوخ)، 1 كوب: 205 سعرة" in reply
    reply = chat(client, h, "نعم")
    assert reply.startswith("تم الحفظ! غداء: 453 سعرة.") and "تبقّى 1547 سعرة" in reply
    assert chat(client, h, "اليوم").startswith("اليوم: 1 وجبة، 453 سعرة")
    reply = chat(client, h, "٢ بيض، ١ كوب حليب")  # Arabic-Indic digits
    assert "بيضة، 2 حبات كبيرة: 143 سعرة" in reply and "حليب كامل الدسم، 1 كوب: 149 سعرة" in reply
    assert "أيّهما؟" in chat(client, h, "150 غ دجاج")


def test_mandarin_conversation(client, make_user):
    h = make_user(lang="zh")["headers"]
    client.put("/v1/me/targets", headers=h, json={"calories_kcal": 2000})
    assert chat(client, h, "你好").startswith("你好，Test！")
    reply = chat(client, h, "午餐：我吃了150克烤鸡胸肉和1杯米饭")
    assert reply.startswith("你的午餐：")
    assert "烤鸡胸肉，150 克：248 千卡" in reply
    assert "米饭，1 杯：205 千卡" in reply
    reply = chat(client, h, "是")
    assert reply.startswith("已保存！午餐：453 千卡。") and "还剩 1547 千卡" in reply
    assert chat(client, h, "今天").startswith("今天：1 餐，453 千卡")
    reply = chat(client, h, "两个鸡蛋")
    assert "鸡蛋，2 个：143 千卡" in reply
    assert "哪一种？" in chat(client, h, "150克鸡胸肉")
    assert "我需要你帮个忙" in chat(client, h, "一碗米饭")  # a bowl has no fixed size: ask for grams


@pytest.mark.parametrize("lang,word", [("ar", "مساعدة"), ("zh", "帮助")])
def test_arabic_and_chinese_texts_keep_every_character(client, make_user, lang, word):
    from app.i18n import needs_unicode_sms
    h = make_user(lang=lang)["headers"]
    verify_phone(client, h)
    body = text(client, h, word)[0]["body"]
    assert needs_unicode_sms(body) and len(body) > 40  # sent as a Unicode text, nothing stripped


def test_somali_is_no_longer_offered(client):
    r = client.post("/v1/auth/register", json={"email": "so@example.com", "password": "a-long-test-password",
                                               "display_name": "x", "preferred_language": "so"})
    assert r.status_code == 422


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
    h = make_user(lang="fr")["headers"]
    rem = client.post("/v1/reminders", headers=h, json={"label": "lunch", "at_time": "12:30"}).json()
    assert rem["text"].startswith("Dream Health : c'est l'heure de noter le déjeuner")

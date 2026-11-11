"""Every sentence the app says to a user, in English, Somali and Spanish.

Rules for writers:
  * Short, friendly, plain words. One idea per line.
  * Text messages cost more with some accents (UCS-2), so sms_safe() swaps a/e/i/o/u accents that the
    standard GSM text alphabet lacks. n-tilde, e-acute and the Spanish question/exclamation marks are fine.
  * Somali and Spanish translations MUST be checked by a native speaker before launch.

Use: t(lang, "key", name="Abdirisak")
"""
import unicodedata

LANGS = ("en", "so", "es")

T: dict[str, dict[str, str]] = {
    # ---- chat basics -----------------------------------------------------------------------
    "help": {
        "en": "Tell me what you ate, like:\n150 g roasted chicken, 1 cup rice\n"
              "Then reply YES to save or NO to cancel.\nTODAY = today's total\nUNDO = remove your last meal",
        "so": "Ii sheeg waxaad cuntay, tusaale:\n150 g digaag la dubay, 1 koob bariis\n"
              "Kadib u jawaab HAA si aad u kaydiso ama MAYA si aad u joojiso.\nMAANTA = wadarta maanta\n"
              "TIRTIR = tirtir cuntadii ugu dambeysay",
        "es": "Dime qué comiste, por ejemplo:\n150 g de pollo asado, 1 taza de arroz\n"
              "Luego responde SÍ para guardar o NO para cancelar.\nHOY = total de hoy\n"
              "DESHACER = borrar tu última comida",
    },
    "greet": {
        "en": "Hi {name}! What did you eat?\nFor example: 150 g roasted chicken, 1 cup rice",
        "so": "Salaan {name}! Maxaad cuntay?\nTusaale: 150 g digaag la dubay, 1 koob bariis",
        "es": "¡Hola {name}! ¿Qué comiste?\nPor ejemplo: 150 g de pollo asado, 1 taza de arroz",
    },
    "no_amount": {
        "en": "I didn't see an amount. Try something like:\n150 g roasted chicken, 1 cup rice",
        "so": "Ma arkin tiro. Isku day sidan:\n150 g digaag la dubay, 1 koob bariis",
        "es": "No vi una cantidad. Prueba algo como:\n150 g de pollo asado, 1 taza de arroz",
    },
    "cant_read": {
        "en": "I couldn't read that. Reply HELP for examples.",
        "so": "Taas ma akhrin karin. U jawaab CAAWI si aad u hesho tusaalooyin.",
        "es": "No pude leer eso. Responde AYUDA para ver ejemplos.",
    },

    # ---- draft -------------------------------------------------------------------------------
    "draft_head": {"en": "Here's your {meal}:", "so": "Cuntadaada ({meal}):", "es": "Tu {meal}:"},
    "item": {"en": "- {food}, {qty}: {kcal} kcal", "so": "- {food}, {qty}: {kcal} kcal",
             "es": "- {food}, {qty}: {kcal} kcal"},
    "total": {"en": "Total: {kcal} kcal, {protein} g protein",
              "so": "Wadarta: {kcal} kcal, {protein} g borotiin",
              "es": "Total: {kcal} kcal, {protein} g de proteína"},
    "ask_save": {"en": "Save it? Reply YES or NO.", "so": "Ma kaydiyaa? U jawaab HAA ama MAYA.",
                 "es": "¿Lo guardo? Responde SÍ o NO."},
    "need_help": {"en": "I need a little help:", "so": "Waxoogaa caawimaad ah ayaan u baahanahay:",
                  "es": "Necesito un poco de ayuda:"},
    "resend": {"en": "Then send the whole meal again.", "so": "Kadib dib u soo dir cuntada oo dhan.",
               "es": "Luego envía la comida completa otra vez."},

    # ---- problems with one line ------------------------------------------------------------------
    "p_quantity_missing": {"en": "'{text}': how much? Like 1 cup or 150 g",
                           "so": "'{text}': immisa? Tusaale 1 koob ama 150 g",
                           "es": "'{text}': ¿cuánto? Por ejemplo 1 taza o 150 g"},
    "p_quantity_invalid": {"en": "'{text}': I can't read that amount. Use a number like 150 or 1/2.",
                           "so": "'{text}': tiradan ma akhrin karo. Isticmaal tiro sida 150 ama 1/2.",
                           "es": "'{text}': no entiendo la cantidad. Usa un número como 150 o 1/2."},
    "p_food_missing": {"en": "'{text}': {text} of what? Like {text} rice",
                       "so": "'{text}': {text} maxaa? Tusaale {text} bariis",
                       "es": "'{text}': ¿{text} de qué? Por ejemplo {text} de arroz"},
    "p_food_not_found": {"en": "'{text}': I don't know this food yet. Try another name.",
                         "so": "'{text}': cuntadan weli ma aqaan. Isku day magac kale.",
                         "es": "'{text}': todavía no conozco este alimento. Prueba otro nombre."},
    "p_food_ambiguous": {"en": "'{text}': which one? {options}", "so": "'{text}': midkee? {options}",
                         "es": "'{text}': ¿cuál? {options}"},
    "p_food_typo": {"en": "'{text}': did you mean {options}?",
                    "so": "'{text}': ma waxaad ula jeeddaa {options}?",
                    "es": "'{text}': ¿quisiste decir {options}?"},
    "p_unit_invalid": {"en": "'{text}': I can't measure it that way. Try grams, like 150 g.",
                       "so": "'{text}': sidaas uma qiyaasi karo. Isku day garaam, sida 150 g.",
                       "es": "'{text}': no puedo medirlo así. Usa gramos, como 150 g."},
    "p_too_large": {"en": "'{text}': that amount looks too big. Check for a typo.",
                    "so": "'{text}': tiradu aad bay u badan tahay. Hubi inaanay qalad ahayn.",
                    "es": "'{text}': esa cantidad parece muy grande. Revisa si hay un error."},
    "or": {"en": " or ", "so": " ama ", "es": " o "},

    # ---- yes / no / today / undo -----------------------------------------------------------------
    "saved": {"en": "Saved! {meal}: {kcal} kcal.", "so": "Waa la kaydiyay! {meal}: {kcal} kcal.",
              "es": "¡Guardado! {meal}: {kcal} kcal."},
    "nothing_to_save": {"en": "There's nothing to save yet. Tell me what you ate first.",
                        "so": "Wax la kaydiyo ma jiraan. Marka hore ii sheeg waxaad cuntay.",
                        "es": "Todavía no hay nada que guardar. Primero dime qué comiste."},
    "cant_save": {"en": "This one still needs a fix before I can save it. Send the meal again.",
                  "so": "Tani weli sixid ayay u baahan tahay. Dib u soo dir cuntada.",
                  "es": "Esto todavía necesita un arreglo. Envía la comida otra vez."},
    "cancelled": {"en": "OK, cancelled. Nothing was saved.", "so": "Waa la joojiyay. Waxba lama kaydin.",
                  "es": "Listo, cancelado. No se guardó nada."},
    "no_draft": {"en": "There's nothing to cancel.", "so": "Wax la joojiyo ma jiraan.",
                 "es": "No hay nada que cancelar."},
    "today": {"en": "Today: {n} {meals}, {kcal} kcal, {protein} g protein.",
              "so": "Maanta: {n} cunto, {kcal} kcal, {protein} g borotiin.",
              "es": "Hoy: {n} {meals}, {kcal} kcal, {protein} g de proteína."},
    "meals_one": {"en": "meal", "so": "cunto", "es": "comida"},
    "meals_many": {"en": "meals", "so": "cunto", "es": "comidas"},
    "goal_left": {"en": "Goal {goal} kcal: {left} kcal left.", "so": "Hadafka {goal} kcal: {left} kcal ayaa haray.",
                  "es": "Meta {goal} kcal: te quedan {left} kcal."},
    "goal_over": {"en": "Goal {goal} kcal: {over} kcal over.", "so": "Hadafka {goal} kcal: {over} kcal ayaad dhaaftay.",
                  "es": "Meta {goal} kcal: te pasaste por {over} kcal."},
    "protein_left": {"en": "Protein: {left} g to go of {goal} g.", "so": "Borotiin: {left} g ayaa ka haray {goal} g.",
                     "es": "Proteína: te faltan {left} g de {goal} g."},
    "no_goal": {"en": "Set a daily goal in Settings to see what's left.",
                "so": "Dhig hadaf maalinle ah (Settings) si aad u aragto inta haray.",
                "es": "Pon una meta diaria en Ajustes para ver cuánto te queda."},
    "undo_none": {"en": "No meals saved today.", "so": "Maanta cunto lama kaydin.", "es": "Hoy no hay comidas guardadas."},
    "undo_done": {"en": "Removed your last meal ({meal}).", "so": "Waa la tirtiray cuntadii ugu dambeysay ({meal}).",
                  "es": "Se borró tu última comida ({meal})."},

    # ---- text-message rules --------------------------------------------------------------------
    "stop": {"en": "You won't get more texts from Dream Health. Reply START to turn them back on.",
             "so": "Dream Health fariimo kale kuuma soo diri doono. U jawaab START si aad dib ugu shido.",
             "es": "Ya no recibirás mensajes de Dream Health. Responde START para activarlos otra vez."},
    "start": {"en": "Texts are back on. Reply HELP for help, STOP to stop.",
              "so": "Fariimaha dib ayaa loo shiday. U jawaab HELP caawimaad, STOP si aad u joojiso.",
              "es": "Mensajes activados. Responde AYUDA para ayuda, STOP para parar."},
    "start_needed": {"en": "Dream Health: reply START to get text replies.",
                     "so": "Dream Health: u jawaab START si aad jawaabo u hesho.",
                     "es": "Dream Health: responde START para recibir respuestas."},
    "code": {"en": "Dream Health code: {code}. It expires in {minutes} min. Don't share it.",
             "so": "Koodka Dream Health: {code}. Wuxuu dhacayaa {minutes} daqiiqo kadib. Cidna ha la wadaagin.",
             "es": "Código de Dream Health: {code}. Vence en {minutes} min. No lo compartas."},
    "texts_on": {"en": "Dream Health: texts are on. Send what you ate, like '1 cup rice, 2 eggs'. "
                       "Reply HELP for help, STOP to stop.",
                 "so": "Dream Health: fariimaha waa shidan yihiin. Soo dir waxaad cuntay, sida '1 koob bariis, 2 ukun'. "
                       "U jawaab HELP caawimaad, STOP si aad u joojiso.",
                 "es": "Dream Health: mensajes activados. Envía lo que comiste, como '1 taza de arroz, 2 huevos'. "
                       "Responde AYUDA para ayuda, STOP para parar."},

    # ---- reminders -----------------------------------------------------------------------------
    "rem_breakfast": {"en": "Dream Health: did you have breakfast? Send what you ate, like '1 cup oats, 1 banana'.",
                      "so": "Dream Health: quraac ma cuntay? Soo dir waxaad cuntay, sida '1 koob boorash, 1 muus'.",
                      "es": "Dream Health: ¿desayunaste? Envía lo que comiste, como '1 taza de avena, 1 banana'."},
    "rem_lunch": {"en": "Dream Health: time to log lunch. Send what you ate, like '1 cup rice, 150 g roasted chicken'.",
                  "so": "Dream Health: waa waqtigii qadada. Soo dir waxaad cuntay, sida '1 koob bariis, 150 g digaag la dubay'.",
                  "es": "Dream Health: hora de anotar el almuerzo. Envía lo que comiste, como '1 taza de arroz, 150 g de pollo asado'."},
    "rem_dinner": {"en": "Dream Health: how was dinner? Send what you ate to log it.",
                   "so": "Dream Health: casho sidee ahayd? Soo dir waxaad cuntay si loo diiwaangeliyo.",
                   "es": "Dream Health: ¿qué tal la cena? Envía lo que comiste para anotarlo."},
    "rem_snack": {"en": "Dream Health: had a snack? Send it to log it.",
                  "so": "Dream Health: cunto fudud ma cuntay? Soo dir si loo diiwaangeliyo.",
                  "es": "Dream Health: ¿comiste algo? Envíalo para anotarlo."},
    "rem_custom": {"en": "Dream Health reminder.", "so": "Xasuusin Dream Health.", "es": "Recordatorio de Dream Health."},
}

MEAL = {
    "breakfast": {"en": "breakfast", "so": "quraac", "es": "desayuno"},
    "lunch": {"en": "lunch", "so": "qado", "es": "almuerzo"},
    "dinner": {"en": "dinner", "so": "casho", "es": "cena"},
    "snack": {"en": "snack", "so": "cunto fudud", "es": "merienda"},
    "other": {"en": "meal", "so": "cunto", "es": "comida"},
}

# (singular, plural) per language. Mass units stay as symbols.
UNIT = {
    "cup": {"en": ("cup", "cups"), "so": ("koob", "koob"), "es": ("taza", "tazas")},
    "slice": {"en": ("slice", "slices"), "so": ("jeex", "jeex"), "es": ("rebanada", "rebanadas")},
    "tbsp": {"en": ("tbsp", "tbsp"), "so": ("qaado weyn", "qaado weyn"), "es": ("cucharada", "cucharadas")},
    "tsp": {"en": ("tsp", "tsp"), "so": ("qaado yar", "qaado yar"), "es": ("cucharadita", "cucharaditas")},
    "large": {"en": ("large", "large"), "so": ("weyn", "weyn"), "es": ("grande", "grandes")},
    "medium": {"en": ("medium", "medium"), "so": ("dhexdhexaad", "dhexdhexaad"), "es": ("mediano", "medianos")},
    "small": {"en": ("small", "small"), "so": ("yar", "yar"), "es": ("pequeño", "pequeños")},
    "piece": {"en": ("piece", "pieces"), "so": ("xabbo", "xabbo"), "es": ("pieza", "piezas")},
}


def lang_of(user_or_code) -> str:
    code = getattr(user_or_code, "preferred_language", user_or_code) or "en"
    code = str(code).split("-")[0].lower()
    return code if code in LANGS else "en"


def t(lang: str, key: str, **kw) -> str:
    entry = T[key]
    return entry.get(lang, entry["en"]).format(**kw)


def meal_name(lang: str, meal_type: str) -> str:
    return MEAL.get(meal_type, MEAL["other"]).get(lang, meal_type)


def unit_name(lang: str, unit: str, many: bool) -> str:
    names = UNIT.get(unit)
    if not names:
        return unit
    one, plural = names.get(lang, names["en"])
    return plural if many else one


# GSM-7 (the standard text alphabet) has é, ñ, ü, ¿, ¡ but not á, í, ó, ú. Swap those so a text stays cheap.
_SMS_SWAP = str.maketrans({"á": "a", "í": "i", "ó": "o", "ú": "u", "Á": "A", "Í": "I", "Ó": "O", "Ú": "U",
                           "’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"})
GSM7_EXTRA = set("£¥èéùìòÇØøÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉÄÖÑÜ§¿äöñüà¡")


def sms_safe(text: str) -> str:
    text = text.translate(_SMS_SWAP)
    out = []
    for ch in text:
        if ch.isascii() or ch in GSM7_EXTRA:
            out.append(ch)
        else:  # any other accent: drop it ("ç" -> "c"); unknown symbols are removed
            base = unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode("ascii")
            out.append(base)
    return "".join(out)


def is_gsm7(text: str) -> bool:
    return all(ch.isascii() or ch in GSM7_EXTRA for ch in text)

"""Every sentence the app says to a user, in English, Spanish, French, Arabic and Mandarin (Simplified Chinese).
© 2026 Abdirisak Omar. All rights reserved.

Rules for writers:
  * Short, friendly, plain words. One idea per line.
  * Latin-script texts: sms_safe() keeps them in the cheap GSM-7 alphabet by dropping accents it lacks.
    Arabic and Chinese can't use GSM-7: they go out as Unicode texts (70 characters per part instead of 160).
  * Spanish, French, Arabic and Chinese translations MUST be checked by a native speaker before launch.

Use: t(lang, "key", name="Abdirisak")
"""
import re
import unicodedata

LANGS = ("en", "es", "fr", "ar", "zh")
RTL_LANGS = ("ar",)

T: dict[str, dict[str, str]] = {
    # ---- chat basics -----------------------------------------------------------------------
    "help": {
        "en": "Tell me what you ate, like:\n150 g roasted chicken, 1 cup rice\n"
              "Then reply YES to save or NO to cancel.\nTODAY = today's total\nUNDO = remove your last meal",
        "es": "Dime qué comiste, por ejemplo:\n150 g de pollo asado, 1 taza de arroz\n"
              "Luego responde SÍ para guardar o NO para cancelar.\nHOY = total de hoy\n"
              "DESHACER = borrar tu última comida",
        "fr": "Dis-moi ce que tu as mangé, par exemple :\n150 g de poulet rôti, 1 tasse de riz\n"
              "Puis réponds OUI pour enregistrer ou NON pour annuler.\nAUJOURD'HUI = total du jour\n"
              "EFFACER = supprimer ton dernier repas",
        "ar": "أخبرني بما أكلت، مثلًا:\n150 غ دجاج مشوي، 1 كوب أرز\n"
              "ثم أرسل نعم للحفظ أو لا للإلغاء.\nاليوم = مجموع اليوم\nتراجع = حذف آخر وجبة",
        "zh": "告诉我你吃了什么，例如：\n150克烤鸡胸肉，1杯米饭\n"
              "然后回复 是 保存，或 不 取消。\n今天 = 今天的总计\n撤销 = 删除最后一餐",
    },
    "greet": {
        "en": "Hi {name}! What did you eat?\nFor example: 150 g roasted chicken, 1 cup rice",
        "es": "¡Hola {name}! ¿Qué comiste?\nPor ejemplo: 150 g de pollo asado, 1 taza de arroz",
        "fr": "Bonjour {name} ! Qu'as-tu mangé ?\nPar exemple : 150 g de poulet rôti, 1 tasse de riz",
        "ar": "مرحبًا {name}! ماذا أكلت؟\nمثلًا: 150 غ دجاج مشوي، 1 كوب أرز",
        "zh": "你好，{name}！你吃了什么？\n例如：150克烤鸡胸肉，1杯米饭",
    },
    "no_amount": {
        "en": "I didn't see an amount. Try something like:\n150 g roasted chicken, 1 cup rice",
        "es": "No vi una cantidad. Prueba algo como:\n150 g de pollo asado, 1 taza de arroz",
        "fr": "Je n'ai pas vu de quantité. Essaie par exemple :\n150 g de poulet rôti, 1 tasse de riz",
        "ar": "لم أجد كمية. جرّب مثلًا:\n150 غ دجاج مشوي، 1 كوب أرز",
        "zh": "我没有看到份量。可以这样写：\n150克烤鸡胸肉，1杯米饭",
    },
    "cant_read": {
        "en": "I couldn't read that. Reply HELP for examples.",
        "es": "No pude leer eso. Responde AYUDA para ver ejemplos.",
        "fr": "Je n'ai pas pu lire ça. Réponds AIDE pour des exemples.",
        "ar": "لم أستطع قراءة ذلك. أرسل مساعدة لترى أمثلة.",
        "zh": "我没看懂。回复 帮助 查看例子。",
    },

    # ---- draft -------------------------------------------------------------------------------
    "draft_head": {"en": "Here's your {meal}:", "es": "Tu {meal}:", "fr": "Ton repas ({meal}) :",
                   "ar": "وجبتك ({meal}):", "zh": "你的{meal}："},
    "item": {"en": "- {food}, {qty}: {kcal} kcal", "es": "- {food}, {qty}: {kcal} kcal",
             "fr": "- {food}, {qty} : {kcal} kcal", "ar": "- {food}، {qty}: {kcal} سعرة",
             "zh": "- {food}，{qty}：{kcal} 千卡"},
    "total": {"en": "Total: {kcal} kcal, {protein} g protein",
              "es": "Total: {kcal} kcal, {protein} g de proteína",
              "fr": "Total : {kcal} kcal, {protein} g de protéines",
              "ar": "المجموع: {kcal} سعرة، {protein} غ بروتين",
              "zh": "合计：{kcal} 千卡，蛋白质 {protein} 克"},
    "ask_save": {"en": "Save it? Reply YES or NO.", "es": "¿Lo guardo? Responde SÍ o NO.",
                 "fr": "Je l'enregistre ? Réponds OUI ou NON.", "ar": "هل أحفظها؟ أرسل نعم أو لا.",
                 "zh": "要保存吗？回复 是 或 不。"},
    "need_help": {"en": "I need a little help:", "es": "Necesito un poco de ayuda:",
                  "fr": "J'ai besoin d'un peu d'aide :", "ar": "أحتاج إلى بعض المساعدة:", "zh": "我需要你帮个忙："},
    "resend": {"en": "Then send the whole meal again.", "es": "Luego envía la comida completa otra vez.",
               "fr": "Puis renvoie le repas en entier.", "ar": "ثم أرسل الوجبة كاملة مرة أخرى.",
               "zh": "然后把整餐再发一次。"},

    # ---- problems with one line ------------------------------------------------------------------
    "p_quantity_missing": {"en": "'{text}': how much? Like 1 cup or 150 g",
                           "es": "'{text}': ¿cuánto? Por ejemplo 1 taza o 150 g",
                           "fr": "'{text}' : combien ? Par exemple 1 tasse ou 150 g",
                           "ar": "'{text}': كم؟ مثلًا 1 كوب أو 150 غ",
                           "zh": "“{text}”：多少？例如 1杯 或 150克"},
    "p_quantity_invalid": {"en": "'{text}': I can't read that amount. Use a number like 150 or 1/2.",
                           "es": "'{text}': no entiendo la cantidad. Usa un número como 150 o 1/2.",
                           "fr": "'{text}' : je ne comprends pas la quantité. Utilise un nombre comme 150 ou 1/2.",
                           "ar": "'{text}': لا أفهم الكمية. استخدم رقمًا مثل 150 أو 1/2.",
                           "zh": "“{text}”：我看不懂这个份量。请用数字，例如 150 或 1/2。"},
    "p_food_missing": {"en": "'{text}': {text} of what? Like {text} rice",
                       "es": "'{text}': ¿{text} de qué? Por ejemplo {text} de arroz",
                       "fr": "'{text}' : {text} de quoi ? Par exemple {text} de riz",
                       "ar": "'{text}': {text} من ماذا؟ مثلًا {text} أرز",
                       "zh": "“{text}”：{text}什么？例如 {text}米饭"},
    "p_food_not_found": {"en": "'{text}': I don't know this food yet. Try another name.",
                         "es": "'{text}': todavía no conozco este alimento. Prueba otro nombre.",
                         "fr": "'{text}' : je ne connais pas encore cet aliment. Essaie un autre nom.",
                         "ar": "'{text}': لا أعرف هذا الطعام بعد. جرّب اسمًا آخر.",
                         "zh": "“{text}”：我还不认识这种食物。换个名字试试。"},
    "p_food_ambiguous": {"en": "'{text}': which one? {options}", "es": "'{text}': ¿cuál? {options}",
                         "fr": "'{text}' : lequel ? {options}", "ar": "'{text}': أيّهما؟ {options}",
                         "zh": "“{text}”：哪一种？{options}"},
    "p_food_typo": {"en": "'{text}': did you mean {options}?", "es": "'{text}': ¿quisiste decir {options}?",
                    "fr": "'{text}' : tu voulais dire {options} ?", "ar": "'{text}': هل تقصد {options}؟",
                    "zh": "“{text}”：你是说 {options} 吗？"},
    "p_unit_invalid": {"en": "'{text}': I can't measure it that way. Try grams, like 150 g.",
                       "es": "'{text}': no puedo medirlo así. Usa gramos, como 150 g.",
                       "fr": "'{text}' : je ne peux pas le mesurer comme ça. Essaie en grammes, comme 150 g.",
                       "ar": "'{text}': لا أستطيع قياسه بهذه الطريقة. استخدم الغرامات، مثل 150 غ.",
                       "zh": "“{text}”：我没法这样计量。请用克，例如 150克。"},
    "p_too_large": {"en": "'{text}': that amount looks too big. Check for a typo.",
                    "es": "'{text}': esa cantidad parece muy grande. Revisa si hay un error.",
                    "fr": "'{text}' : cette quantité semble trop grande. Vérifie s'il y a une erreur.",
                    "ar": "'{text}': هذه الكمية كبيرة جدًا. تأكد من عدم وجود خطأ.",
                    "zh": "“{text}”：这个份量好像太大了，请检查一下。"},
    "or": {"en": " or ", "es": " o ", "fr": " ou ", "ar": " أو ", "zh": " 或 "},

    # ---- yes / no / today / undo -----------------------------------------------------------------
    "saved": {"en": "Saved! {meal}: {kcal} kcal.", "es": "¡Guardado! {meal}: {kcal} kcal.",
              "fr": "Enregistré ! {meal} : {kcal} kcal.", "ar": "تم الحفظ! {meal}: {kcal} سعرة.",
              "zh": "已保存！{meal}：{kcal} 千卡。"},
    "nothing_to_save": {"en": "There's nothing to save yet. Tell me what you ate first.",
                        "es": "Todavía no hay nada que guardar. Primero dime qué comiste.",
                        "fr": "Il n'y a rien à enregistrer. Dis-moi d'abord ce que tu as mangé.",
                        "ar": "لا يوجد شيء لحفظه بعد. أخبرني أولًا بما أكلت.",
                        "zh": "还没有可保存的内容。先告诉我你吃了什么。"},
    "cant_save": {"en": "This one still needs a fix before I can save it. Send the meal again.",
                  "es": "Esto todavía necesita un arreglo. Envía la comida otra vez.",
                  "fr": "Il faut encore corriger ceci avant de l'enregistrer. Renvoie le repas.",
                  "ar": "ما زال هذا يحتاج إلى تصحيح قبل الحفظ. أرسل الوجبة مرة أخرى.",
                  "zh": "这一餐还需要修改才能保存。请再发一次。"},
    "cancelled": {"en": "OK, cancelled. Nothing was saved.", "es": "Listo, cancelado. No se guardó nada.",
                  "fr": "D'accord, annulé. Rien n'a été enregistré.", "ar": "حسنًا، تم الإلغاء. لم يُحفظ شيء.",
                  "zh": "好的，已取消，没有保存任何内容。"},
    "no_draft": {"en": "There's nothing to cancel.", "es": "No hay nada que cancelar.",
                 "fr": "Il n'y a rien à annuler.", "ar": "لا يوجد شيء لإلغائه.", "zh": "没有可以取消的内容。"},
    "today": {"en": "Today: {n} {meals}, {kcal} kcal, {protein} g protein.",
              "es": "Hoy: {n} {meals}, {kcal} kcal, {protein} g de proteína.",
              "fr": "Aujourd'hui : {n} {meals}, {kcal} kcal, {protein} g de protéines.",
              "ar": "اليوم: {n} {meals}، {kcal} سعرة، {protein} غ بروتين.",
              "zh": "今天：{n} {meals}，{kcal} 千卡，蛋白质 {protein} 克。"},
    "meals_one": {"en": "meal", "es": "comida", "fr": "repas", "ar": "وجبة", "zh": "餐"},
    "meals_many": {"en": "meals", "es": "comidas", "fr": "repas", "ar": "وجبات", "zh": "餐"},
    "goal_left": {"en": "Goal {goal} kcal: {left} kcal left.", "es": "Meta {goal} kcal: te quedan {left} kcal.",
                  "fr": "Objectif {goal} kcal : il te reste {left} kcal.",
                  "ar": "الهدف {goal} سعرة: تبقّى {left} سعرة.", "zh": "目标 {goal} 千卡：还剩 {left} 千卡。"},
    "goal_over": {"en": "Goal {goal} kcal: {over} kcal over.", "es": "Meta {goal} kcal: te pasaste por {over} kcal.",
                  "fr": "Objectif {goal} kcal : dépassé de {over} kcal.",
                  "ar": "الهدف {goal} سعرة: تجاوزته بـ {over} سعرة.", "zh": "目标 {goal} 千卡：超出 {over} 千卡。"},
    "protein_left": {"en": "Protein: {left} g to go of {goal} g.", "es": "Proteína: te faltan {left} g de {goal} g.",
                     "fr": "Protéines : encore {left} g sur {goal} g.",
                     "ar": "البروتين: تبقّى {left} غ من {goal} غ.", "zh": "蛋白质：还差 {left} 克（目标 {goal} 克）。"},
    "no_goal": {"en": "Set a daily goal in Settings to see what's left.",
                "es": "Pon una meta diaria en Ajustes para ver cuánto te queda.",
                "fr": "Fixe un objectif quotidien dans Réglages pour voir ce qu'il te reste.",
                "ar": "حدّد هدفًا يوميًا في الإعدادات لترى ما تبقّى.",
                "zh": "在设置里设定每日目标，就能看到还剩多少。"},
    "undo_none": {"en": "No meals saved today.", "es": "Hoy no hay comidas guardadas.",
                  "fr": "Aucun repas enregistré aujourd'hui.", "ar": "لا توجد وجبات محفوظة اليوم.",
                  "zh": "今天还没有保存的餐。"},
    "undo_done": {"en": "Removed your last meal ({meal}).", "es": "Se borró tu última comida ({meal}).",
                  "fr": "Ton dernier repas ({meal}) a été supprimé.", "ar": "تم حذف آخر وجبة ({meal}).",
                  "zh": "已删除你最后一餐（{meal}）。"},

    # ---- text-message rules (STOP/START/HELP stay in English: phone carriers look for those words) ----------
    "stop": {"en": "You won't get more texts from Dream Health. Reply START to turn them back on.",
             "es": "Ya no recibirás mensajes de Dream Health. Responde START para activarlos otra vez.",
             "fr": "Tu ne recevras plus de SMS de Dream Health. Réponds START pour les réactiver.",
             "ar": "لن تصلك رسائل أخرى من Dream Health. أرسل START لتفعيلها من جديد.",
             "zh": "你将不再收到 Dream Health 的短信。回复 START 可重新开启。"},
    "start": {"en": "Texts are back on. Reply HELP for help, STOP to stop.",
              "es": "Mensajes activados. Responde AYUDA para ayuda, STOP para parar.",
              "fr": "Les SMS sont réactivés. Réponds AIDE pour de l'aide, STOP pour arrêter.",
              "ar": "تم تفعيل الرسائل. أرسل HELP للمساعدة، وSTOP للإيقاف.",
              "zh": "短信已重新开启。回复 HELP 获取帮助，回复 STOP 停止。"},
    "start_needed": {"en": "Dream Health: reply START to get text replies.",
                     "es": "Dream Health: responde START para recibir respuestas.",
                     "fr": "Dream Health : réponds START pour recevoir des réponses.",
                     "ar": "Dream Health: أرسل START لتصلك الردود.",
                     "zh": "Dream Health：回复 START 接收回复。"},
    "code": {"en": "Dream Health code: {code}. It expires in {minutes} min. Don't share it.",
             "es": "Código de Dream Health: {code}. Vence en {minutes} min. No lo compartas.",
             "fr": "Code Dream Health : {code}. Il expire dans {minutes} min. Ne le partage pas.",
             "ar": "رمز Dream Health: {code}. ينتهي بعد {minutes} دقائق. لا تشاركه مع أحد.",
             "zh": "Dream Health 验证码：{code}，{minutes} 分钟内有效。请勿告诉他人。"},
    "texts_on": {"en": "Dream Health: texts are on. Send what you ate, like '1 cup rice, 2 eggs'. "
                       "Reply HELP for help, STOP to stop.",
                 "es": "Dream Health: mensajes activados. Envía lo que comiste, como '1 taza de arroz, 2 huevos'. "
                       "Responde AYUDA para ayuda, STOP para parar.",
                 "fr": "Dream Health : les SMS sont activés. Envoie ce que tu as mangé, comme '1 tasse de riz, 2 oeufs'. "
                       "Réponds AIDE pour de l'aide, STOP pour arrêter.",
                 "ar": "Dream Health: تم تفعيل الرسائل. أرسل ما أكلت، مثل '1 كوب أرز، 2 بيض'. "
                       "أرسل HELP للمساعدة، وSTOP للإيقاف.",
                 "zh": "Dream Health：短信已开启。发送你吃了什么，例如“1杯米饭，2个鸡蛋”。"
                       "回复 HELP 获取帮助，回复 STOP 停止。"},

    # ---- reminders -----------------------------------------------------------------------------
    "rem_breakfast": {"en": "Dream Health: did you have breakfast? Send what you ate, like '1 cup oats, 1 banana'.",
                      "es": "Dream Health: ¿desayunaste? Envía lo que comiste, como '1 taza de avena, 1 banana'.",
                      "fr": "Dream Health : as-tu pris ton petit-déjeuner ? Envoie ce que tu as mangé, comme '1 tasse d'avoine, 1 banane'.",
                      "ar": "Dream Health: هل تناولت الفطور؟ أرسل ما أكلت، مثل '1 كوب شوفان، 1 موزة'.",
                      "zh": "Dream Health：吃早餐了吗？发送你吃了什么，例如“1杯燕麦，1根香蕉”。"},
    "rem_lunch": {"en": "Dream Health: time to log lunch. Send what you ate, like '1 cup rice, 150 g roasted chicken'.",
                  "es": "Dream Health: hora de anotar el almuerzo. Envía lo que comiste, como '1 taza de arroz, 150 g de pollo asado'.",
                  "fr": "Dream Health : c'est l'heure de noter le déjeuner. Envoie ce que tu as mangé, comme '1 tasse de riz, 150 g de poulet rôti'.",
                  "ar": "Dream Health: حان وقت تسجيل الغداء. أرسل ما أكلت، مثل '1 كوب أرز، 150 غ دجاج مشوي'.",
                  "zh": "Dream Health：该记录午餐了。发送你吃了什么，例如“1杯米饭，150克烤鸡胸肉”。"},
    "rem_dinner": {"en": "Dream Health: how was dinner? Send what you ate to log it.",
                   "es": "Dream Health: ¿qué tal la cena? Envía lo que comiste para anotarlo.",
                   "fr": "Dream Health : comment s'est passé le dîner ? Envoie ce que tu as mangé pour le noter.",
                   "ar": "Dream Health: كيف كان العشاء؟ أرسل ما أكلت لتسجيله.",
                   "zh": "Dream Health：晚餐吃得怎么样？发送你吃了什么来记录。"},
    "rem_snack": {"en": "Dream Health: had a snack? Send it to log it.",
                  "es": "Dream Health: ¿comiste algo? Envíalo para anotarlo.",
                  "fr": "Dream Health : une collation ? Envoie-la pour la noter.",
                  "ar": "Dream Health: هل تناولت وجبة خفيفة؟ أرسلها لتسجيلها.",
                  "zh": "Dream Health：吃零食了吗？发过来记录一下。"},
    "rem_custom": {"en": "Dream Health reminder.", "es": "Recordatorio de Dream Health.",
                   "fr": "Rappel Dream Health.", "ar": "تذكير من Dream Health.", "zh": "Dream Health 提醒。"},
}

MEAL = {
    "breakfast": {"en": "breakfast", "es": "desayuno", "fr": "petit-déjeuner", "ar": "فطور", "zh": "早餐"},
    "lunch": {"en": "lunch", "es": "almuerzo", "fr": "déjeuner", "ar": "غداء", "zh": "午餐"},
    "dinner": {"en": "dinner", "es": "cena", "fr": "dîner", "ar": "عشاء", "zh": "晚餐"},
    "snack": {"en": "snack", "es": "merienda", "fr": "collation", "ar": "وجبة خفيفة", "zh": "加餐"},
    "other": {"en": "meal", "es": "comida", "fr": "repas", "ar": "وجبة", "zh": "餐"},
}

# (singular, plural) per language.
UNIT = {
    "g": {"en": ("g", "g"), "es": ("g", "g"), "fr": ("g", "g"), "ar": ("غ", "غ"), "zh": ("克", "克")},
    "kg": {"en": ("kg", "kg"), "es": ("kg", "kg"), "fr": ("kg", "kg"), "ar": ("كغ", "كغ"), "zh": ("公斤", "公斤")},
    "cup": {"en": ("cup", "cups"), "es": ("taza", "tazas"), "fr": ("tasse", "tasses"), "ar": ("كوب", "أكواب"),
            "zh": ("杯", "杯")},
    "slice": {"en": ("slice", "slices"), "es": ("rebanada", "rebanadas"), "fr": ("tranche", "tranches"),
              "ar": ("شريحة", "شرائح"), "zh": ("片", "片")},
    "tbsp": {"en": ("tbsp", "tbsp"), "es": ("cucharada", "cucharadas"), "fr": ("c. à soupe", "c. à soupe"),
             "ar": ("ملعقة كبيرة", "ملاعق كبيرة"), "zh": ("汤匙", "汤匙")},
    "tsp": {"en": ("tsp", "tsp"), "es": ("cucharadita", "cucharaditas"), "fr": ("c. à café", "c. à café"),
            "ar": ("ملعقة صغيرة", "ملاعق صغيرة"), "zh": ("茶匙", "茶匙")},
    "large": {"en": ("large", "large"), "es": ("grande", "grandes"), "fr": ("gros", "gros"),
              "ar": ("حبة كبيرة", "حبات كبيرة"), "zh": ("个", "个")},
    "medium": {"en": ("medium", "medium"), "es": ("mediano", "medianos"), "fr": ("moyen", "moyens"),
               "ar": ("حبة متوسطة", "حبات متوسطة"), "zh": ("个", "个")},
    "small": {"en": ("small", "small"), "es": ("pequeño", "pequeños"), "fr": ("petit", "petits"),
              "ar": ("حبة صغيرة", "حبات صغيرة"), "zh": ("个", "个")},
    "piece": {"en": ("piece", "pieces"), "es": ("pieza", "piezas"), "fr": ("morceau", "morceaux"),
              "ar": ("قطعة", "قطع"), "zh": ("块", "块")},
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


# ---- text-message alphabet ---------------------------------------------------------------------
# GSM-7 (the standard text alphabet) has é, è, à, ù, ñ, ü, ¿, ¡ but not á, í, ó, ú, â, ê, ô... Swap those so a
# Latin-script text stays cheap. Arabic and Chinese have no GSM-7 form, so those texts are sent as Unicode.
_SMS_SWAP = str.maketrans({"á": "a", "í": "i", "ó": "o", "ú": "u", "Á": "A", "Í": "I", "Ó": "O", "Ú": "U",
                           "’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"})
GSM7_EXTRA = set("£¥èéùìòÇØøÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉÄÖÑÜ§¿äöñüà¡")
_NON_LATIN = re.compile(r"[؀-ۿݐ-ݿ　-〿㐀-鿿＀-￯]")


def needs_unicode_sms(text: str) -> bool:
    return bool(_NON_LATIN.search(text))


def sms_safe(text: str) -> str:
    if needs_unicode_sms(text):  # Arabic / Chinese: keep every character
        return text
    text = text.translate(_SMS_SWAP)
    out = []
    for ch in text:
        if ch.isascii() or ch in GSM7_EXTRA:
            out.append(ch)
        else:  # any other accent: drop it ("ç" -> "c", "ô" -> "o"); unknown symbols are removed
            out.append(unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode("ascii"))
    return "".join(out)


def is_gsm7(text: str) -> bool:
    return all(ch.isascii() or ch in GSM7_EXTRA for ch in text)

# Dream Health AI (test version 0.4)

By **Abdirisak Omar** · © 2026 Abdirisak Omar. All rights reserved. See [LICENSE](LICENSE).

A helper where people text what they ate and see how much "fuel" is left for the day.

> Test version for a personal pilot. Not medical advice.
> Food numbers are **development placeholders** and must be replaced with reviewed data before real users.

## What's inside

| Part | What it does |
|---|---|
| **Web app** (http://localhost:8000) | Today screen with a fuel gauge, Chat, Texts, Reminders, Settings |
| **Chat** | Type `lunch: 1 cup rice, 2 eggs` → you get a draft with calories → reply `YES` to save |
| **Texts (fake phone)** | Same as chat, but by "text message". In **test mode**, texts stay on your computer and cost nothing |
| **Reminders** | "Time to log lunch" at the time you pick, in your own time zone. Skips if you already logged that meal. Sends to the app, pop-up notifications, and texts |
| **Phone + consent** | Add a number, confirm with a 6-digit code, agree to texts. `STOP` turns texts off, `START` turns them back on |
| **API remote control** | http://localhost:8000/docs |

**Languages:** English, Soomaali and Español. Pick one on the login page or in Settings → Profile.
Screens, chat replies, texts and reminders all follow that choice.
Somali and Spanish translations need a native speaker's check before launch
(screen text: `backend/app/web/i18n.js`, replies: `backend/app/i18n.py`).

Words the app understands in chat and texts:

| You send | What happens |
|---|---|
| `lunch: 1 cup rice, 150 g roasted chicken` | Makes a draft (nothing saved yet) |
| `i ate 150g of roasted chicken 200g of rice` | Also works: everyday sentences, no commas needed. Typos get a "did you mean" |
| `YES` / `HAA` / `SÍ` | Saves the draft |
| `NO` / `MAYA` | Throws the draft away (in chat) |
| `TODAY` / `MAANTA` / `HOY` | Today's totals and what's left |
| `UNDO` / `TIRTIR` / `DESHACER` | Removes the last saved meal today |
| `HELP` / `CAAWI` / `AYUDA` | How to use it |
| `waxaan cunay 1 koob bariis iyo 2 ukun` | Somali meal |
| `comí 1 taza de arroz y 2 huevos` | Spanish meal |
| `STOP` / `CANCEL` (texts) | Turns texts off. Required by phone carriers |
| `START` (texts) | Turns texts back on |

## First time setup

You need **Docker Desktop** running ("Engine running" in green).

1. Open a terminal in this folder (the one with `docker-compose.yml`).
2. Make your settings file: `copy .env.example .env` (Windows) or `cp .env.example .env` (Mac/Linux).
3. Put long random values in `POSTGRES_PASSWORD` and `JWT_SECRET` in `.env`.
4. Start it: `docker compose up --build`
5. Open **http://localhost:8000**

## Updating from an older version

Your `.env` file and your saved data are kept.

1. Stop the app: press `Ctrl + C` in the terminal where it runs.
2. Unzip the new version **over** the old folder and choose **Replace** when asked.
3. Run `docker compose up --build`. The database updates itself.

## Try the full flow (about 5 minutes)

1. **Log in** at http://localhost:8000 (or create an account).
2. **Settings → Daily goal**: e.g. 2200 kcal, 140 g protein → *Save goal*.
3. **Settings → Phone and texts**: type any number, e.g. `+1 612 555 0100` → *Text me a code*.
4. Open **Texts**. The code is on the fake phone. Go back to Settings, type it, keep the box ticked, *Confirm number*.
5. **Chat**: send `lunch: 1 cup rice, 150 g roasted chicken breast`, then tap *Yes, save*.
6. **Texts**: text `dinner: 1 cup lentils`, then `YES`.
7. **Reminders**: add one, tick *Text message*, press *Send now*. It shows up in Chat and Texts.
8. **Today**: the gauge shows what's left.

## Turning on real texts later (launch)

Nothing in the app changes. Only `.env` does:

```
SMS_PROVIDER=twilio
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM=+1...
```

Still to build for launch: the incoming-text webhook (so replies from real phones reach the app), WhatsApp, and
checking per-country prices. See `docs/phase-1-status.md`.

## Run the tests

```
docker compose run --rm api pytest
```

99 tests: nutrition math, the text reader, login, targets, meals, chat, texts, STOP/START, phone codes,
reminders, and checks that one user never sees another user's data.

## Folder map

```
backend/app/
  core/       settings, database, login tokens, error format
  users/      register, login, profile
  targets/    daily goal
  foods/      food records + sample food list
  meals/      draft → confirm, nutrition math, text reader, daily totals
  messaging/  chat brain (engine.py), texts, phone codes, SMS provider switch
  reminders/  reminders + background checker
  audit/      change history
  web/        the web app (index.html, styles.css, app.js)
backend/alembic/   database updates
backend/tests/
docs/
```

## Copyright

© 2026 Abdirisak Omar. All rights reserved. Contact: Abdirisak8427@gmail.com

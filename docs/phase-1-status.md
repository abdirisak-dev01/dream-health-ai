# Status (2026-11-07, version 0.2 "test version")

## Done and tested (85 automated tests on PostgreSQL 16, plus a full click-through in a real browser)

Phase 1 core
- Docker Compose (API + PostgreSQL), `/health`, login with bcrypt + 30-minute tokens + login throttling
- Editable daily goals, food lookup (raw vs cooked kept apart), text meal logging → draft → confirm
- Day totals in the user's own time zone, soft delete, append-only audit history, cross-user access blocked

Added in 0.2
- Web app at `/` (Today gauge, Chat, Texts, Reminders, Settings), phone-first, light + dark mode
- One conversation brain for chat and texts: meal → draft, YES/NO, TODAY, UNDO, HELP; Somali shortcuts (HAA, MAYA, MAANTA)
- Text replies are plain ASCII (non-ASCII texts cost 2-3x per message)
- Phone number + 6-digit code (hashed, 10-minute expiry, 5 tries) + explicit consent to texts
- STOP / CANCEL / UNSUBSCRIBE turn texts off with one confirmation, START turns them back on
- SMS provider switch: `outbox` (test mode, free) or `twilio` (real). Fake phone only works in test mode
- Reminders: per user time zone, chosen days, 2-hour send window, once a day, skip if that meal is logged,
  in-app + browser pop-up + text; background checker every 30 s; safe if two API containers run (SKIP LOCKED)
- Migration 0002 tested on a database that already has users

## Needed before launch (owner in brackets)
1. Incoming-text webhook for the real provider (with signature check) so replies from real phones reach the app. [Backend]
2. WhatsApp channel (main channel for users outside the US/Canada, where SMS costs 5-37 cents per text). [Backend + Product]
3. Check per-country prices for the launch countries; set a monthly spending cap at the provider. [Product/Finance]
4. US texting registration (toll-free verification or 10DLC). [Product/Legal]
5. Replace dev food values with a reviewed USDA FoodData Central import. [Nutrition]
6. Native-speaker check of Somali/Spanish words and replies; reply translations. [Localization]
7. Account deletion + data export; logout/token revocation; password reset. [Security/Privacy]
8. Login limiter on shared storage if more than one API container runs; backups + restore drill. [DevOps/SRE]

## Known limits of the test version
- Browser pop-up reminders only appear while the web app is open in a tab.
- Login lasts 30 minutes; after that the app asks you to log in again.
- The text reader is rule-based: unclear foods are asked about, never guessed.

## Open questions for the Product Owner
- Allow saving the clear lines of a meal while asking about the unclear ones?
- Default reminder set for new users (e.g. lunch 12:30, dinner 18:30)?
- Day boundary for night-shift users?

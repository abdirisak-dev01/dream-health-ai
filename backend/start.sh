#!/bin/sh
# Update the database, load sample foods (skips ones already there), then start the API.
set -e
alembic upgrade head
python -m app.foods.service
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 ${UVICORN_EXTRA_ARGS}

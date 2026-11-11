"""Dream Health AI - backend (modular monolith)."""
import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.audit.router import router as audit_router
from app.audit.service import current_request_id
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.errors import install_error_handlers
from app.foods.router import router as foods_router
from app.meals.router import days_router, meals_router
from app.messaging.router import chat_router, dev_router, phone_router
from app.reminders import service as reminders_service
from app.reminders.router import router as reminders_router
from app.targets.router import router as targets_router
from app.users.router import auth_router, me_router

API_VERSION = "0.4.0"
log = logging.getLogger("dhai")
WEB_DIR = Path(__file__).parent / "web"


async def _reminder_loop(tick: int):
    """Background alarm clock: checks reminders every `tick` seconds."""
    while True:
        try:
            with get_sessionmaker()() as db:
                sent = await asyncio.to_thread(reminders_service.run_due, db)
            if sent:
                log.info(json.dumps({"event": "reminders_sent", "count": sent}))
        except Exception:  # never let one bad run stop the clock
            log.exception("reminder loop error")
        await asyncio.sleep(tick)


@asynccontextmanager
async def lifespan(app: FastAPI):
    tick = get_settings().reminder_tick_seconds
    task = asyncio.create_task(_reminder_loop(tick)) if tick > 0 else None
    yield
    if task:
        task.cancel()


def create_app() -> FastAPI:
    get_settings().check_safe_for_env()
    app = FastAPI(
        title="Dream Health AI API",
        version=API_VERSION,
        description="Login, targets, food lookup, meal logging with confirmation, daily totals, chat, "
                    "text messages (test mode), reminders and audit history. "
                    "Planning-stage software: not medical advice. The web app is at /app/",
        lifespan=lifespan,
    )
    install_error_handlers(app)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        rid = rid[:64]
        request.state.request_id = rid
        token = current_request_id.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            current_request_id.reset(token)
        response.headers["X-Request-ID"] = rid
        # Structured log line. No bodies, no tokens: paths only.
        log.info(json.dumps({"request_id": rid, "method": request.method, "path": request.url.path,
                             "status": response.status_code,
                             "ms": round((time.perf_counter() - start) * 1000, 1)}))
        return response

    @app.get("/health", tags=["health"], summary="Is the API up and can it reach the database?")
    def health():
        try:
            with get_sessionmaker()() as db:
                db.execute(text("SELECT 1"))
            return {"status": "ok", "database": "ok", "version": API_VERSION}
        except Exception:
            return JSONResponse({"status": "degraded", "database": "unreachable", "version": API_VERSION},
                                status_code=503)

    for r in (auth_router, me_router, phone_router, targets_router, foods_router, meals_router, days_router,
              chat_router, reminders_router, dev_router, audit_router):
        app.include_router(r)

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/app/")

    app.mount("/app", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app


logging.basicConfig(level=logging.INFO, format="%(message)s")
app = create_app()

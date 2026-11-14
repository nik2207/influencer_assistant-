import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from . import background, models, schema_upgrade  # noqa: F401  (models registers tables)
from .services import workspace_bootstrap
from .config import settings
from .db import Base, engine
from .routers import (agent, analytics, auth, brand_crm, calendar, campaign_roi, contacts, content, deals, events,
                      expenses, followups, gmail, invoices, media_kit, outreach, profile, voice, workspace)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)  # creates any new tables; existing tables are untouched
    schema_upgrade.upgrade()
    workspace_bootstrap.upgrade_schema_columns()
    from .db import SessionLocal
    db = SessionLocal()
    try:
        workspace_bootstrap.backfill_all_users(db)
    finally:
        db.close()
    task = None
    if settings.background_jobs:
        task = asyncio.create_task(background.run(settings.background_interval_minutes))
    yield
    if task:
        task.cancel()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.state.limiter = auth.limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["*"], allow_headers=["*"],
)

for r in (auth, workspace, deals, events, contacts, invoices, expenses, campaign_roi, analytics, content, media_kit,
          brand_crm, agent, voice, outreach, gmail, calendar, followups, profile):
    app.include_router(r.router)


@app.get("/health")
def health():
    return {"status": "ok", "llm": settings.llm_provider}


web_dir = Path(__file__).resolve().parent.parent / "web"
if web_dir.exists():
    app.mount("/app", StaticFiles(directory=web_dir, html=True), name="web")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/app/")

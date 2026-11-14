"""Create personal workspaces and backfill workspace_id on legacy rows."""
from __future__ import annotations

import re

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from .. import models
from ..db import engine

TENANT_TABLES = (
    "deals", "events", "contacts", "invoices", "invoice_payments", "expenses",
    "outreach_pitches", "bookings", "pending_actions", "chat_messages",
    "email_messages", "follow_ups", "brand_records", "brand_notes", "brand_follow_ups",
    "content_plan_items", "content_drafts", "content_items", "metric_snapshots",
    "import_batches", "social_accounts", "platform_connections",
    "media_kits", "media_kit_rate_lines", "media_kit_portfolio", "media_kit_samples",
    "media_kit_shares", "creator_profiles", "gmail_accounts", "calendar_links",
    "event_syncs", "event_suggestions",
)


def _slug(name: str, user_id: int) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (name or "workspace").lower()).strip("-")[:40] or "workspace"
    return f"{base}-{user_id}"


def ensure_personal_workspace(db: Session, user: models.User) -> models.WorkspaceMembership:
    mem = (
        db.query(models.WorkspaceMembership)
        .filter_by(user_id=user.id, status="active")
        .order_by(models.WorkspaceMembership.id)
        .first()
    )
    if mem:
        return mem
    ws = models.Workspace(
        name=f"{user.name or 'Creator'}'s workspace",
        slug=_slug(user.name or "creator", user.id),
        workspace_type="creator",
        owner_user_id=user.id,
    )
    db.add(ws)
    db.flush()
    mem = models.WorkspaceMembership(
        workspace_id=ws.id, user_id=user.id, role="owner", status="active",
    )
    db.add(mem)
    db.commit()
    backfill_user_workspace(db, user.id, ws.id)
    return mem


def backfill_user_workspace(db: Session, user_id: int, workspace_id: int) -> None:
    for table in TENANT_TABLES:
        if table not in inspect(engine).get_table_names():
            continue
        cols = {c["name"] for c in inspect(engine).get_columns(table)}
        if "workspace_id" not in cols:
            continue
        db.execute(
            text(f"UPDATE {table} SET workspace_id = :wid WHERE user_id = :uid AND (workspace_id IS NULL OR workspace_id = 0)"),
            {"wid": workspace_id, "uid": user_id},
        )
    db.commit()


def backfill_all_users(db: Session) -> int:
    count = 0
    for user in db.query(models.User).order_by(models.User.id).all():
        if db.query(models.WorkspaceMembership).filter_by(user_id=user.id, status="active").first():
            ws_id = (
                db.query(models.WorkspaceMembership.workspace_id)
                .filter_by(user_id=user.id, status="active")
                .order_by(models.WorkspaceMembership.id)
                .scalar()
            )
            if ws_id:
                backfill_user_workspace(db, user.id, ws_id)
            continue
        ensure_personal_workspace(db, user)
        count += 1
    return count


def upgrade_schema_columns() -> None:
    if not str(engine.url).startswith("sqlite"):
        return
    insp = inspect(engine)
    tables = insp.get_table_names()
    for table in TENANT_TABLES:
        if table not in tables:
            continue
        cols = {c["name"] for c in insp.get_columns(table)}
        if "workspace_id" in cols:
            continue
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN workspace_id INTEGER"))
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_workspace_id ON {table} (workspace_id)"))
    audit_cols = {c["name"] for c in insp.get_columns("audit_logs")} if "audit_logs" in tables else set()
    if "audit_logs" in tables:
        with engine.begin() as conn:
            if "workspace_id" not in audit_cols:
                conn.execute(text("ALTER TABLE audit_logs ADD COLUMN workspace_id INTEGER"))
            if "resource_type" not in audit_cols:
                conn.execute(text("ALTER TABLE audit_logs ADD COLUMN resource_type VARCHAR(40) DEFAULT ''"))
            if "resource_id" not in audit_cols:
                conn.execute(text("ALTER TABLE audit_logs ADD COLUMN resource_id INTEGER"))

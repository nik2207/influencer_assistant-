"""Lightweight SQLite column adds for existing deployments (non-destructive)."""
from sqlalchemy import inspect, text

from .db import engine


def _cols(table: str) -> set[str]:
    insp = inspect(engine)
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def _add(table: str, col: str, ddl: str) -> None:
    if col in _cols(table):
        return
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))


def upgrade() -> None:
    if not str(engine.url).startswith("sqlite"):
        return
    inv = [
        ("issue_date", "issue_date DATE"),
        ("due_date", "due_date DATE"),
        ("creator_name", "creator_name VARCHAR(160) DEFAULT ''"),
        ("creator_email", "creator_email VARCHAR(255) DEFAULT ''"),
        ("creator_phone", "creator_phone VARCHAR(40) DEFAULT ''"),
        ("creator_address", "creator_address TEXT DEFAULT ''"),
        ("client_name", "client_name VARCHAR(160) DEFAULT ''"),
        ("client_email", "client_email VARCHAR(255) DEFAULT ''"),
        ("client_address", "client_address TEXT DEFAULT ''"),
        ("campaign", "campaign VARCHAR(255) DEFAULT ''"),
        ("deliverables", "deliverables TEXT DEFAULT ''"),
        ("work_description", "work_description TEXT DEFAULT ''"),
        ("line_items", "line_items JSON"),
        ("discount_inr", "discount_inr FLOAT DEFAULT 0"),
        ("tax_percent", "tax_percent FLOAT DEFAULT 0"),
        ("tax_inr", "tax_inr FLOAT DEFAULT 0"),
        ("currency", "currency VARCHAR(3) DEFAULT 'INR'"),
        ("paid_inr", "paid_inr FLOAT DEFAULT 0"),
        ("payment_method", "payment_method VARCHAR(24) DEFAULT ''"),
        ("payment_reference", "payment_reference VARCHAR(120) DEFAULT ''"),
        ("notes", "notes TEXT DEFAULT ''"),
        ("terms", "terms TEXT DEFAULT ''"),
        ("signature_text", "signature_text VARCHAR(120) DEFAULT ''"),
        ("sent_at", "sent_at DATETIME"),
        ("updated_at", "updated_at DATETIME"),
    ]
    for col, ddl in inv:
        _add("invoices", col, ddl)
    for col, ddl in [
        ("connection_status", "connection_status VARCHAR(12) DEFAULT 'manual'"),
        ("external_id", "external_id VARCHAR(64) DEFAULT ''"),
        ("last_synced_at", "last_synced_at DATETIME"),
    ]:
        _add("social_accounts", col, ddl)
    for col, ddl in [
        ("brand_record_id", "brand_record_id INTEGER"),
        ("email_verified", "email_verified BOOLEAN DEFAULT 0"),
    ]:
        _add("contacts", col, ddl)
    for col, ddl in [
        ("production_cost_estimate_inr", "production_cost_estimate_inr FLOAT DEFAULT 0"),
    ]:
        _add("deals", col, ddl)
    for col, ddl in [
        ("source", "source VARCHAR(10) DEFAULT 'text'"),
        ("voice_meta", "voice_meta JSON DEFAULT '{}'"),
    ]:
        _add("chat_messages", col, ddl)
    for col, ddl in [
        ("recognized_text", "recognized_text VARCHAR(2000) DEFAULT ''"),
    ]:
        _add("pending_actions", col, ddl)
    for col, ddl in [
        ("brand_record_id", "brand_record_id INTEGER"),
        ("is_brand_inquiry", "is_brand_inquiry BOOLEAN DEFAULT 0"),
        ("intelligence_version", "intelligence_version INTEGER DEFAULT 0"),
        ("intelligence_json", "intelligence_json JSON DEFAULT '{}'"),
        ("intelligence_at", "intelligence_at DATETIME"),
        ("suggested_reply", "suggested_reply TEXT DEFAULT ''"),
    ]:
        _add("email_messages", col, ddl)
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE invoices SET paid_inr = amount_inr WHERE status = 'paid' AND (paid_inr IS NULL OR paid_inr = 0)"
        ))

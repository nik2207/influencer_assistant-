"""Expense summaries and receipt validation."""
from __future__ import annotations

import imghdr
from datetime import date
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from .. import models

OUT_DIR = Path("data/receipts")
MAX_RECEIPT_BYTES = 5 * 1024 * 1024
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


def sniff_kind(data: bytes) -> Optional[str]:
    if data[:4] == b"%PDF":
        return "application/pdf"
    kind = imghdr.what(None, data)
    if kind == "jpeg":
        return "image/jpeg"
    if kind == "png":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def save_receipt(workspace_id: int, user_id: int, expense_id: int, data: bytes, claimed_mime: str) -> tuple[str, str]:
    if len(data) > MAX_RECEIPT_BYTES:
        raise ValueError("Receipt must be 5 MB or smaller.")
    mime = sniff_kind(data)
    if not mime or mime not in ALLOWED_MIME:
        raise ValueError("Receipt must be a JPEG, PNG, WebP or PDF file.")
    ext = { "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "application/pdf": ".pdf" }[mime]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"w{workspace_id}_u{user_id}_e{expense_id}{ext}"
    path.write_bytes(data)
    return str(path), mime


def period_total_ws(db: Session, workspace_id: int, from_date: date, to_date: date) -> float:
    rows = (
        db.query(models.Expense)
        .filter(
            models.Expense.workspace_id == workspace_id,
            models.Expense.spent_on >= from_date,
            models.Expense.spent_on <= to_date,
        )
        .all()
    )
    return round(sum(r.amount_inr for r in rows), 2)


def period_total(db: Session, user_id: int, from_date: date, to_date: date) -> float:
    rows = (db.query(models.Expense)
            .filter(models.Expense.user_id == user_id,
                    models.Expense.spent_on >= from_date,
                    models.Expense.spent_on <= to_date).all())
    return round(sum(r.amount_inr for r in rows), 2)

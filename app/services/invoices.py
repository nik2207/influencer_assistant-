"""Invoice totals, status, PDF and payment helpers."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .. import models
from ..security import audit
from . import invoice_pdf, payments, profile as profile_service
from .tools import now_ist


def _today() -> date:
    return now_ist().date()


def line_subtotal(items: list) -> float:
    total = 0.0
    for row in items or []:
        q = float(row.get("quantity") or 0)
        p = float(row.get("unit_price") or 0)
        if q < 0 or p < 0:
            raise ValueError("Quantity and unit price must be zero or positive.")
        total += q * p
    return round(total, 2)


def compute_totals(discount_inr: float, tax_percent: float, items: list) -> tuple[float, float, float]:
    sub = line_subtotal(items)
    discount = max(0.0, float(discount_inr or 0))
    if discount > sub:
        raise ValueError("Discount cannot exceed the subtotal.")
    taxable = round(sub - discount, 2)
    tax_pct = max(0.0, float(tax_percent or 0))
    tax = round(taxable * tax_pct / 100.0, 2)
    total = round(taxable + tax, 2)
    return taxable, tax, total


def apply_overdue(inv: models.Invoice) -> None:
    if inv.status in ("sent", "partially_paid") and inv.due_date and inv.due_date < _today():
        inv.status = "overdue"


def refresh_amount(inv: models.Invoice) -> None:
    _, tax, total = compute_totals(inv.discount_inr, inv.tax_percent, inv.line_items)
    inv.tax_inr = tax
    inv.amount_inr = total


def creator_defaults(db: Session, user: models.User) -> dict:
    ctx = profile_service.pitch_context(db, user)
    cp = db.query(models.CreatorProfile).filter_by(user_id=user.id).first()
    return {
        "creator_name": user.name or "",
        "creator_email": (cp.contact_email if cp else "") or user.email,
        "creator_phone": (cp.phone if cp else "") or "",
        "creator_address": (cp.home_location if cp else "") or user.city or "",
        "currency": (cp.currency if cp else "INR") or "INR",
        "terms": ctx.get("invoice_notes") or "",
        "terms_days": ctx.get("terms_days") or 15,
    }


def invoice_from_deal(db: Session, user: models.User, deal: models.Deal) -> models.Invoice:
    defaults = creator_defaults(db, user)
    desc = deal.deliverables or deal.title or f"Content for {deal.brand}"
    unit = float(deal.value_inr or 0)
    items = [{"description": desc[:200], "quantity": 1, "unit_price": unit}] if unit else []
    inv = models.Invoice(
        user_id=user.id, workspace_id=deal.workspace_id, deal_id=deal.id, status="draft",
        client_name=deal.brand, campaign=deal.title or "",
        deliverables=deal.deliverables or "", work_description=desc,
        line_items=items, issue_date=_today(),
        due_date=_today() + timedelta(days=int(defaults["terms_days"])),
        creator_name=defaults["creator_name"], creator_email=defaults["creator_email"],
        creator_phone=defaults["creator_phone"], creator_address=defaults["creator_address"],
        currency=defaults["currency"], terms=defaults["terms"], notes="",
    )
    if items:
        refresh_amount(inv)
    else:
        inv.amount_inr = 0
    return inv


def assign_number(inv: models.Invoice) -> None:
    if not inv.number:
        inv.number = f"INV-{now_ist():%Y%m}-{inv.id:04d}"


def duplicate_open_draft(db: Session, user_id: int, deal_id: int) -> Optional[models.Invoice]:
    return (db.query(models.Invoice)
            .filter_by(user_id=user_id, deal_id=deal_id, status="draft").first())


def regenerate_pdf(db: Session, user: models.User, inv: models.Invoice) -> str:
    assign_number(inv)
    inv.pdf_path = invoice_pdf.build_invoice_pdf(inv, user)
    return inv.pdf_path


def mark_sent(db: Session, user: models.User, inv: models.Invoice) -> None:
    if inv.status != "draft":
        raise ValueError("Only draft invoices can be marked as sent.")
    if inv.amount_inr <= 0:
        raise ValueError("Add at least one line item with an amount before sending.")
    refresh_amount(inv)
    inv.payment_link = payments.make_payment_link(user, inv.amount_inr, inv.number or "invoice",
                                                   inv.creator_name or user.name or "Creator")
    inv.sent_at = now_ist()
    inv.status = "sent"
    regenerate_pdf(db, user, inv)


def record_payment(db: Session, user: models.User, inv: models.Invoice, amount: float,
                   paid_at: date, method: str = "", reference: str = "", notes: str = "") -> models.InvoicePayment:
    if inv.status in ("draft", "cancelled"):
        raise ValueError("Cannot record payments on a draft or cancelled invoice.")
    if amount <= 0:
        raise ValueError("Payment amount must be greater than zero.")
    outstanding = round(inv.amount_inr - inv.paid_inr, 2)
    if amount > outstanding + 0.01:
        raise ValueError(f"Payment exceeds outstanding balance ({outstanding:.2f}).")
    pay = models.InvoicePayment(user_id=user.id, invoice_id=inv.id, amount_inr=round(amount, 2),
                                paid_at=paid_at, method=method or "", reference=reference or "", notes=notes or "")
    db.add(pay)
    inv.paid_inr = round(inv.paid_inr + pay.amount_inr, 2)
    if inv.paid_inr >= inv.amount_inr - 0.01:
        inv.status = "paid"
        inv.paid_inr = inv.amount_inr
        if inv.deal_id:
            deal = db.get(models.Deal, inv.deal_id)
            if deal and deal.user_id == user.id:
                deal.status = "done"
    else:
        inv.status = "partially_paid"
    apply_overdue(inv)
    audit(db, user.id, "invoice_payment", f"{inv.number} +{pay.amount_inr}")
    return pay


def mark_paid_full(db: Session, user: models.User, inv: models.Invoice) -> None:
    outstanding = round(inv.amount_inr - inv.paid_inr, 2)
    if outstanding <= 0:
        inv.status = "paid"
        return
    record_payment(db, user, inv, outstanding, _today(), method=inv.payment_method or "other",
                   reference=inv.payment_reference or "manual")


def payment_reminder_draft(inv: models.Invoice, deal: Optional[models.Deal]) -> str:
    brand = inv.client_name or (deal.brand if deal else "there")
    due = inv.due_date.strftime("%d %b %Y") if inv.due_date else "the due date"
    outstanding = max(0.0, round(inv.amount_inr - inv.paid_inr, 2))
    return (
        f"Hi {brand} team,\n\n"
        f"Hope you're doing well. This is a gentle reminder that invoice {inv.number} for "
        f"₹{outstanding:,.2f} was due on {due}. "
        f"{'We have received ₹' + f'{inv.paid_inr:,.2f} so far; the remaining balance is ₹' + f'{outstanding:,.2f}.' if inv.paid_inr else ''}\n\n"
        f"Please let me know if you need the invoice or payment link resent.\n\n"
        f"Thank you,\n{inv.creator_name or 'Creator'}"
    )


def summary(db: Session, user: models.User, from_date: Optional[date] = None, to_date: Optional[date] = None,
            *, workspace_id: int | None = None) -> dict:
    q = db.query(models.Invoice)
    rows = q.filter_by(workspace_id=workspace_id).all() if workspace_id else q.filter_by(user_id=user.id).all()
    for inv in rows:
        apply_overdue(inv)
    db.commit()
    total_invoiced = 0.0
    total_received = 0.0
    outstanding = 0.0
    overdue_count = 0
    overdue_amount = 0.0
    for inv in rows:
        if inv.status == "cancelled":
            continue
        if from_date and inv.issue_date and inv.issue_date < from_date:
            continue
        if to_date and inv.issue_date and inv.issue_date > to_date:
            continue
        if inv.status != "draft":
            total_invoiced += inv.amount_inr
        total_received += inv.paid_inr
        bal = max(0.0, round(inv.amount_inr - inv.paid_inr, 2))
        if inv.status in ("sent", "partially_paid", "overdue") and bal > 0:
            outstanding += bal
        if inv.status == "overdue" and bal > 0:
            overdue_count += 1
            overdue_amount += bal
    return {
        "total_invoiced": round(total_invoiced, 2),
        "total_received": round(total_received, 2),
        "outstanding": round(outstanding, 2),
        "overdue_count": overdue_count,
        "overdue_amount": round(overdue_amount, 2),
    }

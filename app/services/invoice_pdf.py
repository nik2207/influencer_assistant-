from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from .. import models

OUT_DIR = Path("data/invoices")


def _money(amount: float, currency: str = "INR") -> str:
    sym = "₹" if currency == "INR" else f"{currency} "
    return f"{sym}{amount:,.2f}"


def build_invoice_pdf(inv: models.Invoice, user: models.User) -> str:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    number = inv.number or f"draft-{inv.id}"
    path = OUT_DIR / f"{number}.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    y = h - 20 * mm
    c.setFont("Helvetica-Bold", 22)
    c.drawString(20 * mm, y, "INVOICE")
    c.setFont("Helvetica", 10)
    y -= 9 * mm
    c.drawString(20 * mm, y, f"Invoice no: {number}")
    issue = inv.issue_date or (inv.created_at.date() if inv.created_at else datetime.now().date())
    c.drawRightString(w - 20 * mm, y, f"Issue date: {issue:%d %b %Y}")
    y -= 6 * mm
    if inv.due_date:
        c.drawRightString(w - 20 * mm, y, f"Due date: {inv.due_date:%d %b %Y}")
    y -= 10 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, "From")
    c.drawString(105 * mm, y, "Bill to")
    c.setFont("Helvetica", 10)
    y -= 5 * mm
    from_lines = [inv.creator_name or user.name or "Creator", inv.creator_email, inv.creator_phone, inv.creator_address]
    to_lines = [inv.client_name, inv.client_email, inv.client_address, ""]
    for i in range(4):
        if from_lines[i]:
            c.drawString(20 * mm, y - i * 5 * mm, str(from_lines[i])[:55])
        if to_lines[i]:
            c.drawString(105 * mm, y - i * 5 * mm, str(to_lines[i])[:55])
    y -= 28 * mm
    if inv.campaign or inv.deal_id:
        c.setFont("Helvetica", 9)
        meta = f"Deal #{inv.deal_id}" if inv.deal_id else ""
        if inv.campaign:
            meta = (meta + " · " if meta else "") + inv.campaign
        c.drawString(20 * mm, y, meta[:100])
        y -= 8 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, y, "Description")
    c.drawRightString(155 * mm, y, "Qty")
    c.drawRightString(w - 20 * mm, y, "Amount")
    c.line(20 * mm, y - 2 * mm, w - 20 * mm, y - 2 * mm)
    y -= 7 * mm
    c.setFont("Helvetica", 10)
    items = inv.line_items or []
    if not items and (inv.work_description or inv.deliverables):
        items = [{"description": inv.work_description or inv.deliverables, "quantity": 1, "unit_price": inv.amount_inr}]
    for row in items:
        if y < 45 * mm:
            c.showPage()
            y = h - 25 * mm
        desc = str(row.get("description") or "Service")[:65]
        qty = float(row.get("quantity") or 1)
        price = float(row.get("unit_price") or 0)
        c.drawString(20 * mm, y, desc)
        c.drawRightString(155 * mm, y, f"{qty:g}")
        c.drawRightString(w - 20 * mm, y, _money(qty * price, inv.currency))
        y -= 6 * mm
    y -= 4 * mm
    c.line(120 * mm, y, w - 20 * mm, y)
    y -= 7 * mm
    sub = sum(float(r.get("quantity") or 0) * float(r.get("unit_price") or 0) for r in items)
    c.drawRightString(140 * mm, y, "Subtotal")
    c.drawRightString(w - 20 * mm, y, _money(sub, inv.currency))
    y -= 6 * mm
    if inv.discount_inr:
        c.drawRightString(140 * mm, y, "Discount")
        c.drawRightString(w - 20 * mm, y, f"-{_money(inv.discount_inr, inv.currency).lstrip('₹')}")
        y -= 6 * mm
    if inv.tax_inr:
        c.drawRightString(140 * mm, y, f"Tax ({inv.tax_percent:g}%)")
        c.drawRightString(w - 20 * mm, y, _money(inv.tax_inr, inv.currency))
        y -= 6 * mm
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(140 * mm, y, "Total")
    c.drawRightString(w - 20 * mm, y, _money(inv.amount_inr, inv.currency))
    y -= 10 * mm
    c.setFont("Helvetica", 9)
    if inv.paid_inr:
        c.drawRightString(140 * mm, y, "Received")
        c.drawRightString(w - 20 * mm, y, _money(inv.paid_inr, inv.currency))
        y -= 6 * mm
        bal = max(0, inv.amount_inr - inv.paid_inr)
        if bal:
            c.drawRightString(140 * mm, y, "Balance due")
            c.drawRightString(w - 20 * mm, y, _money(bal, inv.currency))
            y -= 8 * mm
    if inv.payment_link and inv.status not in ("paid", "cancelled", "draft"):
        c.drawString(20 * mm, y, "Pay online:")
        y -= 5 * mm
        c.drawString(20 * mm, y, inv.payment_link[:105])
        y -= 8 * mm
    if inv.terms:
        c.setFont("Helvetica-Bold", 9)
        c.drawString(20 * mm, y, "Terms")
        y -= 5 * mm
        c.setFont("Helvetica", 9)
        for line in [inv.terms[i:i + 95] for i in range(0, min(len(inv.terms), 400), 95)]:
            c.drawString(20 * mm, y, line)
            y -= 5 * mm
    if inv.notes:
        y -= 3 * mm
        c.setFont("Helvetica-Bold", 9)
        c.drawString(20 * mm, y, "Notes")
        y -= 5 * mm
        c.setFont("Helvetica", 9)
        for line in [inv.notes[i:i + 95] for i in range(0, min(len(inv.notes), 300), 95)]:
            c.drawString(20 * mm, y, line)
            y -= 5 * mm
    if inv.signature_text:
        y = max(y, 35 * mm)
        c.drawString(20 * mm, y, inv.signature_text)
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, 15 * mm, f"Status: {inv.status.replace('_', ' ').title()} · Generated {datetime.now():%d %b %Y %H:%M}")
    c.showPage()
    c.save()
    return str(path)

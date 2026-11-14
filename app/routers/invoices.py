from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db
from ..security import audit, workspace_context
from ..services import invoices as inv_svc
from ..services import tools
from ..services.tenancy import WorkspaceCtx, get_deal, get_invoice, invoices_query, stamp

router = APIRouter(prefix="/invoices", tags=["invoices"])


def _out(inv: models.Invoice) -> schemas.InvoiceOut:
    inv_svc.apply_overdue(inv)
    bal = max(0.0, round(inv.amount_inr - inv.paid_inr, 2))
    return schemas.InvoiceOut.model_validate(inv).model_copy(
        update={"balance_inr": bal, "is_overdue": inv.status == "overdue"})


def _owned(db: Session, ctx: WorkspaceCtx, invoice_id: int) -> models.Invoice:
    return get_invoice(db, ctx, invoice_id)


@router.get("/summary", response_model=schemas.FinanceSummaryOut)
def finance_summary(from_date: date | None = None, to_date: date | None = None,
                    ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    ctx.require("invoice.read")
    s = inv_svc.summary(db, ctx.user, from_date, to_date, workspace_id=ctx.workspace_id)
    from ..services import expenses as exp_svc
    if from_date and to_date:
        s["expenses"] = exp_svc.period_total_ws(db, ctx.workspace_id, from_date, to_date)
    else:
        s["expenses"] = 0.0
    s["net_cash_flow"] = round(s["total_received"] - s["expenses"], 2)
    return s


@router.get("", response_model=list[schemas.InvoiceOut])
def list_invoices(status: str | None = None, brand: str | None = None, q: str | None = None,
                  sort: str = Query("newest", pattern="^(newest|oldest|due|amount)$"),
                  overdue_only: bool = False,
                  ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    rows = invoices_query(db, ctx).all()
    for inv in rows:
        inv_svc.apply_overdue(inv)
    db.commit()
    if status:
        rows = [r for r in rows if r.status == status]
    if brand:
        b = brand.lower()
        rows = [r for r in rows if b in (r.client_name or "").lower()]
    if q:
        qq = q.lower()
        rows = [r for r in rows if qq in (r.number or "").lower() or qq in (r.client_name or "").lower()]
    if overdue_only:
        rows = [r for r in rows if r.status == "overdue"]
    if sort == "oldest":
        rows.sort(key=lambda x: x.id)
    elif sort == "due":
        rows.sort(key=lambda x: x.due_date or date.max)
    elif sort == "amount":
        rows.sort(key=lambda x: x.amount_inr, reverse=True)
    else:
        rows.sort(key=lambda x: x.id, reverse=True)
    return [_out(r) for r in rows]


@router.post("", response_model=schemas.InvoiceOut)
def create_draft(body: schemas.InvoiceIn, ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    ctx.require("invoice.draft")
    if body.deal_id:
        get_deal(db, ctx, body.deal_id)
        if inv_svc.duplicate_open_draft(db, ctx.user.id, body.deal_id):
            raise HTTPException(400, "A draft invoice already exists for this deal. Edit it or send it first.")
    if not body.line_items:
        raise HTTPException(400, "Add at least one line item.")
    inv = models.Invoice(user_id=ctx.user.id, status="draft", **body.model_dump())
    stamp(inv, ctx)
    try:
        inv_svc.refresh_amount(inv)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.add(inv)
    db.flush()
    inv_svc.assign_number(inv)
    db.commit()
    db.refresh(inv)
    audit(db, ctx.user.id, "invoice_draft", inv.number, workspace_id=ctx.workspace_id, resource_type="invoice", resource_id=inv.id)
    return _out(inv)


@router.post("/for-deal/{deal_id}")
def create_for_deal(deal_id: int, amount_inr: float | None = None,
                    ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    ctx.require("invoice.draft")
    result = tools.run_tool(db, ctx.user, "create_invoice", {"deal_id": deal_id, "amount_inr": amount_inr}, ctx=ctx)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.get("/{invoice_id}", response_model=schemas.InvoiceOut)
def get_invoice_route(invoice_id: int, ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    return _out(_owned(db, ctx, invoice_id))


@router.patch("/{invoice_id}", response_model=schemas.InvoiceOut)
def update_draft(invoice_id: int, body: schemas.InvoiceUpdate,
                 ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    ctx.require("invoice.draft")
    inv = _owned(db, ctx, invoice_id)
    if inv.status != "draft":
        raise HTTPException(409, "Only draft invoices can be edited. Create a new draft or record a correction via payments.")
    data = body.model_dump(exclude_unset=True)
    if "line_items" in data and data["line_items"] is not None:
        data["line_items"] = [x.model_dump() if hasattr(x, "model_dump") else x for x in data["line_items"]]
    for k, v in data.items():
        setattr(inv, k, v)
    try:
        inv_svc.refresh_amount(inv)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    db.refresh(inv)
    return _out(inv)


@router.post("/{invoice_id}/send", response_model=schemas.InvoiceOut)
def send_invoice(invoice_id: int, ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    ctx.require("invoice.send")
    inv = _owned(db, ctx, invoice_id)
    try:
        inv_svc.mark_sent(db, ctx.user, inv)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    db.refresh(inv)
    audit(db, ctx.user.id, "invoice_sent", inv.number, workspace_id=ctx.workspace_id, resource_type="invoice", resource_id=inv.id)
    return _out(inv)


@router.get("/{invoice_id}/pdf")
def download_pdf(invoice_id: int, ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    ctx.require("invoice.export")
    inv = _owned(db, ctx, invoice_id)
    if inv.status == "draft":
        inv_svc.regenerate_pdf(db, ctx.user, inv)
        db.commit()
    if not inv.pdf_path:
        raise HTTPException(404, "Invoice PDF not available")
    return FileResponse(inv.pdf_path, media_type="application/pdf", filename=f"{inv.number}.pdf")


@router.get("/{invoice_id}/payments", response_model=list[schemas.InvoicePaymentOut])
def list_payments(invoice_id: int, ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    inv = _owned(db, ctx, invoice_id)
    return (
        db.query(models.InvoicePayment)
        .filter_by(invoice_id=invoice_id)
        .filter(models.InvoicePayment.workspace_id == ctx.workspace_id)
        .order_by(models.InvoicePayment.id)
        .all()
    )


@router.post("/{invoice_id}/payments", response_model=schemas.InvoicePaymentOut)
def add_payment(invoice_id: int, body: schemas.InvoicePaymentIn,
                ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    ctx.require("invoice.pay")
    inv = _owned(db, ctx, invoice_id)
    try:
        pay = inv_svc.record_payment(db, ctx.user, inv, body.amount_inr, body.paid_at or date.today(),
                                     body.method, body.reference, body.notes)
        pay.workspace_id = ctx.workspace_id
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    db.refresh(pay)
    return pay


@router.post("/{invoice_id}/mark-paid", response_model=schemas.InvoiceOut)
def mark_paid(invoice_id: int, ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    ctx.require("invoice.pay")
    inv = _owned(db, ctx, invoice_id)
    try:
        inv_svc.mark_paid_full(db, ctx.user, inv)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    db.refresh(inv)
    audit(db, ctx.user.id, "invoice_paid", inv.number, workspace_id=ctx.workspace_id, resource_type="invoice", resource_id=inv.id)
    return _out(inv)


@router.post("/{invoice_id}/reminder-draft", response_model=schemas.ReminderDraftOut)
def reminder_draft(invoice_id: int, ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    ctx.require("invoice.draft")
    inv = _owned(db, ctx, invoice_id)
    deal = get_deal(db, ctx, inv.deal_id) if inv.deal_id else None
    text = inv_svc.payment_reminder_draft(inv, deal)
    return {"draft": text, "invoice_id": inv.id}


@router.post("/{invoice_id}/cancel", response_model=schemas.InvoiceOut)
def cancel_invoice(invoice_id: int, ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    ctx.require("invoice.send")
    inv = _owned(db, ctx, invoice_id)
    if inv.status == "paid":
        raise HTTPException(400, "Paid invoices cannot be cancelled.")
    if inv.paid_inr > 0:
        raise HTTPException(400, "Record a refund or adjustment before cancelling a partially paid invoice.")
    inv.status = "cancelled"
    db.commit()
    db.refresh(inv)
    return _out(inv)

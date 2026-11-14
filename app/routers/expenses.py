from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db
from ..security import audit, workspace_context
from ..services import expenses as exp_svc
from ..services.tenancy import WorkspaceCtx, expenses_query, get_deal, get_expense, stamp

router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.get("/summary")
def expense_summary(from_date: date = Query(...), to_date: date = Query(...),
                    ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    ctx.require("expense.read")
    if to_date < from_date:
        raise HTTPException(400, "End date must be on or after start date.")
    total = exp_svc.period_total_ws(db, ctx.workspace_id, from_date, to_date)
    return {"from": from_date, "to": to_date, "total_inr": total}


@router.get("", response_model=list[schemas.ExpenseOut])
def list_expenses(category: str | None = None, q: str | None = None, deal_id: int | None = None,
                  from_date: date | None = None, to_date: date | None = None,
                  ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    qry = expenses_query(db, ctx)
    if category:
        qry = qry.filter_by(category=category)
    if deal_id:
        get_deal(db, ctx, deal_id)
        qry = qry.filter_by(deal_id=deal_id)
    if from_date:
        qry = qry.filter(models.Expense.spent_on >= from_date)
    if to_date:
        qry = qry.filter(models.Expense.spent_on <= to_date)
    rows = qry.order_by(models.Expense.spent_on.desc(), models.Expense.id.desc()).all()
    if q:
        qq = q.lower()
        rows = [r for r in rows if qq in r.description.lower() or qq in r.vendor.lower()]
    return rows


@router.post("", response_model=schemas.ExpenseOut)
def create_expense(body: schemas.ExpenseIn, ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    ctx.require("expense.write")
    if body.deal_id:
        get_deal(db, ctx, body.deal_id)
    row = models.Expense(user_id=ctx.user.id, **body.model_dump())
    stamp(row, ctx)
    db.add(row)
    db.commit()
    db.refresh(row)
    audit(db, ctx.user.id, "expense_added", f"{row.category} {row.amount_inr}",
          workspace_id=ctx.workspace_id, resource_type="expense", resource_id=row.id)
    return row


@router.patch("/{expense_id}", response_model=schemas.ExpenseOut)
def update_expense(expense_id: int, body: schemas.ExpenseIn,
                   ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    ctx.require("expense.write")
    row = get_expense(db, ctx, expense_id)
    if body.deal_id:
        get_deal(db, ctx, body.deal_id)
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{expense_id}")
def delete_expense(expense_id: int, ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    ctx.require("expense.write")
    row = get_expense(db, ctx, expense_id)
    db.delete(row)
    db.commit()
    audit(db, ctx.user.id, "expense_deleted", str(expense_id), workspace_id=ctx.workspace_id)
    return {"ok": True}


@router.post("/{expense_id}/receipt", response_model=schemas.ExpenseOut)
async def upload_receipt(expense_id: int, file: UploadFile = File(...),
                         ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    ctx.require("expense.write")
    row = get_expense(db, ctx, expense_id)
    data = await file.read()
    try:
        path, mime = exp_svc.save_receipt(ctx.workspace_id, ctx.user.id, row.id, data, file.content_type or "")
    except ValueError as e:
        raise HTTPException(400, str(e))
    row.receipt_path = path
    row.receipt_mime = mime
    db.commit()
    db.refresh(row)
    return row

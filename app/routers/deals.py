from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db
from ..models import STAGES
from ..security import workspace_context
from ..services.tenancy import WorkspaceCtx, assign_deal_lead, deals_query, get_deal, stamp

router = APIRouter(prefix="/deals", tags=["deals"])


@router.get("", response_model=list[schemas.DealOut])
def list_deals(ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    ctx.require("deals.read")
    return deals_query(db, ctx).order_by(models.Deal.id.desc()).all()


@router.get("/stages")
def stages():
    return STAGES


@router.post("", response_model=schemas.DealOut, status_code=201)
def create_deal(body: schemas.DealIn, ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    ctx.require("deals.write")
    if body.status not in STAGES:
        raise HTTPException(422, f"status must be one of {STAGES}")
    deal = models.Deal(user_id=ctx.user.id, **body.model_dump())
    stamp(deal, ctx)
    db.add(deal)
    db.flush()
    assign_deal_lead(db, ctx, deal)
    db.commit()
    return deal


@router.patch("/{deal_id}", response_model=schemas.DealOut)
def update_deal(deal_id: int, body: schemas.DealPatch, ctx: WorkspaceCtx = Depends(workspace_context),
                db: Session = Depends(get_db)):
    ctx.require("deals.write")
    deal = get_deal(db, ctx, deal_id)
    data = body.model_dump(exclude_none=True)
    if "status" in data and data["status"] not in STAGES:
        raise HTTPException(422, f"status must be one of {STAGES}")
    for k, v in data.items():
        setattr(deal, k, v)
    db.commit()
    return deal


@router.delete("/{deal_id}", status_code=204)
def delete_deal(deal_id: int, ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    ctx.require("deals.delete")
    db.delete(get_deal(db, ctx, deal_id))
    db.commit()

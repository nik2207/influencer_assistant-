from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..schemas_campaign_roi import CampaignRoiOut, PortfolioRoiSummary
from ..security import workspace_context
from ..services.tenancy import WorkspaceCtx, get_deal
from ..services import campaign_roi as roi_svc

router = APIRouter(prefix="/roi", tags=["campaign-roi"])


@router.get("/campaigns", response_model=PortfolioRoiSummary)
def list_campaigns(brand: str = "", status: str = "", from_date: date | None = None, to_date: date | None = None,
                   limit: int = Query(50, ge=1, le=100),
                   ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    ctx.require("analytics.read")
    return roi_svc.list_campaign_roi(db, ctx.user, brand=brand, from_date=from_date, to_date=to_date,
                                     status=status, limit=limit, workspace_id=ctx.workspace_id)


@router.get("/campaigns/export.csv")
def export_campaigns(brand: str = "", from_date: date | None = None, to_date: date | None = None,
                     ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    ctx.require("analytics.read")
    summary = roi_svc.list_campaign_roi(db, ctx.user, brand=brand, from_date=from_date, to_date=to_date, limit=200,
                                          workspace_id=ctx.workspace_id)
    return PlainTextResponse(roi_svc.export_csv(summary), media_type="text/csv",
                           headers={"Content-Disposition": "attachment; filename=campaign-roi.csv"})


@router.get("/deals/{deal_id}", response_model=CampaignRoiOut)
def deal_roi(deal_id: int, from_date: date | None = None, to_date: date | None = None,
             ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    ctx.require("analytics.read")
    get_deal(db, ctx, deal_id)
    try:
        return roi_svc.compute_deal_roi(db, ctx.user, deal_id, from_date, to_date, workspace_id=ctx.workspace_id)
    except ValueError:
        raise HTTPException(404, "Deal not found")


@router.get("/deals/{deal_id}/suggestions")
def deal_suggestions(deal_id: int, ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    ctx.require("analytics.read")
    get_deal(db, ctx, deal_id)
    try:
        return roi_svc.ai_suggestions(db, ctx.user, deal_id)
    except ValueError:
        raise HTTPException(404, "Deal not found")

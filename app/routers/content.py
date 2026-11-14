from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..models import CONTENT_FORMATS, CONTENT_STATUSES, CONTENT_TONES
from ..schemas_content import (DraftIn, DraftOut, GenerateIdeasIn, GenerateScriptIn, PlanItemIn,
                               PlanItemOut, PlanItemPatch, RepurposeIn)
from ..security import audit, current_user
from ..services import content_planner as planner
from ..services.personas import PLATFORMS

router = APIRouter(prefix="/content", tags=["content"])


@router.get("/meta")
def meta():
    return {
        "statuses": list(CONTENT_STATUSES),
        "formats": list(CONTENT_FORMATS),
        "tones": list(CONTENT_TONES),
        "platforms": [{"id": k, "label": v["label"]} for k, v in PLATFORMS.items()],
        "publish_note": "Drafts only. You publish on each platform yourself. This app never auto-posts.",
    }


@router.get("/suggestions")
def suggestions(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return {"tips": planner.suggestions(db, user)}


@router.get("/plan", response_model=list[PlanItemOut])
def list_plan(status: str = "", platform: str = "", deal_id: int | None = None, q: str = "",
              from_at: datetime | None = None, to_at: datetime | None = None,
              user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return planner.list_items(db, user, status=status, platform=platform, deal_id=deal_id, q=q,
                               from_at=from_at, to_at=to_at)


@router.post("/plan", response_model=PlanItemOut, status_code=201)
def create_plan(body: PlanItemIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        row = planner.create_item(db, user, body.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))
    audit(db, user.id, "content_plan_created", f"{row.platform}:{row.format}")
    return row


@router.patch("/plan/{item_id}", response_model=PlanItemOut)
def patch_plan(item_id: int, body: PlanItemPatch, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_none=True)
    try:
        row = planner.update_item(db, user, item_id, data)
    except ValueError as e:
        raise HTTPException(404 if "not found" in str(e).lower() else 400, str(e))
    audit(db, user.id, "content_plan_updated", str(item_id))
    return row


@router.delete("/plan/{item_id}")
def delete_plan(item_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        planner.delete_item(db, user, item_id)
    except ValueError:
        raise HTTPException(404, "Content item not found")
    audit(db, user.id, "content_plan_deleted", str(item_id))
    return {"ok": True}


@router.get("/calendar")
def calendar(from_at: datetime | None = None, to_at: datetime | None = None,
             user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    to_at = to_at or (datetime.utcnow() + timedelta(days=30))
    from_at = from_at or datetime.utcnow()
    return planner.calendar_view(db, user, from_at, to_at)


@router.get("/plan/{item_id}/drafts", response_model=list[DraftOut])
def get_drafts(item_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return planner.list_drafts(db, user, item_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/plan/{item_id}/drafts", response_model=DraftOut, status_code=201)
def post_draft(item_id: int, body: DraftIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        row = planner.save_draft(db, user, item_id, body.model_dump(), source="manual")
    except ValueError as e:
        raise HTTPException(404, str(e))
    audit(db, user.id, "content_draft_saved", str(row.id))
    return row


@router.get("/drafts/{draft_id}/export.txt")
def export_draft(draft_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        text = planner.export_draft(db, user, draft_id)
    except ValueError:
        raise HTTPException(404, "Draft not found")
    return PlainTextResponse(text,
                             headers={"Content-Disposition": f'attachment; filename="content-{draft_id}.txt"'})


@router.post("/generate/ideas")
def gen_ideas(body: GenerateIdeasIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    if body.platform not in PLATFORMS:
        raise HTTPException(400, "Unknown platform")
    try:
        return planner.generate_ideas(db, user, body.platform, body.count, body.theme, body.tone, body.deal_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/generate/script")
def gen_script(body: GenerateScriptIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    if body.platform not in PLATFORMS:
        raise HTTPException(400, "Unknown platform")
    try:
        res = planner.generate_script(db, user, body.plan_item_id, body.format, body.platform,
                                      body.topic, body.tone, body.deal_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {
        "plan_item": PlanItemOut.model_validate(res["plan_item"]).model_dump(),
        "draft": DraftOut.model_validate(res["draft"]).model_dump(),
        "source": res["source"],
        "disclaimer": res["disclaimer"],
    }


@router.post("/repurpose")
def repurpose(body: RepurposeIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    if body.target_platform not in PLATFORMS:
        raise HTTPException(400, "Unknown platform")
    try:
        res = planner.repurpose(db, user, body.draft_id, body.target_format, body.target_platform)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {
        "plan_item": PlanItemOut.model_validate(res["plan_item"]).model_dump(),
        "draft": DraftOut.model_validate(res["draft"]).model_dump(),
    }


@router.post("/plan/{item_id}/schedule-shoot")
def link_shoot_event(item_id: int, title: str = "", start_at: datetime = Query(...),
                     user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    """Creates a calendar event via existing events stack and links it — does not replace Schedule module."""
    from ..services import calendar_sync

    try:
        plan = planner._owned_plan(db, user, item_id)
    except ValueError:
        raise HTTPException(404, "Content item not found")
    end = start_at + timedelta(hours=1)
    ev_title = (title or f"Shoot: {plan.title}")[:255]
    res = calendar_sync.add_event(db, user, ev_title, start_at.replace(tzinfo=None), end.replace(tzinfo=None), "")
    ev = res["event"]
    planner.update_item(db, user, item_id, {"event_id": ev.id, "scheduled_at": start_at, "status": "scheduled"})
    return {"event_id": ev.id, "google_synced": res.get("google_synced"), "message": "Shoot added to Schedule. Publish content yourself when ready."}

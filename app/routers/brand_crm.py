from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..schemas_brand_crm import BrandCreateIn, BrandUpdateIn, ContactCreateIn, FollowUpScheduleIn, NoteIn
from ..security import audit, current_user
from ..services import brand_crm as crm

router = APIRouter(prefix="/brands-crm", tags=["brand-crm"])


@router.get("/meta")
def meta():
    return {"note": "CRM aggregates existing deals, emails and pitches. Nothing is sent without your approval in Gmail."}


@router.get("")
def list_brands(q: str = "", sort: str = Query("updated", pattern="^(updated|name|deals|follow_up)$"),
                stage: str = "", follow_up: bool = False,
                user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return crm.list_brands(db, user, q=q, sort=sort, stage=stage, follow_up=follow_up)


@router.get("/discover")
def discover(q: str = "", limit: int = Query(20, ge=1, le=50),
             user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return crm.discover(db, user, q=q, limit=limit)


@router.get("/suggestions")
def suggestions(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return {"brands": crm.follow_up_suggestions(db, user)}


@router.post("", status_code=201)
def create_brand(body: BrandCreateIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        row = crm.get_or_create(db, user, body.display_name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    audit(db, user.id, "brand_crm_created", row.display_name)
    return crm.brand_detail(db, user, row.id)


@router.post("/sync")
def sync_deals(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    n = crm.sync_from_deals(db, user)
    return {"synced": n}


@router.get("/{record_id}")
def get_brand(record_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return crm.brand_detail(db, user, record_id)
    except ValueError:
        raise HTTPException(404, "Brand not found")


@router.patch("/{record_id}")
def patch_brand(record_id: int, body: BrandUpdateIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        crm.update_brand(db, user, record_id, body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(404 if "not found" in str(e).lower() else 400, str(e))
    audit(db, user.id, "brand_crm_updated", str(record_id))
    return crm.brand_detail(db, user, record_id)


@router.get("/{record_id}/timeline")
def get_timeline(record_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return crm.timeline(db, user, record_id)
    except ValueError:
        raise HTTPException(404, "Brand not found")


@router.post("/{record_id}/notes", status_code=201)
def add_note(record_id: int, body: NoteIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        n = crm.add_note(db, user, record_id, body.body, body.kind)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"id": n.id, "kind": n.kind, "created_at": n.created_at}


@router.post("/{record_id}/follow-ups", status_code=201)
def schedule_follow_up(record_id: int, body: FollowUpScheduleIn,
                       user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        fu = crm.schedule_follow_up(db, user, record_id, body.due_date, body.notes, body.deal_id, body.pitch_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"id": fu.id, "due_date": fu.due_date.isoformat()}


@router.post("/follow-ups/{follow_up_id}/complete")
def complete_follow_up(follow_up_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        crm.complete_follow_up(db, user, follow_up_id)
    except ValueError:
        raise HTTPException(404, "Follow-up not found")
    return {"ok": True}


@router.get("/{record_id}/summary")
def ai_summary(record_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        text = crm.relationship_summary(db, user, record_id)
    except ValueError:
        raise HTTPException(404, "Brand not found")
    return {"summary": text}


@router.post("/{record_id}/contacts", status_code=201)
def create_contact(record_id: int, body: ContactCreateIn,
                   user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        c = crm.create_contact(db, user, record_id, body.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"id": c.id, "name": c.name, "email": c.email, "email_verified": c.email_verified}

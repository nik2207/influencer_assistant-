import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db
from ..security import audit, current_user
from ..services import outreach as outreach_service
from ..services import outreach_studio
from ..services import profile as profile_service
from ..services.gmail_client import GmailError
from ..services import gmail_sync

router = APIRouter(prefix="/outreach", tags=["outreach"])

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class StudioGenerateIn(BaseModel):
    brand: str = Field(min_length=1, max_length=160)
    goals: str = Field(default="", max_length=400)
    deliverables: str = Field(default="", max_length=400)
    recipient_email: str = ""


class StudioRegenerateIn(StudioGenerateIn):
    variant: str = Field(pattern="^(professional|friendly|campaign)$")
    tone: str = Field(default="", max_length=80)
    language: str = Field(default="", pattern="^(|en|hi|mr)$")
    subject: str = Field(default="", max_length=300)
    body: str = Field(default="", max_length=8000)


class OutreachDraftIn(BaseModel):
    brand: str = Field(min_length=1, max_length=160)
    category: str = ""
    variant: str = "professional"
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=8000)
    recipient_email: str = ""
    status: str = Field(default="draft", pattern="^(draft|ready|gmail_saved|replied)$")
    deal_id: int | None = None
    follow_up_date: str | None = None
    goals: str = ""
    deliverables: str = ""


class GmailPitchIn(BaseModel):
    to: str = ""
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=8000)


@router.get("/brands")
def brands(user: models.User = Depends(current_user)):
    return outreach_service.suggest(user, limit=12)


@router.get("/pitch")
def pitch(brand: str, note: str = "", user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = profile_service.pitch_context(db, user)
    return {"pitch": outreach_service.draft_pitch(user, brand, note, ctx)}


@router.post("/studio/generate")
def studio_generate(body: StudioGenerateIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return outreach_studio.generate_suggestions(db, user, body.brand, body.goals, body.deliverables, body.recipient_email)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/studio/regenerate")
def studio_regenerate(body: StudioRegenerateIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return outreach_studio.regenerate_variant(db, user, body.brand, body.variant, body.tone, body.language,
                                                body.goals, body.deliverables, body.subject, body.body)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/drafts", response_model=list[schemas.OutreachPitchOut])
def list_drafts(brand: str | None = None, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    q = db.query(models.OutreachPitch).filter_by(user_id=user.id)
    if brand:
        q = q.filter(models.OutreachPitch.brand.ilike(brand.strip()))
    return q.order_by(models.OutreachPitch.updated_at.desc()).all()


def _owned_pitch(db: Session, user: models.User, pitch_id: int) -> models.OutreachPitch:
    row = db.get(models.OutreachPitch, pitch_id)
    if not row or row.user_id != user.id:
        raise HTTPException(404, "Pitch draft not found")
    return row


@router.post("/drafts", response_model=schemas.OutreachPitchOut)
def save_draft(body: OutreachDraftIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    if body.deal_id:
        deal = db.get(models.Deal, body.deal_id)
        if not deal or deal.user_id != user.id:
            raise HTTPException(400, "Deal not found")
    if body.recipient_email and not _EMAIL.match(body.recipient_email.strip()):
        raise HTTPException(400, "Enter a valid recipient email address.")
    row = models.OutreachPitch(user_id=user.id, **body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    audit(db, user.id, "outreach_draft_saved", f"{row.brand} #{row.id}")
    return row


@router.patch("/drafts/{pitch_id}", response_model=schemas.OutreachPitchOut)
def update_draft(pitch_id: int, body: OutreachDraftIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    row = _owned_pitch(db, user, pitch_id)
    if body.recipient_email and not _EMAIL.match(body.recipient_email.strip()):
        raise HTTPException(400, "Enter a valid recipient email address.")
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/drafts/{pitch_id}")
def delete_draft(pitch_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    row = _owned_pitch(db, user, pitch_id)
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/drafts/{pitch_id}/gmail")
def save_gmail_draft(pitch_id: int, body: GmailPitchIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    row = _owned_pitch(db, user, pitch_id)
    to = (body.to or row.recipient_email or "").strip()
    if to and not _EMAIL.match(to):
        raise HTTPException(400, "Enter a valid recipient email address.")
    try:
        draft_id = gmail_sync.push_outreach_draft(db, user, to, body.subject, body.body)
    except GmailError as e:
        raise HTTPException(400, str(e))
    row.gmail_draft_id = draft_id
    row.subject = body.subject
    row.body = body.body
    row.recipient_email = to
    row.status = "gmail_saved"
    db.commit()
    return {
        "gmail_draft_id": draft_id,
        "status": row.status,
        "message": "Saved to your Gmail Drafts folder. Open Gmail to review and send — nothing was sent from this app.",
        "recipient": to or "(add a recipient in Gmail)",
    }

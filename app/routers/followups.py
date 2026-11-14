from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db
from ..security import audit, current_user
from ..services import followups
from ..services.gmail_client import GmailError

router = APIRouter(prefix="/followups", tags=["follow-ups"])


def _own(db: Session, user: models.User, fid: int):
    fu, em = followups.get_owned(db, user, fid)
    if not fu or not em:
        raise HTTPException(404, "Follow-up not found")
    return fu, em


@router.get("")
def list_followups(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return followups.active_list(db, user)


@router.post("/refresh")
def refresh(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return followups.refresh(db, user)
    except GmailError as exc:
        raise HTTPException(400, str(exc))


@router.post("/{fid}/snooze")
def snooze(fid: int, days: int = 2, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    fu, _ = _own(db, user, fid)
    followups.snooze(db, fu, days)
    return {"snoozed_until": fu.snoozed_until}


@router.post("/{fid}/resolve", status_code=204)
def resolve(fid: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    fu, _ = _own(db, user, fid)
    followups.resolve(db, fu)


@router.post("/{fid}/nudge")
def nudge(fid: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    fu, em = _own(db, user, fid)
    return {"draft_reply": followups.nudge_text(db, user, fu, em)}


@router.put("/{fid}/nudge")
def edit_nudge(fid: int, body: schemas.DraftEdit, user: models.User = Depends(current_user),
               db: Session = Depends(get_db)):
    fu, _ = _own(db, user, fid)
    fu.nudge_draft = body.draft_reply
    db.commit()
    return {"draft_reply": fu.nudge_draft}


@router.post("/{fid}/nudge/push")
def push_nudge(fid: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    """Saves the nudge in Gmail Drafts inside the same thread. Nothing is sent."""
    fu, em = _own(db, user, fid)
    try:
        draft_id = followups.push_nudge(db, user, fu, em)
    except GmailError as exc:
        raise HTTPException(400, str(exc))
    audit(db, user.id, "gmail_nudge_draft_created", f"email #{em.id}")
    return {"gmail_draft_id": draft_id}

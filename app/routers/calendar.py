from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..security import current_user
from ..services import calendar_sync, gmail_client, gmail_sync, tools
from ..services.calendar_client import CalendarError
from ..services.gmail_client import GmailError

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/status")
def status(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    link = calendar_sync.get_link(db, user)
    return {"configured": gmail_client.configured(),
            "gmail_connected": gmail_sync.get_account(db, user) is not None,
            "granted": link.granted, "last_pull_at": link.last_pull_at, "last_error": link.last_error}


@router.post("/sync")
def sync(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    """Push local events to Google, then pull Google changes into the app."""
    try:
        pushed = calendar_sync.push_all(db, user)
        pulled = calendar_sync.pull(db, user)
    except (CalendarError, GmailError) as exc:
        calendar_sync._record_error(db, user, str(exc))
        raise HTTPException(400, str(exc))
    return {"pushed": pushed, **pulled}


@router.get("/suggestions")
def suggestions(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    rows = (db.query(models.EventSuggestion, models.EmailMessage)
            .join(models.EmailMessage, models.EmailMessage.id == models.EventSuggestion.email_id)
            .filter(models.EventSuggestion.user_id == user.id, models.EventSuggestion.status == "pending")
            .order_by(models.EventSuggestion.start_at).all())
    return [{"id": s.id, "kind": s.kind, "title": s.title, "start_at": s.start_at, "end_at": s.end_at,
             "email_id": e.id, "brand": e.brand or e.sender_name, "subject": e.subject} for s, e in rows]


def _own(db: Session, user: models.User, sid: int) -> models.EventSuggestion:
    s = db.get(models.EventSuggestion, sid)
    if not s or s.user_id != user.id:
        raise HTTPException(404, "Suggestion not found")
    return s


@router.post("/suggestions/{sid}/accept")
def accept(sid: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    sug = _own(db, user, sid)
    if sug.status != "pending":
        raise HTTPException(409, f"Suggestion already {sug.status}")
    res = calendar_sync.accept_suggestion(db, user, sug)
    return {"event": tools.event_dict(res["event"]), "conflicts": [tools.event_dict(c) for c in res["conflicts"]],
            "google_synced": res["google_synced"], "google_error": res["google_error"]}


@router.post("/suggestions/{sid}/dismiss", status_code=204)
def dismiss(sid: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    _own(db, user, sid).status = "dismissed"
    db.commit()

from sqlalchemy.orm import Session

from .. import models
from . import email_dates


def create_for_email(db: Session, user: models.User, em: models.EmailMessage, body: str) -> int:
    items = email_dates.extract(f"{em.subject}\n{body}", em.brand)
    added = 0
    for it in items:
        exists = db.query(models.EventSuggestion).filter_by(
            user_id=user.id, email_id=em.id, start_at=it["start"], kind=it["kind"]).first()
        if exists:
            continue
        db.add(models.EventSuggestion(user_id=user.id, email_id=em.id, kind=it["kind"], title=it["title"],
                                      start_at=it["start"], end_at=it["end"]))
        added += 1
    db.commit()
    return added

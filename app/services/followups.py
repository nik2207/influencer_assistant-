"""Find brand email threads that need attention.

needs_reply     the brand wrote last and you have not answered for REPLY_AFTER_DAYS
awaiting_brand  you wrote last and the brand has been silent for FOLLOWUP_AFTER_DAYS
Works from Gmail thread metadata, so replies sent from Gmail itself are noticed too.
"""
from datetime import timedelta

from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..models import utcnow
from . import email_ai, gmail_client, gmail_sync
from .gmail_client import GmailError

ACTIVE = ("needs_reply", "awaiting_brand")


def refresh(db: Session, user: models.User) -> dict:
    acct = gmail_sync.get_account(db, user)
    if not acct:
        raise GmailError("Gmail is not connected.")
    token = gmail_sync.access_token(db, acct)
    me = acct.email.lower()
    now = utcnow()
    emails = (db.query(models.EmailMessage)
              .filter(models.EmailMessage.user_id == user.id, models.EmailMessage.status != "dismissed",
                      models.EmailMessage.received_at >= now - timedelta(days=45))
              .order_by(models.EmailMessage.received_at.desc()).limit(40).all())
    checked = 0
    for em in emails:
        fu = db.query(models.FollowUp).filter_by(email_id=em.id).first()
        deal = db.get(models.Deal, em.deal_id) if em.deal_id else None
        try:
            msgs = gmail_client.thread_meta(token, em.thread_id) if em.thread_id else []
        except GmailError:
            continue
        if not msgs:
            continue
        checked += 1
        last = msgs[-1]
        days = (now - last["date"]).total_seconds() / 86400
        state = None
        if deal and deal.status in ("done", "cancelled"):
            state = None
        elif last["from_email"] == me and days >= settings.followup_after_days:
            state = "awaiting_brand"
        elif last["from_email"] != me and days >= settings.reply_after_days:
            state = "needs_reply"

        if fu is None:
            if state:
                db.add(models.FollowUp(user_id=user.id, email_id=em.id, state=state, last_message_at=last["date"]))
            continue
        if fu.state == "dismissed" and fu.last_message_at == last["date"]:
            continue  # user dismissed this exact situation; new activity reopens it
        if state is None:
            fu.state = "resolved"
        elif fu.state != state or fu.last_message_at != last["date"]:
            fu.state, fu.reminded_at, fu.nudge_draft, fu.snoozed_until = state, None, "", None
        fu.last_message_at = last["date"]
    db.commit()
    return {"checked": checked, "active": len(active_list(db, user, include_snoozed=True))}


def active_list(db: Session, user: models.User, include_snoozed: bool = False) -> list[dict]:
    now = utcnow()
    rows = (db.query(models.FollowUp, models.EmailMessage)
            .join(models.EmailMessage, models.EmailMessage.id == models.FollowUp.email_id)
            .filter(models.FollowUp.user_id == user.id, models.FollowUp.state.in_(ACTIVE),
                    models.EmailMessage.status != "dismissed")
            .order_by(models.FollowUp.last_message_at).all())
    out = []
    for fu, em in rows:
        if not include_snoozed and fu.snoozed_until and fu.snoozed_until > now:
            continue
        waited = (now - fu.last_message_at).days if fu.last_message_at else 0
        out.append({"id": fu.id, "email_id": em.id, "state": fu.state, "days_waiting": waited,
                    "brand": em.brand or em.sender_name, "subject": em.subject, "sender_name": em.sender_name,
                    "category": em.category, "nudge_draft": fu.nudge_draft,
                    "snoozed_until": fu.snoozed_until, "last_message_at": fu.last_message_at})
    return out


def get_owned(db: Session, user: models.User, followup_id: int):
    fu = db.get(models.FollowUp, followup_id)
    if not fu or fu.user_id != user.id:
        return None, None
    return fu, db.get(models.EmailMessage, fu.email_id)


def snooze(db: Session, fu: models.FollowUp, days: int) -> None:
    fu.snoozed_until = utcnow() + timedelta(days=max(1, min(days, 30)))
    db.commit()


def resolve(db: Session, fu: models.FollowUp) -> None:
    fu.state = "dismissed"  # stays quiet until the thread changes
    db.commit()


def nudge_text(db: Session, user: models.User, fu: models.FollowUp, em: models.EmailMessage) -> str:
    days = (utcnow() - fu.last_message_at).days if fu.last_message_at else settings.followup_after_days
    fu.nudge_draft = email_ai.followup_draft(user, em, max(days, 1))
    db.commit()
    return fu.nudge_draft


def push_nudge(db: Session, user: models.User, fu: models.FollowUp, em: models.EmailMessage) -> str:
    acct = gmail_sync.get_account(db, user)
    if not acct:
        raise GmailError("Gmail is not connected.")
    if not fu.nudge_draft:
        nudge_text(db, user, fu, em)
    return gmail_client.create_draft(gmail_sync.access_token(db, acct), em.sender_email, em.subject,
                                     fu.nudge_draft, em.thread_id, em.message_id_header)

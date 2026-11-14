"""Scheduled work. Called by Celery (app/worker.py) or by the in-process loop (app/background.py)."""
import logging
from datetime import timedelta

from . import models
from .db import SessionLocal
from .models import utcnow
from .notify import send_telegram
from .services import calendar_sync, followups, gmail_sync
from .services.calendar_client import CalendarError
from .services.gmail_client import GmailError
from .timeutil import now_ist

log = logging.getLogger("jobs")
REMIND_AGAIN_AFTER = timedelta(days=2)


def send_reminders() -> dict:
    """Event reminders (30 min before) and content due dates (1 day before)."""
    db = SessionLocal()
    sent = 0
    try:
        now = now_ist()
        events = db.query(models.Event).filter(
            models.Event.reminded.is_(False), models.Event.start_at > now,
            models.Event.start_at <= now + timedelta(minutes=30)).all()
        for ev in events:
            user = db.get(models.User, ev.user_id)
            if user and user.telegram_chat_id:
                where = f" at {ev.location}" if ev.location else ""
                send_telegram(user.telegram_chat_id, f"Reminder: {ev.title} at {ev.start_at:%H:%M}{where}")
                sent += 1
            ev.reminded = True

        soon = (now + timedelta(days=1)).date()
        deals = db.query(models.Deal).filter(
            models.Deal.due_reminded.is_(False), models.Deal.due_date.isnot(None),
            models.Deal.due_date <= soon,
            models.Deal.status.in_(["confirmed", "product_received", "content_due"])).all()
        for d in deals:
            user = db.get(models.User, d.user_id)
            if user and user.telegram_chat_id:
                send_telegram(user.telegram_chat_id, f"Content for {d.brand} is due {d.due_date:%d %b}.")
                sent += 1
            d.due_reminded = True
        db.commit()
    finally:
        db.close()
    return {"sent": sent}


def sync_gmail_all() -> dict:
    """Pull new brand emails for every connected account and ping Telegram about collabs and payments."""
    db = SessionLocal()
    total = 0
    try:
        for acct in db.query(models.GmailAccount).all():
            user = db.get(models.User, acct.user_id)
            try:
                result = gmail_sync.sync(db, user)
            except GmailError as exc:
                log.warning("gmail sync failed for user %s: %s", acct.user_id, exc)
                continue
            total += len(result["new"])
            if user.telegram_chat_id:
                for em in result["new"]:
                    if em.category in ("paid_collab", "barter_collab", "payment"):
                        send_telegram(user.telegram_chat_id,
                                      f"New {em.category.replace('_', ' ')} email from {em.brand}: {em.summary}\n"
                                      "Open the Inbox tab to review and draft a reply.")
    finally:
        db.close()
    return {"new_emails": total}


def pull_calendars() -> dict:
    """Bring Google Calendar changes into the app for every user who granted calendar access."""
    db = SessionLocal()
    users = 0
    try:
        for link in db.query(models.CalendarLink).filter_by(granted=True).all():
            user = db.get(models.User, link.user_id)
            try:
                calendar_sync.push_all(db, user)
                calendar_sync.pull(db, user)
                users += 1
            except (CalendarError, GmailError) as exc:
                calendar_sync._record_error(db, user, str(exc))
    finally:
        db.close()
    return {"users": users}


def followup_cycle() -> dict:
    """Re-scan threads, then remind about the ones that need attention (again after 2 days)."""
    db = SessionLocal()
    reminded = 0
    try:
        for acct in db.query(models.GmailAccount).all():
            user = db.get(models.User, acct.user_id)
            try:
                followups.refresh(db, user)
            except GmailError as exc:
                log.warning("follow-up refresh failed for user %s: %s", acct.user_id, exc)
                continue
            if not user.telegram_chat_id:
                continue
            now = utcnow()
            for item in followups.active_list(db, user):
                fu = db.get(models.FollowUp, item["id"])
                if fu.reminded_at and now - fu.reminded_at < REMIND_AGAIN_AFTER:
                    continue
                if item["state"] == "needs_reply":
                    text = (f"{item['brand']} is still waiting for your reply ({item['days_waiting']} days): "
                            f"{item['subject']}")
                else:
                    text = (f"No reply from {item['brand']} for {item['days_waiting']} days: {item['subject']}\n"
                            "Open Inbox > Follow-ups to send a nudge.")
                if send_telegram(user.telegram_chat_id, text):
                    fu.reminded_at = now
                    reminded += 1
            db.commit()
    finally:
        db.close()
    return {"reminded": reminded}

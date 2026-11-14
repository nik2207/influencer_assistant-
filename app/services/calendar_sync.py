"""Two-way sync between local events and Google Calendar (primary calendar).

Imports flow one way to avoid cycles:  timeutil <- calendar_client <- gmail_sync <- calendar_sync <- tools/routers.
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..models import utcnow
from ..timeutil import parse_dt
from . import calendar_client, gmail_sync
from .calendar_client import CalendarError, CalendarScopeError
from .gmail_client import GmailError

__all__ = ["CalendarError", "CalendarScopeError", "find_conflicts", "add_event", "remove_event",
           "push_all", "pull", "accept_suggestion", "get_link", "mark_granted", "is_ready"]


def get_link(db: Session, user: models.User) -> models.CalendarLink:
    link = db.query(models.CalendarLink).filter_by(user_id=user.id).first()
    if not link:
        link = models.CalendarLink(user_id=user.id)
        db.add(link)
        db.commit()
    return link


def mark_granted(db: Session, user: models.User, scope_text: str) -> bool:
    link = get_link(db, user)
    link.granted = "auth/calendar" in (scope_text or "")
    if link.granted:
        link.last_error = ""
    db.commit()
    return link.granted


def is_ready(db: Session, user: models.User) -> bool:
    return get_link(db, user).granted and gmail_sync.get_account(db, user) is not None


def _token(db: Session, user: models.User) -> str:
    acct = gmail_sync.get_account(db, user)
    if not acct or not get_link(db, user).granted:
        raise CalendarError("Google Calendar is not connected.")
    return gmail_sync.access_token(db, acct)


def _record_error(db: Session, user: models.User, message: str) -> None:
    link = get_link(db, user)
    link.last_error = message[:300]
    if message.startswith("Google Calendar permission"):
        link.granted = False  # scope was revoked or never granted: ask the user to reconnect
    db.commit()


def find_conflicts(db: Session, user_id: int, start: datetime, end: datetime, exclude_id=None):
    q = db.query(models.Event).filter(
        models.Event.user_id == user_id, models.Event.start_at < end, models.Event.end_at > start)
    return [e for e in q.all() if e.id != exclude_id]


def _body(ev: models.Event) -> dict:
    return {
        "summary": ev.title,
        "location": ev.location or "",
        "start": {"dateTime": ev.start_at.isoformat(timespec="seconds"), "timeZone": "Asia/Kolkata"},
        "end": {"dateTime": ev.end_at.isoformat(timespec="seconds"), "timeZone": "Asia/Kolkata"},
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 30}]},
    }


def push_event(db: Session, user: models.User, ev: models.Event) -> bool:
    """Create the event in Google Calendar. Safe to call twice; returns True if it exists remotely."""
    if db.query(models.EventSync).filter_by(user_id=user.id, event_id=ev.id).first():
        return True
    token = _token(db, user)
    gid = calendar_client.insert_event(token, _body(ev))
    db.add(models.EventSync(user_id=user.id, google_event_id=gid, event_id=ev.id, source="app"))
    db.commit()
    return True


def add_event(db: Session, user: models.User, title: str, start: datetime,
              end: datetime | None = None, location: str = "", workspace_id: int | None = None) -> dict:
    """The one place events are created (chat, API and email suggestions all use it)."""
    end = end or start + timedelta(hours=1)
    conflicts = find_conflicts(db, user.id, start, end)
    ev = models.Event(user_id=user.id, workspace_id=workspace_id, title=title, start_at=start, end_at=end, location=location)
    db.add(ev)
    db.commit()
    synced, error = False, ""
    if is_ready(db, user):
        try:
            synced = push_event(db, user, ev)
        except (CalendarError, GmailError) as exc:  # local event is kept even if Google fails
            error = str(exc)
            _record_error(db, user, error)
    return {"event": ev, "conflicts": conflicts, "google_synced": synced, "google_error": error}


def remove_event(db: Session, user: models.User, ev: models.Event) -> None:
    sync = db.query(models.EventSync).filter_by(user_id=user.id, event_id=ev.id).first()
    if sync:
        if sync.source == "app":
            try:
                calendar_client.delete_event(_token(db, user), sync.google_event_id)
            except (CalendarError, GmailError) as exc:
                _record_error(db, user, str(exc))
            db.delete(sync)
        else:
            # Created in Google. Do not delete someone's real calendar entry; just stop mirroring it.
            sync.event_id = None
            sync.ignored = True
    db.delete(ev)
    db.commit()


def push_all(db: Session, user: models.User) -> int:
    """Send every upcoming local event that is not in Google yet."""
    pushed = 0
    synced_ids = {i for (i,) in db.query(models.EventSync.event_id).filter_by(user_id=user.id).all() if i}
    upcoming = db.query(models.Event).filter(
        models.Event.user_id == user.id, models.Event.end_at >= datetime.now() - timedelta(days=1)).all()
    for ev in upcoming:
        if ev.id not in synced_ids:
            push_event(db, user, ev)
            pushed += 1
    return pushed


def pull(db: Session, user: models.User) -> dict:
    """Bring Google Calendar changes into the local calendar so clash detection sees everything."""
    token = _token(db, user)
    now = utcnow()
    items = calendar_client.list_events(token, now - timedelta(days=1), now + timedelta(days=settings.calendar_pull_days))
    created = updated = removed = 0
    for it in items:
        gid = it["id"]
        sync = db.query(models.EventSync).filter_by(user_id=user.id, google_event_id=gid).first()

        if it.get("status") == "cancelled":
            if sync and sync.event_id:
                ev = db.get(models.Event, sync.event_id)
                if ev:
                    db.delete(ev)
                    removed += 1
                sync.event_id = None
            continue

        start, end = it.get("start", {}), it.get("end", {})
        if "dateTime" not in start or "dateTime" not in end:
            continue  # all-day entries (birthdays, holidays) would block every clash check
        if sync and (sync.ignored or sync.source == "app"):
            continue  # our own push, or one the user removed here

        s, e = parse_dt(start["dateTime"]), parse_dt(end["dateTime"])
        title = (it.get("summary") or "Busy")[:255]
        place = (it.get("location") or "")[:255]
        ev = db.get(models.Event, sync.event_id) if sync and sync.event_id else None
        if ev:
            if (ev.title, ev.start_at, ev.end_at, ev.location) != (title, s, e, place):
                ev.title, ev.start_at, ev.end_at, ev.location = title, s, e, place
                updated += 1
        else:
            wid = (
                db.query(models.WorkspaceMembership.workspace_id)
                .filter_by(user_id=user.id, status="active")
                .order_by(models.WorkspaceMembership.id)
                .scalar()
            )
            ev = models.Event(user_id=user.id, workspace_id=wid, title=title, start_at=s, end_at=e, location=place)
            db.add(ev)
            db.flush()
            if sync:
                sync.event_id = ev.id
            else:
                db.add(models.EventSync(user_id=user.id, google_event_id=gid, event_id=ev.id, source="google"))
            created += 1

    link = get_link(db, user)
    link.last_pull_at = utcnow()
    link.last_error = ""
    db.commit()
    return {"created": created, "updated": updated, "removed": removed}


def accept_suggestion(db: Session, user: models.User, sug: models.EventSuggestion) -> dict:
    result = add_event(db, user, sug.title, sug.start_at, sug.end_at)
    sug.status = "accepted"
    sug.event_id = result["event"].id
    if sug.kind == "deadline":
        em = db.get(models.EmailMessage, sug.email_id)
        deal = db.get(models.Deal, em.deal_id) if em and em.deal_id else None
        if deal:
            deal.due_date = sug.start_at.date()
    db.commit()
    return result

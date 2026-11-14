from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..security import decrypt_secret, encrypt_secret
from ..models import utcnow
from . import email_ai, email_intelligence, gmail_client, suggestions
from .gmail_client import GmailError

RELEVANT = {"paid_collab", "barter_collab", "negotiation", "payment", "event_invite"}


def get_account(db: Session, user: models.User) -> models.GmailAccount | None:
    return db.query(models.GmailAccount).filter_by(user_id=user.id).first()


def store_tokens(db: Session, user: models.User, tokens: dict) -> models.GmailAccount:
    acct = get_account(db, user) or models.GmailAccount(user_id=user.id)
    acct.access_token_enc = encrypt_secret(tokens["access_token"])
    acct.token_expiry = utcnow() + timedelta(seconds=int(tokens.get("expires_in", 3600)))
    if tokens.get("refresh_token"):  # Google only returns it on first consent
        acct.refresh_token_enc = encrypt_secret(tokens["refresh_token"])
    if not acct.refresh_token_enc:
        raise GmailError("Google did not return offline access. Disconnect the app in your Google account and retry.")
    db.add(acct)
    db.commit()
    return acct


def access_token(db: Session, acct: models.GmailAccount) -> str:
    if acct.token_expiry and acct.token_expiry > utcnow() + timedelta(seconds=60) and acct.access_token_enc:
        return decrypt_secret(acct.access_token_enc)
    fresh = gmail_client.refresh_access_token(decrypt_secret(acct.refresh_token_enc))
    acct.access_token_enc = encrypt_secret(fresh["access_token"])
    acct.token_expiry = utcnow() + timedelta(seconds=int(fresh.get("expires_in", 3600)))
    db.commit()
    return fresh["access_token"]


def sync(db: Session, user: models.User) -> dict:
    """Fetch new mail, keep only business-relevant messages, classify them."""
    acct = get_account(db, user)
    if not acct:
        raise GmailError("Gmail is not connected.")
    token = access_token(db, acct)
    if acct.last_sync_at:
        epoch = int((acct.last_sync_at - datetime(1970, 1, 1)).total_seconds()) - 120  # 2 min overlap
        query = f"after:{epoch} -from:me -in:chats"
    else:
        query = f"newer_than:{settings.gmail_sync_days}d -from:me -in:chats"
    started = utcnow()
    ids = gmail_client.list_message_ids(token, query, settings.gmail_max_per_sync)
    known = {g for (g,) in db.query(models.EmailMessage.gmail_id).filter_by(user_id=user.id).all()}
    new, skipped, bodies = [], 0, {}
    for gid in ids:
        if gid in known:
            continue
        mail = gmail_client.parse_message(gmail_client.get_message(token, gid))
        if mail["sender_email"] == acct.email.lower():
            continue
        result = email_ai.classify(mail)
        if result["category"] not in RELEVANT:
            skipped += 1  # data minimisation: irrelevant mail is never stored
            continue
        intel = email_intelligence.analyze(mail, result)
        wid = (
            db.query(models.WorkspaceMembership.workspace_id)
            .filter_by(user_id=user.id, status="active")
            .order_by(models.WorkspaceMembership.id)
            .scalar()
        )
        em = models.EmailMessage(
            user_id=user.id, workspace_id=wid, gmail_id=mail["gmail_id"], thread_id=mail["thread_id"],
            message_id_header=mail["message_id_header"][:300],
            sender_name=mail["sender_name"][:200], sender_email=mail["sender_email"][:255],
            subject=mail["subject"][:500], snippet=mail["snippet"],
            body_enc=encrypt_secret(mail["body"]), received_at=mail["received_at"],
            category=result["category"], confidence=result["confidence"], brand=result["brand"],
            amount_inr=result["amount_inr"], deliverables=result["deliverables"], summary=result["summary"],
            intelligence_json=intel, intelligence_version=intel["version"], is_brand_inquiry=bool(
                intel.get("inquiry", {}).get("is_brand_inquiry")),
        )
        email_intelligence.apply_to_email_row(em, intel, force=True)
        db.add(em)
        new.append(em)
        bodies[mail["gmail_id"]] = mail["body"]
    acct.last_sync_at = started
    db.commit()
    for em in new:
        try:
            email_intelligence.attach_suggested_reply(em, bodies.get(em.gmail_id, ""), user)
        except Exception:
            pass
        suggestions.create_for_email(db, user, em, bodies.get(em.gmail_id, ""))
    db.commit()
    return {"fetched": len(ids), "new": new, "skipped": skipped}


def body_of(em: models.EmailMessage) -> str:
    return decrypt_secret(em.body_enc) if em.body_enc else ""


def make_draft(db: Session, user: models.User, em: models.EmailMessage) -> str:
    if em.suggested_reply:
        em.draft_reply = em.suggested_reply
    else:
        em.draft_reply = email_ai.draft_reply(user, em, body_of(em))
    db.commit()
    return em.draft_reply


def push_outreach_draft(db: Session, user: models.User, to: str, subject: str, body: str) -> str:
    acct = get_account(db, user)
    if not acct:
        raise GmailError("Gmail is not connected. Connect Gmail from the Inbox tab first.")
    return gmail_client.create_compose_draft(access_token(db, acct), to, subject, body)


def push_draft_to_gmail(db: Session, user: models.User, em: models.EmailMessage) -> str:
    acct = get_account(db, user)
    if not acct:
        raise GmailError("Gmail is not connected.")
    if not em.draft_reply:
        make_draft(db, user, em)
    draft_id = gmail_client.create_draft(
        access_token(db, acct), em.sender_email, em.subject, em.draft_reply, em.thread_id, em.message_id_header)
    em.gmail_draft_id = draft_id
    db.commit()
    return draft_id


def to_deal(db: Session, user: models.User, em: models.EmailMessage, *,
            apply_intelligence: bool = True, link_deal_id: int | None = None) -> models.Deal:
    from . import brand_crm

    wid = em.workspace_id or (
        db.query(models.WorkspaceMembership.workspace_id)
        .filter_by(user_id=user.id, status="active")
        .order_by(models.WorkspaceMembership.id)
        .scalar()
    )

    if link_deal_id:
        deal = db.get(models.Deal, link_deal_id)
        if not deal or deal.user_id != user.id or (wid and deal.workspace_id != wid):
            raise ValueError("Deal not found")
        em.deal_id = deal.id
        db.commit()
        return deal
    if em.deal_id:
        deal = db.get(models.Deal, em.deal_id)
        if deal:
            return deal
    intel = em.intelligence_json or {}
    kind = "barter"
    if intel.get("collab_kind") == "paid" or em.category == "paid_collab":
        kind = "paid"
    elif intel.get("collab_kind") == "barter" or em.category == "barter_collab":
        kind = "barter"
    value = em.amount_inr or 0
    deliverables = em.deliverables
    due = None
    if apply_intelligence and intel:
        bud = intel.get("budget") or {}
        if bud.get("amount_inr"):
            value = float(bud["amount_inr"])
        items = intel.get("deliverables") or []
        if items:
            deliverables = ", ".join(x["text"] for x in items)[:300]
        for dl in intel.get("deadlines") or []:
            if dl.get("kind") == "deadline" and dl.get("date"):
                try:
                    from datetime import date as dt
                    due = dt.fromisoformat(str(dl["date"])[:10])
                    break
                except ValueError:
                    pass
    brand = em.brand or em.sender_name
    deal = models.Deal(
        user_id=user.id, workspace_id=wid, brand=brand, kind=kind, title=em.subject[:200],
        value_inr=value or 0, deliverables=deliverables, due_date=due,
        status="negotiating" if em.category == "negotiation" else "lead",
        notes=f"From email #{em.id} by {em.sender_name} <{em.sender_email}> (user confirmed)",
    )
    db.add(deal)
    db.flush()
    em.deal_id = deal.id
    try:
        rec = brand_crm.get_or_create(db, user, brand)
        em.brand_record_id = rec.id
    except Exception:
        pass
    db.commit()
    return deal


def reanalyze(db: Session, user: models.User, em: models.EmailMessage) -> dict:
    mail = {
        "gmail_id": em.gmail_id,
        "sender_name": em.sender_name,
        "sender_email": em.sender_email,
        "subject": em.subject,
        "body": body_of(em),
        "bulk": False,
    }
    result = email_ai.classify(mail)
    intel = email_intelligence.analyze(mail, result)
    email_intelligence.apply_to_email_row(em, intel, force=True)
    email_intelligence.attach_suggested_reply(em, mail["body"], user)
    db.commit()
    return intel


def disconnect(db: Session, user: models.User, delete_emails: bool = True) -> None:
    acct = get_account(db, user)
    if acct:
        try:
            gmail_client.revoke(decrypt_secret(acct.refresh_token_enc))
        except Exception:
            pass
        db.delete(acct)
    if delete_emails:
        db.query(models.EventSuggestion).filter_by(user_id=user.id).delete()
        db.query(models.FollowUp).filter_by(user_id=user.id).delete()
        db.query(models.EmailMessage).filter_by(user_id=user.id).delete()
    db.commit()


def cleanup_saved(db: Session, user: models.User) -> int:
    """Re-check saved emails with the noise filter and delete job alerts, notifications and the like."""
    removed = 0
    for em in db.query(models.EmailMessage).filter_by(user_id=user.id).all():
        mail = {"sender_name": em.sender_name, "sender_email": em.sender_email,
                "subject": em.subject, "body": body_of(em)}
        if em.deal_id or not email_ai.is_noise(mail):
            continue
        db.query(models.EventSuggestion).filter_by(email_id=em.id).delete()
        db.query(models.FollowUp).filter_by(email_id=em.id).delete()
        db.delete(em)
        removed += 1
    db.commit()
    return removed

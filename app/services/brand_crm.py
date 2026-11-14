"""Brand Collaboration CRM — aggregate deals, emails, pitches without duplicating them."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..models import STAGES
from . import followups, outreach
from . import llm

NOTE_KINDS = ("general", "negotiation")


def brand_key(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())[:160]


def _owned_brand(db: Session, user: models.User, record_id: int) -> models.BrandRecord:
    row = db.get(models.BrandRecord, record_id)
    if not row or row.user_id != user.id:
        raise ValueError("Brand not found")
    return row


def _csv_row(name: str) -> dict:
    for b in outreach.load_brands():
        if b["name"].strip().lower() == name.strip().lower():
            return b
    return {}


def get_or_create(db: Session, user: models.User, display_name: str) -> models.BrandRecord:
    key = brand_key(display_name)
    if not key:
        raise ValueError("Brand name is required")
    row = db.query(models.BrandRecord).filter_by(user_id=user.id, brand_key=key).first()
    if row:
        return row
    csv = _csv_row(display_name)
    row = models.BrandRecord(
        user_id=user.id,
        brand_key=key,
        display_name=display_name.strip()[:160],
        category=(csv.get("category") or "")[:80],
        website=(csv.get("website") or "")[:300],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def sync_from_deals(db: Session, user: models.User) -> int:
    """Ensure one BrandRecord per distinct deal.brand (no duplicate keys)."""
    brands = {d.brand for d in db.query(models.Deal).filter_by(user_id=user.id).all() if d.brand}
    n = 0
    for b in brands:
        get_or_create(db, user, b)
        n += 1
    return n


def _deals_for(db: Session, user: models.User, record: models.BrandRecord) -> list[models.Deal]:
    return (db.query(models.Deal).filter_by(user_id=user.id)
            .filter(models.Deal.brand.ilike(record.display_name))
            .order_by(models.Deal.updated_at.desc()).all())


def _active_stage(deals: list[models.Deal]) -> str:
    if not deals:
        return "lead"
    open_order = [s for s in STAGES if s not in ("done", "cancelled")]
    for st in reversed(open_order):
        if any(d.status == st for d in deals):
            return st
    return deals[0].status


def _rollup(record: models.BrandRecord, deals: list[models.Deal], db: Session, user: models.User) -> dict:
    invoices = []
    if deals:
        ids = [d.id for d in deals]
        invoices = db.query(models.Invoice).filter(
            models.Invoice.user_id == user.id, models.Invoice.deal_id.in_(ids)).limit(5).all()
    return {
        "id": record.id,
        "display_name": record.display_name,
        "category": record.category,
        "website": record.website,
        "lead_stage": record.lead_stage or _active_stage(deals),
        "pipeline_stage": _active_stage(deals),
        "deal_count": len(deals),
        "open_deals": sum(1 for d in deals if d.status not in ("done", "cancelled")),
        "done_deals": sum(1 for d in deals if d.status == "done"),
        "next_follow_up": record.next_follow_up.isoformat() if record.next_follow_up else None,
        "preferences": record.preferences or {},
        "relationship_summary": record.relationship_summary,
        "last_touch": record.updated_at.isoformat() if record.updated_at else None,
        "campaigns": [{"invoice": inv.number, "campaign": inv.campaign, "deal_id": inv.deal_id} for inv in invoices],
    }


def list_brands(db: Session, user: models.User, q: str = "", sort: str = "updated",
                stage: str = "", follow_up: bool = False) -> list[dict]:
    sync_from_deals(db, user)
    qry = db.query(models.BrandRecord).filter_by(user_id=user.id)
    if q:
        qq = q.strip().lower()
        qry = qry.filter(or_(models.BrandRecord.display_name.ilike(f"%{qq}%"),
                             models.BrandRecord.brand_key.contains(qq),
                             models.BrandRecord.category.ilike(f"%{qq}%")))
    rows = qry.all()
    out = []
    today = date.today()
    for row in rows:
        deals = _deals_for(db, user, row)
        item = _rollup(row, deals, db, user)
        if stage and item["pipeline_stage"] != stage:
            continue
        if follow_up and not (row.next_follow_up and row.next_follow_up <= today):
            fu = db.query(models.BrandFollowUp).filter_by(user_id=user.id, brand_record_id=row.id,
                                                          completed=False).filter(
                models.BrandFollowUp.due_date <= today).first()
            if not fu:
                continue
        out.append(item)
    if sort == "name":
        out.sort(key=lambda x: x["display_name"].lower())
    elif sort == "deals":
        out.sort(key=lambda x: -x["deal_count"])
    elif sort == "follow_up":
        out.sort(key=lambda x: x["next_follow_up"] or "9999")
    else:
        out.sort(key=lambda x: x["last_touch"] or "", reverse=True)
    return out


def discover(db: Session, user: models.User, q: str = "", limit: int = 20) -> list[dict]:
    """CSV directory + CRM flag."""
    sync_from_deals(db, user)
    existing = {r.brand_key for r in db.query(models.BrandRecord).filter_by(user_id=user.id).all()}
    scored = outreach.suggest(user, limit=50)
    out = []
    for b in scored:
        if q and q.lower() not in b["name"].lower() and q.lower() not in b.get("category", "").lower():
            continue
        key = brand_key(b["name"])
        out.append({**b, "in_crm": key in existing, "brand_record_id": None})
        if len(out) >= limit:
            break
    # attach record id when in crm
    for item in out:
        if item["in_crm"]:
            rec = db.query(models.BrandRecord).filter_by(user_id=user.id, brand_key=brand_key(item["name"])).first()
            item["brand_record_id"] = rec.id if rec else None
    return out


def brand_detail(db: Session, user: models.User, record_id: int) -> dict:
    record = _owned_brand(db, user, record_id)
    deals = _deals_for(db, user, record)
    contacts = db.query(models.Contact).filter_by(user_id=user.id, brand_record_id=record.id).all()
    notes = db.query(models.BrandNote).filter_by(user_id=user.id, brand_record_id=record.id).order_by(
        models.BrandNote.created_at.desc()).all()
    scheduled = db.query(models.BrandFollowUp).filter_by(user_id=user.id, brand_record_id=record.id,
                                                           completed=False).order_by(models.BrandFollowUp.due_date).all()
    pitches = db.query(models.OutreachPitch).filter_by(user_id=user.id).filter(
        models.OutreachPitch.brand.ilike(record.display_name)).order_by(models.OutreachPitch.updated_at.desc()).limit(20).all()
    kanban = {s: [] for s in STAGES if s != "cancelled"}
    for d in deals:
        if d.status in kanban:
            kanban[d.status].append({
                "id": d.id, "brand": d.brand, "kind": d.kind, "value_inr": d.value_inr,
                "deliverables": d.deliverables, "due_date": d.due_date.isoformat() if d.due_date else None,
            })
    return {
        **_rollup(record, deals, db, user),
        "contacts": [{
            "id": c.id, "name": c.name, "role": c.role, "email": c.email, "phone": c.phone,
            "email_verified": c.email_verified, "notes": c.notes,
        } for c in contacts],
        "notes": [{"id": n.id, "kind": n.kind, "body": n.body, "created_at": n.created_at.isoformat()} for n in notes],
        "scheduled_follow_ups": [{
            "id": f.id, "due_date": f.due_date.isoformat(), "notes": f.notes, "deal_id": f.deal_id, "pitch_id": f.pitch_id,
        } for f in scheduled],
        "pitches_count": len(pitches),
        "kanban": kanban,
        "deals": [{
            "id": d.id, "status": d.status, "kind": d.kind, "value_inr": d.value_inr,
            "deliverables": d.deliverables, "due_date": d.due_date.isoformat() if d.due_date else None,
            "notes": d.notes[:200],
        } for d in deals],
    }


def timeline(db: Session, user: models.User, record_id: int, limit: int = 40) -> list[dict]:
    record = _owned_brand(db, user, record_id)
    events = []
    name = record.display_name
    for d in _deals_for(db, user, record):
        events.append({"at": d.updated_at.isoformat(), "type": "deal", "title": f"Deal #{d.id} — {d.status}",
                       "detail": d.deliverables or d.title, "ref_id": d.id})
    for p in db.query(models.OutreachPitch).filter_by(user_id=user.id).filter(
            models.OutreachPitch.brand.ilike(name)):
        events.append({"at": p.updated_at.isoformat(), "type": "pitch", "title": f"Pitch ({p.status})",
                       "detail": p.subject, "ref_id": p.id})
    for em in db.query(models.EmailMessage).filter_by(user_id=user.id).filter(
            or_(models.EmailMessage.brand.ilike(name),
                models.EmailMessage.sender_name.ilike(f"%{name}%"))).limit(30):
        events.append({"at": em.received_at.isoformat(), "type": "email", "title": em.subject,
                       "detail": em.category, "ref_id": em.id})
    for n in db.query(models.BrandNote).filter_by(user_id=user.id, brand_record_id=record.id):
        events.append({"at": n.created_at.isoformat(), "type": "note", "title": n.kind,
                       "detail": n.body[:120], "ref_id": n.id})
    events.sort(key=lambda x: x["at"], reverse=True)
    return events[:limit]


def update_brand(db: Session, user: models.User, record_id: int, data: dict) -> models.BrandRecord:
    record = _owned_brand(db, user, record_id)
    if "display_name" in data and data["display_name"]:
        new_key = brand_key(data["display_name"])
        if new_key != record.brand_key:
            clash = db.query(models.BrandRecord).filter_by(user_id=user.id, brand_key=new_key).first()
            if clash and clash.id != record.id:
                raise ValueError("Another brand already uses that name")
        record.display_name = data["display_name"].strip()[:160]
        record.brand_key = new_key
    for k in ("category", "website", "relationship_summary", "lead_stage"):
        if k in data:
            setattr(record, k, (data[k] or "")[:500] if k == "relationship_summary" else data[k])
    if "preferences" in data:
        record.preferences = data["preferences"] or {}
    if "next_follow_up" in data:
        record.next_follow_up = data["next_follow_up"]
    db.commit()
    db.refresh(record)
    return record


def add_note(db: Session, user: models.User, record_id: int, body: str, kind: str = "general") -> models.BrandNote:
    if kind not in NOTE_KINDS:
        raise ValueError("Invalid note kind")
    _owned_brand(db, user, record_id)
    n = models.BrandNote(user_id=user.id, brand_record_id=record_id, body=body[:5000], kind=kind)
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def schedule_follow_up(db: Session, user: models.User, record_id: int, due_date: date, notes: str = "",
                       deal_id: int | None = None, pitch_id: int | None = None) -> models.BrandFollowUp:
    _owned_brand(db, user, record_id)
    if deal_id:
        deal = db.get(models.Deal, deal_id)
        if not deal or deal.user_id != user.id:
            raise ValueError("Deal not found")
    if pitch_id:
        pitch = db.get(models.OutreachPitch, pitch_id)
        if not pitch or pitch.user_id != user.id:
            raise ValueError("Pitch not found")
    fu = models.BrandFollowUp(user_id=user.id, brand_record_id=record_id, due_date=due_date,
                            notes=notes[:300], deal_id=deal_id, pitch_id=pitch_id)
    db.add(fu)
    record = _owned_brand(db, user, record_id)
    if not record.next_follow_up or due_date < record.next_follow_up:
        record.next_follow_up = due_date
    db.commit()
    db.refresh(fu)
    return fu


def complete_follow_up(db: Session, user: models.User, follow_up_id: int) -> None:
    fu = db.get(models.BrandFollowUp, follow_up_id)
    if not fu or fu.user_id != user.id:
        raise ValueError("Follow-up not found")
    fu.completed = True
    db.commit()


def link_contact(db: Session, user: models.User, record_id: int, contact_id: int) -> models.Contact:
    _owned_brand(db, user, record_id)
    c = db.get(models.Contact, contact_id)
    if not c or c.user_id != user.id:
        raise ValueError("Contact not found")
    c.brand_record_id = record_id
    c.company = c.company or _owned_brand(db, user, record_id).display_name
    db.commit()
    return c


def create_contact(db: Session, user: models.User, record_id: int, data: dict) -> models.Contact:
    record = _owned_brand(db, user, record_id)
    c = models.Contact(
        user_id=user.id, brand_record_id=record_id,
        name=data["name"][:160], company=data.get("company") or record.display_name,
        role=(data.get("role") or "")[:120], email=(data.get("email") or "")[:255],
        phone=(data.get("phone") or "")[:40], notes=data.get("notes") or "",
        email_verified=bool(data.get("email_verified")),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def verify_contact_from_email(db: Session, user: models.User, contact_id: int, email_id: int) -> models.Contact:
    c = db.get(models.Contact, contact_id)
    em = db.get(models.EmailMessage, email_id)
    if not c or c.user_id != user.id or not em or em.user_id != user.id:
        raise ValueError("Not found")
    if c.email and em.sender_email.lower() == c.email.lower():
        c.email_verified = True
        db.commit()
    else:
        raise ValueError("Email does not match this contact")
    return c


def follow_up_suggestions(db: Session, user: models.User) -> list[dict]:
    """Brands needing attention — from CRM dates, inbox follow-ups, pitch follow_up_date."""
    sync_from_deals(db, user)
    today = date.today()
    out = []
    for row in db.query(models.BrandRecord).filter_by(user_id=user.id).all():
        reasons = []
        if row.next_follow_up and row.next_follow_up <= today:
            reasons.append("scheduled follow-up due")
        overdue_fu = db.query(models.BrandFollowUp).filter_by(
            user_id=user.id, brand_record_id=row.id, completed=False).filter(
            models.BrandFollowUp.due_date <= today).count()
        if overdue_fu:
            reasons.append(f"{overdue_fu} overdue reminder(s)")
        deals = _deals_for(db, user, row)
        if any(d.status in ("negotiating", "lead") for d in deals):
            reasons.append("open negotiation")
        if reasons:
            out.append({"brand_record_id": row.id, "display_name": row.display_name, "reasons": reasons})
    try:
        for fu in followups.active_list(db, user):
            key = brand_key(fu.get("brand") or "")
            rec = db.query(models.BrandRecord).filter_by(user_id=user.id, brand_key=key).first()
            if rec and not any(x["brand_record_id"] == rec.id for x in out):
                out.append({"brand_record_id": rec.id, "display_name": rec.display_name,
                            "reasons": [f"inbox: {fu['state']}"]})
    except Exception:
        pass
    for p in db.query(models.OutreachPitch).filter_by(user_id=user.id).filter(
            models.OutreachPitch.follow_up_date <= today).all():
        rec = get_or_create(db, user, p.brand)
        if not any(x["brand_record_id"] == rec.id for x in out):
            out.append({"brand_record_id": rec.id, "display_name": rec.display_name,
                        "reasons": ["pitch follow-up date"]})
    return out[:15]


def relationship_summary(db: Session, user: models.User, record_id: int) -> str:
    """Facts-only summary; optional LLM polish without inventing data."""
    record = _owned_brand(db, user, record_id)
    deals = _deals_for(db, user, record)
    tl = timeline(db, user, record_id, limit=8)
    lines = [
        f"Brand: {record.display_name}",
        f"Deals: {len(deals)} total, {sum(1 for d in deals if d.status == 'done')} completed.",
        f"Open pipeline stage: {_active_stage(deals)}.",
    ]
    if record.preferences:
        lines.append(f"Preferences: {record.preferences}")
    for ev in tl[:5]:
        lines.append(f"- {ev['type']}: {ev['title']} ({ev['at'][:10]})")
    base = "\n".join(lines)
    if settings.llm_provider != "openai_compat":
        return base
    try:
        prompt = (
            "Write a short relationship summary for the creator using ONLY these facts. "
            "Do not invent contacts, amounts, or outcomes.\n\n" + base
        )
        out = llm.simple_completion(prompt)
        return out[:1200] if out else base
    except Exception:
        return base

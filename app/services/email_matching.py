"""Match emails to BrandRecord and open deals (read-only scoring)."""
from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models
from . import brand_crm


def _brand_from_email(em: models.EmailMessage) -> str:
    return (em.brand or em.sender_name or "").strip()


def match_brands(db: Session, user: models.User, em: models.EmailMessage) -> list[dict]:
    name = _brand_from_email(em)
    if not name:
        return []
    key = brand_crm.brand_key(name)
    rows = db.query(models.BrandRecord).filter_by(user_id=user.id).all()
    out = []
    for row in rows:
        score = 0.0
        reasons = []
        if row.brand_key == key:
            score = 1.0
            reasons.append("exact brand key")
        elif name.lower() in row.display_name.lower() or row.display_name.lower() in name.lower():
            score = max(score, 0.85)
            reasons.append("name similarity")
        if em.sender_email and "@" in em.sender_email:
            domain = em.sender_email.split("@")[-1].split(".")[0]
            if domain and domain.lower() in row.brand_key.replace(" ", ""):
                score = max(score, 0.7)
                reasons.append("sender domain")
        if score >= 0.65:
            out.append({
                "brand_record_id": row.id,
                "display_name": row.display_name,
                "score": round(score, 2),
                "reasons": reasons,
                "unverified": True,
            })
    out.sort(key=lambda x: -x["score"])
    return out[:5]


def match_deals(db: Session, user: models.User, em: models.EmailMessage) -> list[dict]:
    name = _brand_from_email(em)
    q = db.query(models.Deal).filter_by(user_id=user.id).filter(
        models.Deal.status.notin_(("done", "cancelled")))
    if name:
        q = q.filter(or_(models.Deal.brand.ilike(f"%{name}%"),
                         models.Deal.brand.ilike(f"%{em.sender_name}%")))
    deals = q.order_by(models.Deal.updated_at.desc()).limit(20).all()
    intel = em.intelligence_json or {}
    budget = float((intel.get("budget") or {}).get("amount_inr") or em.amount_inr or 0)
    out = []
    for d in deals:
        score = 0.5
        reasons = ["open deal"]
        if name and name.lower() in d.brand.lower():
            score += 0.35
            reasons.append("brand name match")
        if em.deal_id == d.id:
            score = 1.0
            reasons = ["already linked"]
        if budget > 0 and d.value_inr and abs(d.value_inr - budget) / max(d.value_inr, 1) < 0.2:
            score += 0.15
            reasons.append("similar budget")
        out.append({
            "deal_id": d.id,
            "brand": d.brand,
            "status": d.status,
            "value_inr": d.value_inr,
            "score": round(min(score, 1.0), 2),
            "reasons": reasons,
            "unverified": True,
        })
    out.sort(key=lambda x: -x["score"])
    return out[:8]


def all_matches(db: Session, user: models.User, em: models.EmailMessage) -> dict:
    return {
        "brand_records": match_brands(db, user, em),
        "deals": match_deals(db, user, em),
        "unverified_notice": "Matches are suggestions. Confirm before linking.",
    }


def recommendations(db: Session, user: models.User) -> list[dict]:
    """Inbox-level follow-up recommendations from stored intelligence."""
    rows = (db.query(models.EmailMessage)
            .filter_by(user_id=user.id)
            .filter(models.EmailMessage.status != "dismissed")
            .filter(models.EmailMessage.is_brand_inquiry.is_(True))
            .order_by(models.EmailMessage.received_at.desc())
            .limit(30).all())
    out = []
    for em in rows:
        intel = em.intelligence_json or {}
        fu = intel.get("follow_up") or {}
        if not fu.get("recommended"):
            continue
        out.append({
            "email_id": em.id,
            "brand": em.brand or em.sender_name,
            "subject": em.subject,
            "priority": fu.get("priority", "medium"),
            "reason": fu.get("reason", "Follow up suggested"),
            "category": em.category,
            "unverified": True,
        })
    return out[:15]

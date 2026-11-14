"""Assemble media kit preview and published snapshots (no fabricated metrics)."""
from __future__ import annotations

import secrets
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .. import models
from . import analytics as analytics_svc
from .personas import CREATOR_TYPES, PLATFORMS, persona
from . import profile as profile_svc


def get_kit(db: Session, user: models.User) -> models.MediaKit:
    row = db.query(models.MediaKit).filter_by(user_id=user.id).first()
    if not row:
        row = models.MediaKit(user_id=user.id)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _latest_metrics(db: Session, user: models.User, platform: str) -> list[dict]:
    to = date.today()
    fr = to - timedelta(days=90)
    out = []
    for mk in ("followers", "engagement_rate", "reach", "views", "engagement"):
        rows = analytics_svc.list_snapshots(db, user, platform=platform, metric_key=mk, from_date=fr, to_date=to)
        if not rows:
            continue
        r = rows[0]
        out.append({
            "metric": mk, "value": r.value, "source": r.source, "confidence": r.confidence,
            "as_of": (r.period_start or r.created_at.date()).isoformat(),
        })
    return out


def _platform_stats(db: Session, user: models.User, include_metrics: bool) -> list[dict]:
    accts = profile_svc.platforms_of(db, user)
    items = []
    for a in accts:
        if a.platform not in PLATFORMS:
            continue
        entry = {
            "platform": a.platform,
            "label": PLATFORMS[a.platform]["label"],
            "handle": a.handle,
            "url": a.url,
            "followers": a.followers,
            "followers_source": "profile_manual",
        }
        if include_metrics:
            entry["metrics"] = _latest_metrics(db, user, a.platform)
        items.append(entry)
    return items


def list_rates(db: Session, user: models.User) -> list[models.MediaKitRateLine]:
    return (db.query(models.MediaKitRateLine).filter_by(user_id=user.id, is_active=True)
            .order_by(models.MediaKitRateLine.sort_order, models.MediaKitRateLine.id).all())


def save_rates(db: Session, user: models.User, lines: list[dict]) -> list[models.MediaKitRateLine]:
    db.query(models.MediaKitRateLine).filter_by(user_id=user.id).delete()
    out = []
    for i, row in enumerate(lines):
        d = row.get("deliverable", "other")
        if d not in models.RATE_DELIVERABLES:
            raise ValueError(f"Invalid deliverable: {d}")
        price = float(row.get("price") or 0)
        if price < 0:
            raise ValueError("Price cannot be negative")
        cur = (row.get("currency") or "INR")[:3].upper()
        rl = models.MediaKitRateLine(
            user_id=user.id, deliverable=d, title=(row.get("title") or d)[:120],
            price=price, currency=cur, notes=(row.get("notes") or "")[:200], sort_order=i,
        )
        db.add(rl)
        out.append(rl)
    db.commit()
    for r in out:
        db.refresh(r)
    return out


def list_portfolio(db: Session, user: models.User) -> list[models.MediaKitPortfolioItem]:
    return (db.query(models.MediaKitPortfolioItem).filter_by(user_id=user.id)
            .order_by(models.MediaKitPortfolioItem.sort_order).all())


def save_portfolio(db: Session, user: models.User, items: list[dict]) -> list[models.MediaKitPortfolioItem]:
    db.query(models.MediaKitPortfolioItem).filter_by(user_id=user.id).delete()
    out = []
    for i, row in enumerate(items):
        deal_id = row.get("deal_id")
        if not deal_id:
            continue
        deal = db.get(models.Deal, deal_id)
        if not deal or deal.user_id != user.id:
            raise ValueError("Deal not found")
        pi = models.MediaKitPortfolioItem(
            user_id=user.id, deal_id=deal_id, summary=(row.get("summary") or "")[:300],
            sort_order=i, visible=bool(row.get("visible", True)),
        )
        db.add(pi)
        out.append(pi)
    db.commit()
    return out


def list_samples(db: Session, user: models.User) -> list[models.MediaKitSample]:
    return (db.query(models.MediaKitSample).filter_by(user_id=user.id)
            .order_by(models.MediaKitSample.sort_order).all())


def save_samples(db: Session, user: models.User, items: list[dict]) -> list[models.MediaKitSample]:
    db.query(models.MediaKitSample).filter_by(user_id=user.id).delete()
    out = []
    for i, row in enumerate(items):
        cid = row.get("content_item_id")
        if cid:
            ci = db.get(models.ContentItem, cid)
            if not ci or ci.user_id != user.id:
                raise ValueError("Content item not found")
        sm = models.MediaKitSample(
            user_id=user.id, content_item_id=cid,
            title=(row.get("title") or "")[:255], url=(row.get("url") or "")[:400],
            platform=(row.get("platform") or "")[:16], notes=(row.get("notes") or "")[:200],
            sort_order=i, visible=bool(row.get("visible", True)),
        )
        db.add(sm)
        out.append(sm)
    db.commit()
    return out


def _portfolio_public(db: Session, user: models.User) -> list[dict]:
    rows = [p for p in list_portfolio(db, user) if p.visible]
    out = []
    for p in rows:
        deal = db.get(models.Deal, p.deal_id)
        if not deal:
            continue
        out.append({
            "deal_id": p.deal_id,
            "brand": deal.brand,
            "deliverables": deal.deliverables or "",
            "summary": p.summary,
            "status": deal.status,
        })
    return out


def _samples_public(db: Session, user: models.User) -> list[dict]:
    rows = [s for s in list_samples(db, user) if s.visible]
    out = []
    for s in rows:
        item = {"title": s.title, "url": s.url, "platform": s.platform, "notes": s.notes}
        if s.content_item_id:
            ci = db.get(models.ContentItem, s.content_item_id)
            if ci and ci.user_id == user.id:
                item["metrics"] = {
                    "views": ci.views, "engagement": ci.engagement, "source": ci.source,
                }
        out.append(item)
    return out


def build_preview(db: Session, user: models.User) -> dict:
    cp = profile_svc.get_or_create(db, user)
    kit = get_kit(db, user)
    p = persona(cp.creator_type)
    intro = kit.intro.strip() or cp.bio or ""
    share = db.query(models.MediaKitShare).filter_by(user_id=user.id).first()
    return {
        "creator": {
            "name": user.name,
            "handle": user.handle,
            "niche": user.niche,
            "city": user.city,
            "creator_type": p["label"],
            "languages": cp.languages or ["en"],
            "bio": cp.bio,
            "headline": kit.headline or f"{user.name or 'Creator'} · {user.niche or 'Creator'}",
            "intro": intro,
        },
        "avatar_url": f"/media-kit/avatar" if kit.avatar_path else None,
        "platforms": _platform_stats(db, user, kit.show_metrics),
        "rates": [
            {"deliverable": r.deliverable, "title": r.title, "price": r.price,
             "currency": r.currency, "notes": r.notes}
            for r in list_rates(db, user)
        ] if kit.show_rates else [],
        "portfolio": _portfolio_public(db, user),
        "samples": _samples_public(db, user),
        "contact": {
            "email": cp.contact_email if kit.show_contact_email and cp.contact_email else "",
            "phone": cp.phone if kit.show_phone and cp.phone else "",
        },
        "settings": {
            "pdf_template": kit.pdf_template if kit.pdf_template in models.MEDIA_KIT_TEMPLATES else "classic",
            "show_rates": kit.show_rates,
            "show_metrics": kit.show_metrics,
            "show_contact_email": kit.show_contact_email,
            "show_phone": kit.show_phone,
            "currency": cp.currency,
        },
        "share": {
            "active": bool(share and share.is_active),
            "public_path": f"/media-kit/public/{share.token}" if share and share.is_active else None,
            "published_at": share.published_at.isoformat() if share and share.published_at else None,
        },
        "disclaimer": "All numbers are as entered or imported by the creator. Nothing is fabricated.",
        "gaps": profile_svc.completeness(db, user, cp)["missing"],
    }


def build_publish_snapshot(db: Session, user: models.User) -> dict:
    """Frozen public payload — no private fields beyond explicit toggles."""
    preview = build_preview(db, user)
    preview.pop("gaps", None)
    kit = get_kit(db, user)
    preview["avatar_public"] = bool(kit.avatar_path)
    preview["avatar_url"] = None
    return preview


def publish_share(db: Session, user: models.User, confirm: bool) -> models.MediaKitShare:
    if not confirm:
        raise ValueError("You must confirm before publishing the public media kit link.")
    share = db.query(models.MediaKitShare).filter_by(user_id=user.id).first()
    if not share:
        share = models.MediaKitShare(user_id=user.id, token=secrets.token_urlsafe(32))
        db.add(share)
    share.published_snapshot = build_publish_snapshot(db, user)
    share.is_active = True
    share.published_at = models.utcnow()
    share.revoked_at = None
    db.commit()
    db.refresh(share)
    return share


def revoke_share(db: Session, user: models.User) -> None:
    share = db.query(models.MediaKitShare).filter_by(user_id=user.id).first()
    if share:
        share.is_active = False
        share.revoked_at = models.utcnow()
        db.commit()


def public_snapshot(db: Session, token: str) -> dict:
    share = db.query(models.MediaKitShare).filter_by(token=token, is_active=True).first()
    if not share or not share.published_snapshot:
        raise ValueError("This media kit link is not available.")
    return {**share.published_snapshot, "disclaimer": share.published_snapshot.get("disclaimer", "")}

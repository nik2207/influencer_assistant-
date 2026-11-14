"""Context bundle for content generation (profile + optional deal + verified analytics hints)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .. import models
from . import analytics as analytics_svc
from .personas import LANGUAGES, PLATFORMS, persona
from . import profile as profile_svc


def _deal_block(db: Session, user: models.User, deal_id: Optional[int]) -> dict:
    if not deal_id:
        return {}
    deal = db.get(models.Deal, deal_id)
    if not deal or deal.user_id != user.id:
        raise ValueError("Deal not found")
    return {
        "deal_id": deal.id,
        "brand": deal.brand,
        "deliverables": deal.deliverables or "",
        "due_date": deal.due_date.isoformat() if deal.due_date else None,
        "notes": (deal.notes or "")[:400],
        "sponsored": deal.kind in ("paid", "barter"),
    }


def analytics_hints(db: Session, user: models.User, platform: str) -> str:
    """Only use stored metrics; never invent numbers."""
    to = date.today()
    fr = to - timedelta(days=30)
    lines = []
    for mk in ("views", "engagement", "followers"):
        rows = analytics_svc.list_snapshots(db, user, platform=platform, metric_key=mk,
                                             from_date=fr, to_date=to)
        if not rows:
            continue
        r = rows[0]
        if r.confidence != "verified" and r.source not in ("manual", "api"):
            continue
        lines.append(f"{mk}: {r.value:,.0f} ({r.source})")
    top = analytics_svc.top_content(db, user, platform=platform, limit=2)
    for c in top:
        lines.append(f"Past top: {c.title or 'Untitled'} — {int(c.views):,} views")
    return "; ".join(lines) if lines else ""


def build_context(db: Session, user: models.User, platform: str = "instagram",
                  deal_id: Optional[int] = None) -> dict:
    cp = profile_svc.get_or_create(db, user)
    p = persona(cp.creator_type)
    accts = profile_svc.platforms_of(db, user)
    plat_row = next((a for a in accts if a.platform == platform), None)
    return {
        "creator_name": user.name or "Creator",
        "handle": user.handle or "",
        "niche": user.niche or "lifestyle",
        "city": user.city or "",
        "language": user.language or "en",
        "languages": profile_svc._langs(cp, user),
        "creator_type": p["label"],
        "bio": (cp.bio or "")[:400],
        "platform": platform,
        "platform_label": PLATFORMS.get(platform, {}).get("label", platform),
        "followers": plat_row.followers if plat_row else user.followers,
        "deliverable_examples": p.get("deliverable_examples", []),
        "deal": _deal_block(db, user, deal_id),
        "analytics_hint": analytics_hints(db, user, platform),
        "disclaimer": "Draft for your review. You publish manually on the platform.",
        "sponsored_line": "#ad / Paid partnership" if deal_id else "",
    }


def lang_name(code: str) -> str:
    return LANGUAGES.get(code, "English")

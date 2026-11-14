"""Pitch Studio: context-aware variants (rule-based; optional LLM polish)."""
from __future__ import annotations

import json
import re
from typing import Optional

from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from . import llm, outreach, profile as profile_service

VARIANTS = (
    ("professional", "Professional and concise"),
    ("friendly", "Friendly and personalized"),
    ("campaign", "Campaign-focused and persuasive"),
)


def _brand_row(name: str) -> dict:
    for b in outreach.load_brands():
        if b["name"].lower() == name.strip().lower():
            return b
    return {"name": name.strip(), "category": "", "tags": ""}


def _deal_hints(db: Session, user: models.User, brand: str) -> tuple[Optional[int], str]:
    rows = (db.query(models.Deal).filter_by(user_id=user.id)
            .filter(models.Deal.brand.ilike(brand.strip())).order_by(models.Deal.id.desc()).limit(3).all())
    if not rows:
        return None, ""
    parts = [f"#{d.id} ({d.status}): {d.deliverables or d.title or 'collaboration'}" for d in rows]
    return rows[0].id, "; ".join(parts)


def _channel_line(ctx: dict, user: models.User) -> str:
    if ctx.get("channels"):
        return ", ".join(f"{n:,} on {label}" for label, n in ctx["channels"])
    if user.followers:
        return f"{user.followers:,} followers on your primary channel"
    return "[your audience reach — add platforms in Profile]"


def _build_variant(variant: str, brand: str, category: str, who: str, handle: str, niche: str,
                   city: str, ctx: dict, user: models.User, goals: str, deliverables: str,
                   deal_note: str) -> dict:
    reach = _channel_line(ctx, user)
    kind = ctx["type_label"].lower()
    article = "an" if kind[0] in "aeiou" else "a"
    loc = f" in {city}" if city else ""
    offer = deliverables or ctx["offer"]
    goal_line = goals.strip() or "grow awareness with authentic creator-led content"
    bio = (ctx.get("bio") or "").strip()
    bio_bit = f" {bio}" if bio else ""

    if variant == "professional":
        subject = f"Collaboration idea for {brand}"
        body = (
            f"Dear {brand} partnerships team,\n\n"
            f"I am {who}{handle}, {article} {kind} focused on {niche}{loc}. "
            f"My audience includes {reach}.\n\n"
            f"I am reaching out regarding a potential collaboration aligned with {brand}'s work in {category or 'your category'}. "
            f"Campaign objective: {goal_line}.\n\n"
            f"Proposed deliverables: {offer}.\n"
            f"{('Prior work with your brand: ' + deal_note + '.') if deal_note else ''}\n\n"
            f"Please let me know the right contact for creator partnerships. I can share a media kit and rate card on request.\n\n"
            f"Regards,\n{who}"
        )
        collab = "Paid partnership or structured barter"
    elif variant == "friendly":
        subject = f"Would love to collaborate with {brand}!"
        body = (
            f"Hi {brand} team,\n\n"
            f"I'm {who}{handle} — I create {niche} content{loc} and genuinely enjoy what {brand} is building.{bio_bit}\n\n"
            f"I'd love to explore a collab that feels natural for my community ({reach}). "
            f"I'm thinking: {offer}.\n\n"
            f"If you're planning campaigns around {goal_line}, I'd be happy to share a few creative ideas — no pressure, just a quick chat works for me.\n\n"
            f"Cheers,\n{who}"
        )
        collab = "Open to paid or barter — happy to align on what fits"
    else:
        subject = f"{brand} x {who} — campaign concept"
        body = (
            f"Hi {brand} team,\n\n"
            f"**Creator:** {who}{handle} ({kind}, {niche}{loc})\n"
            f"**Audience:** {reach}\n"
            f"**Category fit:** {category or brand} / {', '.join((_brand_row(brand).get('tags') or '').split()[:3])}\n\n"
            f"**Campaign goal:** {goal_line}\n\n"
            f"**Deliverable package:**\n• {offer}\n"
            f"• Performance recap after publish (reach and engagement — actuals shared post-campaign)\n\n"
            f"{('**Note:** We have an existing deal record: ' + deal_note + '.') if deal_note else ''}\n"
            f"I am not assuming budget or timelines — please share your brief and we can adapt.\n\n"
            f"Best,\n{who}"
        )
        collab = "Campaign package (deliverables above)"

    return {
        "variant": variant,
        "tone_label": dict(VARIANTS)[variant] if variant in dict(VARIANTS) else variant,
        "subject": subject.strip(),
        "body": body.strip(),
        "collaboration_format": collab,
        "deliverables": offer,
        "creator_name": who,
        "brand": brand,
    }


def generate_suggestions(db: Session, user: models.User, brand: str, goals: str = "",
                         deliverables: str = "", recipient_email: str = "") -> dict:
    brand = brand.strip()
    if not brand:
        raise ValueError("Brand name is required.")
    row = _brand_row(brand)
    ctx = profile_service.pitch_context(db, user)
    who = user.name or "Creator"
    handle = f" ({user.handle})" if user.handle else ""
    niche = user.niche or "[your niche]"
    city = user.city or ""
    deal_id, deal_note = _deal_hints(db, user, brand)
    suggestions = [_build_variant(v, row["name"], row.get("category", ""), who, handle, niche, city, ctx, user,
                                  goals, deliverables, deal_note) for v, _ in VARIANTS]
    return {
        "brand": row["name"],
        "category": row.get("category", ""),
        "deal_id": deal_id,
        "recipient_email": recipient_email or "",
        "suggestions": suggestions,
        "disclaimer": "Figures come from your profile only. Edit placeholders before sending.",
    }


def regenerate_variant(db: Session, user: models.User, brand: str, variant: str, tone: str = "",
                       language: str = "", goals: str = "", deliverables: str = "",
                       subject: str = "", body: str = "") -> dict:
    base = generate_suggestions(db, user, brand, goals, deliverables)
    pick = next((s for s in base["suggestions"] if s["variant"] == variant), base["suggestions"][0])
    if tone and settings.llm_provider == "openai_compat":
        prompt = (
            f"Rewrite this outreach email to be more {tone}. Keep facts exactly as given; do not invent metrics or past deals.\n"
            f"Subject: {pick['subject']}\n\n{pick['body']}\n\nReturn JSON: {{\"subject\":\"...\",\"body\":\"...\"}}"
        )
        try:
            raw = llm.simple_completion(prompt)
            m = re.search(r"\{.*\}", raw, re.S)
            if m:
                data = json.loads(m.group())
                pick["subject"] = str(data.get("subject") or pick["subject"])[:300]
                pick["body"] = str(data.get("body") or pick["body"])[:8000]
        except (json.JSONDecodeError, ValueError):
            pass
    elif tone == "professional" and variant != "professional":
        pick = _build_variant("professional", brand, base["category"], user.name or "Creator",
                              f" ({user.handle})" if user.handle else "", user.niche or "[niche]",
                              user.city or "", profile_service.pitch_context(db, user), user, goals, deliverables, "")
    if language in ("hi", "mr") and settings.llm_provider == "openai_compat":
        lang = "Hindi" if language == "hi" else "Marathi"
        prompt = f"Translate this email to {lang}. Keep the subject line translated too.\nSubject: {pick['subject']}\n\n{pick['body']}"
        try:
            translated = llm.simple_completion(prompt)
            if translated:
                pick["body"] = translated[:8000]
                pick["tone_label"] += f" ({lang})"
        except Exception:
            pass
    elif language in ("hi", "mr"):
        pick["body"] = f"[{language.upper()} draft — connect a real LLM for translation]\n\n" + pick["body"]
    if subject:
        pick["subject"] = subject[:300]
    if body:
        pick["body"] = body[:8000]
    return pick


def legacy_pitch_text(suggestion: dict) -> str:
    return f"Subject: {suggestion['subject']}\n\n{suggestion['body']}"

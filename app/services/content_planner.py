"""Content plan CRUD, template/LLM generation, calendar listing, repurposing."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from . import llm
from . import content_context as ctx
from .personas import PLATFORMS

STATUS_FLOW = set(models.CONTENT_STATUSES)


def _owned_plan(db: Session, user: models.User, item_id: int) -> models.ContentPlanItem:
    row = db.get(models.ContentPlanItem, item_id)
    if not row or row.user_id != user.id:
        raise ValueError("Content item not found")
    return row


def _owned_draft(db: Session, user: models.User, draft_id: int) -> models.ContentDraft:
    row = db.get(models.ContentDraft, draft_id)
    if not row or row.user_id != user.id:
        raise ValueError("Draft not found")
    return row


def _sync_search(row: models.ContentPlanItem) -> None:
    parts = [row.title, row.notes, row.platform, row.format, row.status, " ".join(row.tags or [])]
    row.search_text = " ".join(p for p in parts if p).lower()[:600]


def create_item(db: Session, user: models.User, data: dict) -> models.ContentPlanItem:
    if data.get("deal_id"):
        ctx.build_context(db, user, data.get("platform", "instagram"), data["deal_id"])
    if data.get("platform") not in PLATFORMS:
        raise ValueError("Unknown platform")
    if data.get("format") not in models.CONTENT_FORMATS:
        raise ValueError("Unknown format")
    if data.get("status") not in STATUS_FLOW:
        raise ValueError("Unknown status")
    row = models.ContentPlanItem(
        user_id=user.id,
        deal_id=data.get("deal_id"),
        platform=data.get("platform", "instagram"),
        format=data.get("format", "idea"),
        title=(data.get("title") or "Untitled idea")[:255],
        status=data.get("status", "idea"),
        scheduled_at=data.get("scheduled_at"),
        language=(data.get("language") or user.language or "en")[:5],
        tone=(data.get("tone") or "friendly")[:16],
        tags=list(data.get("tags") or [])[:20],
        notes=(data.get("notes") or "")[:500],
    )
    _sync_search(row)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_item(db: Session, user: models.User, item_id: int, data: dict) -> models.ContentPlanItem:
    row = _owned_plan(db, user, item_id)
    if "deal_id" in data and data["deal_id"]:
        ctx.build_context(db, user, row.platform, data["deal_id"])
    if data.get("event_id"):
        ev = db.get(models.Event, data["event_id"])
        if not ev or ev.user_id != user.id:
            raise ValueError("Event not found")
    for k in ("title", "status", "platform", "format", "notes", "tone", "language", "tags",
              "scheduled_at", "published_at", "deal_id", "event_id"):
        if k in data:
            setattr(row, k, data[k])
    if row.status not in STATUS_FLOW:
        raise ValueError("Unknown status")
    if row.format not in models.CONTENT_FORMATS:
        raise ValueError("Unknown format")
    if row.status == "published" and not row.published_at:
        row.published_at = datetime.utcnow()
    _sync_search(row)
    db.commit()
    db.refresh(row)
    return row


def delete_item(db: Session, user: models.User, item_id: int) -> bool:
    row = _owned_plan(db, user, item_id)
    db.query(models.ContentDraft).filter_by(plan_item_id=row.id, user_id=user.id).delete()
    db.delete(row)
    db.commit()
    return True


def list_items(db: Session, user: models.User, status: str = "", platform: str = "", deal_id: int | None = None,
               q: str = "", from_at: Optional[datetime] = None, to_at: Optional[datetime] = None) -> list:
    qry = db.query(models.ContentPlanItem).filter_by(user_id=user.id)
    if status:
        qry = qry.filter_by(status=status)
    if platform:
        qry = qry.filter_by(platform=platform)
    if deal_id:
        qry = qry.filter_by(deal_id=deal_id)
    if from_at:
        qry = qry.filter(models.ContentPlanItem.scheduled_at >= from_at)
    if to_at:
        qry = qry.filter(models.ContentPlanItem.scheduled_at <= to_at)
    if q:
        qq = q.strip().lower()
        qry = qry.filter(or_(models.ContentPlanItem.search_text.contains(qq),
                             models.ContentPlanItem.title.ilike(f"%{qq}%")))
    return qry.order_by(models.ContentPlanItem.updated_at.desc(), models.ContentPlanItem.id.desc()).all()


def calendar_view(db: Session, user: models.User, from_at: datetime, to_at: datetime) -> dict:
    items = list_items(db, user, from_at=from_at, to_at=to_at)
    return {
        "from": from_at.isoformat(),
        "to": to_at.isoformat(),
        "items": items,
        "note": "Calendar shows planned content only. Publish on platforms yourself.",
    }


def list_drafts(db: Session, user: models.User, plan_item_id: int) -> list[models.ContentDraft]:
    _owned_plan(db, user, plan_item_id)
    return (db.query(models.ContentDraft).filter_by(user_id=user.id, plan_item_id=plan_item_id)
            .order_by(models.ContentDraft.id.desc()).all())


def save_draft(db: Session, user: models.User, plan_item_id: int, data: dict,
               source: str = "manual") -> models.ContentDraft:
    _owned_plan(db, user, plan_item_id)
    row = models.ContentDraft(
        user_id=user.id,
        plan_item_id=plan_item_id,
        variant=(data.get("variant") or "primary")[:24],
        body_json=data.get("body_json") or {},
        caption=(data.get("caption") or "")[:12000],
        hashtags=(data.get("hashtags") or "")[:2000],
        source=source if source in models.DRAFT_SOURCES else "manual",
        parent_draft_id=data.get("parent_draft_id"),
    )
    db.add(row)
    plan = _owned_plan(db, user, plan_item_id)
    if plan.status == "idea":
        plan.status = "draft"
    db.commit()
    db.refresh(row)
    return row


def export_draft(db: Session, user: models.User, draft_id: int) -> str:
    draft = _owned_draft(db, user, draft_id)
    plan = _owned_plan(db, user, draft.plan_item_id)
    return export_text(draft, plan)


def export_text(draft: models.ContentDraft, plan: models.ContentPlanItem) -> str:
    parts = [f"# {plan.title}", f"Platform: {plan.platform} · Format: {plan.format}", ""]
    bj = draft.body_json or {}
    if bj.get("hook"):
        parts += ["## Hook", bj["hook"], ""]
    if bj.get("sections"):
        for s in bj["sections"]:
            parts.append(f"### {s.get('title', 'Section')}")
            parts.append(s.get("text", ""))
            parts.append("")
    if bj.get("script"):
        parts += ["## Script", bj["script"], ""]
    if draft.caption:
        parts += ["## Caption", draft.caption, ""]
    if draft.hashtags:
        parts += ["## Hashtags", draft.hashtags, ""]
    parts.append("— Publish manually. This app does not post for you.")
    return "\n".join(parts)


# --- generation templates ---

def _llm_json(prompt: str, fallback: dict) -> dict:
    if settings.llm_provider != "openai_compat":
        return fallback
    try:
        raw = llm.simple_completion(prompt + "\n\nReturn valid JSON only.")
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            return json.loads(m.group())
    except (json.JSONDecodeError, ValueError, Exception):
        pass
    return fallback


def _idea_templates(c: dict, count: int, theme: str) -> list[dict]:
    niche = c["niche"]
    plat = c["platform_label"]
    brand = c["deal"].get("brand", "")
    sponsor = f" (sponsored angle for {brand})" if brand else ""
    base = theme or f"{niche} tips"
    ideas = []
    hooks = [
        f"3 {niche} mistakes I stopped making{sponsor}",
        f"POV: {plat} creator in {c['city'] or 'your city'} tries {base}",
        f"What nobody tells you about {niche}{sponsor}",
        f"Day in my life — {niche} edition",
        f"Before vs after: {base}",
        f"Answering your top {niche} questions",
        f"My honest review format — {brand or 'favorite find'}",
        f"Quick tutorial: {base} in 60 seconds",
    ]
    for i in range(min(count, 12)):
        title = hooks[i % len(hooks)]
        ideas.append({"title": title, "angle": f"{plat} · {c['tone'] if 'tone' in c else 'friendly'} tone",
                      "format_hint": "reel" if plat == "Instagram" else "shorts"})
    return ideas[:count]


def generate_ideas(db: Session, user: models.User, platform: str, count: int = 5,
                   theme: str = "", tone: str = "friendly", deal_id: int | None = None) -> dict:
    count = max(1, min(count, 12))
    c = ctx.build_context(db, user, platform, deal_id)
    c["tone"] = tone
    fallback = {"ideas": _idea_templates(c, count, theme)}
    prompt = (
        f"Generate {count} unique {platform} content ideas for a {c['creator_type']} in niche '{c['niche']}'. "
        f"Language: {ctx.lang_name(c['language'])}. Tone: {tone}. Theme: {theme or 'general'}. "
        f"Deal context: {c['deal'] or 'none'}. "
        f"Analytics (use only if helpful, do not invent stats): {c['analytics_hint'] or 'none'}. "
        'JSON: {"ideas":[{"title":"...","angle":"...","format_hint":"reel|youtube|carousel"}]}'
    )
    data = _llm_json(prompt, fallback)
    ideas = data.get("ideas") or fallback["ideas"]
    created = []
    for idea in ideas[:count]:
        row = create_item(db, user, {
            "platform": platform, "format": "idea", "title": str(idea.get("title", "Idea"))[:255],
            "status": "idea", "tone": tone, "deal_id": deal_id,
            "notes": str(idea.get("angle", ""))[:500],
        })
        created.append(row)
    return {"ideas": ideas, "plan_item_ids": [r.id for r in created], "source": "llm" if settings.llm_provider == "openai_compat" else "template"}


def _reel_template(c: dict, topic: str) -> dict:
    niche = c["niche"]
    hook = f"Stop scrolling — this {niche} tip saved me hours."
    body = [
        {"title": "0–3s Hook", "text": hook},
        {"title": "3–20s Value", "text": f"Show the problem, then demo: {topic or niche}."},
        {"title": "20–45s Story", "text": c["bio"] or f"Quick personal take as a {c['creator_type']}."},
        {"title": "CTA", "text": "Save this for later · Follow for part 2"},
    ]
    cap = f"{topic or niche} ✨\n{c['sponsored_line']}".strip()
    tags = f"#{niche.replace(' ', '')} #creator #reels #india"
    if c["deal"].get("brand"):
        tags += f" #{c['deal']['brand'].replace(' ', '')}"
    return {"body_json": {"hook": hook, "sections": body, "duration_sec": 45},
            "caption": cap, "hashtags": tags}


def _youtube_template(c: dict, topic: str) -> dict:
    title = topic or f"{c['niche']} — full breakdown"
    script = (
        f"INTRO (0:00–0:45)\nHook: Why {title} matters for my audience.\n\n"
        f"SECTION 1 — Context\nWho this is for · my experience in {c['niche']}.\n\n"
        f"SECTION 2 — Main value\n3–5 bullet points on {title}.\n\n"
        f"SECTION 3 — Demo / B-roll notes\nVisual cues for editor.\n\n"
        f"OUTRO\nCTA: subscribe + comment keyword.\n"
    )
    if c["deal"].get("brand"):
        script += f"\nSPONSOR SEGMENT: Include #ad for {c['deal']['brand']}. Deliverables: {c['deal'].get('deliverables', '')}\n"
    desc = f"{title}\n\n{c['bio'][:200]}\n\n{c['sponsored_line']}"
    return {"body_json": {"title": title, "script": script, "chapters": ["Intro", "Context", "Main", "Outro"]},
            "caption": desc, "hashtags": f"#{c['niche'].replace(' ', '')} #youtube #creator"}


def _caption_template(c: dict, topic: str) -> dict:
    text = (
        f"{topic or c['niche']} 🌿\n\n"
        f"Drop a comment if you want the full guide.\n"
        f"{c['sponsored_line']}"
    ).strip()
    tags = " ".join(f"#{w}" for w in [c["niche"].split()[0], "creator", c["platform"], "india"] if w)
    return {"body_json": {"type": "caption"}, "caption": text, "hashtags": tags}


def generate_script(db: Session, user: models.User, plan_item_id: int | None, fmt: str,
                    platform: str, topic: str = "", tone: str = "friendly",
                    deal_id: int | None = None) -> dict:
    if fmt not in ("reel", "youtube", "caption", "shorts", "carousel"):
        raise ValueError("Unsupported format for generation")
    if plan_item_id:
        plan = _owned_plan(db, user, plan_item_id)
        platform = plan.platform
        deal_id = plan.deal_id or deal_id
        topic = topic or plan.title
    c = ctx.build_context(db, user, platform, deal_id)
    c["tone"] = tone
    if fmt in ("reel", "shorts"):
        pack = _reel_template(c, topic)
    elif fmt == "youtube":
        pack = _youtube_template(c, topic)
    elif fmt == "carousel":
        pack = _reel_template(c, topic)
        pack["body_json"]["slides"] = [{"title": f"Slide {i}", "text": topic or c["niche"]} for i in range(1, 6)]
    else:
        pack = _caption_template(c, topic)

    if settings.llm_provider == "openai_compat":
        prompt = (
            f"Write a {fmt} script for {platform}. Creator: {c['creator_name']}, niche: {c['niche']}, "
            f"tone: {tone}, language: {ctx.lang_name(c['language'])}. Topic: {topic}. "
            f"Deal: {c['deal'] or 'none'}. Verified analytics hints only: {c['analytics_hint'] or 'none'}. "
            "Do not invent metrics. JSON: {\"body_json\":{...},\"caption\":\"...\",\"hashtags\":\"...\"}"
        )
        pack = {**pack, **_llm_json(prompt, pack)}

    if not plan_item_id:
        plan = create_item(db, user, {
            "platform": platform, "format": fmt, "title": (topic or f"{fmt.title()} draft")[:255],
            "status": "draft", "tone": tone, "deal_id": deal_id,
        })
        plan_item_id = plan.id
    else:
        plan = _owned_plan(db, user, plan_item_id)
        plan.format = fmt
        plan.status = "draft"
        db.commit()

    src = "llm" if settings.llm_provider == "openai_compat" else "template"
    draft = save_draft(db, user, plan_item_id, pack, source=src)
    return {"plan_item": plan, "draft": draft, "source": src, "disclaimer": c["disclaimer"]}


def repurpose(db: Session, user: models.User, draft_id: int, target_format: str,
              target_platform: str) -> dict:
    if target_format not in models.CONTENT_FORMATS:
        raise ValueError("Unknown target format")
    src = _owned_draft(db, user, draft_id)
    plan = _owned_plan(db, user, src.plan_item_id)
    c = ctx.build_context(db, user, target_platform, plan.deal_id)
    excerpt = src.caption or json.dumps(src.body_json)[:1500]
    fallback = _caption_template(c, f"Repurposed from: {plan.title}")
    fallback["body_json"]["repurposed_from"] = plan.id
    if target_format == "reel":
        fallback = _reel_template(c, plan.title)
        fallback["body_json"]["voiceover"] = excerpt[:800]
    elif target_format == "youtube":
        fallback = _youtube_template(c, plan.title)
        fallback["body_json"]["script"] = f"Adapted from short-form:\n{excerpt}\n\n" + fallback["body_json"].get("script", "")
    prompt = (
        f"Repurpose this content to {target_format} on {target_platform}. Keep facts; no new metrics.\n"
        f"Source:\n{excerpt}\nJSON: {{\"body_json\":{{}},\"caption\":\"\",\"hashtags\":\"\"}}"
    )
    pack = _llm_json(prompt, fallback)
    new_plan = create_item(db, user, {
        "platform": target_platform, "format": target_format,
        "title": f"{plan.title} ({target_format})"[:255], "status": "draft",
        "deal_id": plan.deal_id, "notes": f"Repurposed from plan #{plan.id}",
    })
    draft = save_draft(db, user, new_plan.id, {**pack, "parent_draft_id": src.id}, source="repurpose")
    return {"plan_item": new_plan, "draft": draft}


def suggestions(db: Session, user: models.User) -> list[str]:
    """Rule-based suggestions using profile + verified analytics only."""
    tips = []
    c = ctx.build_context(db, user, "instagram", None)
    if c["deal"]:
        tips.append(f"Draft a {c['platform_label']} reel for {c['deal']['brand']} before the due date.")
    elif not ctx.analytics_hints(db, user, "youtube"):
        tips.append("Log a few metrics in Analytics so ideas can reference real performance.")
    items = list_items(db, user, status="scheduled")
    if not items:
        tips.append("Schedule your next post in the Content calendar — even a rough date helps.")
    ready = list_items(db, user, status="ready")
    if ready:
        tips.append(f"You have {len(ready)} pieces marked Ready — pick one to publish manually.")
    if c["bio"]:
        tips.append(f"Turn your bio line into a carousel: \"{c['bio'][:80]}…\"")
    if not tips:
        tips.append(f"Generate 5 {c['niche']} ideas for {c['platform_label']}.")
    return tips[:6]

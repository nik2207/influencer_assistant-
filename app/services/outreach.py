import csv
from pathlib import Path

from .. import models

BRANDS_FILE = Path("data/brands.csv")


def load_brands() -> list[dict]:
    if not BRANDS_FILE.exists():
        return []
    with BRANDS_FILE.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def suggest(user: models.User, limit: int = 5) -> list[dict]:
    words = {w.strip().lower() for w in user.niche.replace(",", " ").split() if w.strip()}
    scored = []
    for b in load_brands():
        tags = set(b["tags"].split())
        score = len(words & tags)
        scored.append((score, b))
    scored.sort(key=lambda x: -x[0])
    return [dict(b, match=score) for score, b in scored[:limit]]


def draft_pitch(user: models.User, brand_name: str, note: str = "", ctx: dict | None = None) -> str:
    """Legacy single-pitch string (Subject + body). Used by chat and GET /pitch."""
    from .outreach_studio import _build_variant, _brand_row
    if ctx is None:
        from . import profile as profile_service
        from sqlalchemy.orm import object_session
        sess = object_session(user)
        ctx = profile_service.pitch_context(sess, user) if sess else {
            "type_label": "Creator", "offer": "Reels, stories and a short review", "bio": "", "channels": [],
        }
    row = _brand_row(brand_name)
    who = user.name or "a content creator"
    handle = f" ({user.handle})" if user.handle else ""
    niche = user.niche or "lifestyle"
    city = user.city or ""
    s = _build_variant("professional", row["name"], row.get("category", ""), who, handle, niche, city,
                       ctx, user, note, "", "")
    return f"Subject: {s['subject']}\n\n{s['body']}"

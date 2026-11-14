"""Creator profile: load/save, completeness, and the privacy-filtered context given to the AI."""
from sqlalchemy.orm import Session

from .. import models
from .personas import CREATOR_TYPES, LANGUAGES, PLATFORMS, options, persona

PRIVATE_FIELDS = ("phone", "home_location", "contact_email", "upi_vpa", "gstin")  # never sent to the AI


def get_or_create(db: Session, user: models.User) -> models.CreatorProfile:
    cp = db.query(models.CreatorProfile).filter_by(user_id=user.id).first()
    if not cp:
        cp = models.CreatorProfile(user_id=user.id, languages=[user.language or "en"])
        db.add(cp)
        db.commit()
    return cp


def platforms_of(db: Session, user: models.User) -> list[models.SocialAccount]:
    return (db.query(models.SocialAccount).filter_by(user_id=user.id)
            .order_by(models.SocialAccount.followers.desc(), models.SocialAccount.id).all())


def _langs(cp: models.CreatorProfile, user: models.User) -> list[str]:
    langs = [x for x in (cp.languages or []) if x in LANGUAGES] or ["en"]
    if user.language in LANGUAGES and user.language not in langs:
        langs.append(user.language)  # the reply language is always one of the preferred languages
    return langs


def total_followers(db: Session, user: models.User) -> int:
    accts = platforms_of(db, user)
    return sum(a.followers for a in accts) if accts else (user.followers or 0)


def sync_followers(db: Session, user: models.User) -> None:
    """Keep User.followers (used by pitches and email drafts) equal to the sum across platforms."""
    accts = platforms_of(db, user)
    if accts:
        user.followers = sum(a.followers for a in accts)
        db.commit()


def completeness(db: Session, user: models.User, cp: models.CreatorProfile) -> dict:
    checks = [
        ("display name", bool(user.name)), ("handle", bool(user.handle)), ("niche", bool(user.niche)),
        ("short bio", bool(cp.bio)), ("a social account", bool(platforms_of(db, user))),
        ("city", bool(user.city)), ("payment details", bool(user.upi_vpa or cp.payment_method == "bank")),
    ]
    done = sum(1 for _, ok in checks if ok)
    return {"percent": round(100 * done / len(checks)), "missing": [n for n, ok in checks if not ok]}


def personalization(cp: models.CreatorProfile) -> dict:
    p = persona(cp.creator_type)
    return {"creator_type": cp.creator_type if cp.creator_type in CREATOR_TYPES else "influencer",
            "label": p["label"], "labels": p["labels"], "chips": p["chips"],
            "chat_suggestions": p["chat_suggestions"], "deliverable_examples": p["deliverable_examples"]}


def full(db: Session, user: models.User) -> dict:
    cp = get_or_create(db, user)
    accts = platforms_of(db, user)
    return {
        "user": {"id": user.id, "email": user.email, "name": user.name, "handle": user.handle, "niche": user.niche,
                 "city": user.city, "language": user.language, "upi_vpa": user.upi_vpa},
        "creator": {"creator_type": cp.creator_type, "bio": cp.bio, "currency": cp.currency,
                    "languages": _langs(cp, user), "contact_email": cp.contact_email, "phone": cp.phone,
                    "home_location": cp.home_location, "payment_method": cp.payment_method,
                    "payment_terms_days": cp.payment_terms_days, "invoice_notes": cp.invoice_notes, "gstin": cp.gstin},
        "platforms": [{"platform": a.platform, "label": PLATFORMS[a.platform]["label"], "handle": a.handle,
                       "url": a.url, "followers": a.followers} for a in accts if a.platform in PLATFORMS],
        "total_followers": total_followers(db, user),
        "completeness": completeness(db, user, cp),
        "personalization": personalization(cp),
        "options": options(),
    }


def ai_context(db: Session, user: models.User) -> str:
    """Safe summary for the assistant. Deliberately leaves out phone, email, home location, UPI and GSTIN."""
    cp = get_or_create(db, user)
    p = persona(cp.creator_type)
    chans = ", ".join(f"{PLATFORMS[a.platform]['label']} {a.followers:,}" for a in platforms_of(db, user)
                      if a.platform in PLATFORMS and a.followers) or "none added"
    langs = ", ".join(LANGUAGES[x] for x in _langs(cp, user))
    lines = [
        f"Creator type: {p['label']}",
        f"Niche: {user.niche or 'not set'}",
        f"Channels and audience: {chans}",
        f"City: {user.city or 'not set'}",
        f"Understands: {langs}. Currency: {cp.currency}.",
        f"Words to use: call deals '{p['labels']['deals_lower']}', and calendar items '{p['labels']['event']}s'.",
    ]
    if cp.bio:
        lines.append(f"Bio (creator's own words): {cp.bio}")
    return "\n".join(lines)


def pitch_context(db: Session, user: models.User) -> dict:
    cp = get_or_create(db, user)
    p = persona(cp.creator_type)
    return {"type_label": p["label"], "offer": p["pitch_offer"], "bio": cp.bio,
            "channels": [(PLATFORMS[a.platform]["label"], a.followers) for a in platforms_of(db, user)
                         if a.platform in PLATFORMS and a.followers],
            "terms_days": cp.payment_terms_days, "invoice_notes": cp.invoice_notes}

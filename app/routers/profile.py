from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..schemas_profile import PlatformIn, ProfileIn, check_platform_url
from ..security import audit, current_user
from ..services import profile as svc
from ..services.personas import PLATFORMS

router = APIRouter(prefix="/profile", tags=["profile"])

USER_FIELDS = ("name", "handle", "niche", "city", "language", "upi_vpa")
CREATOR_FIELDS = ("creator_type", "bio", "currency", "languages", "contact_email", "phone", "home_location",
                  "payment_method", "payment_terms_days", "invoice_notes", "gstin")


@router.get("")
def get_profile(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return svc.full(db, user)


@router.patch("")
def update_profile(body: ProfileIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_none=True)
    cp = svc.get_or_create(db, user)
    for k in USER_FIELDS:
        if k in data:
            setattr(user, k, data[k])
    for k in CREATOR_FIELDS:
        if k in data:
            setattr(cp, k, data[k])
    if "language" in data and "languages" not in data:
        langs = list(cp.languages or [])
        if data["language"] not in langs:
            cp.languages = langs + [data["language"]]
    if "languages" in data and user.language not in data["languages"]:
        user.language = data["languages"][0]  # reply language must be one of the chosen languages
    db.commit()
    audit(db, user.id, "profile_updated", ",".join(sorted(data)))  # field names only, never the values
    return svc.full(db, user)


@router.put("/platforms/{platform}")
def save_platform(platform: str, body: PlatformIn, user: models.User = Depends(current_user),
                  db: Session = Depends(get_db)):
    if platform not in PLATFORMS:
        raise HTTPException(404, "Unknown platform")
    try:
        check_platform_url(platform, body.url)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    acct = db.query(models.SocialAccount).filter_by(user_id=user.id, platform=platform).first()
    if not acct:
        acct = models.SocialAccount(user_id=user.id, platform=platform)
        db.add(acct)
    acct.handle = body.handle
    acct.url = body.url or (PLATFORMS[platform]["base"] + body.handle)
    acct.followers = body.followers
    if acct.connection_status != "connected":
        acct.connection_status = "manual"
    db.commit()
    svc.sync_followers(db, user)
    audit(db, user.id, "platform_saved", platform)
    return svc.full(db, user)


@router.delete("/platforms/{platform}")
def remove_platform(platform: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    acct = db.query(models.SocialAccount).filter_by(user_id=user.id, platform=platform).first()
    if not acct:
        raise HTTPException(404, "That account isn't added")
    db.delete(acct)
    db.commit()
    svc.sync_followers(db, user)
    audit(db, user.id, "platform_removed", platform)
    return svc.full(db, user)

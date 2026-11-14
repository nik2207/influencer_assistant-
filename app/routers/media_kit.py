from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..models import MEDIA_KIT_TEMPLATES, RATE_DELIVERABLES
from ..schemas_media_kit import MediaKitIn, PortfolioIn, PublishIn, RatesIn, SamplesIn
from ..security import audit, current_user
from ..services import media_kit as mk
from ..services import media_kit_assets as assets
from ..services import media_kit_pdf as pdf_svc

router = APIRouter(tags=["media-kit"])


@router.get("/media-kit/meta")
def meta():
    return {
        "templates": list(MEDIA_KIT_TEMPLATES),
        "deliverables": list(RATE_DELIVERABLES),
        "note": "Public links expose only the published snapshot you approve.",
    }


@router.get("/media-kit")
def get_preview(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return mk.build_preview(db, user)


@router.put("/media-kit")
def update_kit(body: MediaKitIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    kit = mk.get_kit(db, user)
    data = body.model_dump(exclude_none=True)
    for k, v in data.items():
        setattr(kit, k, v)
    db.commit()
    audit(db, user.id, "media_kit_updated", ",".join(data.keys()))
    return mk.build_preview(db, user)


@router.put("/media-kit/rates")
def put_rates(body: RatesIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        mk.save_rates(db, user, [x.model_dump() for x in body.lines])
    except ValueError as e:
        raise HTTPException(400, str(e))
    return mk.build_preview(db, user)


@router.put("/media-kit/portfolio")
def put_portfolio(body: PortfolioIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        mk.save_portfolio(db, user, [x.model_dump() for x in body.items])
    except ValueError as e:
        raise HTTPException(400, str(e))
    return mk.build_preview(db, user)


@router.put("/media-kit/samples")
def put_samples(body: SamplesIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        mk.save_samples(db, user, [x.model_dump() for x in body.items])
    except ValueError as e:
        raise HTTPException(400, str(e))
    return mk.build_preview(db, user)


@router.post("/media-kit/avatar")
async def upload_avatar(file: UploadFile = File(...), user: models.User = Depends(current_user),
                        db: Session = Depends(get_db)):
    data = await file.read()
    try:
        path, mime = assets.save_avatar(user.id, data, file.content_type or "")
    except ValueError as e:
        raise HTTPException(400, str(e))
    kit = mk.get_kit(db, user)
    kit.avatar_path = path
    kit.avatar_mime = mime
    db.commit()
    audit(db, user.id, "media_kit_avatar", "uploaded")
    return {"ok": True}


@router.get("/media-kit/avatar")
def get_avatar(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    kit = mk.get_kit(db, user)
    if not kit.avatar_path:
        raise HTTPException(404, "No profile image")
    return FileResponse(kit.avatar_path, media_type=kit.avatar_mime or "image/jpeg")


@router.delete("/media-kit/avatar")
def delete_avatar(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    kit = mk.get_kit(db, user)
    kit.avatar_path = ""
    kit.avatar_mime = ""
    db.commit()
    return {"ok": True}


@router.get("/media-kit/export/pdf")
def export_pdf(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    preview = mk.build_preview(db, user)
    kit = mk.get_kit(db, user)
    path = pdf_svc.build_media_kit_pdf(preview, kit.pdf_template, kit.avatar_path)
    return FileResponse(path, media_type="application/pdf", filename="media-kit.pdf")


@router.post("/media-kit/share/publish")
def publish(body: PublishIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        share = mk.publish_share(db, user, body.confirm_public)
    except ValueError as e:
        raise HTTPException(400, str(e))
    audit(db, user.id, "media_kit_published", share.token[:8])
    return {
        "active": True,
        "public_url": f"/media-kit/public/{share.token}",
        "published_at": share.published_at.isoformat() if share.published_at else None,
    }


@router.post("/media-kit/share/revoke")
def revoke(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    mk.revoke_share(db, user)
    audit(db, user.id, "media_kit_revoked", "")
    return {"active": False}


@router.get("/media-kit/share")
def share_status(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    share = db.query(models.MediaKitShare).filter_by(user_id=user.id).first()
    if not share:
        return {"active": False, "public_url": None}
    return {
        "active": share.is_active,
        "public_url": f"/media-kit/public/{share.token}" if share.is_active else None,
        "published_at": share.published_at.isoformat() if share.published_at else None,
    }


@router.get("/media-kit/public/{token}")
def public_view(token: str, db: Session = Depends(get_db)):
    """No auth — frozen snapshot only; never live private analytics."""
    try:
        snap = mk.public_snapshot(db, token)
    except ValueError:
        raise HTTPException(404, "Media kit not found or link revoked")
    return snap


@router.get("/media-kit/public/{token}/avatar")
def public_avatar(token: str, db: Session = Depends(get_db)):
    share = db.query(models.MediaKitShare).filter_by(token=token, is_active=True).first()
    if not share or not (share.published_snapshot or {}).get("avatar_public"):
        raise HTTPException(404, "Not available")
    user = db.get(models.User, share.user_id)
    if not user:
        raise HTTPException(404, "Not available")
    kit = mk.get_kit(db, user)
    if not kit.avatar_path:
        raise HTTPException(404, "Not available")
    return FileResponse(kit.avatar_path, media_type=kit.avatar_mime or "image/jpeg")


@router.get("/media-kit/public/{token}/pdf")
def public_pdf(token: str, db: Session = Depends(get_db)):
    try:
        snap = mk.public_snapshot(db, token)
    except ValueError:
        raise HTTPException(404, "Media kit not found or link revoked")
    tpl = (snap.get("settings") or {}).get("pdf_template", "classic")
    path = pdf_svc.build_media_kit_pdf(snap, tpl, "")
    return FileResponse(path, media_type="application/pdf", filename="media-kit.pdf")

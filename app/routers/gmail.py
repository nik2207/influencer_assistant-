from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db
from ..schemas_email_intel import ConfirmIntelligenceIn, LinkBrandIn, ToDealIn
from ..security import audit, current_user, decode_token, make_token
from ..services import calendar_sync, email_intelligence, email_matching, gmail_client, gmail_sync
from ..services.gmail_client import GmailError

router = APIRouter(prefix="/gmail", tags=["gmail"])


def _need_config():
    if not gmail_client.configured():
        raise HTTPException(503, "Gmail is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.")


def _email(db: Session, user: models.User, email_id: int) -> models.EmailMessage:
    em = db.get(models.EmailMessage, email_id)
    if not em or em.user_id != user.id:
        raise HTTPException(404, "Email not found")
    return em


@router.get("/status")
def status(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    acct = gmail_sync.get_account(db, user)
    return {"configured": gmail_client.configured(), "connected": bool(acct),
            "email": acct.email if acct else None,
            "last_sync_at": acct.last_sync_at if acct else None}


@router.get("/connect")
def connect(calendar: bool = False, user: models.User = Depends(current_user)):
    """calendar=true also asks for Google Calendar access. The state token remembers which was requested."""
    _need_config()
    state = make_token(user.id, "gmail_state", 10)  # signed, expires in 10 minutes
    return {"url": gmail_client.build_auth_url(state, calendar=calendar)}


@router.get("/callback", include_in_schema=False)
def callback(code: str = "", state: str = "", error: str = "", db: Session = Depends(get_db)):
    if error or not code:
        return RedirectResponse("/app/?gmail=denied")
    user = db.get(models.User, decode_token(state, "gmail_state"))
    if not user:
        raise HTTPException(400, "Unknown user")
    try:
        tokens = gmail_client.exchange_code(code)
        acct = gmail_sync.store_tokens(db, user, tokens)
        acct.email = gmail_client.profile_email(tokens["access_token"])
        db.commit()
    except GmailError:
        return RedirectResponse("/app/?gmail=error")
    cal = calendar_sync.mark_granted(db, user, tokens.get("scope", ""))
    audit(db, user.id, "gmail_connected", f"{acct.email} calendar={cal}")
    return RedirectResponse("/app/?gmail=connected" + ("&cal=1" if cal else ""))


@router.post("/sync")
def sync_now(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        result = gmail_sync.sync(db, user)
    except GmailError as exc:
        raise HTTPException(400, str(exc))
    return {"fetched": result["fetched"], "new": len(result["new"]), "skipped": result["skipped"]}


@router.post("/cleanup")
def cleanup(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    """Remove saved emails that the noise filter now recognises (job alerts, noreply notifications)."""
    return {"removed": gmail_sync.cleanup_saved(db, user)}


@router.get("/emails", response_model=list[schemas.EmailOut])
def list_emails(category: str | None = None, q: str = "", inquiry_only: bool = False,
                include_dismissed: bool = False,
                user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    query = db.query(models.EmailMessage).filter_by(user_id=user.id)
    if category:
        query = query.filter_by(category=category)
    if inquiry_only:
        query = query.filter(models.EmailMessage.is_brand_inquiry.is_(True))
    if q:
        qq = f"%{q.strip()}%"
        query = query.filter(
            models.EmailMessage.subject.ilike(qq)
            | models.EmailMessage.brand.ilike(qq)
            | models.EmailMessage.sender_name.ilike(qq)
        )
    if not include_dismissed:
        query = query.filter(models.EmailMessage.status != "dismissed")
    return query.order_by(models.EmailMessage.received_at.desc()).limit(100).all()


@router.get("/recommendations")
def email_recommendations(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return {"items": email_matching.recommendations(db, user),
            "notice": "Suggestions only — nothing is sent automatically."}


@router.get("/emails/{email_id}", response_model=schemas.EmailDetail)
def email_detail(email_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    em = _email(db, user, email_id)
    out = schemas.EmailDetail.model_validate(em)
    out.body = gmail_sync.body_of(em)
    intel = email_intelligence.public_view(em)
    intel["matches"] = email_matching.all_matches(db, user, em)
    out.intelligence = intel
    out.unverified_notice = intel.get("unverified_notice", email_intelligence.UNVERIFIED_NOTICE)
    return out


@router.get("/emails/{email_id}/intelligence")
def get_intelligence(email_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    em = _email(db, user, email_id)
    intel = email_intelligence.public_view(em)
    intel["matches"] = email_matching.all_matches(db, user, em)
    return intel


@router.get("/emails/{email_id}/matches")
def get_matches(email_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    em = _email(db, user, email_id)
    return email_matching.all_matches(db, user, em)


@router.post("/emails/{email_id}/reanalyze")
def reanalyze_email(email_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    em = _email(db, user, email_id)
    intel = gmail_sync.reanalyze(db, user, em)
    audit(db, user.id, "email_reanalyzed", str(email_id))
    return intel


@router.post("/emails/{email_id}/confirm-intelligence")
def confirm_intelligence(email_id: int, body: ConfirmIntelligenceIn,
                         user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    em = _email(db, user, email_id)
    intel = email_intelligence.mark_verified(em.intelligence_json or {}, body.model_dump())
    em.intelligence_json = intel
    db.commit()
    audit(db, user.id, "email_intel_verified", str(email_id))
    return intel


@router.post("/emails/{email_id}/draft")
def make_draft(email_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    em = _email(db, user, email_id)
    return {"draft_reply": gmail_sync.make_draft(db, user, em)}


@router.put("/emails/{email_id}/draft")
def edit_draft(email_id: int, body: schemas.DraftEdit, user: models.User = Depends(current_user),
               db: Session = Depends(get_db)):
    em = _email(db, user, email_id)
    em.draft_reply = body.draft_reply
    db.commit()
    return {"draft_reply": em.draft_reply}


@router.post("/emails/{email_id}/push-draft")
def push_draft(email_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    """Puts the reply into the user's Gmail Drafts folder. Nothing is ever sent automatically."""
    em = _email(db, user, email_id)
    try:
        draft_id = gmail_sync.push_draft_to_gmail(db, user, em)
    except GmailError as exc:
        raise HTTPException(400, str(exc))
    audit(db, user.id, "gmail_draft_created", f"email #{em.id}")
    return {"gmail_draft_id": draft_id}


@router.post("/emails/{email_id}/to-deal")
def email_to_deal(email_id: int, body: ToDealIn | None = None,
                  user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    em = _email(db, user, email_id)
    body = body or ToDealIn()
    if not body.confirm:
        raise HTTPException(400, "Set confirm=true to create or link a deal from this email.")
    try:
        deal = gmail_sync.to_deal(db, user, em, apply_intelligence=body.apply_intelligence,
                                  link_deal_id=body.deal_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    audit(db, user.id, "email_to_deal", f"email #{em.id} deal #{deal.id}")
    return {"deal_id": deal.id, "brand": deal.brand, "status": deal.status,
            "notice": "Deal created from email — amounts are unverified until you confirm in Deals."}


@router.post("/emails/{email_id}/link-brand")
def link_brand(email_id: int, body: LinkBrandIn,
               user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    if not body.confirm:
        raise HTTPException(400, "Set confirm=true to link this email to a brand CRM record.")
    em = _email(db, user, email_id)
    br = db.get(models.BrandRecord, body.brand_record_id)
    if not br or br.user_id != user.id:
        raise HTTPException(404, "Brand not found")
    em.brand_record_id = br.id
    db.commit()
    audit(db, user.id, "email_link_brand", f"email #{em.id} brand #{br.id}")
    return {"brand_record_id": br.id, "display_name": br.display_name}


@router.post("/emails/{email_id}/dismiss", status_code=204)
def dismiss(email_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    _email(db, user, email_id).status = "dismissed"
    db.commit()


@router.delete("/disconnect", status_code=204)
def disconnect(delete_emails: bool = True, user: models.User = Depends(current_user),
               db: Session = Depends(get_db)):
    gmail_sync.disconnect(db, user, delete_emails)
    audit(db, user.id, "gmail_disconnected")

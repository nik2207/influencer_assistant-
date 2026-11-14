import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import settings
from ..db import get_db
from ..security import (audit, current_user, decode_token, hash_password, make_token,
                        verify_password)

router = APIRouter(prefix="/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)


def _tokens(user_id: int) -> schemas.TokenOut:
    return schemas.TokenOut(
        access_token=make_token(user_id, "access", settings.access_token_minutes),
        refresh_token=make_token(user_id, "refresh", settings.refresh_token_days * 24 * 60),
    )


def _user_out(u: models.User) -> schemas.UserOut:
    out = schemas.UserOut.model_validate(u)
    out.telegram_linked = bool(u.telegram_chat_id)
    return out


@router.post("/register", response_model=schemas.TokenOut, status_code=201)
@limiter.limit("10/minute")
def register(request: Request, body: schemas.RegisterIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.query(models.User).filter_by(email=email).first():
        raise HTTPException(409, "Email already registered")
    user = models.User(email=email, password_hash=hash_password(body.password), name=body.name)
    db.add(user)
    db.commit()
    db.refresh(user)
    from ..services import workspace_bootstrap
    ws_mem = workspace_bootstrap.ensure_personal_workspace(db, user)
    audit(db, user.id, "register", ip=request.client.host if request.client else "",
          workspace_id=ws_mem.workspace_id, resource_type="user", resource_id=user.id)
    return _tokens(user.id)


@router.post("/login", response_model=schemas.TokenOut)
@limiter.limit("10/minute")
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter_by(email=form.username.lower()).first()
    ip = request.client.host if request.client else ""
    if not user or not verify_password(form.password, user.password_hash):
        audit(db, user.id if user else None, "login_failed", form.username, ip)
        raise HTTPException(401, "Wrong email or password")
    audit(db, user.id, "login", ip=ip)
    return _tokens(user.id)


@router.post("/refresh", response_model=schemas.TokenOut)
def refresh(body: schemas.RefreshIn, db: Session = Depends(get_db)):
    user_id = decode_token(body.refresh_token, "refresh")
    if not db.get(models.User, user_id):
        raise HTTPException(401, "User not found")
    return _tokens(user_id)


@router.get("/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(current_user)):
    return _user_out(user)


@router.patch("/me", response_model=schemas.UserOut)
def update_me(body: schemas.ProfileIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(user, key, value)
    db.commit()
    return _user_out(user)


@router.post("/telegram-code")
def telegram_code(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    user.telegram_link_code = secrets.token_hex(3).upper()
    db.commit()
    return {"code": user.telegram_link_code, "instruction": f"Send /link {user.telegram_link_code} to your bot"}

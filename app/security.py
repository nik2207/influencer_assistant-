import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from cryptography.fernet import Fernet
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from . import models
from .config import settings
from .db import get_db
from .services.tenancy import WorkspaceCtx

oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")
ALGO = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:72], hashed.encode())
    except ValueError:
        return False


def make_token(user_id: int, kind: str, minutes: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    return jwt.encode({"sub": str(user_id), "type": kind, "exp": exp}, settings.secret_key, algorithm=ALGO)


def decode_token(token: str, kind: str) -> int:
    try:
        data = jwt.decode(token, settings.secret_key, algorithms=[ALGO])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    if data.get("type") != kind:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")
    return int(data["sub"])


def current_user(token: str = Depends(oauth2), db: Session = Depends(get_db)) -> models.User:
    user = db.get(models.User, decode_token(token, "access"))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


def _fernet() -> Fernet:
    key = settings.fernet_key
    if not key:
        digest = hashlib.sha256(settings.secret_key.encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    return Fernet(key.encode())


def encrypt_secret(value: str) -> str:
    """Use for OAuth tokens (Gmail, Calendar) before storing them."""
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()


def audit(
    db: Session,
    user_id,
    action: str,
    detail: str = "",
    ip: str = "",
    *,
    workspace_id: Optional[int] = None,
    resource_type: str = "",
    resource_id: Optional[int] = None,
) -> None:
    db.add(models.AuditLog(
        user_id=user_id,
        workspace_id=workspace_id,
        action=action,
        detail=detail[:2000],
        ip=ip,
        resource_type=resource_type[:40],
        resource_id=resource_id,
    ))
    db.commit()


def workspace_context(
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
    x_workspace_id: Optional[int] = Header(None, alias="X-Workspace-Id"),
) -> WorkspaceCtx:
    memberships = (
        db.query(models.WorkspaceMembership)
        .filter_by(user_id=user.id, status="active")
        .order_by(models.WorkspaceMembership.id)
        .all()
    )
    if not memberships:
        from .services import workspace_bootstrap
        workspace_bootstrap.ensure_personal_workspace(db, user)
        memberships = (
            db.query(models.WorkspaceMembership)
            .filter_by(user_id=user.id, status="active")
            .order_by(models.WorkspaceMembership.id)
            .all()
        )
    mem = None
    if x_workspace_id is not None:
        mem = next((m for m in memberships if m.workspace_id == x_workspace_id), None)
        if not mem:
            raise HTTPException(403, "You are not a member of that workspace")
    else:
        if len(memberships) == 1:
            mem = memberships[0]
        else:
            mem = next((m for m in memberships if m.role == "owner"), memberships[0])
    ws = db.get(models.Workspace, mem.workspace_id)
    if not ws or ws.marked_for_deletion_at:
        raise HTTPException(403, "Workspace is not available")
    return WorkspaceCtx(user=user, workspace=ws, membership=mem)

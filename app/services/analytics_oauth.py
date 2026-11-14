"""YouTube analytics OAuth (Google). Tokens are stored encrypted; never returned to the client."""
from urllib.parse import urlencode

import httpx

from .. import models
from ..config import settings
from ..security import decrypt_secret, encrypt_secret
from . import gmail_client
from .gmail_client import GmailError

YOUTUBE_SCOPES = [
    "openid",
    "email",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def redirect_uri() -> str:
    base = settings.google_redirect_uri.rsplit("/", 1)[0]
    return f"{base}/analytics/oauth/callback"


def youtube_available() -> bool:
    return gmail_client.configured()


def build_youtube_auth_url(state: str) -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": " ".join(YOUTUBE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"


def exchange_code(code: str) -> dict:
    try:
        r = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": redirect_uri(),
                "grant_type": "authorization_code",
            },
            timeout=20,
        )
    except httpx.HTTPError as exc:
        raise GmailError(f"Could not reach Google: {exc}") from exc
    if r.status_code != 200:
        raise GmailError(f"Google rejected the token request: {r.text[:200]}")
    return r.json()


def store_youtube_tokens(db, user: models.User, tokens: dict) -> models.PlatformConnection:
    row = db.query(models.PlatformConnection).filter_by(user_id=user.id, platform="youtube").first()
    if not row:
        row = models.PlatformConnection(user_id=user.id, platform="youtube")
        db.add(row)
    row.access_token_enc = encrypt_secret(tokens["access_token"])
    if tokens.get("refresh_token"):
        row.refresh_token_enc = encrypt_secret(tokens["refresh_token"])
    row.scopes = tokens.get("scope", "")
    row.status = "connected"
    row.last_error = ""
    acct = db.query(models.SocialAccount).filter_by(user_id=user.id, platform="youtube").first()
    if acct:
        acct.connection_status = "connected"
    db.commit()
    db.refresh(row)
    return row


def connection_public(db, user: models.User, platform: str) -> dict:
    row = db.query(models.PlatformConnection).filter_by(user_id=user.id, platform=platform).first()
    if not row:
        return {"platform": platform, "status": "disconnected", "last_sync_at": None, "last_error": ""}
    return {
        "platform": platform,
        "status": row.status,
        "last_sync_at": row.last_sync_at.isoformat() if row.last_sync_at else None,
        "last_error": row.last_error[:120] if row.last_error else "",
    }


def sync_youtube(db, user: models.User) -> dict:
    """Placeholder sync: records attempt only — no fabricated metrics."""
    row = db.query(models.PlatformConnection).filter_by(user_id=user.id, platform="youtube").first()
    if not row or row.status != "connected":
        return {"error": "YouTube is not connected. Connect Google or enter metrics manually."}
    if not row.refresh_token_enc and not row.access_token_enc:
        return {"error": "Missing tokens. Reconnect YouTube."}
    from datetime import datetime

    row.last_sync_at = datetime.utcnow()
    row.last_error = "API metric pull is not enabled; use manual entry or CSV import."
    acct = db.query(models.SocialAccount).filter_by(user_id=user.id, platform="youtube").first()
    if acct:
        acct.last_synced_at = row.last_sync_at
    db.commit()
    return {"synced": 0, "note": row.last_error}


def disconnect(db, user: models.User, platform: str) -> None:
    row = db.query(models.PlatformConnection).filter_by(user_id=user.id, platform=platform).first()
    if row:
        if row.access_token_enc:
            try:
                gmail_client.revoke(decrypt_secret(row.access_token_enc))
            except Exception:
                pass
        db.delete(row)
    acct = db.query(models.SocialAccount).filter_by(user_id=user.id, platform=platform).first()
    if acct:
        acct.connection_status = "manual"
    db.commit()

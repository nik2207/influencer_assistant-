"""Thin Gmail REST client (no Google SDK needed). Only drafts are created, mail is never sent."""
import base64
import re
from datetime import datetime, timezone
from email.message import EmailMessage as MimeMessage
from email.utils import parseaddr
from html import unescape
from urllib.parse import urlencode

import httpx

from ..config import settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://gmail.googleapis.com/gmail/v1/users/me"
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"
SCOPES = [
    "openid", "email",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]


class GmailError(Exception):
    pass


def configured() -> bool:
    return bool(settings.google_client_id and settings.google_client_secret)


def build_auth_url(state: str, calendar: bool = False) -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES + ([CALENDAR_SCOPE] if calendar else [])),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def _token_request(data: dict) -> dict:
    try:
        r = httpx.post(TOKEN_URL, data=data, timeout=20)
    except httpx.HTTPError as exc:
        raise GmailError(f"Could not reach Google: {exc}") from exc
    if r.status_code != 200:
        raise GmailError(f"Google rejected the token request: {r.text[:200]}")
    return r.json()


def exchange_code(code: str) -> dict:
    return _token_request({
        "code": code, "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri, "grant_type": "authorization_code",
    })


def refresh_access_token(refresh_token: str) -> dict:
    return _token_request({
        "refresh_token": refresh_token, "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret, "grant_type": "refresh_token",
    })


def revoke(token: str) -> None:
    try:
        httpx.post(REVOKE_URL, data={"token": token}, timeout=15)
    except httpx.HTTPError:
        pass


def _get(token: str, path: str, params: dict | None = None) -> dict:
    try:
        r = httpx.get(f"{API}{path}", headers={"Authorization": f"Bearer {token}"}, params=params, timeout=30)
    except httpx.HTTPError as exc:
        raise GmailError(f"Could not reach Gmail: {exc}") from exc
    if r.status_code == 401:
        raise GmailError("Gmail access expired. Reconnect your account.")
    if r.status_code != 200:
        raise GmailError(f"Gmail error {r.status_code}: {r.text[:200]}")
    return r.json()


def profile_email(access_token: str) -> str:
    return _get(access_token, "/profile").get("emailAddress", "")


def list_message_ids(token: str, query: str, max_results: int) -> list[str]:
    data = _get(token, "/messages", {"q": query, "maxResults": max_results})
    return [m["id"] for m in data.get("messages", [])]


def get_message(token: str, message_id: str) -> dict:
    return _get(token, f"/messages/{message_id}", {"format": "full"})


def thread_meta(token: str, thread_id: str) -> list[dict]:
    """Sender and time of every message in a thread, oldest first. Bodies are not fetched."""
    data = _get(token, f"/threads/{thread_id}", {"format": "metadata", "metadataHeaders": "From"})
    out = []
    for m in data.get("messages", []):
        headers = {h["name"].lower(): h["value"] for h in m.get("payload", {}).get("headers", [])}
        _, addr = parseaddr(headers.get("from", ""))
        ts = int(m.get("internalDate", "0")) / 1000
        out.append({"from_email": addr.lower(),
                    "date": datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo=None)})
    out.sort(key=lambda x: x["date"])
    return out


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", html)
    text = unescape(re.sub(r"<[^>]+>", " ", html))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", text)).strip()


def _walk(part: dict, plain: list, html: list) -> None:
    mime = part.get("mimeType", "")
    data = part.get("body", {}).get("data")
    if data and mime == "text/plain":
        plain.append(_decode(data))
    elif data and mime == "text/html":
        html.append(_decode(data))
    for sub in part.get("parts", []) or []:
        _walk(sub, plain, html)


def parse_message(raw: dict) -> dict:
    payload = raw.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    name, addr = parseaddr(headers.get("from", ""))
    plain, html = [], []
    _walk(payload, plain, html)
    body = "\n".join(plain).strip() or _strip_html("\n".join(html))
    ts = int(raw.get("internalDate", "0")) / 1000
    bulk = ("list-unsubscribe" in headers
            or headers.get("precedence", "").lower() in ("bulk", "list", "junk")
            or headers.get("auto-submitted", "no").lower() != "no")
    return {
        "bulk": bulk,
        "gmail_id": raw["id"], "thread_id": raw.get("threadId", ""),
        "message_id_header": headers.get("message-id", ""),
        "sender_name": name, "sender_email": addr.lower(),
        "subject": headers.get("subject", "(no subject)"),
        "snippet": unescape(raw.get("snippet", ""))[:300],
        "body": body[:6000],
        "received_at": datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo=None),
    }


def create_compose_draft(token: str, to: str, subject: str, body: str) -> str:
    """New outbound draft (not a reply). Does not send mail."""
    msg = MimeMessage()
    if to:
        msg["To"] = to
    msg["Subject"] = subject or "(no subject)"
    msg.set_content(body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    payload = {"message": {"raw": raw}}
    try:
        r = httpx.post(f"{API}/drafts", headers={"Authorization": f"Bearer {token}"}, json=payload, timeout=30)
    except httpx.HTTPError as exc:
        raise GmailError(f"Could not reach Gmail: {exc}") from exc
    if r.status_code not in (200, 201):
        raise GmailError(f"Gmail could not create the draft: {r.text[:200]}")
    return r.json().get("id", "")


def create_draft(token: str, to: str, subject: str, body: str, thread_id: str, in_reply_to: str) -> str:
    msg = MimeMessage()
    msg["To"] = to
    msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    payload = {"message": {"raw": raw}}
    if thread_id:
        payload["message"]["threadId"] = thread_id
    try:
        r = httpx.post(f"{API}/drafts", headers={"Authorization": f"Bearer {token}"}, json=payload, timeout=30)
    except httpx.HTTPError as exc:
        raise GmailError(f"Could not reach Gmail: {exc}") from exc
    if r.status_code not in (200, 201):
        raise GmailError(f"Gmail could not create the draft: {r.text[:200]}")
    return r.json().get("id", "")

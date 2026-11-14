import httpx

from .config import settings


def send_telegram(chat_id: str, text: str) -> bool:
    if not settings.telegram_bot_token:
        return False
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text}, timeout=15)
        return r.status_code == 200
    except httpx.HTTPError:
        return False

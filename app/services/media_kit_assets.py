"""Profile image storage for media kit (validated uploads)."""
from pathlib import Path

from ..services.expenses import MAX_RECEIPT_BYTES, sniff_kind

OUT_DIR = Path("data/media-kit")
ALLOWED = {"image/jpeg", "image/png", "image/webp"}
EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def save_avatar(user_id: int, data: bytes, claimed_mime: str = "") -> tuple[str, str]:
    if len(data) > MAX_RECEIPT_BYTES:
        raise ValueError("Image must be 5 MB or smaller.")
    mime = sniff_kind(data)
    if mime not in ALLOWED:
        raise ValueError("Profile image must be JPEG, PNG or WebP.")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob(f"u{user_id}_avatar.*"):
        old.unlink(missing_ok=True)
    path = OUT_DIR / f"u{user_id}_avatar{EXT[mime]}"
    path.write_bytes(data)
    return str(path), mime

import uuid
from datetime import datetime
from urllib.parse import quote

from sqlalchemy.orm import Session

from .. import models


def deep_links(kind: str, pickup: str, drop: str) -> dict:
    links = {
        "google_maps": f"https://www.google.com/maps/dir/?api=1&origin={quote(pickup)}&destination={quote(drop)}",
    }
    if kind == "cab":
        links["uber"] = (
            "https://m.uber.com/ul/?action=setPickup"
            f"&pickup[formatted_address]={quote(pickup)}&dropoff[formatted_address]={quote(drop)}"
        )
    return links


def create_booking(db: Session, user: models.User, kind: str, pickup: str, drop: str, when: datetime) -> dict:
    """Demo provider: stores a mock booking and returns deep links.

    Replace the body with a real partner API (for example a Porter or Borzo business API)
    once you have credentials. Keep the same return shape.
    """
    booking = models.Booking(
        user_id=user.id, kind=kind, pickup=pickup, drop=drop, when_at=when,
        status="confirmed", provider="mock", reference=f"MOCK-{uuid.uuid4().hex[:8].upper()}",
    )
    db.add(booking)
    db.commit()
    return {
        "booking_id": booking.id,
        "reference": booking.reference,
        "kind": kind,
        "pickup": pickup,
        "drop": drop,
        "when": when.isoformat(timespec="minutes"),
        "provider": "mock (demo)",
        "links": deep_links(kind, pickup, drop),
    }

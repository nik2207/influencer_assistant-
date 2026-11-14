from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def now_ist() -> datetime:
    """Current India time as a naive datetime (the app stores event times this way)."""
    return datetime.now(IST).replace(tzinfo=None)


def to_ist_naive(dt: datetime) -> datetime:
    if dt.tzinfo:
        return dt.astimezone(IST).replace(tzinfo=None)
    return dt


def parse_dt(value: str) -> datetime:
    return to_ist_naive(datetime.fromisoformat(value.strip().replace("Z", "+00:00")))

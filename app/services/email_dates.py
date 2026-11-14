"""Find shoot, event, meeting and deadline dates inside email text (simple, rule-based)."""
import re
from datetime import date, datetime, timedelta

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
P_DAY_FIRST = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{MON}\b(?:[,\s]+(\d{{4}}))?", re.I)
P_MON_FIRST = re.compile(rf"\b{MON}\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(\d{{4}}))?", re.I)
P_NUMERIC = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4}|\d{2})\b")
P_TIME = re.compile(r"(?:at|@|from|by)?\s*\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b|\b([01]?\d|2[0-3]):([0-5]\d)\b", re.I)

EVENT_WORDS = {"shoot": "Shoot", "event": "Event", "launch": "Launch event", "meeting": "Meeting",
               "call": "Call", "workshop": "Workshop", "visit": "Visit", "session": "Session", "meet": "Meeting"}
DEADLINE_WORDS = {"deadline": "Deadline", "due": "Due", "deliver": "Delivery", "submit": "Submission",
                  "go live": "Go live", "post by": "Post", "publish": "Publish"}


def _mk_date(day: int, month: int, year: int | None, today: date) -> date | None:
    try:
        if year is None:
            d = date(today.year, month, day)
            if d < today - timedelta(days=1):
                d = date(today.year + 1, month, day)
            return d
        if year < 100:
            year += 2000
        d = date(year, month, day)
        return d if d >= today - timedelta(days=1) else None
    except ValueError:
        return None


def _time_near(text: str, end: int) -> tuple[int, int] | None:
    m = P_TIME.search(text[end:end + 45])
    if not m:
        return None
    if m.group(3):
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        if hour > 12 or hour == 0:
            return None
        if m.group(3).lower() == "pm" and hour < 12:
            hour += 12
        if m.group(3).lower() == "am" and hour == 12:
            hour = 0
        return hour, minute
    return int(m.group(4)), int(m.group(5))


def _keyword(ctx: str, ds: int, de: int) -> tuple[str, str] | None:
    """Nearest event/deadline word to the date (ds..de are the date's offsets inside ctx)."""
    best = None
    for table, kind in ((DEADLINE_WORDS, "deadline"), (EVENT_WORDS, "event")):
        for word, label in table.items():
            for m in re.finditer(rf"\b{re.escape(word)}", ctx.lower()):
                dist = min(abs(m.start() - ds), abs(m.start() - de))
                if best is None or dist < best[0]:
                    best = (dist, kind, label)
    return (best[1], best[2]) if best else None


def extract(text: str, brand: str = "", today: date | None = None) -> list[dict]:
    today = today or date.today()
    found: list[tuple[int, date, int]] = []  # (position, date, end position)
    for m in P_DAY_FIRST.finditer(text):
        d = _mk_date(int(m.group(1)), MONTHS[m.group(2)[:3].lower()], int(m.group(3)) if m.group(3) else None, today)
        if d:
            found.append((m.start(), d, m.end()))
    for m in P_MON_FIRST.finditer(text):
        d = _mk_date(int(m.group(2)), MONTHS[m.group(1)[:3].lower()], int(m.group(3)) if m.group(3) else None, today)
        if d:
            found.append((m.start(), d, m.end()))
    for m in P_NUMERIC.finditer(text):
        d = _mk_date(int(m.group(1)), int(m.group(2)), int(m.group(3)), today)  # India: day first
        if d:
            found.append((m.start(), d, m.end()))

    out, seen = [], set()
    for start, d, end in sorted(found):
        lo = max(0, start - 70)
        kw = _keyword(text[lo:end + 70], start - lo, end - lo)
        if not kw:
            continue
        kind, label = kw
        hm = _time_near(text, end) or (10, 0)
        s = datetime(d.year, d.month, d.day, hm[0], hm[1])
        length = timedelta(minutes=30) if kind == "deadline" else (
            timedelta(hours=1) if label in ("Call", "Meeting") else timedelta(hours=2))
        key = (s, kind)
        if key in seen:
            continue
        seen.add(key)
        out.append({"kind": kind, "title": f"{label} - {brand}" if brand else label, "start": s, "end": s + length})
    return out[:3]

"""Google Calendar REST calls (primary calendar only)."""
from datetime import datetime, timezone

import httpx

BASE = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


class CalendarError(Exception):
    pass


class CalendarScopeError(CalendarError):
    pass


def _raise(r: httpx.Response):
    text = r.text[:300]
    low = text.lower()
    if r.status_code == 403 and ("accessnotconfigured" in low or "has not been used" in low or "is disabled" in low):
        raise CalendarError("The Google Calendar API is not enabled in your Google Cloud project. Enable it and retry.")
    if r.status_code in (401, 403) and ("insufficient" in low or "scope" in low):
        raise CalendarScopeError("Google Calendar permission is missing. Click Connect Google Calendar and allow access.")
    raise CalendarError(f"Google Calendar error {r.status_code}: {text}")


def _req(method: str, token: str, url: str, **kw) -> httpx.Response:
    try:
        return httpx.request(method, url, headers={"Authorization": f"Bearer {token}"}, timeout=30, **kw)
    except httpx.HTTPError as exc:
        raise CalendarError(f"Could not reach Google Calendar: {exc}") from exc


def _z(dt: datetime) -> str:
    return dt.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def list_events(token: str, time_min_utc: datetime, time_max_utc: datetime) -> list[dict]:
    params = {"timeMin": _z(time_min_utc), "timeMax": _z(time_max_utc), "singleEvents": "true",
              "showDeleted": "true", "maxResults": 250, "orderBy": "startTime"}
    items: list[dict] = []
    while True:
        r = _req("GET", token, BASE, params=params)
        if r.status_code != 200:
            _raise(r)
        data = r.json()
        items += data.get("items", [])
        if not data.get("nextPageToken") or len(items) >= 1000:
            return items
        params["pageToken"] = data["nextPageToken"]


def insert_event(token: str, body: dict) -> str:
    r = _req("POST", token, BASE, json=body)
    if r.status_code not in (200, 201):
        _raise(r)
    return r.json()["id"]


def delete_event(token: str, google_event_id: str) -> None:
    r = _req("DELETE", token, f"{BASE}/{google_event_id}")
    if r.status_code not in (200, 204, 404, 410):
        _raise(r)

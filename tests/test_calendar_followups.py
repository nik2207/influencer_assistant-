import base64
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from app import models
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import utcnow
from app.services import (calendar_client, calendar_sync, email_ai, email_dates, followups, gmail_client,
                          gmail_sync)

Base.metadata.create_all(bind=engine)
client = TestClient(app)
CAL_SCOPE = "openid https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/calendar.events"


def b64(text):
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def raw_mail(gid, sender, subject, body, bulk=False):
    headers = [{"name": "From", "value": sender}, {"name": "Subject", "value": subject},
               {"name": "Message-ID", "value": f"<{gid}@m.example>"}]
    if bulk:
        headers.append({"name": "List-Unsubscribe", "value": "<mailto:u@x.com>"})
    return {"id": gid, "threadId": "t" + gid, "internalDate": "1790000000000", "snippet": body[:80],
            "payload": {"mimeType": "text/plain", "body": {"data": b64(body)}, "headers": headers}}


def account(email, calendar=True):
    r = client.post("/auth/register", json={"email": email, "password": "password123", "name": "Riya"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    db = SessionLocal()
    user = db.query(models.User).filter_by(email=email).first()
    gmail_sync.store_tokens(db, user, {"access_token": "at", "refresh_token": "rt", "expires_in": 3600})
    gmail_sync.get_account(db, user).email = "riya@gmail.com"
    db.commit()
    if calendar:
        calendar_sync.mark_granted(db, user, CAL_SCOPE)
    uid = user.id
    db.close()
    return h, uid


def fake_google(monkeypatch):
    """In-memory Google Calendar."""
    store = {"events": [], "deleted": [], "n": 0}

    def insert(token, body):
        store["n"] += 1
        gid = f"g{store['n']}"
        store["events"].append({"id": gid, **body})
        return gid
    monkeypatch.setattr(calendar_client, "insert_event", insert)
    monkeypatch.setattr(calendar_client, "delete_event", lambda token, gid: store["deleted"].append(gid))
    monkeypatch.setattr(calendar_client, "list_events", lambda token, a, b: store["events"])
    return store


# ------------------------------------------------------------------ noise filter
def test_noise_filter_blocks_job_alerts_and_notifications():
    job = {"sender_name": "Indeed", "sender_email": "donotreply@jobalert.indeed.com",
           "subject": "Web Developer Intern at X. 12 more jobs", "body": "Salary Rs. 6,000 per month. Apply now"}
    assert email_ai.heuristic_classify(job)["category"] == "other"
    pay = {"sender_name": "Google Payments", "sender_email": "payments-noreply@google.com",
           "subject": "Update your tax info", "body": "Payment profile Rs. 9,000"}
    assert email_ai.heuristic_classify(pay)["category"] == "other"
    real = {"sender_name": "Priya", "sender_email": "priya@mamaearth.in", "subject": "Paid collaboration",
            "body": "Budget Rs. 30,000 for 1 reel. Collab proposal."}
    assert email_ai.heuristic_classify(real)["category"] == "paid_collab"
    bulk_weak = {**real, "subject": "Hello", "body": "our campaign is live", "bulk": True}
    assert email_ai.heuristic_classify(bulk_weak)["category"] == "other"


def test_cleanup_removes_saved_noise():
    h, uid = account("clean@example.com", calendar=False)
    db = SessionLocal()
    from app.security import encrypt_secret
    for i, (addr, subj) in enumerate([("donotreply@jobalert.indeed.com", "Jobs in Mumbai"),
                                      ("priya@nykaa.com", "Paid collaboration")]):
        db.add(models.EmailMessage(user_id=uid, gmail_id=f"c{i}", thread_id=f"tc{i}", sender_email=addr,
                                   sender_name="X", subject=subj, body_enc=encrypt_secret("Apply now" if i == 0 else "Budget Rs. 5000"),
                                   category="paid_collab", brand="B"))
    db.commit()
    db.close()
    assert client.post("/gmail/cleanup", headers=h).json()["removed"] == 1
    assert len(client.get("/gmail/emails", headers=h).json()) == 1


# ------------------------------------------------------------------ date extraction
def test_email_dates():
    today = date(2026, 10, 3)
    out = email_dates.extract("We would like to shoot with you on 15th October at 3 pm in Bandra.", "Nykaa", today)
    assert len(out) == 1 and out[0]["kind"] == "event"
    assert out[0]["start"] == datetime(2026, 10, 15, 15, 0) and out[0]["title"] == "Shoot - Nykaa"
    dl = email_dates.extract("Content deadline: Nov 20. Please deliver 2 reels.", "boAt", today)
    assert dl[0]["kind"] == "deadline" and dl[0]["start"] == datetime(2026, 11, 20, 10, 0)
    numeric = email_dates.extract("Meeting on 05/11/2026 at 11:30", "Zepto", today)
    assert numeric[0]["start"] == datetime(2026, 11, 5, 11, 30)
    assert email_dates.extract("Invoice dated 1 January 2020 is attached", "X", today) == []
    assert email_dates.extract("Great weather on 12 October", "X", today) == []  # no event keyword
    assert email_dates.extract("Shoot on 2 Feb", "X", date(2026, 12, 20))[0]["start"].year == 2027


# ------------------------------------------------------------------ calendar push / pull
def test_push_on_create_and_remote_delete(monkeypatch):
    store = fake_google(monkeypatch)
    h, uid = account("push@example.com")
    r = client.post("/events", json={"title": "Shoot", "start_at": "2031-03-01T10:00:00"}, headers=h).json()
    assert r["google_synced"] is True and store["events"][0]["summary"] == "Shoot"
    assert store["events"][0]["start"]["timeZone"] == "Asia/Kolkata"
    # chat path uses the same code
    out = client.post("/agent/chat", json={"message": "schedule shoot tomorrow at 5 pm"}, headers=h).json()
    assert "Google Calendar" in out["reply"] and len(store["events"]) == 2
    assert client.delete(f"/events/{r['event']['id']}", headers=h).status_code == 204
    assert store["deleted"] == ["g1"]


def test_no_google_when_not_granted(monkeypatch):
    store = fake_google(monkeypatch)
    h, _ = account("nogrant@example.com", calendar=False)
    r = client.post("/events", json={"title": "Local", "start_at": "2031-03-01T10:00:00"}, headers=h).json()
    assert r["google_synced"] is False and store["events"] == []


def test_pull_reconcile(monkeypatch):
    store = fake_google(monkeypatch)
    h, uid = account("pull@example.com")
    client.post("/events", json={"title": "Mine", "start_at": "2031-04-01T09:00:00"}, headers=h)  # pushed as g1
    store["events"] += [
        {"id": "x1", "summary": "Dentist", "start": {"dateTime": "2031-04-02T10:00:00+05:30"},
         "end": {"dateTime": "2031-04-02T11:00:00+05:30"}},
        {"id": "x2", "summary": "Birthday", "start": {"date": "2031-04-03"}, "end": {"date": "2031-04-04"}},
        {"id": "x3", "summary": "UTC call", "start": {"dateTime": "2031-04-05T04:30:00Z"},
         "end": {"dateTime": "2031-04-05T05:30:00Z"}},
    ]
    res = client.post("/calendar/sync", headers=h).json()
    assert res["created"] == 2  # all-day skipped, own push not duplicated
    titles = {e["title"]: e for e in client.get("/events", headers=h).json()}
    assert set(titles) == {"Mine", "Dentist", "UTC call"}
    assert titles["UTC call"]["start_at"].startswith("2031-04-05T10:00")  # converted to India time
    again = client.post("/calendar/sync", headers=h).json()
    assert again["created"] == 0 and again["updated"] == 0

    store["events"][1]["summary"] = "Dentist (moved)"           # edit in Google
    store["events"][1]["start"]["dateTime"] = "2031-04-02T12:00:00+05:30"
    store["events"][1]["end"]["dateTime"] = "2031-04-02T13:00:00+05:30"
    assert client.post("/calendar/sync", headers=h).json()["updated"] == 1
    store["events"][3]["status"] = "cancelled"                  # cancelled in Google
    assert client.post("/calendar/sync", headers=h).json()["removed"] == 1
    assert "UTC call" not in {e["title"] for e in client.get("/events", headers=h).json()}

    dentist = [e for e in client.get("/events", headers=h).json() if e["title"].startswith("Dentist")][0]
    client.delete(f"/events/{dentist['id']}", headers=h)        # deleting a Google-origin event is local only
    assert "x1" not in store["deleted"]
    client.post("/calendar/sync", headers=h)
    assert not [e for e in client.get("/events", headers=h).json() if e["title"].startswith("Dentist")]

    clash = client.post("/events", json={"title": "Clash", "start_at": "2031-04-02T10:30:00"}, headers=h).json()
    assert isinstance(clash["conflicts"], list)


def test_scope_error_is_clear(monkeypatch):
    h, _ = account("scope@example.com")

    def boom(*a, **k):
        raise calendar_client.CalendarScopeError("Google Calendar permission is missing. Reconnect.")
    monkeypatch.setattr(calendar_client, "list_events", boom)
    r = client.post("/calendar/sync", headers=h)
    assert r.status_code == 400 and "permission" in r.json()["detail"].lower()
    st = client.get("/calendar/status", headers=h).json()
    assert st["granted"] is False and "permission" in st["last_error"].lower()


def test_connect_with_calendar_scope():
    h, _ = account("scopeurl@example.com", calendar=False)
    plain = client.get("/gmail/connect", headers=h).json()["url"]
    withcal = client.get("/gmail/connect?calendar=true", headers=h).json()["url"]
    assert "calendar.events" not in plain and "calendar.events" in withcal


# ------------------------------------------------------------------ email -> suggestion -> event
def test_email_suggestion_accept(monkeypatch):
    store = fake_google(monkeypatch)
    h, uid = account("sug@example.com")
    when = date.today() + timedelta(days=20)
    body = f"Paid collaboration! Budget Rs. 20000. Product shoot on {when.day} {when:%B} at 11 am. Deadline {when.day + 0} {when:%B}."
    mails = {"s1": raw_mail("s1", "Sam <sam@wakefit.co>", "Paid collaboration", body)}
    monkeypatch.setattr(gmail_client, "list_message_ids", lambda *a, **k: list(mails))
    monkeypatch.setattr(gmail_client, "get_message", lambda t, g: mails[g])
    client.post("/gmail/sync", headers=h)
    sugs = client.get("/calendar/suggestions", headers=h).json()
    assert sugs and sugs[0]["brand"] == "Wakefit"
    shoot = [s for s in sugs if s["kind"] == "event"][0]
    assert shoot["start_at"].endswith("11:00:00")
    res = client.post(f"/calendar/suggestions/{shoot['id']}/accept", headers=h).json()
    assert res["google_synced"] is True and store["events"][0]["summary"].startswith("Shoot")
    assert client.post(f"/calendar/suggestions/{shoot['id']}/accept", headers=h).status_code == 409
    other = [s for s in client.get("/calendar/suggestions", headers=h).json()]
    if other:
        assert client.post(f"/calendar/suggestions/{other[0]['id']}/dismiss", headers=h).status_code == 204
    intruder, _ = account("sug2@example.com")
    assert client.post(f"/calendar/suggestions/{shoot['id']}/accept", headers=intruder).status_code in (404, 409)


# ------------------------------------------------------------------ follow-ups
def seed_email(uid, gid, brand="Mamaearth", category="paid_collab"):
    db = SessionLocal()
    em = models.EmailMessage(user_id=uid, gmail_id=gid, thread_id="t" + gid, sender_name="Priya Shah",
                             sender_email="priya@mamaearth.in", subject="Collab", brand=brand,
                             category=category, received_at=utcnow() - timedelta(days=6),
                             message_id_header="<x@m>")
    db.add(em)
    db.commit()
    eid = em.id
    db.close()
    return eid


def threads(monkeypatch, mapping):
    monkeypatch.setattr(gmail_client, "thread_meta", lambda token, tid: mapping.get(tid, []))


def test_followup_states_and_actions(monkeypatch):
    h, uid = account("fu@example.com", calendar=False)
    a, b, c = seed_email(uid, "a"), seed_email(uid, "b", "Boat"), seed_email(uid, "c", "Nykaa")
    now = utcnow()
    threads(monkeypatch, {
        "ta": [{"from_email": "priya@mamaearth.in", "date": now - timedelta(days=4)}],                    # brand waiting
        "tb": [{"from_email": "priya@mamaearth.in", "date": now - timedelta(days=6)},
               {"from_email": "riya@gmail.com", "date": now - timedelta(days=4)}],                        # you waiting
        "tc": [{"from_email": "riya@gmail.com", "date": now - timedelta(days=5)},
               {"from_email": "priya@mamaearth.in", "date": now - timedelta(hours=3)}],                   # fresh reply
    })
    res = client.post("/followups/refresh", headers=h).json()
    assert res["checked"] == 3 and res["active"] == 2
    items = {i["email_id"]: i for i in client.get("/followups", headers=h).json()}
    assert items[a]["state"] == "needs_reply" and items[b]["state"] == "awaiting_brand" and c not in items

    fid = items[b]["id"]
    draft = client.post(f"/followups/{fid}/nudge", headers=h).json()["draft_reply"]
    assert draft.startswith("Hi Priya") and "following up" in draft
    client.put(f"/followups/{fid}/nudge", json={"draft_reply": "Edited nudge"}, headers=h)
    sent = {}

    def fake_draft(token, to, subject, body, thread_id, in_reply_to):
        sent.update(to=to, body=body, thread=thread_id)
        return "d1"
    monkeypatch.setattr(gmail_client, "create_draft", fake_draft)
    assert client.post(f"/followups/{fid}/nudge/push", headers=h).json()["gmail_draft_id"] == "d1"
    assert sent == {"to": "priya@mamaearth.in", "body": "Edited nudge", "thread": "tb"}

    assert client.post(f"/followups/{items[a]['id']}/snooze?days=3", headers=h).status_code == 200
    assert [i["email_id"] for i in client.get("/followups", headers=h).json()] == [b]
    assert client.post(f"/followups/{fid}/resolve", headers=h).status_code == 204
    assert client.get("/followups", headers=h).json() == []
    client.post("/followups/refresh", headers=h)  # same thread state: stays dismissed
    assert all(i["email_id"] != b for i in client.get("/followups", headers=h).json())

    # brand finally answers, then goes quiet again -> reopens
    threads(monkeypatch, {"ta": [{"from_email": "riya@gmail.com", "date": now - timedelta(days=5)}],
                          "tb": [{"from_email": "priya@mamaearth.in", "date": now - timedelta(days=3)}],
                          "tc": [{"from_email": "riya@gmail.com", "date": now - timedelta(days=1)}]})
    client.post("/followups/refresh", headers=h)
    states = {i["email_id"]: i["state"] for i in client.get("/followups", headers=h).json()}
    assert states == {b: "needs_reply", a: "awaiting_brand"}  # dismissed thread reopened, snooze reset on state change


def test_closed_deal_and_isolation(monkeypatch):
    h, uid = account("fu2@example.com", calendar=False)
    eid = seed_email(uid, "z")
    db = SessionLocal()
    deal = models.Deal(user_id=uid, brand="Mamaearth", status="done")
    db.add(deal)
    db.commit()
    db.get(models.EmailMessage, eid).deal_id = deal.id
    db.commit()
    db.close()
    threads(monkeypatch, {"tz": [{"from_email": "priya@mamaearth.in", "date": utcnow() - timedelta(days=9)}]})
    client.post("/followups/refresh", headers=h)
    assert client.get("/followups", headers=h).json() == []
    h2, uid2 = account("fu3@example.com", calendar=False)
    eid2 = seed_email(uid2, "y")
    threads(monkeypatch, {"ty": [{"from_email": "priya@mamaearth.in", "date": utcnow() - timedelta(days=9)}]})
    client.post("/followups/refresh", headers=h2)
    fid = client.get("/followups", headers=h2).json()[0]["id"]
    assert client.post(f"/followups/{fid}/snooze", headers=h).status_code == 404


def test_chat_followups_and_marathi_keywords(monkeypatch):
    h, uid = account("chatfu@example.com", calendar=False)
    seed_email(uid, "q")
    threads(monkeypatch, {"tq": [{"from_email": "priya@mamaearth.in", "date": utcnow() - timedelta(days=5)}]})
    out = client.post("/agent/chat", json={"message": "any follow-ups pending?"}, headers=h).json()
    assert "waiting for your reply" in out["reply"]
    out = client.post("/agent/chat", json={"message": "मला boAt ब्रँडसोबत बार्टर डील करायची आहे"}, headers=h).json()
    assert "boAt" in out["reply"] and "barter" in out["reply"]


def test_jobs_send_followup_reminders(monkeypatch):
    from app import jobs
    h, uid = account("job@example.com", calendar=False)
    seed_email(uid, "j")
    db = SessionLocal()
    db.get(models.User, uid).telegram_chat_id = "999"
    db.commit()
    db.close()
    threads(monkeypatch, {"tj": [{"from_email": "priya@mamaearth.in", "date": utcnow() - timedelta(days=5)}]})
    messages = []
    monkeypatch.setattr(jobs, "send_telegram", lambda chat, text: messages.append((chat, text)) or True)
    assert jobs.followup_cycle()["reminded"] >= 1
    assert any("waiting for your reply" in t for _, t in messages)
    before = len(messages)
    jobs.followup_cycle()
    assert len(messages) == before  # not repeated within 2 days

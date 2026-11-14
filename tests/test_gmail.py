import base64
from urllib.parse import parse_qs, urlparse  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app import models  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.security import make_token  # noqa: E402
from app.services import email_ai, gmail_client, gmail_sync  # noqa: E402

Base.metadata.create_all(bind=engine)
client = TestClient(app)


def b64(text):
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def raw_mail(gid, sender, subject, body, html=False):
    part = {"mimeType": "text/html" if html else "text/plain", "body": {"data": b64(body)}}
    return {"id": gid, "threadId": "t" + gid, "internalDate": "1790000000000", "snippet": body[:80],
            "payload": {"mimeType": "multipart/alternative", "parts": [part], "headers": [
                {"name": "From", "value": sender}, {"name": "Subject", "value": subject},
                {"name": "Message-ID", "value": f"<{gid}@mail.example>"}]}}


def signup(email):
    r = client.post("/auth/register", json={"email": email, "password": "password123", "name": "Riya Patil"})
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def connect_account(email):
    h = signup(email)
    db = SessionLocal()
    user = db.query(models.User).filter_by(email=email).first()
    gmail_sync.store_tokens(db, user, {"access_token": "at", "refresh_token": "rt", "expires_in": 3600})
    acct = gmail_sync.get_account(db, user)
    acct.email = "riya@gmail.com"
    db.commit()
    db.close()
    return h


def test_classifier_rules():
    base = dict(sender_name="Priya", sender_email="priya@mamaearth.in", body="")
    paid = email_ai.heuristic_classify({**base, "subject": "Paid collaboration", "body":
        "We have a budget of Rs. 40,000 for 2 reels and 3 stories."})
    assert paid["category"] == "paid_collab" and paid["amount_inr"] == 40000
    assert paid["brand"] == "Mamaearth" and "2 reels" in paid["deliverables"]
    barter = email_ai.heuristic_classify({**base, "subject": "Gifting", "body": "We'd love to send you our product hamper"})
    assert barter["category"] == "barter_collab"
    spam = email_ai.heuristic_classify({**base, "subject": "Flash sale", "body": "50% off. Unsubscribe here."})
    assert spam["category"] == "other"
    assert email_ai._amount("fee is 1.5 lakh") == 0  # needs a currency marker
    assert email_ai._amount("budget ₹2k") == 2000
    assert email_ai._amount("fee is ₹, only commas") == 0.0
    assert email_ai._amount("inr ") == 0.0


def test_parse_message_plain_and_html():
    plain = gmail_client.parse_message(raw_mail("a1", "Priya <priya@nykaa.com>", "Hi", "Hello there"))
    assert plain["sender_email"] == "priya@nykaa.com" and plain["body"] == "Hello there"
    html = gmail_client.parse_message(raw_mail("a2", "x@y.com", "Hi", "<p>Hello <b>world</b></p>", html=True))
    assert "Hello" in html["body"] and "<" not in html["body"]


def test_connect_and_callback_state():
    h = signup("conn@example.com")
    url = client.get("/gmail/connect", headers=h).json()["url"]
    q = parse_qs(urlparse(url).query)
    assert q["client_id"][0].startswith("cid") and q["access_type"] == ["offline"]
    assert "gmail.readonly" in q["scope"][0] and "gmail.send" not in q["scope"][0]
    bad = client.get("/gmail/callback", params={"code": "x", "state": "garbage"}, follow_redirects=False)
    assert bad.status_code == 401
    wrong_kind = make_token(1, "access", 5)
    assert client.get("/gmail/callback", params={"code": "x", "state": wrong_kind}, follow_redirects=False).status_code == 401
    denied = client.get("/gmail/callback", params={"error": "access_denied"}, follow_redirects=False)
    assert denied.headers["location"].endswith("gmail=denied")


def test_sync_stores_only_relevant_and_encrypts(monkeypatch):
    h = connect_account("sync@example.com")
    mails = {
        "m1": raw_mail("m1", "Priya <priya@mamaearth.in>", "Paid collaboration", "Budget Rs. 30000 for 1 reel"),
        "m2": raw_mail("m2", "Deals <news@shop.com>", "Flash sale", "50% off. Unsubscribe anytime."),
        "m3": raw_mail("m3", "Riya <riya@gmail.com>", "Note to self", "collaboration budget"),
    }
    monkeypatch.setattr(gmail_client, "list_message_ids", lambda *a, **k: list(mails))
    monkeypatch.setattr(gmail_client, "get_message", lambda token, gid: mails[gid])
    res = client.post("/gmail/sync", headers=h).json()
    assert res["new"] == 1 and res["skipped"] == 1
    listed = client.get("/gmail/emails", headers=h).json()
    assert len(listed) == 1 and listed[0]["brand"] == "Mamaearth" and listed[0]["amount_inr"] == 30000
    db = SessionLocal()
    row = db.query(models.EmailMessage).first()
    assert "Budget" not in row.body_enc  # stored encrypted
    db.close()
    assert "Budget" in client.get(f"/gmail/emails/{listed[0]['id']}", headers=h).json()["body"]
    again = client.post("/gmail/sync", headers=h).json()
    assert again["new"] == 0  # no duplicates


def test_draft_push_deal_dismiss_isolation(monkeypatch):
    h = connect_account("flow@example.com")
    mails = {"f1": raw_mail("f1", "Sam <sam@wakefit.co>", "Barter offer",
                            "We'd like to send you a free product in exchange for 2 reels.")}
    monkeypatch.setattr(gmail_client, "list_message_ids", lambda *a, **k: list(mails))
    monkeypatch.setattr(gmail_client, "get_message", lambda token, gid: mails[gid])
    client.post("/gmail/sync", headers=h)
    eid = client.get("/gmail/emails", headers=h).json()[0]["id"]

    draft = client.post(f"/gmail/emails/{eid}/draft", headers=h).json()["draft_reply"]
    assert draft.startswith("Hi Sam") and "barter" in draft.lower()
    client.put(f"/gmail/emails/{eid}/draft", json={"draft_reply": "Edited reply"}, headers=h)

    sent = {}
    def fake_draft(token, to, subject, body, thread_id, in_reply_to):
        sent.update(to=to, subject=subject, body=body, thread=thread_id)
        return "draft-123"
    monkeypatch.setattr(gmail_client, "create_draft", fake_draft)
    assert client.post(f"/gmail/emails/{eid}/push-draft", headers=h).json()["gmail_draft_id"] == "draft-123"
    assert sent["to"] == "sam@wakefit.co" and sent["body"] == "Edited reply" and sent["thread"] == "tf1"

    deal = client.post(f"/gmail/emails/{eid}/to-deal", headers=h, json={"confirm": True}).json()
    assert deal["brand"] == "Wakefit"
    assert client.get("/deals", headers=h).json()[0]["kind"] == "barter"
    assert client.post(f"/gmail/emails/{eid}/to-deal", headers=h, json={"confirm": True}).json()["deal_id"] == deal["deal_id"]

    other = signup("intruder@example.com")
    assert client.get(f"/gmail/emails/{eid}", headers=other).status_code == 404
    assert client.post(f"/gmail/emails/{eid}/push-draft", headers=other).status_code == 404

    client.post(f"/gmail/emails/{eid}/dismiss", headers=h)
    assert client.get("/gmail/emails", headers=h).json() == []


def test_chat_check_inbox_and_disconnect(monkeypatch):
    h = connect_account("chat@example.com")
    mails = {"c1": raw_mail("c1", "Ann <ann@boat.com>", "Collab", "Paid collaboration, budget Rs. 20000")}
    monkeypatch.setattr(gmail_client, "list_message_ids", lambda *a, **k: list(mails))
    monkeypatch.setattr(gmail_client, "get_message", lambda token, gid: mails[gid])
    out = client.post("/agent/chat", json={"message": "check my inbox for brand emails"}, headers=h).json()
    assert "Boat" in out["reply"] and "paid collab" in out["reply"]
    eid = client.get("/gmail/emails", headers=h).json()[0]["id"]
    out = client.post("/agent/chat", json={"message": f"draft a reply to email {eid}"}, headers=h).json()
    assert "not sent" in out["reply"]
    revoked = []
    monkeypatch.setattr(gmail_client, "revoke", lambda t: revoked.append(t))
    assert client.delete("/gmail/disconnect", headers=h).status_code == 204
    assert revoked == ["rt"]
    assert client.get("/gmail/status", headers=h).json()["connected"] is False
    assert client.get("/gmail/emails", headers=h).json() == []


def test_not_connected_errors():
    h = signup("none@example.com")
    assert client.post("/gmail/sync", headers=h).status_code == 400
    out = client.post("/agent/chat", json={"message": "check my email"}, headers=h).json()
    assert "not connected" in out["reply"].lower()

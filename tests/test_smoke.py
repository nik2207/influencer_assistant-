from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

Base.metadata.create_all(bind=engine)
client = TestClient(app)


def auth_headers(email="a@example.com"):
    r = client.post("/auth/register", json={"email": email, "password": "password123", "name": "Test Creator"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def chat(h, msg):
    r = client.post("/agent/chat", json={"message": msg}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_auth_flow():
    h = auth_headers("auth@example.com")
    assert client.get("/auth/me", headers=h).json()["email"] == "auth@example.com"
    assert client.get("/deals").status_code == 401
    bad = client.post("/auth/login", data={"username": "auth@example.com", "password": "wrong-pass"})
    assert bad.status_code == 401
    ok = client.post("/auth/login", data={"username": "auth@example.com", "password": "password123"})
    assert ok.status_code == 200
    ref = client.post("/auth/refresh", json={"refresh_token": ok.json()["refresh_token"]})
    assert ref.status_code == 200


def test_deals_via_chat_and_isolation():
    h = auth_headers("deals@example.com")
    out = chat(h, "Add a barter deal with Mamaearth")
    assert "Mamaearth" in out["reply"]
    deals = client.get("/deals", headers=h).json()
    assert len(deals) == 1 and deals[0]["kind"] == "barter"
    chat(h, f"Mark deal {deals[0]['id']} as content due")
    assert client.get("/deals", headers=h).json()[0]["status"] == "content_due"
    other = auth_headers("other@example.com")
    assert client.get("/deals", headers=other).json() == []
    assert client.patch(f"/deals/{deals[0]['id']}", json={"notes": "x"}, headers=other).status_code == 404


def test_calendar_conflict():
    h = auth_headers("cal@example.com")
    body = {"title": "Shoot", "start_at": "2031-01-10T10:00:00", "end_at": "2031-01-10T12:00:00"}
    assert client.post("/events", json=body, headers=h).json()["conflicts"] == []
    clash = client.post("/events", json={**body, "title": "Meeting", "start_at": "2031-01-10T11:00:00",
                                         "end_at": "2031-01-10T12:30:00"}, headers=h).json()
    assert len(clash["conflicts"]) == 1


def test_ride_needs_approval():
    h = auth_headers("ride@example.com")
    out = chat(h, "Book a cab from Panvel to Bandra tomorrow at 4 pm")
    assert len(out["pending"]) == 1
    action = out["pending"][0]
    assert "Panvel" in action["summary"]
    res = client.post(f"/agent/approve/{action['id']}", headers=h).json()
    assert res["status"] == "executed" and res["result"]["reference"].startswith("MOCK-")
    again = client.post(f"/agent/approve/{action['id']}", headers=h).json()
    assert "error" in again


def test_invoice_and_pitch():
    h = auth_headers("inv@example.com")
    client.patch("/auth/me", json={"name": "Riya", "niche": "beauty", "followers": 50000}, headers=h)
    client.post("/deals", json={"brand": "Nykaa", "value_inr": 20000}, headers=h)
    deal_id = client.get("/deals", headers=h).json()[0]["id"]
    inv = client.post(f"/invoices/for-deal/{deal_id}", headers=h).json()["invoice"]
    assert inv["number"].startswith("INV-")
    pdf = client.get(f"/invoices/{inv['id']}/pdf", headers=h)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert "Nykaa" in client.get("/outreach/pitch", params={"brand": "Nykaa"}, headers=h).json()["pitch"]
    assert client.get("/outreach/brands", headers=h).json()[0]["name"]

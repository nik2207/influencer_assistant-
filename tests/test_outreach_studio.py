from unittest.mock import patch

from tests.test_smoke import auth_headers, client


def test_studio_generates_three_distinct_variants():
    h = auth_headers("out1@example.com")
    client.patch("/auth/me", json={"name": "Riya", "niche": "beauty lifestyle"}, headers=h)
    r = client.post("/outreach/studio/generate", json={"brand": "Nykaa"}, headers=h)
    assert r.status_code == 200
    data = r.json()
    assert len(data["suggestions"]) == 3
    bodies = [s["body"] for s in data["suggestions"]]
    assert len(set(bodies)) == 3
    assert all(s["subject"] and s["body"] for s in data["suggestions"])


def test_save_draft_and_ownership():
    h1 = auth_headers("out2@example.com")
    h2 = auth_headers("out3@example.com")
    created = client.post("/outreach/drafts", headers=h1, json={
        "brand": "boAt", "variant": "friendly", "subject": "Hi", "body": "Test body",
    }).json()
    assert created["status"] == "draft"
    listed = client.get("/outreach/drafts", headers=h1).json()
    assert not any(x["id"] == created["id"] for x in client.get("/outreach/drafts", headers=h2).json())
    assert any(x["id"] == created["id"] for x in listed)
    assert client.delete(f"/outreach/drafts/{created['id']}", headers=h2).status_code == 404
    assert client.delete(f"/outreach/drafts/{created['id']}", headers=h1).status_code == 200


@patch("app.services.gmail_sync.push_outreach_draft", return_value="gmail-draft-123")
def test_gmail_save_mocked(mock_push):
    h = auth_headers("out4@example.com")
    d = client.post("/outreach/drafts", headers=h, json={
        "brand": "Noise", "variant": "professional", "subject": "Hello", "body": "Body text",
        "recipient_email": "partner@example.com",
    }).json()
    r = client.post(f"/outreach/drafts/{d['id']}/gmail", headers=h, json={
        "to": "partner@example.com", "subject": "Hello", "body": "Body text",
    })
    assert r.status_code == 200
    assert r.json()["gmail_draft_id"] == "gmail-draft-123"
    assert "Gmail" in r.json()["message"]
    assert "sent" in r.json()["message"].lower() or "review" in r.json()["message"].lower()
    mock_push.assert_called_once()


def test_invalid_recipient_rejected():
    h = auth_headers("out5@example.com")
    r = client.post("/outreach/drafts", headers=h, json={
        "brand": "Zepto", "variant": "campaign", "subject": "S", "body": "B", "recipient_email": "not-an-email",
    })
    assert r.status_code == 400


def test_legacy_pitch_endpoint():
    h = auth_headers("out6@example.com")
    p = client.get("/outreach/pitch", params={"brand": "Nykaa"}, headers=h).json()["pitch"]
    assert "Collaboration idea" in p and "Nykaa" in p

from fastapi.testclient import TestClient

from app import models
from app.db import Base, SessionLocal, engine
from app.main import app
from app.services import agent, llm, outreach, profile

Base.metadata.create_all(bind=engine)
client = TestClient(app)


def signup(email, name="Riya Patil"):
    r = client.post("/auth/register", json={"email": email, "password": "password123", "name": name})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def uid(email):
    db = SessionLocal()
    u = db.query(models.User).filter_by(email=email).first().id
    db.close()
    return u


# ------------------------------------------------------------------ access control
def test_requires_login():
    for method, path in [("get", "/profile"), ("patch", "/profile"), ("put", "/profile/platforms/youtube"),
                         ("delete", "/profile/platforms/youtube")]:
        r = getattr(client, method)(path, **({"json": {}} if method in ("patch", "put") else {}))
        assert r.status_code == 401, (method, path)


def test_defaults_and_options():
    h = signup("p1@example.com")
    p = client.get("/profile", headers=h).json()
    assert p["creator"]["creator_type"] == "influencer" and p["creator"]["currency"] == "INR"
    assert p["creator"]["languages"] == ["en"] and p["platforms"] == []
    assert p["personalization"]["labels"]["deals"] == "Deals"
    ids = [t["id"] for t in p["options"]["creator_types"]]
    assert ids == ["influencer", "youtuber", "gamer", "streamer", "podcaster", "blogger", "other"]
    assert {"instagram", "youtube", "twitch"} <= {x["id"] for x in p["options"]["platforms"]}
    assert p["completeness"]["percent"] < 100 and "handle" in p["completeness"]["missing"]


# ------------------------------------------------------------------ update + persistence
def test_update_and_persist():
    h = signup("p2@example.com")
    body = {"name": "Arjun Rao", "handle": "arjungames", "niche": "gaming", "city": "Pune", "language": "hi",
            "creator_type": "gamer", "bio": "Mobile gamer and tournament caster.", "currency": "USD",
            "languages": ["en", "hi"], "contact_email": "Arjun@Example.com", "phone": "+91 98765 43210",
            "home_location": "Baner, Pune", "payment_method": "bank", "payment_terms_days": 30,
            "invoice_notes": "Please pay by bank transfer.", "gstin": "27ABCDE1234F1Z5", "upi_vpa": "arjun@okbank"}
    r = client.patch("/profile", json=body, headers=h)
    assert r.status_code == 200, r.text
    again = TestClient(app).get("/profile", headers=h).json()  # a fresh client = a reload
    assert again["user"]["name"] == "Arjun Rao" and again["user"]["handle"] == "@arjungames"
    c = again["creator"]
    assert c["creator_type"] == "gamer" and c["currency"] == "USD" and c["contact_email"] == "arjun@example.com"
    assert c["languages"] == ["en", "hi"] and c["payment_terms_days"] == 30 and c["gstin"] == "27ABCDE1234F1Z5"
    assert client.get("/auth/me", headers=h).json()["language"] == "hi"
    assert again["personalization"]["labels"]["deals"] == "Sponsorships"
    assert again["completeness"]["percent"] >= 80


def test_partial_update_keeps_other_fields():
    h = signup("p3@example.com")
    client.patch("/profile", json={"niche": "tech", "creator_type": "youtuber"}, headers=h)
    client.patch("/profile", json={"city": "Mumbai"}, headers=h)
    p = client.get("/profile", headers=h).json()
    assert p["user"]["niche"] == "tech" and p["creator"]["creator_type"] == "youtuber" and p["user"]["city"] == "Mumbai"


def test_reply_language_stays_in_preferred_languages():
    h = signup("p4@example.com")
    client.patch("/auth/me", json={"language": "mr"}, headers=h)      # the older endpoint still works
    assert "mr" in client.get("/profile", headers=h).json()["creator"]["languages"]
    client.patch("/profile", json={"languages": ["en", "hi"]}, headers=h)
    assert client.get("/auth/me", headers=h).json()["language"] == "en"


# ------------------------------------------------------------------ validation
def test_validation_failures():
    h = signup("p5@example.com")
    bad = [
        {"creator_type": "wizard"}, {"name": "   "}, {"name": "x" * 81}, {"handle": "bad handle!"},
        {"language": "fr"}, {"languages": []}, {"languages": ["en", "xx"]}, {"currency": "XYZ"},
        {"payment_method": "cash"}, {"payment_terms_days": 500}, {"phone": "call me"},
        {"contact_email": "not-an-email"}, {"gstin": "123"}, {"upi_vpa": "nobank"}, {"bio": "b" * 401},
        {"invoice_notes": "n" * 401}, {"niche": "n" * 121}, {"home_location": "h" * 201},
    ]
    for payload in bad:
        r = client.patch("/profile", json=payload, headers=h)
        assert r.status_code == 422, payload
        assert isinstance(r.json()["detail"], list)
    p = client.get("/profile", headers=h).json()
    assert p["creator"]["creator_type"] == "influencer"  # nothing was saved by the failed calls


def test_control_characters_are_removed():
    h = signup("p6@example.com")
    client.patch("/profile", json={"niche": "tech\x00\x07  reviews", "bio": "line1\nline2\x1b"}, headers=h)
    p = client.get("/profile", headers=h).json()
    assert p["user"]["niche"] == "tech reviews" and p["creator"]["bio"] == "line1\nline2"


# ------------------------------------------------------------------ platforms
def test_platforms_crud_and_follower_total():
    h = signup("p7@example.com")
    r = client.put("/profile/platforms/youtube", json={"handle": "@riyatech", "followers": 120000}, headers=h)
    assert r.status_code == 200
    yt = r.json()["platforms"][0]
    assert yt["handle"] == "riyatech" and yt["url"] == "https://www.youtube.com/@riyatech"
    client.put("/profile/platforms/instagram", json={"handle": "riya", "url": "https://www.instagram.com/riya/",
                                                      "followers": 30000}, headers=h)
    p = client.get("/profile", headers=h).json()
    assert p["total_followers"] == 150000 and [x["platform"] for x in p["platforms"]] == ["youtube", "instagram"]
    assert client.get("/auth/me", headers=h).json()["followers"] == 150000
    client.put("/profile/platforms/youtube", json={"handle": "riyatech", "followers": 100}, headers=h)  # update, not duplicate
    assert len(client.get("/profile", headers=h).json()["platforms"]) == 2
    r = client.delete("/profile/platforms/instagram", headers=h)
    assert r.status_code == 200 and r.json()["total_followers"] == 100
    assert client.delete("/profile/platforms/instagram", headers=h).status_code == 404


def test_platform_validation():
    h = signup("p8@example.com")
    ok = {"handle": "riya", "followers": 10}
    assert client.put("/profile/platforms/myspace", json=ok, headers=h).status_code == 404
    assert client.put("/profile/platforms/youtube", json={"handle": "", "followers": 1}, headers=h).status_code == 422
    assert client.put("/profile/platforms/youtube", json={"handle": "a b", "followers": 1}, headers=h).status_code == 422
    assert client.put("/profile/platforms/youtube", json={**ok, "followers": -5}, headers=h).status_code == 422
    assert client.put("/profile/platforms/youtube", json={**ok, "followers": 3_000_000_000}, headers=h).status_code == 422
    for url in ["javascript:alert(1)", "http://evil.example.com/riya", "https://www.instagram.com/riya",
                "https://user:pw@youtube.com/@riya", "https://youtube.com/a b", "ftp://youtube.com/x"]:
        assert client.put("/profile/platforms/youtube", json={**ok, "url": url}, headers=h).status_code == 422, url
    assert client.put("/profile/platforms/youtube", json={**ok, "url": "https://m.youtube.com/@riya"}, headers=h).status_code == 200
    assert client.get("/profile", headers=h).json()["platforms"][0]["url"] == "https://m.youtube.com/@riya"


# ------------------------------------------------------------------ ownership
def test_profiles_are_private_to_each_user():
    a, b = signup("profile-owner@example.com", "Owner"), signup("profile-other@example.com", "Other")
    client.patch("/profile", json={"niche": "secret niche", "phone": "+91 90000 11111", "creator_type": "podcaster"}, headers=a)
    client.put("/profile/platforms/spotify", json={"handle": "ownerpod", "followers": 500}, headers=a)
    pb = client.get("/profile", headers=b).json()
    assert pb["user"]["niche"] == "" and pb["creator"]["phone"] == "" and pb["platforms"] == []
    assert client.delete("/profile/platforms/spotify", headers=b).status_code == 404
    assert len(client.get("/profile", headers=a).json()["platforms"]) == 1
    # a user id in the request body is ignored: there is no way to name another user
    client.patch("/profile", json={"user_id": uid("profile-owner@example.com"), "niche": "hacked"}, headers=b)
    assert client.get("/profile", headers=a).json()["user"]["niche"] == "secret niche"


# ------------------------------------------------------------------ personalization
def test_creator_type_personalization():
    h = signup("p9@example.com")
    expect = {"youtuber": ("Sponsorships", "videos due"), "gamer": ("Sponsorships", "streams due"),
              "streamer": ("Sponsorships", "streams due"), "podcaster": ("Sponsorships", "episodes due"),
              "blogger": ("Collaborations", "posts due"), "other": ("Deals", "deliverables due"),
              "influencer": ("Deals", "deliverables due")}
    for t, (deals, due) in expect.items():
        client.patch("/profile", json={"creator_type": t}, headers=h)
        pz = client.get("/profile", headers=h).json()["personalization"]
        assert pz["creator_type"] == t and pz["labels"]["deals"] == deals and pz["labels"]["due_label"] == due
        assert pz["chips"] and pz["chat_suggestions"]


# ------------------------------------------------------------------ AI context and privacy
def test_ai_context_leaves_out_private_data(monkeypatch):
    h = signup("p10@example.com")
    client.patch("/profile", json={
        "name": "Meera Joshi", "creator_type": "youtuber", "niche": "travel", "city": "Nashik",
        "bio": "I film slow travel stories.", "phone": "+91 99887 76655", "home_location": "12 Rose Villa, Gangapur Road",
        "contact_email": "private.meera@example.com", "gstin": "27ABCDE1234F1Z5", "upi_vpa": "meera@okbank"}, headers=h)
    client.put("/profile/platforms/youtube", json={"handle": "meeratravels", "followers": 80000}, headers=h)
    db = SessionLocal()
    user = db.query(models.User).filter_by(email="p10@example.com").first()
    ctx = profile.ai_context(db, user)
    assert "YouTuber" in ctx and "travel" in ctx and "YouTube 80,000" in ctx and "slow travel" in ctx
    for secret in ["99887", "Rose Villa", "private.meera", "27ABCDE", "okbank"]:
        assert secret not in ctx, secret

    seen = {}
    real = llm.chat
    def spy(messages, tools=None):
        seen["system"] = messages[0]["content"]
        return real(messages, tools)
    monkeypatch.setattr(llm, "chat", spy)
    out = agent.handle_message(db, user, "list deals")
    assert out["tools_used"] == ["list_deals"]
    assert "YouTuber" in seen["system"] and "sponsorships" in seen["system"]
    for secret in ["99887", "Rose Villa", "private.meera", "27ABCDE", "okbank"]:
        assert secret not in seen["system"], secret
    db.close()


def test_audit_log_records_field_names_not_values():
    h = signup("p11@example.com")
    client.patch("/profile", json={"phone": "+91 91111 22222", "bio": "very private words"}, headers=h)
    db = SessionLocal()
    rows = db.query(models.AuditLog).filter_by(action="profile_updated", user_id=uid("p11@example.com")).all()
    db.close()
    assert rows and all("91111" not in r.detail and "private" not in r.detail for r in rows)
    assert "phone" in rows[-1].detail


def test_pitch_uses_creator_type_and_channels():
    h = signup("p12@example.com")
    default = client.get("/outreach/pitch", params={"brand": "Nykaa"}, headers=h).json()["pitch"]
    assert "Nykaa" in default and "reels" in default.lower()
    client.patch("/profile", json={"name": "Meera Joshi", "creator_type": "youtuber", "niche": "travel",
                                   "bio": "I film slow travel stories."}, headers=h)
    client.put("/profile/platforms/youtube", json={"handle": "meeratravels", "followers": 80000}, headers=h)
    pitch = client.get("/outreach/pitch", params={"brand": "boAt"}, headers=h).json()["pitch"]
    assert "youtuber" in pitch.lower() and "travel" in pitch.lower() and "80,000 on YouTube" in pitch
    assert "slow travel stories" in pitch or "dedicated video" in pitch.lower()
    chat = client.post("/agent/chat", json={"message": "draft a pitch to Lenskart"}, headers=h).json()["reply"]
    assert "youtuber" in chat.lower() and "Lenskart" in chat


def test_invoice_uses_saved_defaults():
    h = signup("p13@example.com")
    client.patch("/profile", json={"payment_terms_days": 30, "invoice_notes": "Pay by NEFT."}, headers=h)
    client.post("/deals", json={"brand": "Nykaa", "value_inr": 20000}, headers=h)
    deal = client.get("/deals", headers=h).json()[0]["id"]
    inv = client.post(f"/invoices/for-deal/{deal}", headers=h).json()["invoice"]
    pdf = client.get(f"/invoices/{inv['id']}/pdf", headers=h)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


def test_older_profile_endpoint_still_works():
    h = signup("p14@example.com")
    r = client.patch("/auth/me", json={"name": "New Name", "niche": "food", "followers": 1234}, headers=h)
    assert r.status_code == 200 and client.get("/profile", headers=h).json()["user"]["niche"] == "food"

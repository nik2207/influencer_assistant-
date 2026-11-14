import io

from tests.test_smoke import auth_headers, client


def test_auth_required():
    assert client.get("/media-kit").status_code == 401


def test_preview_and_rates():
    h = auth_headers("mk1@example.com")
    client.patch("/auth/me", json={"name": "Riya", "niche": "beauty"}, headers=h)
    client.put("/profile/platforms/instagram", headers=h, json={"handle": "riya", "followers": 5000, "url": ""})
    r = client.get("/media-kit", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["creator"]["niche"] == "beauty"
    assert body["platforms"][0]["followers"] == 5000
    assert body["platforms"][0]["followers_source"] == "profile_manual"
    rates = client.put("/media-kit/rates", headers=h, json={"lines": [
        {"deliverable": "reel", "title": "IG Reel", "price": 25000, "currency": "INR", "notes": ""},
        {"deliverable": "story", "title": "Stories", "price": 8000, "currency": "INR", "notes": ""},
    ]})
    assert rates.status_code == 200
    assert len(rates.json()["rates"]) == 2


def test_portfolio_deal_isolation():
    h1 = auth_headers("mk2a@example.com")
    h2 = auth_headers("mk2b@example.com")
    d2 = client.post("/deals", headers=h2, json={"brand": "Secret", "kind": "paid"}).json()["id"]
    bad = client.put("/media-kit/portfolio", headers=h1, json={"items": [{"deal_id": d2, "summary": "x"}]})
    assert bad.status_code == 400


def test_publish_revoke_public_snapshot():
    h = auth_headers("mk3@example.com")
    client.put("/media-kit", headers=h, json={"show_phone": False, "show_metrics": False})
    nop = client.post("/media-kit/share/publish", headers=h, json={"confirm_public": False})
    assert nop.status_code == 400
    pub = client.post("/media-kit/share/publish", headers=h, json={"confirm_public": True})
    assert pub.status_code == 200
    token = pub.json()["public_url"].split("/")[-1]
    snap = client.get(f"/media-kit/public/{token}")
    assert snap.status_code == 200
    assert "phone" not in snap.json().get("contact", {}) or not snap.json()["contact"].get("phone")
    for plat in snap.json().get("platforms", []):
        assert not plat.get("metrics")
    client.post("/media-kit/share/revoke", headers=h)
    assert client.get(f"/media-kit/public/{token}").status_code == 404


def test_avatar_validation():
    h = auth_headers("mk4@example.com")
    bad = client.post("/media-kit/avatar", headers=h, files={"file": ("x.txt", io.BytesIO(b"not image"), "text/plain")})
    assert bad.status_code == 400
    jpeg = bytes.fromhex("ffd8ffe000104a46494600010100004800600000ffd9")
    ok = client.post("/media-kit/avatar", headers=h, files={"file": ("a.jpg", io.BytesIO(jpeg), "image/jpeg")})
    assert ok.status_code == 200
    assert client.get("/media-kit/avatar", headers=h).status_code == 200


def test_pdf_export():
    h = auth_headers("mk5@example.com")
    pdf = client.get("/media-kit/export/pdf", headers=h)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"

from datetime import date, timedelta

from tests.test_smoke import auth_headers, client


def test_crm_requires_auth():
    assert client.get("/brands-crm").status_code == 401
    assert client.post("/brands-crm", json={"display_name": "X"}).status_code == 401


def test_create_brand_and_ownership():
    h1 = auth_headers("crm1@example.com")
    h2 = auth_headers("crm2@example.com")
    r = client.post("/brands-crm", headers=h1, json={"display_name": "Nykaa"})
    assert r.status_code == 201
    bid = r.json()["id"]
    assert client.get(f"/brands-crm/{bid}", headers=h1).status_code == 200
    assert client.get(f"/brands-crm/{bid}", headers=h2).status_code == 404


def test_no_duplicate_brand_keys():
    h = auth_headers("crm3@example.com")
    client.post("/brands-crm", headers=h, json={"display_name": "boAt"})
    again = client.post("/brands-crm", headers=h, json={"display_name": "  boat  "})
    assert again.status_code == 201
    assert again.json()["id"] == client.get("/brands-crm", headers=h).json()[0]["id"]


def test_sync_deals_without_duplicating():
    h = auth_headers("crm4@example.com")
    client.post("/deals", headers=h, json={"brand": "Mamaearth", "kind": "paid", "value_inr": 5000})
    client.post("/deals", headers=h, json={"brand": "mamaearth", "kind": "barter", "value_inr": 0})
    synced = client.post("/brands-crm/sync", headers=h)
    assert synced.status_code == 200
    brands = client.get("/brands-crm", headers=h).json()
    keys = {b["display_name"].lower() for b in brands if "mamaearth" in b["display_name"].lower()}
    assert len([b for b in brands if b["display_name"].lower().replace(" ", "") == "mamaearth"]) == 1


def test_notes_followups_and_timeline():
    h = auth_headers("crm5@example.com")
    bid = client.post("/brands-crm", headers=h, json={"display_name": "Zepto"}).json()["id"]
    n = client.post(f"/brands-crm/{bid}/notes", headers=h, json={"body": "Rate discussed", "kind": "negotiation"})
    assert n.status_code == 201
    due = (date.today() + timedelta(days=3)).isoformat()
    fu = client.post(f"/brands-crm/{bid}/follow-ups", headers=h, json={"due_date": due, "notes": "Nudge"})
    assert fu.status_code == 201
    detail = client.get(f"/brands-crm/{bid}", headers=h).json()
    assert any(x["kind"] == "negotiation" for x in detail["notes"])
    assert detail["scheduled_follow_ups"]
    tl = client.get(f"/brands-crm/{bid}/timeline", headers=h).json()
    assert any(ev["type"] == "note" for ev in tl)


def test_contact_on_brand_and_patch():
    h = auth_headers("crm6@example.com")
    bid = client.post("/brands-crm", headers=h, json={"display_name": "Lenskart"}).json()["id"]
    c = client.post(f"/brands-crm/{bid}/contacts", headers=h, json={"name": "Priya", "email": "p@lenskart.com"})
    assert c.status_code == 201
    cid = c.json()["id"]
    patched = client.patch(f"/contacts/{cid}", headers=h, json={"email_verified": True})
    assert patched.status_code == 200
    assert patched.json()["email_verified"] is True


def test_suggestions_and_summary():
    h = auth_headers("crm7@example.com")
    bid = client.post("/brands-crm", headers=h, json={"display_name": "Noise"}).json()["id"]
    client.patch(f"/brands-crm/{bid}", headers=h, json={"next_follow_up": date.today().isoformat()})
    sug = client.get("/brands-crm/suggestions", headers=h).json()
    assert any(s["brand_record_id"] == bid for s in sug["brands"])
    summary = client.get(f"/brands-crm/{bid}/summary", headers=h)
    assert summary.status_code == 200
    assert "Noise" in summary.json()["summary"]


def test_discover_lists_csv():
    h = auth_headers("crm8@example.com")
    r = client.get("/brands-crm/discover", headers=h, params={"limit": 5})
    assert r.status_code == 200
    assert len(r.json()) >= 1
    assert "in_crm" in r.json()[0]

from datetime import datetime, timedelta

from tests.test_smoke import auth_headers, client


def _add_deal(h, brand="Nykaa"):
    r = client.post("/deals", headers=h, json={"brand": brand, "kind": "paid", "deliverables": "2 reels"})
    return r.json()["id"]


def test_content_requires_auth():
    assert client.get("/content/plan").status_code == 401


def test_plan_crud_isolation_and_search():
    h1 = auth_headers("cp1@example.com")
    h2 = auth_headers("cp2@example.com")
    deal = _add_deal(h1)
    created = client.post("/content/plan", headers=h1, json={
        "title": "Monsoon skincare reel", "platform": "instagram", "format": "reel",
        "status": "idea", "deal_id": deal, "tags": ["skincare"],
    })
    assert created.status_code == 201
    pid = created.json()["id"]
    listed = client.get("/content/plan?q=monsoon", headers=h1).json()
    assert any(x["id"] == pid for x in listed)
    assert not any(x["id"] == pid for x in client.get("/content/plan", headers=h2).json())
    patch = client.patch(f"/content/plan/{pid}", headers=h1, json={"status": "ready", "title": "Monsoon reel v2"})
    assert patch.status_code == 200 and patch.json()["status"] == "ready"
    assert client.delete(f"/content/plan/{pid}", headers=h2).status_code == 404
    assert client.delete(f"/content/plan/{pid}", headers=h1).status_code == 200


def test_draft_revisions():
    h = auth_headers("cp3@example.com")
    pid = client.post("/content/plan", headers=h, json={"title": "Test", "format": "reel"}).json()["id"]
    d1 = client.post(f"/content/plan/{pid}/drafts", headers=h, json={"caption": "v1", "body_json": {"hook": "hi"}})
    d2 = client.post(f"/content/plan/{pid}/drafts", headers=h, json={"caption": "v2", "body_json": {"hook": "hello"}})
    assert d1.status_code == 201 and d2.status_code == 201
    drafts = client.get(f"/content/plan/{pid}/drafts", headers=h).json()
    assert len(drafts) >= 2
    exp = client.get(f"/content/drafts/{drafts[0]['id']}/export.txt", headers=h)
    assert exp.status_code == 200 and "Publish manually" in exp.text


def test_generate_ideas_and_script_template():
    h = auth_headers("cp4@example.com")
    client.patch("/auth/me", json={"niche": "beauty"}, headers=h)
    ideas = client.post("/content/generate/ideas", headers=h, json={"platform": "instagram", "count": 3})
    assert ideas.status_code == 200
    assert len(ideas.json()["ideas"]) == 3
    assert client.get("/content/plan", headers=h).json()
    script = client.post("/content/generate/script", headers=h, json={
        "format": "reel", "platform": "instagram", "topic": "Vitamin C serum",
    })
    assert script.status_code == 200
    body = script.json()
    assert body["draft"]["caption"]
    assert "manually" in body["disclaimer"].lower() or "publish" in body["disclaimer"].lower()
    cap = client.post("/content/generate/script", headers=h, json={"format": "caption", "platform": "instagram"})
    assert cap.status_code == 200


def test_repurpose_and_status_flow():
    h = auth_headers("cp5@example.com")
    gen = client.post("/content/generate/script", headers=h, json={"format": "reel", "platform": "instagram", "topic": "Glow"})
    draft_id = gen.json()["draft"]["id"]
    rep = client.post("/content/repurpose", headers=h, json={
        "draft_id": draft_id, "target_format": "youtube", "target_platform": "youtube",
    })
    assert rep.status_code == 200
    new_id = rep.json()["plan_item"]["id"]
    client.patch(f"/content/plan/{new_id}", headers=h, json={"status": "scheduled",
                    "scheduled_at": (datetime.utcnow() + timedelta(days=2)).isoformat()})
    cal = client.get("/content/calendar", headers=h).json()
    assert any(i["id"] == new_id for i in cal["items"])


def test_deal_validation():
    h = auth_headers("cp6@example.com")
    h2 = auth_headers("cp6b@example.com")
    deal = _add_deal(h2)
    bad = client.post("/content/plan", headers=h, json={"title": "X", "deal_id": deal})
    assert bad.status_code == 400


def test_suggestions_endpoint():
    h = auth_headers("cp7@example.com")
    r = client.get("/content/suggestions", headers=h)
    assert r.status_code == 200 and isinstance(r.json()["tips"], list)

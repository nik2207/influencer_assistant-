import io
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app import models
from app.db import Base, SessionLocal, engine
from app.main import app
from app.routers import auth

Base.metadata.create_all(bind=engine)
auth.limiter.enabled = False
client = TestClient(app)


def signup(email):
    r = client.post("/auth/register", json={"email": email, "password": "password123", "name": "Creator"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def add_platform(h, platform="youtube", handle="mychan", followers=1000):
    client.put(f"/profile/platforms/{platform}", headers=h, json={"handle": handle, "followers": followers, "url": ""})


def test_requires_auth():
    assert client.get("/analytics/overview").status_code == 401


def test_manual_metric_crud_and_validation():
    h = signup("an1@example.com")
    add_platform(h)
    plats = client.get("/analytics/platforms", headers=h).json()
    acct_id = plats[0]["social_account_id"]
    bad = client.post("/analytics/metrics", headers=h, json={"platform": "youtube", "metric_key": "nope", "value": 1})
    assert bad.status_code == 422
    r = client.post("/analytics/metrics", headers=h, json={
        "platform": "youtube", "metric_key": "followers", "value": 1200,
        "period_start": "2025-01-01", "social_account_id": acct_id,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "manual" and body["confidence"] == "verified"
    listed = client.get("/analytics/metrics?platform=youtube", headers=h).json()
    assert len(listed) >= 1
    assert client.delete(f"/analytics/metrics/{body['id']}", headers=h).status_code == 200
    assert client.delete(f"/analytics/metrics/{body['id']}", headers=h).status_code == 404


def test_historical_snapshots_and_growth():
    h = signup("an2@example.com")
    add_platform(h)
    d0 = date.today() - timedelta(days=14)
    d1 = date.today() - timedelta(days=7)
    for d, val in ((d0, 1000), (d1, 1100)):
        client.post("/analytics/metrics", headers=h, json={
            "platform": "youtube", "metric_key": "followers", "value": val, "period_start": d.isoformat(),
        })
    g = client.get(
        f"/analytics/growth?platform=youtube&metric_key=followers&from_date={d0.isoformat()}&to_date={date.today().isoformat()}",
        headers=h,
    ).json()
    assert g["delta"] == 100 and g["points"] == 2


def test_date_filtering():
    h = signup("an3@example.com")
    add_platform(h, platform="instagram", handle="insta")
    inside = date.today() - timedelta(days=3)
    outside = date.today() - timedelta(days=60)
    client.post("/analytics/metrics", headers=h, json={
        "platform": "instagram", "metric_key": "reach", "value": 5000, "period_start": inside.isoformat(),
    })
    client.post("/analytics/metrics", headers=h, json={
        "platform": "instagram", "metric_key": "reach", "value": 999, "period_start": outside.isoformat(),
    })
    fr = (date.today() - timedelta(days=7)).isoformat()
    rows = client.get(f"/analytics/metrics?platform=instagram&from_date={fr}", headers=h).json()
    assert len(rows) == 1 and rows[0]["value"] == 5000


def test_user_isolation():
    h1 = signup("an4a@example.com")
    h2 = signup("an4b@example.com")
    add_platform(h1)
    r = client.post("/analytics/metrics", headers=h1, json={
        "platform": "youtube", "metric_key": "views", "value": 42, "period_start": date.today().isoformat(),
    })
    sid = r.json()["id"]
    assert client.get("/analytics/metrics", headers=h2).json() == []
    assert client.delete(f"/analytics/metrics/{sid}", headers=h2).status_code == 404


def test_csv_import_and_export():
    h = signup("an5@example.com")
    csv_body = "date,platform,metric,value\n2025-06-01,youtube,views,100\n2025-06-02,youtube,views,120\n"
    r = client.post("/analytics/import", headers=h, files={"file": ("m.csv", io.BytesIO(csv_body.encode()), "text/csv")})
    assert r.status_code == 200 and r.json()["row_count"] == 2
    out = client.get(
        f"/analytics/export/csv?from_date=2025-06-01&to_date=2025-06-30", headers=h,
    )
    assert out.status_code == 200 and "youtube" in out.text


def test_overview_and_insights_no_fabrication():
    h = signup("an6@example.com")
    add_platform(h)
    to = date.today().isoformat()
    fr = (date.today() - timedelta(days=30)).isoformat()
    ov = client.get(f"/analytics/overview?from_date={fr}&to_date={to}", headers=h).json()
    assert "platforms" in ov and ov["platforms"][0]["followers"] == 1000
    text = client.get(f"/analytics/insights?from_date={fr}&to_date={to}", headers=h).json()["text"]
    assert "stored data" in text.lower() or "no metrics" in text.lower()


def test_compare_and_content():
    h = signup("an7@example.com")
    add_platform(h)
    add_platform(h, platform="instagram", handle="ig", followers=200)
    today = date.today().isoformat()
    cmp = client.get(f"/analytics/compare?metric_key=followers&from_date={today}&to_date={today}", headers=h).json()
    assert len(cmp) >= 2
    client.post("/analytics/content", headers=h, json={
        "platform": "youtube", "title": "Vlog 1", "views": 9000, "engagement": 400,
    })
    top = client.get("/analytics/content", headers=h).json()
    assert top[0]["title"] == "Vlog 1"


def test_connect_without_google_config():
    h = signup("an8@example.com")
    r = client.get("/analytics/connect/youtube", headers=h)
    assert r.status_code in (503, 200)

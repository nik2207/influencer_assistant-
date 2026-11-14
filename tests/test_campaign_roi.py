from datetime import date

from app.db import SessionLocal
from app import models
from app.security import hash_password
from app.services import campaign_roi, invoices as inv_svc
from tests.test_smoke import auth_headers, client


def _user_db(email="roi-user@ex.com"):
    h = auth_headers(email)
    db = SessionLocal()
    user = db.query(models.User).filter_by(email=email).first()
    return h, user, db


def test_invoiced_not_doubled_with_deal_value():
    h, user, db = _user_db("roi1@ex.com")
    deal = models.Deal(user_id=user.id, brand="Nykaa", kind="paid", value_inr=50000, status="confirmed")
    db.add(deal)
    db.flush()
    inv = models.Invoice(user_id=user.id, deal_id=deal.id, amount_inr=45000, status="sent",
                         paid_inr=0, issue_date=date.today(), client_name="Nykaa")
    db.add(inv)
    db.commit()
    roi = campaign_roi.compute_deal_roi(db, user, deal.id)
    assert roi.invoiced_revenue.amount_inr == 45000
    assert roi.invoiced_revenue.source == "invoices"
    assert roi.invoiced_revenue.is_estimate is False
    db.close()


def test_received_from_payments_not_paid_inr_double():
    h, user, db = _user_db("roi2@ex.com")
    deal = models.Deal(user_id=user.id, brand="boAt", kind="paid", value_inr=20000, status="payment_pending")
    db.add(deal)
    db.flush()
    inv = models.Invoice(user_id=user.id, deal_id=deal.id, amount_inr=20000, status="sent",
                         paid_inr=10000, issue_date=date.today())
    db.add(inv)
    db.flush()
    db.add(models.InvoicePayment(user_id=user.id, invoice_id=inv.id, amount_inr=10000, paid_at=date.today()))
    db.commit()
    roi = campaign_roi.compute_deal_roi(db, user, deal.id)
    assert roi.received_revenue.amount_inr == 10000
    assert roi.outstanding.amount_inr == 10000
    db.close()


def test_expenses_and_profit_estimate():
    h, user, db = _user_db("roi3@ex.com")
    deal = models.Deal(user_id=user.id, brand="Zepto", kind="paid", value_inr=30000,
                       production_cost_estimate_inr=5000, status="posted")
    db.add(deal)
    db.flush()
    db.add(models.Expense(user_id=user.id, deal_id=deal.id, amount_inr=2000, spent_on=date.today(),
                          category="travel", description="Cab to shoot"))
    inv = models.Invoice(user_id=user.id, deal_id=deal.id, amount_inr=30000, status="sent",
                         paid_inr=0, issue_date=date.today())
    db.add(inv)
    db.flush()
    inv_svc.record_payment(db, user, inv, 30000, date.today())
    db.commit()
    roi = campaign_roi.compute_deal_roi(db, user, deal.id)
    assert roi.actual_expenses.amount_inr == 2000
    assert roi.estimated_expenses.amount_inr == 5000
    assert roi.profit_estimate.amount_inr == 23000  # 30000 - 2000 - 5000
    assert roi.roi_pct == round(23000 / 7000 * 100, 2)
    db.close()


def test_deal_value_estimate_when_no_invoice():
    h, user, db = _user_db("roi4@ex.com")
    deal = models.Deal(user_id=user.id, brand="Noise", kind="paid", value_inr=15000, status="lead")
    db.add(deal)
    db.commit()
    roi = campaign_roi.compute_deal_roi(db, user, deal.id)
    assert roi.invoiced_revenue.is_estimate is True
    assert roi.invoiced_revenue.source == "deal_value_estimate"
    assert "no_invoices" in roi.data_gaps
    db.close()


def test_api_ownership_and_export():
    h1 = auth_headers("roi5@ex.com")
    d = client.post("/deals", headers=h1, json={"brand": "Mamaearth", "kind": "paid", "value_inr": 8000}).json()
    h2 = auth_headers("roi6@ex.com")
    assert client.get(f"/roi/deals/{d['id']}", headers=h2).status_code == 404
    r = client.get("/roi/campaigns", headers=h1).json()
    assert r["totals"]["invoiced_inr"] >= 0
    csv = client.get("/roi/campaigns/export.csv", headers=h1)
    assert csv.status_code == 200
    assert "deal_id" in csv.text


def test_engagement_metrics_null_without_data():
    h, user, db = _user_db("roi7@ex.com")
    deal = models.Deal(user_id=user.id, brand="Lenskart", kind="paid", value_inr=10000)
    db.add(deal)
    db.commit()
    roi = campaign_roi.compute_deal_roi(db, user, deal.id)
    assert roi.cost_per_engagement is None
    assert "no_engagement" in roi.data_gaps
    db.close()


def test_brand_filter():
    h1 = auth_headers("roi8@ex.com")
    client.post("/deals", headers=h1, json={"brand": "Swiggy", "kind": "paid", "value_inr": 1})
    client.post("/deals", headers=h1, json={"brand": "Zomato", "kind": "paid", "value_inr": 2})
    r = client.get("/roi/campaigns", headers=h1, params={"brand": "Swig"}).json()
    assert all("Swig" in c["brand"] for c in r["campaigns"])

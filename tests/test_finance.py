from datetime import date, timedelta

from tests.test_smoke import auth_headers, client


def test_invoice_draft_edit_send_and_payment():
    h = auth_headers("fin1@example.com")
    deal = client.post("/deals", json={"brand": "Zepto", "value_inr": 10000, "deliverables": "1 reel"}, headers=h).json()["id"]
    draft = client.post("/invoices", headers=h, json={
        "deal_id": deal, "client_name": "Zepto", "issue_date": str(date.today()),
        "due_date": str(date.today() + timedelta(days=15)),
        "line_items": [{"description": "Instagram reel", "quantity": 1, "unit_price": 10000}],
    }).json()
    assert draft["status"] == "draft" and draft["amount_inr"] == 10000
    dup = client.post("/invoices", headers=h, json={
        "deal_id": deal, "client_name": "Zepto",
        "line_items": [{"description": "x", "quantity": 1, "unit_price": 1}],
    })
    assert dup.status_code == 400
    sent = client.post(f"/invoices/{draft['id']}/send", headers=h).json()
    assert sent["status"] == "sent"
    pdf = client.get(f"/invoices/{draft['id']}/pdf", headers=h)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    patch = client.patch(f"/invoices/{draft['id']}", headers=h, json={"client_name": "Hack"})
    assert patch.status_code == 409
    part = client.post(f"/invoices/{draft['id']}/payments", headers=h, json={"amount_inr": 4000}).json()
    assert part["amount_inr"] == 4000
    inv = client.get(f"/invoices/{draft['id']}", headers=h).json()
    assert inv["status"] == "partially_paid" and inv["paid_inr"] == 4000
    client.post(f"/invoices/{draft['id']}/mark-paid", headers=h)
    inv = client.get(f"/invoices/{draft['id']}", headers=h).json()
    assert inv["status"] == "paid" and inv["balance_inr"] == 0


def test_finance_summary_and_expenses():
    h = auth_headers("fin2@example.com")
    client.post("/expenses", headers=h, json={
        "spent_on": str(date.today()), "category": "travel", "description": "Cab to shoot", "amount_inr": 800,
    })
    s = client.get(f"/invoices/summary?from_date={date.today().replace(day=1)}&to_date={date.today()}", headers=h).json()
    assert s["total_received"] == 0 and s["expenses"] == 800
    assert s["net_cash_flow"] == -800
    other = auth_headers("fin3@example.com")
    assert client.get(f"/expenses", headers=other).json() == []


def test_overdue_and_reminder():
    h = auth_headers("fin4@example.com")
    inv = client.post("/invoices", headers=h, json={
        "client_name": "BrandCo",
        "issue_date": str(date.today() - timedelta(days=30)),
        "due_date": str(date.today() - timedelta(days=5)),
        "line_items": [{"description": "Work", "quantity": 1, "unit_price": 5000}],
    }).json()
    client.post(f"/invoices/{inv['id']}/send", headers=h)
    listed = client.get("/invoices?overdue_only=true", headers=h).json()
    assert any(x["id"] == inv["id"] for x in listed)
    rem = client.post(f"/invoices/{inv['id']}/reminder-draft", headers=h).json()
    assert "BrandCo" in rem["draft"]
    assert "send" in rem["note"].lower()


def test_for_deal_still_works():
    h = auth_headers("fin5@example.com")
    deal = client.post("/deals", json={"brand": "Nykaa", "value_inr": 20000}, headers=h).json()["id"]
    inv = client.post(f"/invoices/for-deal/{deal}", headers=h).json()["invoice"]
    assert inv["status"] == "sent"
    assert client.get(f"/invoices/{inv['id']}/pdf", headers=h).status_code == 200

"""Workspace isolation, roles, invitations, and cross-tenant security."""
from io import BytesIO

from tests.test_smoke import auth_headers, client, chat


def ws_headers(email: str):
    h = auth_headers(email)
    ws = client.get("/workspaces", headers=h).json()[0]["id"]
    h["X-Workspace-Id"] = str(ws)
    return h, ws


def test_register_gets_personal_workspace():
    h = auth_headers("ws-solo@example.com")
    wss = client.get("/workspaces", headers=h).json()
    assert len(wss) == 1
    assert client.get("/workspaces/current", headers=h).status_code == 200


def test_cross_workspace_deal_isolation():
    ha, wa = ws_headers("ws-owner-a@example.com")
    hb, wb = ws_headers("ws-owner-b@example.com")
    d = client.post("/deals", json={"brand": "Secret", "value_inr": 1}, headers=ha).json()
    assert wa != wb
    assert client.get(f"/deals/{d['id']}", headers=hb).status_code in (403, 404) or client.patch(
        f"/deals/{d['id']}", json={"notes": "x"}, headers=hb,
    ).status_code == 404


def test_invite_accept_and_role_enforced():
    owner_h, ws_id = ws_headers("ws-inv-owner@example.com")
    inv = client.post(
        "/workspaces/current/invitations",
        headers=owner_h,
        json={"email": "ws-inv-editor@example.com", "role": "editor"},
    ).json()
    editor_reg = auth_headers("ws-inv-editor@example.com")
    client.post("/workspaces/invitations/accept", headers=editor_reg, json={"token": inv["accept_token"]})
    editor_h = {**editor_reg, "X-Workspace-Id": str(ws_id)}
    assert client.post(
        "/invoices",
        headers=editor_h,
        json={
            "client_name": "X", "line_items": [{"description": "d", "quantity": 1, "unit_price": 100}],
        },
    ).status_code == 403


def test_finance_can_draft_invoice():
    owner_h, ws_id = ws_headers("ws-fin-owner@example.com")
    client.post(
        "/workspaces/current/invitations",
        headers=owner_h,
        json={"email": "ws-fin-mgr@example.com", "role": "finance"},
    )
    tok = client.get("/workspaces/current/invitations", headers=owner_h)
    inv = client.post(
        "/workspaces/current/invitations",
        headers=owner_h,
        json={"email": "ws-fin-mgr@example.com", "role": "finance"},
    )
    fin_reg = auth_headers("ws-fin-mgr@example.com")
    # re-invite once - first invite may conflict; accept from list endpoint omitted — use direct invite
    invs = client.post(
        "/workspaces/current/invitations",
        headers=owner_h,
        json={"email": "ws-fin-manager@example.com", "role": "finance"},
    ).json()
    fin_h = auth_headers("ws-fin-manager@example.com")
    client.post("/workspaces/invitations/accept", headers=fin_h, json={"token": invs["accept_token"]})
    fin_h["X-Workspace-Id"] = str(ws_id)
    deal = client.post("/deals", json={"brand": "Boat", "value_inr": 5000}, headers=owner_h).json()
    r = client.post(
        "/invoices",
        headers=fin_h,
        json={"client_name": "Boat", "deal_id": deal["id"], "line_items": [{"description": "d", "quantity": 1, "unit_price": 100}]},
    )
    assert r.status_code == 200, r.text


def test_deal_assignment_editor_sees_only_assigned():
    owner_h, ws_id = ws_headers("ws-asgn-owner@example.com")
    inv = client.post(
        "/workspaces/current/invitations",
        headers=owner_h,
        json={"email": "ws-asgn-ed@example.com", "role": "editor"},
    ).json()
    ed = auth_headers("ws-asgn-ed@example.com")
    client.post("/workspaces/invitations/accept", headers=ed, json={"token": inv["accept_token"]})
    ed_h = {**ed, "X-Workspace-Id": str(ws_id)}
    d1 = client.post("/deals", json={"brand": "A"}, headers=owner_h).json()
    client.post("/deals", json={"brand": "B"}, headers=owner_h)
    client.post(
        f"/workspaces/deals/{d1['id']}/assignments",
        headers=owner_h,
        json={"user_id": client.get("/auth/me", headers=ed).json()["id"], "assignment_role": "contributor"},
    )
    listed = client.get("/deals", headers=ed_h).json()
    assert len(listed) == 1 and listed[0]["brand"] == "A"


def test_pending_approval_workspace_scoped():
    owner_h, _ = ws_headers("ws-pend-owner@example.com")
    out = chat(owner_h, "Book a cab from Panvel to Bandra tomorrow at 4 pm")
    assert out["pending"]
    pid = out["pending"][0]["id"]
    other = ws_headers("ws-pend-stranger@example.com")[0]
    assert client.post(f"/agent/approve/{pid}", headers=other).json().get("error")


def test_activity_log_requires_permission():
    owner_h, _ = ws_headers("ws-act-owner@example.com")
    assert client.get("/workspaces/current/activity", headers=owner_h).status_code == 200
    inv = client.post(
        "/workspaces/current/invitations",
        headers=owner_h,
        json={"email": "ws-act-view@example.com", "role": "viewer"},
    ).json()
    v = auth_headers("ws-act-view@example.com")
    client.post("/workspaces/invitations/accept", headers=v, json={"token": inv["accept_token"]})
    vh = {**v, "X-Workspace-Id": owner_h["X-Workspace-Id"]}
    assert client.get("/workspaces/current/activity", headers=vh).status_code == 403

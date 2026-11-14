"""Workspace role capabilities (enforced in API and agent tools)."""
from __future__ import annotations

from fastapi import HTTPException

ROLES = ("owner", "admin", "manager", "editor", "finance", "viewer")

ROLE_RANK = {r: i for i, r in enumerate(ROLES)}

PERMS: dict[str, frozenset[str]] = {
    "owner": frozenset({
        "workspace.read", "workspace.settings", "workspace.delete", "workspace.transfer",
        "members.invite", "members.manage", "members.remove",
        "activity.read",
        "deals.read", "deals.write", "deals.delete", "deals.assign",
        "calendar.read", "calendar.write",
        "content.read", "content.write",
        "inbox.read", "inbox.write",
        "outreach.read", "outreach.write",
        "crm.read", "crm.write",
        "invoice.read", "invoice.draft", "invoice.send", "invoice.pay", "invoice.export",
        "expense.read", "expense.write",
        "analytics.read", "analytics.write",
        "agent.use", "agent.approve", "agent.finance_approve",
        "tasks.read", "tasks.write",
        "integrations.manage",
    }),
    "admin": frozenset({
        "workspace.read", "workspace.settings",
        "members.invite", "members.manage", "members.remove",
        "activity.read",
        "deals.read", "deals.write", "deals.delete", "deals.assign",
        "calendar.read", "calendar.write",
        "content.read", "content.write",
        "inbox.read", "inbox.write",
        "outreach.read", "outreach.write",
        "crm.read", "crm.write",
        "invoice.read", "invoice.draft", "invoice.send", "invoice.pay", "invoice.export",
        "expense.read", "expense.write",
        "analytics.read", "analytics.write",
        "agent.use", "agent.approve", "agent.finance_approve",
        "tasks.read", "tasks.write",
        "integrations.manage",
    }),
    "manager": frozenset({
        "workspace.read",
        "members.invite",
        "activity.read",
        "deals.read", "deals.write", "deals.assign",
        "calendar.read", "calendar.write",
        "content.read", "content.write",
        "inbox.read", "inbox.write",
        "outreach.read", "outreach.write",
        "crm.read", "crm.write",
        "invoice.read", "invoice.draft",
        "expense.read", "expense.write",
        "analytics.read",
        "agent.use", "agent.approve",
        "tasks.read", "tasks.write",
    }),
    "editor": frozenset({
        "workspace.read",
        "deals.read", "deals.write",
        "calendar.read", "calendar.write",
        "content.read", "content.write",
        "outreach.read", "outreach.write",
        "crm.read",
        "analytics.read",
        "agent.use",
        "tasks.read", "tasks.write",
    }),
    "finance": frozenset({
        "workspace.read",
        "activity.read",
        "deals.read",
        "calendar.read",
        "invoice.read", "invoice.draft", "invoice.send", "invoice.pay", "invoice.export",
        "expense.read", "expense.write",
        "analytics.read",
        "agent.use", "agent.finance_approve",
        "tasks.read",
    }),
    "viewer": frozenset({
        "workspace.read",
        "deals.read",
        "calendar.read",
        "content.read",
        "outreach.read",
        "crm.read",
        "invoice.read",
        "expense.read",
        "analytics.read",
        "tasks.read",
        "agent.use",
    }),
}

TOOL_PERMS: dict[str, str] = {
    "add_deal": "deals.write",
    "list_deals": "deals.read",
    "update_deal_status": "deals.write",
    "add_event": "calendar.write",
    "list_events": "calendar.read",
    "book_ride": "agent.use",
    "create_invoice": "invoice.draft",
    "draft_pitch": "outreach.write",
    "generate_pitch_studio": "outreach.write",
    "suggest_brands": "outreach.read",
    "check_inbox": "inbox.read",
    "check_followups": "inbox.read",
    "sync_calendar": "calendar.write",
    "draft_email_reply": "inbox.write",
    "list_overdue_invoices": "invoice.read",
    "record_invoice_payment": "invoice.pay",
    "add_expense": "expense.write",
    "list_expenses": "expense.read",
    "draft_payment_reminder": "invoice.draft",
    "summarize_analytics": "analytics.read",
    "generate_content_ideas": "content.write",
    "list_content_plan": "content.read",
    "content_suggestions": "content.read",
    "list_brand_crm": "crm.read",
    "brand_follow_up_suggestions": "crm.read",
    "brand_relationship_summary": "crm.read",
    "get_email_intelligence": "inbox.read",
    "email_follow_up_recommendations": "inbox.read",
    "campaign_roi": "analytics.read",
    "list_campaign_roi": "analytics.read",
}


def can(role: str, perm: str) -> bool:
    if role not in PERMS:
        return False
    return perm in PERMS[role]


def require_role(role: str, perm: str) -> None:
    if not can(role, perm):
        raise HTTPException(403, "You don't have permission to do that in this workspace.")


def can_assign_role(actor_role: str, target_role: str) -> bool:
    """Prevent privilege escalation above actor's rank (owner can assign any role)."""
    if actor_role == "owner":
        return target_role in ROLES
    if actor_role == "admin":
        return ROLE_RANK.get(target_role, 99) >= ROLE_RANK["manager"]
    if actor_role == "manager":
        return target_role in ("editor", "viewer", "finance")
    return False

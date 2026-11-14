"""Workspace-scoped data access (always filter by workspace_id)."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session, Query

from .. import models
from ..permissions import ROLE_RANK, can, require_role


@dataclass
class WorkspaceCtx:
    user: models.User
    workspace: models.Workspace
    membership: models.WorkspaceMembership

    @property
    def workspace_id(self) -> int:
        return self.workspace.id

    @property
    def role(self) -> str:
        return self.membership.role

    def require(self, perm: str) -> None:
        require_role(self.role, perm)


def row_in_workspace(row, workspace_id: int) -> bool:
    wid = getattr(row, "workspace_id", None)
    if wid is None:
        return getattr(row, "user_id", None) is not None  # legacy until backfill
    return wid == workspace_id


def assert_in_workspace(ctx: WorkspaceCtx, row, label: str = "Resource") -> None:
    if row is None or not row_in_workspace(row, ctx.workspace_id):
        raise HTTPException(404, f"{label} not found")


def deals_scope(ctx: WorkspaceCtx) -> bool:
    """True if role sees all workspace deals (not only assignments)."""
    return ctx.role in ("owner", "admin", "manager", "finance", "viewer")


def deals_query(db: Session, ctx: WorkspaceCtx) -> Query:
    q = db.query(models.Deal).filter(models.Deal.workspace_id == ctx.workspace_id)
    if deals_scope(ctx):
        return q
    assigned = db.query(models.DealAssignment.deal_id).filter_by(
        workspace_id=ctx.workspace_id, user_id=ctx.user.id,
    )
    return q.filter(or_(models.Deal.user_id == ctx.user.id, models.Deal.id.in_(assigned)))


def get_deal(db: Session, ctx: WorkspaceCtx, deal_id: int) -> models.Deal:
    ctx.require("deals.read")
    deal = db.get(models.Deal, deal_id)
    assert_in_workspace(ctx, deal, "Deal")
    if not deals_scope(ctx):
        if deal.user_id != ctx.user.id:
            ok = db.query(models.DealAssignment).filter_by(
                workspace_id=ctx.workspace_id, deal_id=deal_id, user_id=ctx.user.id,
            ).first()
            if not ok:
                raise HTTPException(404, "Deal not found")
    return deal


def stamp(row, ctx: WorkspaceCtx) -> None:
    row.workspace_id = ctx.workspace_id
    if hasattr(row, "user_id") and getattr(row, "user_id", None) is None:
        row.user_id = ctx.user.id


def invoices_query(db: Session, ctx: WorkspaceCtx) -> Query:
    ctx.require("invoice.read")
    return db.query(models.Invoice).filter(models.Invoice.workspace_id == ctx.workspace_id)


def get_invoice(db: Session, ctx: WorkspaceCtx, invoice_id: int) -> models.Invoice:
    ctx.require("invoice.read")
    inv = db.get(models.Invoice, invoice_id)
    assert_in_workspace(ctx, inv, "Invoice")
    return inv


def expenses_query(db: Session, ctx: WorkspaceCtx) -> Query:
    ctx.require("expense.read")
    return db.query(models.Expense).filter(models.Expense.workspace_id == ctx.workspace_id)


def get_expense(db: Session, ctx: WorkspaceCtx, expense_id: int) -> models.Expense:
    ctx.require("expense.read")
    row = db.get(models.Expense, expense_id)
    assert_in_workspace(ctx, row, "Expense")
    return row


def events_query(db: Session, ctx: WorkspaceCtx) -> Query:
    ctx.require("calendar.read")
    return db.query(models.Event).filter(models.Event.workspace_id == ctx.workspace_id)


def get_event(db: Session, ctx: WorkspaceCtx, event_id: int) -> models.Event:
    ctx.require("calendar.read")
    ev = db.get(models.Event, event_id)
    assert_in_workspace(ctx, ev, "Event")
    return ev


def assign_deal_lead(db: Session, ctx: WorkspaceCtx, deal: models.Deal) -> None:
    if db.query(models.DealAssignment).filter_by(deal_id=deal.id, user_id=deal.user_id).first():
        return
    db.add(models.DealAssignment(
        workspace_id=ctx.workspace_id, deal_id=deal.id, user_id=deal.user_id,
        assignment_role="lead",
    ))

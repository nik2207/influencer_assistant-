"""Workspace lifecycle, invitations, members, tasks."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..models import utcnow
from ..permissions import ROLES, can_assign_role
from ..services.tenancy import WorkspaceCtx, assign_deal_lead, assert_in_workspace, get_deal, stamp
from ..services import workspace_bootstrap


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_workspace(db: Session, user: models.User, name: str, workspace_type: str) -> models.Workspace:
    slug = workspace_bootstrap._slug(name, user.id) + "-" + secrets.token_hex(2)
    ws = models.Workspace(name=name, slug=slug, workspace_type=workspace_type, owner_user_id=user.id)
    db.add(ws)
    db.flush()
    db.add(models.WorkspaceMembership(
        workspace_id=ws.id, user_id=user.id, role="owner", status="active", joined_at=utcnow(),
    ))
    db.commit()
    return ws


def list_memberships(db: Session, user: models.User) -> list[models.WorkspaceMembership]:
    return (
        db.query(models.WorkspaceMembership)
        .filter_by(user_id=user.id, status="active")
        .order_by(models.WorkspaceMembership.id)
        .all()
    )


def invite_member(db: Session, ctx: WorkspaceCtx, email: str, role: str) -> tuple[models.WorkspaceInvitation, str]:
    ctx.require("members.invite")
    if role not in ROLES or role == "owner":
        raise HTTPException(422, "Invalid role for invitation")
    if not can_assign_role(ctx.role, role):
        raise HTTPException(403, "You cannot invite someone with that role")
    email = email.lower().strip()
    existing = db.query(models.User).filter_by(email=email).first()
    if existing:
        mem = db.query(models.WorkspaceMembership).filter_by(
            workspace_id=ctx.workspace_id, user_id=existing.id, status="active",
        ).first()
        if mem:
            raise HTTPException(409, "That person is already in this workspace")
    token = secrets.token_urlsafe(32)
    inv = models.WorkspaceInvitation(
        workspace_id=ctx.workspace_id,
        email=email,
        role=role,
        token_hash=_hash_token(token),
        invited_by_user_id=ctx.user.id,
        expires_at=utcnow() + timedelta(days=7),
    )
    db.add(inv)
    db.commit()
    return inv, token


def accept_invitation(db: Session, user: models.User, token: str) -> models.WorkspaceMembership:
    inv = db.query(models.WorkspaceInvitation).filter_by(token_hash=_hash_token(token)).first()
    if not inv or inv.revoked_at or inv.accepted_at:
        raise HTTPException(400, "Invitation is not valid")
    if inv.expires_at < utcnow():
        raise HTTPException(400, "Invitation has expired")
    if user.email.lower() != inv.email.lower():
        raise HTTPException(403, "This invitation was sent to a different email address")
    dup = db.query(models.WorkspaceMembership).filter_by(
        workspace_id=inv.workspace_id, user_id=user.id,
    ).first()
    if dup and dup.status == "active":
        raise HTTPException(409, "You are already in this workspace")
    if dup:
        dup.status = "active"
        dup.role = inv.role
        dup.joined_at = utcnow()
        mem = dup
    else:
        mem = models.WorkspaceMembership(
            workspace_id=inv.workspace_id,
            user_id=user.id,
            role=inv.role,
            status="active",
            invited_by_user_id=inv.invited_by_user_id,
            joined_at=utcnow(),
        )
        db.add(mem)
    inv.accepted_at = utcnow()
    db.commit()
    return mem


def set_member_role(db: Session, ctx: WorkspaceCtx, membership_id: int, role: str) -> models.WorkspaceMembership:
    ctx.require("members.manage")
    if role not in ROLES or role == "owner":
        raise HTTPException(422, "Invalid role")
    mem = db.get(models.WorkspaceMembership, membership_id)
    if not mem or mem.workspace_id != ctx.workspace_id or mem.status != "active":
        raise HTTPException(404, "Member not found")
    if mem.role == "owner":
        raise HTTPException(403, "Transfer ownership instead of changing the owner role")
    if not can_assign_role(ctx.role, role):
        raise HTTPException(403, "You cannot assign that role")
    mem.role = role
    db.commit()
    return mem


def remove_member(db: Session, ctx: WorkspaceCtx, membership_id: int) -> None:
    ctx.require("members.remove")
    mem = db.get(models.WorkspaceMembership, membership_id)
    if not mem or mem.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Member not found")
    if mem.role == "owner":
        raise HTTPException(403, "Cannot remove the workspace owner")
    if mem.user_id == ctx.user.id and ctx.role != "owner":
        raise HTTPException(403, "Only the owner can remove themselves via transfer")
    mem.status = "removed"
    db.commit()


def transfer_ownership(db: Session, ctx: WorkspaceCtx, new_owner_id: int, confirm: bool) -> None:
    if ctx.role != "owner":
        raise HTTPException(403, "Only the owner can transfer ownership")
    if not confirm:
        raise HTTPException(400, "Set confirm=true to transfer ownership")
    target = db.query(models.WorkspaceMembership).filter_by(
        workspace_id=ctx.workspace_id, user_id=new_owner_id, status="active",
    ).first()
    if not target:
        raise HTTPException(404, "New owner must be an active member")
    owner_mem = db.query(models.WorkspaceMembership).filter_by(
        workspace_id=ctx.workspace_id, user_id=ctx.user.id, status="active",
    ).first()
    if not owner_mem:
        raise HTTPException(400, "Owner membership missing")
    owner_mem.role = "admin"
    target.role = "owner"
    ctx.workspace.owner_user_id = new_owner_id
    db.commit()


def mark_delete_workspace(db: Session, ctx: WorkspaceCtx, confirm_name: str, confirm: bool) -> None:
    if ctx.role != "owner":
        raise HTTPException(403, "Only the owner can delete a workspace")
    if not confirm or confirm_name != ctx.workspace.name:
        raise HTTPException(400, "Type the workspace name and set confirm=true to schedule deletion")
    ctx.workspace.marked_for_deletion_at = utcnow()
    db.commit()


def assign_deal(db: Session, ctx: WorkspaceCtx, deal_id: int, user_id: int, assignment_role: str) -> models.DealAssignment:
    ctx.require("deals.assign")
    deal = get_deal(db, ctx, deal_id)
    mem = db.query(models.WorkspaceMembership).filter_by(
        workspace_id=ctx.workspace_id, user_id=user_id, status="active",
    ).first()
    if not mem:
        raise HTTPException(404, "Assignee is not a workspace member")
    row = db.query(models.DealAssignment).filter_by(deal_id=deal.id, user_id=user_id).first()
    if row:
        row.assignment_role = assignment_role
    else:
        row = models.DealAssignment(
            workspace_id=ctx.workspace_id, deal_id=deal.id, user_id=user_id,
            assignment_role=assignment_role,
        )
        db.add(row)
    db.commit()
    return row


def create_task(db: Session, ctx: WorkspaceCtx, body) -> models.WorkspaceTask:
    ctx.require("tasks.write")
    if body.deal_id:
        get_deal(db, ctx, body.deal_id)
    task = models.WorkspaceTask(
        workspace_id=ctx.workspace_id,
        deal_id=body.deal_id,
        title=body.title,
        description=body.description or "",
        assignee_user_id=body.assignee_user_id,
        created_by_user_id=ctx.user.id,
        due_at=body.due_at,
    )
    db.add(task)
    db.commit()
    return task

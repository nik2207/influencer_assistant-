from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import models, schemas_workspace as ws
from ..db import get_db
from ..permissions import require_role
from ..security import audit, current_user, workspace_context
from ..services import workspace_svc
from ..services.tenancy import WorkspaceCtx, get_deal

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _ws_out(ws_row: models.Workspace) -> ws.WorkspaceOut:
    return ws.WorkspaceOut.model_validate(ws_row)


@router.get("", response_model=list[ws.WorkspaceOut])
def list_workspaces(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    ids = [m.workspace_id for m in workspace_svc.list_memberships(db, user)]
    rows = db.query(models.Workspace).filter(models.Workspace.id.in_(ids)).order_by(models.Workspace.id).all()
    return [_ws_out(w) for w in rows]


@router.post("", response_model=ws.WorkspaceOut, status_code=201)
def create_workspace(body: ws.WorkspaceCreateIn, user: models.User = Depends(current_user),
                     db: Session = Depends(get_db), request: Request = None):
    row = workspace_svc.create_workspace(db, user, body.name, body.workspace_type)
    audit(db, user.id, "workspace_created", row.name, request.client.host if request and request.client else "",
          workspace_id=row.id, resource_type="workspace", resource_id=row.id)
    return _ws_out(row)


@router.get("/current", response_model=ws.WorkspaceOut)
def current_workspace(ctx: WorkspaceCtx = Depends(workspace_context)):
    return _ws_out(ctx.workspace)


@router.patch("/current/settings", response_model=ws.WorkspaceOut)
def patch_settings(body: ws.WorkspaceSettingsIn, ctx: WorkspaceCtx = Depends(workspace_context),
                   db: Session = Depends(get_db), request: Request = None):
    ctx.require("workspace.settings")
    merged = {**(ctx.workspace.settings or {}), **(body.settings or {})}
    ctx.workspace.settings = merged
    db.commit()
    audit(db, ctx.user.id, "workspace_settings", ",".join(sorted(body.settings.keys())),
          request.client.host if request and request.client else "",
          workspace_id=ctx.workspace_id, resource_type="workspace", resource_id=ctx.workspace_id)
    return _ws_out(ctx.workspace)


@router.get("/current/members", response_model=list[ws.MemberOut])
def list_members(ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    ctx.require("workspace.read")
    mems = db.query(models.WorkspaceMembership).filter_by(
        workspace_id=ctx.workspace_id, status="active",
    ).order_by(models.WorkspaceMembership.id).all()
    out = []
    for m in mems:
        u = db.get(models.User, m.user_id)
        out.append(ws.MemberOut(
            id=m.id, user_id=m.user_id, email=u.email if u else "", name=u.name if u else "",
            role=m.role, status=m.status, joined_at=m.joined_at,
        ))
    return out


@router.post("/current/invitations", response_model=ws.InviteOut, status_code=201)
def invite(body: ws.InviteIn, ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db),
           request: Request = None):
    inv, token = workspace_svc.invite_member(db, ctx, body.email, body.role)
    audit(db, ctx.user.id, "member_invited", f"{body.email}:{body.role}",
          request.client.host if request and request.client else "",
          workspace_id=ctx.workspace_id, resource_type="invitation", resource_id=inv.id)
    return ws.InviteOut(id=inv.id, email=inv.email, role=inv.role, expires_at=inv.expires_at, accept_token=token)


@router.post("/invitations/accept")
def accept_invite(body: ws.AcceptInviteIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    mem = workspace_svc.accept_invitation(db, user, body.token)
    return {"workspace_id": mem.workspace_id, "role": mem.role}


@router.patch("/current/members/{membership_id}", response_model=ws.MemberOut)
def update_member_role(membership_id: int, body: ws.MemberRoleIn, ctx: WorkspaceCtx = Depends(workspace_context),
                       db: Session = Depends(get_db)):
    mem = workspace_svc.set_member_role(db, ctx, membership_id, body.role)
    u = db.get(models.User, mem.user_id)
    return ws.MemberOut(
        id=mem.id, user_id=mem.user_id, email=u.email if u else "", name=u.name if u else "",
        role=mem.role, status=mem.status, joined_at=mem.joined_at,
    )


@router.delete("/current/members/{membership_id}", status_code=204)
def remove_member(membership_id: int, ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    workspace_svc.remove_member(db, ctx, membership_id)


@router.post("/current/transfer")
def transfer_owner(body: ws.TransferOwnerIn, ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    workspace_svc.transfer_ownership(db, ctx, body.new_owner_user_id, body.confirm)
    return {"status": "transferred"}


@router.post("/current/delete")
def schedule_delete(body: ws.DeleteWorkspaceIn, ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    workspace_svc.mark_delete_workspace(db, ctx, body.confirm_name, body.confirm)
    return {"status": "marked_for_deletion"}


@router.get("/current/activity", response_model=list[ws.ActivityOut])
def activity(ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db), limit: int = 50):
    ctx.require("activity.read")
    rows = (
        db.query(models.AuditLog)
        .filter(models.AuditLog.workspace_id == ctx.workspace_id)
        .order_by(models.AuditLog.id.desc())
        .limit(min(limit, 200))
        .all()
    )
    return [ws.ActivityOut.model_validate(r) for r in reversed(rows)]


@router.get("/deals/{deal_id}/assignments", response_model=list[ws.DealAssignmentOut])
def list_assignments(deal_id: int, ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    get_deal(db, ctx, deal_id)
    rows = db.query(models.DealAssignment).filter_by(workspace_id=ctx.workspace_id, deal_id=deal_id).all()
    return [ws.DealAssignmentOut.model_validate(r) for r in rows]


@router.post("/deals/{deal_id}/assignments", response_model=ws.DealAssignmentOut, status_code=201)
def post_assignment(deal_id: int, body: ws.DealAssignmentIn, ctx: WorkspaceCtx = Depends(workspace_context),
                    db: Session = Depends(get_db)):
    return workspace_svc.assign_deal(db, ctx, deal_id, body.user_id, body.assignment_role)


@router.get("/tasks", response_model=list[ws.TaskOut])
def list_tasks(ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db), status: str | None = None):
    ctx.require("tasks.read")
    q = db.query(models.WorkspaceTask).filter_by(workspace_id=ctx.workspace_id)
    if status:
        q = q.filter_by(status=status)
    if ctx.role == "editor":
        q = q.filter(
            (models.WorkspaceTask.assignee_user_id == ctx.user.id)
            | (models.WorkspaceTask.created_by_user_id == ctx.user.id)
        )
    return q.order_by(models.WorkspaceTask.id.desc()).limit(100).all()


@router.post("/tasks", response_model=ws.TaskOut, status_code=201)
def create_task(body: ws.TaskIn, ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    return workspace_svc.create_task(db, ctx, body)


@router.patch("/tasks/{task_id}", response_model=ws.TaskOut)
def patch_task(task_id: int, body: ws.TaskPatchIn, ctx: WorkspaceCtx = Depends(workspace_context),
               db: Session = Depends(get_db)):
    ctx.require("tasks.write")
    task = db.get(models.WorkspaceTask, task_id)
    if not task or task.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Task not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(task, k, v)
    db.commit()
    return task

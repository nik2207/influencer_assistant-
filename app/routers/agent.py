from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db
from ..security import workspace_context
from ..services.tenancy import WorkspaceCtx
from ..services import agent as agent_service

router = APIRouter(prefix="/agent", tags=["assistant"])


@router.post("/chat", response_model=schemas.ChatOut)
def chat(body: schemas.ChatIn, ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    return agent_service.handle_message(db, ctx.user, body.message, ctx=ctx)


@router.get("/history", response_model=list[schemas.ChatHistoryLine])
def history(ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    rows = (
        db.query(models.ChatMessage)
        .filter_by(user_id=ctx.user.id)
        .filter(
            (models.ChatMessage.workspace_id == ctx.workspace_id)
            | (models.ChatMessage.workspace_id.is_(None)),
        )
        .order_by(models.ChatMessage.id.desc())
        .limit(30)
        .all()
    )
    out = []
    for r in reversed(rows):
        meta = r.voice_meta if isinstance(r.voice_meta, dict) else {}
        out.append({
            "role": r.role,
            "content": r.content,
            "source": getattr(r, "source", None) or "text",
            "detected_language": meta.get("detected_language") or "",
        })
    return out


@router.get("/pending", response_model=list[schemas.PendingOut])
def pending(ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    return db.query(models.PendingAction).filter_by(
        workspace_id=ctx.workspace_id, status="pending",
    ).order_by(models.PendingAction.id.desc()).all()


@router.post("/approve/{action_id}")
def approve(action_id: int, ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    return agent_service.resolve_pending(db, ctx.user, action_id, True, ctx=ctx)


@router.post("/reject/{action_id}")
def reject(action_id: int, ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    return agent_service.resolve_pending(db, ctx.user, action_id, False, ctx=ctx)

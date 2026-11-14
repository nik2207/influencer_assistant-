from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db
from ..security import workspace_context
from ..services.tenancy import WorkspaceCtx, events_query, get_event, stamp
from ..services import calendar_sync, tools

router = APIRouter(prefix="/events", tags=["calendar"])


@router.get("", response_model=list[schemas.EventOut])
def list_events(ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    return events_query(db, ctx).order_by(models.Event.start_at).all()


@router.post("", status_code=201)
def create_event(body: schemas.EventIn, ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    ctx.require("calendar.write")
    user = ctx.user
    start = body.start_at.replace(tzinfo=None)
    end = (body.end_at or body.start_at + timedelta(hours=1)).replace(tzinfo=None)
    if end <= start:
        raise HTTPException(422, "end_at must be after start_at")
    res = calendar_sync.add_event(db, user, body.title, start, end, body.location, workspace_id=ctx.workspace_id)
    return {"event": schemas.EventOut.model_validate(res["event"]),
            "conflicts": [tools.event_dict(c) for c in res["conflicts"]],
            "google_synced": res["google_synced"], "google_error": res["google_error"]}


@router.delete("/{event_id}", status_code=204)
def delete_event(event_id: int, ctx: WorkspaceCtx = Depends(workspace_context), db: Session = Depends(get_db)):
    ctx.require("calendar.write")
    ev = get_event(db, ctx, event_id)
    calendar_sync.remove_event(db, ctx.user, ev)

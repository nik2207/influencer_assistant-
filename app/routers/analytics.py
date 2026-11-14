from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..models import ANALYTICS_PLATFORMS, METRIC_KEYS, METRIC_SOURCES
from ..schemas_analytics import ContentItemIn, ContentOut, ManualMetricIn, SnapshotOut
from ..security import audit, current_user, decode_token, make_token
from ..services import analytics as an
from ..services import analytics_oauth as oauth
from ..services import analytics_reports as reports

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _snap_out(row: models.MetricSnapshot) -> dict:
    return SnapshotOut.model_validate(row).model_dump()


@router.get("/meta")
def meta():
    return {
        "platforms": list(ANALYTICS_PLATFORMS),
        "metrics": list(METRIC_KEYS),
        "sources": list(METRIC_SOURCES),
        "confidence": ["verified", "unverified"],
    }


@router.get("/overview")
def overview(from_date: date | None = None, to_date: date | None = None,
             user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    to_date = to_date or date.today()
    from_date = from_date or (to_date - timedelta(days=30))
    if to_date < from_date:
        raise HTTPException(400, "End date must be on or after start date.")
    return an.overview(db, user, from_date, to_date)


@router.get("/platforms")
def platforms(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    cards = an.platforms_overview(db, user)
    for plat in ("youtube", "instagram", "tiktok"):
        conn = oauth.connection_public(db, user, plat)
        for c in cards:
            if c["platform"] == plat:
                c["oauth"] = conn
    return cards


@router.get("/metrics", response_model=list[SnapshotOut])
def list_metrics(platform: str = "", metric_key: str = "",
                 from_date: date | None = None, to_date: date | None = None,
                 user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return an.list_snapshots(db, user, platform=platform, metric_key=metric_key,
                             from_date=from_date, to_date=to_date)


@router.post("/metrics", response_model=SnapshotOut)
def add_metric(body: ManualMetricIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        row = an.add_manual_snapshot(db, user, body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    audit(db, user.id, "metric_manual", f"{row.platform}:{row.metric_key}")
    return row


@router.delete("/metrics/{snapshot_id}")
def delete_metric(snapshot_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    if not an.delete_snapshot(db, user, snapshot_id):
        raise HTTPException(404, "Metric not found")
    audit(db, user.id, "metric_deleted", str(snapshot_id))
    return {"ok": True}


@router.get("/chart")
def chart(platform: str, metric_key: str, from_date: date = Query(...), to_date: date = Query(...),
          grain: str = Query("day", pattern="^(day|week|month)$"),
          user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    if platform not in ANALYTICS_PLATFORMS or metric_key not in METRIC_KEYS:
        raise HTTPException(400, "Invalid platform or metric")
    return an.chart_series(db, user, platform, metric_key, from_date, to_date, grain=grain)


@router.get("/growth")
def growth(platform: str, metric_key: str, from_date: date = Query(...), to_date: date = Query(...),
           user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return an.growth(db, user, platform, metric_key, from_date, to_date)


@router.get("/compare")
def compare(metric_key: str, from_date: date = Query(...), to_date: date = Query(...),
            user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    if metric_key not in METRIC_KEYS:
        raise HTTPException(400, "Invalid metric")
    return an.compare_platforms(db, user, metric_key, from_date, to_date)


@router.get("/content", response_model=list[ContentOut])
def list_content(platform: str = "", limit: int = 20,
                 user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return an.top_content(db, user, platform=platform, limit=limit)


@router.post("/content", response_model=ContentOut)
def add_content(body: ContentItemIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        row = an.add_content(db, user, body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    audit(db, user.id, "content_added", body.platform)
    return row


@router.get("/insights")
def insights(from_date: date | None = None, to_date: date | None = None,
             user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    to_date = to_date or date.today()
    from_date = from_date or (to_date - timedelta(days=30))
    return {"text": an.insights_text(db, user, from_date, to_date)}


@router.post("/import")
async def import_csv(file: UploadFile = File(...), user: models.User = Depends(current_user),
                     db: Session = Depends(get_db)):
    data = await file.read()
    if len(data) > 2_000_000:
        raise HTTPException(413, "File too large (max 2MB).")
    batch = an.parse_csv_import(db, user, file.filename or "import.csv", data)
    audit(db, user.id, "analytics_import", f"{batch.id}:{batch.row_count}")
    return {"batch_id": batch.id, "status": batch.status, "row_count": batch.row_count,
            "errors": batch.errors_json}


@router.get("/export/csv")
def export_csv(from_date: date = Query(...), to_date: date = Query(...),
               user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    body = an.export_csv(db, user, from_date, to_date)
    fname = f"analytics-{from_date.isoformat()}-{to_date.isoformat()}.csv"
    return PlainTextResponse(body, media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/export/pdf")
def export_pdf(from_date: date = Query(...), to_date: date = Query(...),
               user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    path = reports.build_analytics_pdf(db, user, from_date, to_date)
    return FileResponse(path, media_type="application/pdf",
                        filename=f"analytics-{from_date.isoformat()}.pdf")


@router.get("/connect/{platform}")
def connect_platform(platform: str, user: models.User = Depends(current_user)):
    if platform == "youtube":
        if not oauth.youtube_available():
            raise HTTPException(503, "Google OAuth is not configured. Add metrics manually or import CSV.")
        state = make_token(user.id, "analytics_oauth", 10)
        return {"url": oauth.build_youtube_auth_url(state), "platform": platform}
    if platform in ("instagram", "tiktok"):
        raise HTTPException(503, f"{platform.title()} API connection requires app credentials. Use manual metrics for now.")
    raise HTTPException(404, "Unknown platform")


@router.get("/oauth/callback", include_in_schema=False)
def oauth_callback(code: str = "", state: str = "", error: str = "", db: Session = Depends(get_db)):
    from fastapi.responses import RedirectResponse

    if error or not code:
        return RedirectResponse("/app/#/analytics?connect=denied")
    user = db.get(models.User, decode_token(state, "analytics_oauth"))
    if not user:
        raise HTTPException(400, "Invalid state")
    try:
        tokens = oauth.exchange_code(code)
        oauth.store_youtube_tokens(db, user, tokens)
        audit(db, user.id, "analytics_youtube_connected", "ok")
    except Exception:
        return RedirectResponse("/app/#/analytics?connect=error")
    return RedirectResponse("/app/#/analytics?connect=ok")


@router.post("/sync/{platform}")
def sync_platform(platform: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    if platform == "youtube":
        result = oauth.sync_youtube(db, user)
        if result.get("error"):
            raise HTTPException(400, result["error"])
        return result
    raise HTTPException(503, "Sync is not available for this platform yet. Use manual entry.")


@router.delete("/connect/{platform}")
def disconnect_platform(platform: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    oauth.disconnect(db, user, platform)
    audit(db, user.id, "analytics_disconnected", platform)
    return {"ok": True}

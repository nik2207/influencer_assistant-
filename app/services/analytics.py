"""Creator analytics: snapshots, growth, comparisons, insights (data-only, no fabrication)."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .. import models
from ..services import profile as profile_svc
from ..services.personas import PLATFORMS

METRIC_KEYS = models.METRIC_KEYS
POINT_IN_TIME = {"followers", "engagement_rate"}


def _acct(db: Session, user: models.User, account_id: int) -> models.SocialAccount:
    row = db.get(models.SocialAccount, account_id)
    if not row or row.user_id != user.id:
        raise ValueError("Social account not found")
    return row


def _deal_ok(db: Session, user: models.User, deal_id: Optional[int]) -> None:
    if deal_id is None:
        return
    deal = db.get(models.Deal, deal_id)
    if not deal or deal.user_id != user.id:
        raise ValueError("Deal not found")


def add_manual_snapshot(db: Session, user: models.User, body: dict) -> models.MetricSnapshot:
    platform = body["platform"]
    if body.get("social_account_id"):
        acct = _acct(db, user, body["social_account_id"])
        if acct.platform != platform:
            raise ValueError("Platform does not match the linked account")
    _deal_ok(db, user, body.get("deal_id"))
    today = date.today()
    ps = body.get("period_start") or today
    pe = body.get("period_end") or ps
    row = models.MetricSnapshot(
        user_id=user.id,
        social_account_id=body.get("social_account_id"),
        platform=platform,
        metric_key=body["metric_key"],
        value=float(body["value"]),
        period_start=ps,
        period_end=pe,
        source="manual",
        confidence="verified",
        deal_id=body.get("deal_id"),
        notes=(body.get("notes") or "")[:300],
    )
    db.add(row)
    if body["metric_key"] == "followers" and body.get("social_account_id"):
        acct = _acct(db, user, body["social_account_id"])
        acct.followers = int(body["value"])
        profile_svc.sync_followers(db, user)
    db.commit()
    db.refresh(row)
    return row


def list_snapshots(db: Session, user: models.User, platform: str = "", metric_key: str = "",
                   from_date: Optional[date] = None, to_date: Optional[date] = None) -> list[models.MetricSnapshot]:
    q = db.query(models.MetricSnapshot).filter_by(user_id=user.id)
    if platform:
        q = q.filter_by(platform=platform)
    if metric_key:
        q = q.filter_by(metric_key=metric_key)
    if from_date:
        q = q.filter(models.MetricSnapshot.period_start >= from_date)
    if to_date:
        q = q.filter(models.MetricSnapshot.period_start <= to_date)
    return q.order_by(models.MetricSnapshot.period_start.desc(), models.MetricSnapshot.id.desc()).all()


def delete_snapshot(db: Session, user: models.User, snapshot_id: int) -> bool:
    row = db.get(models.MetricSnapshot, snapshot_id)
    if not row or row.user_id != user.id:
        return False
    db.delete(row)
    db.commit()
    return True


def platforms_overview(db: Session, user: models.User) -> list[dict]:
    accts = profile_svc.platforms_of(db, user)
    out = []
    for a in accts:
        conn = db.query(models.PlatformConnection).filter_by(user_id=user.id, platform=a.platform).first()
        out.append({
            "platform": a.platform,
            "label": PLATFORMS.get(a.platform, {}).get("label", a.platform),
            "social_account_id": a.id,
            "handle": a.handle,
            "url": a.url,
            "followers": a.followers,
            "connection_status": a.connection_status,
            "oauth_status": conn.status if conn else "disconnected",
            "last_synced_at": a.last_synced_at.isoformat() if a.last_synced_at else None,
        })
    return out


def _series(db: Session, user: models.User, platform: str, metric_key: str,
            from_date: date, to_date: date) -> list[dict]:
    rows = list_snapshots(db, user, platform=platform, metric_key=metric_key, from_date=from_date, to_date=to_date)
    return [{"date": (r.period_start or r.created_at.date()).isoformat(), "value": r.value,
             "source": r.source, "confidence": r.confidence} for r in reversed(rows)]


def growth(db: Session, user: models.User, platform: str, metric_key: str,
           from_date: date, to_date: date) -> dict:
    series = _series(db, user, platform, metric_key, from_date, to_date)
    if len(series) < 2:
        return {"platform": platform, "metric_key": metric_key, "delta": 0, "pct": 0.0,
                "from_value": series[0]["value"] if series else None,
                "to_value": series[-1]["value"] if series else None, "points": len(series)}
    a, b = series[0]["value"], series[-1]["value"]
    delta = b - a
    pct = round(100 * delta / a, 2) if a else 0.0
    return {"platform": platform, "metric_key": metric_key, "delta": delta, "pct": pct,
            "from_value": a, "to_value": b, "points": len(series)}


def compare_platforms(db: Session, user: models.User, metric_key: str,
                      from_date: date, to_date: date) -> list[dict]:
    accts = {a.platform: a for a in profile_svc.platforms_of(db, user)}
    out = []
    for plat in accts:
        g = growth(db, user, plat, metric_key, from_date, to_date)
        latest = list_snapshots(db, user, platform=plat, metric_key=metric_key, to_date=to_date)
        lv = latest[0].value if latest else None
        src = latest[0].source if latest else None
        out.append({**g, "latest": lv, "latest_source": src})
    return out


def overview(db: Session, user: models.User, from_date: date, to_date: date) -> dict:
    cards = []
    for plat_info in platforms_overview(db, user):
        plat = plat_info["platform"]
        latest_metrics = {}
        for mk in METRIC_KEYS:
            rows = list_snapshots(db, user, platform=plat, metric_key=mk, from_date=from_date, to_date=to_date)
            if rows:
                latest_metrics[mk] = {"value": rows[0].value, "source": rows[0].source,
                                      "confidence": rows[0].confidence}
        cards.append({**plat_info, "metrics": latest_metrics,
                      "growth_followers": growth(db, user, plat, "followers", from_date, to_date)
                      if "followers" in latest_metrics or plat_info["followers"] else None})
    return {"from_date": from_date.isoformat(), "to_date": to_date.isoformat(), "platforms": cards}


def chart_series(db: Session, user: models.User, platform: str, metric_key: str,
                 from_date: date, to_date: date, grain: str = "day") -> list[dict]:
    series = _series(db, user, platform, metric_key, from_date, to_date)
    if grain == "week":
        buckets: dict[str, list[float]] = {}
        for p in series:
            d = date.fromisoformat(p["date"])
            wk = (d - timedelta(days=d.weekday())).isoformat()
            buckets.setdefault(wk, []).append(p["value"])
        return [{"period": k, "value": buckets[k][-1], "source": "mixed"} for k in sorted(buckets)]
    if grain == "month":
        buckets: dict[str, list[float]] = {}
        for p in series:
            d = date.fromisoformat(p["date"])
            mk = f"{d.year}-{d.month:02d}"
            buckets.setdefault(mk, []).append(p["value"])
        return [{"period": k, "value": buckets[k][-1], "source": "mixed"} for k in sorted(buckets)]
    return [{"period": p["date"], "value": p["value"], "source": p["source"]} for p in series]


def add_content(db: Session, user: models.User, body: dict) -> models.ContentItem:
    if body.get("social_account_id"):
        _acct(db, user, body["social_account_id"])
    _deal_ok(db, user, body.get("deal_id"))
    row = models.ContentItem(
        user_id=user.id,
        social_account_id=body.get("social_account_id"),
        platform=body["platform"],
        title=body["title"][:255],
        permalink=(body.get("permalink") or "")[:400],
        published_at=body.get("published_at"),
        views=float(body.get("views") or 0),
        engagement=float(body.get("engagement") or 0),
        source="manual",
        deal_id=body.get("deal_id"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def top_content(db: Session, user: models.User, platform: str = "", limit: int = 10) -> list[models.ContentItem]:
    q = db.query(models.ContentItem).filter_by(user_id=user.id)
    if platform:
        q = q.filter_by(platform=platform)
    limit = max(1, min(limit, 50))
    return q.order_by(models.ContentItem.views.desc(), models.ContentItem.engagement.desc()).limit(limit).all()


def insights_text(db: Session, user: models.User, from_date: date, to_date: date) -> str:
    ov = overview(db, user, from_date, to_date)
    lines = [f"Analytics summary ({from_date} to {to_date}). Only stored data is used; nothing is estimated."]
    for p in ov["platforms"]:
        name = p["label"]
        bits = []
        mets = p.get("metrics") or {}
        if "followers" in mets:
            bits.append(f"followers {int(mets['followers']['value']):,} ({mets['followers']['source']})")
        g = p.get("growth_followers")
        if g and g.get("points", 0) >= 2:
            bits.append(f"follower change {g['delta']:+,} ({g['pct']:+.1f}%) in range")
        if not bits and p.get("followers"):
            bits.append(f"profile shows {p['followers']:,} followers (manual profile entry)")
        if bits:
            lines.append(f"• {name}: " + "; ".join(bits))
        else:
            lines.append(f"• {name}: no metrics logged in this period — add manual entries or connect when available.")
    top = top_content(db, user, limit=3)
    if top:
        lines.append("Top content by views (as recorded):")
        for c in top:
            lines.append(f"  - {c.title or 'Untitled'} ({c.platform}): {int(c.views):,} views, "
                         f"{int(c.engagement):,} engagement [{c.source}]")
    else:
        lines.append("No content items recorded yet.")
    missing = [p["label"] for p in ov["platforms"] if not p.get("metrics")]
    if missing:
        lines.append("Missing metrics for: " + ", ".join(missing) + ". Import CSV or enter figures manually.")
    return "\n".join(lines)


def parse_csv_import(db: Session, user: models.User, filename: str, data: bytes) -> models.ImportBatch:
    batch = models.ImportBatch(user_id=user.id, filename=filename[:255], status="processing")
    db.add(batch)
    db.commit()
    errors = []
    count = 0
    try:
        text = data.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        required = {"date", "platform", "metric", "value"}
        names = {h.strip().lower() for h in (reader.fieldnames or [])}
        if not names or not required.issubset(names):
            raise ValueError(f"CSV must include columns: {', '.join(sorted(required))}")
        for i, row in enumerate(reader, start=2):
            try:
                norm = {k.strip().lower(): (v or "").strip() for k, v in row.items()}
                plat = norm.get("platform", "").lower()
                mk = norm.get("metric", "").lower()
                val = float(norm.get("value", "").replace(",", ""))
                ps = date.fromisoformat(norm.get("date", "")[:10])
                if plat not in models.ANALYTICS_PLATFORMS or mk not in METRIC_KEYS:
                    raise ValueError("invalid platform or metric")
                snap = models.MetricSnapshot(
                    user_id=user.id, platform=plat, metric_key=mk, value=val,
                    period_start=ps, period_end=ps, source="import", confidence="unverified",
                    notes=f"import batch #{batch.id}",
                )
                db.add(snap)
                count += 1
            except Exception as ex:
                errors.append(f"row {i}: {ex}")
        batch.row_count = count
        batch.errors_json = errors[:50]
        batch.status = "completed" if count else "failed"
        db.commit()
    except Exception as ex:
        batch.status = "failed"
        batch.errors_json = [str(ex)]
        db.commit()
    return batch


def export_csv(db: Session, user: models.User, from_date: date, to_date: date) -> str:
    rows = list_snapshots(db, user, from_date=from_date, to_date=to_date)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "platform", "metric", "value", "source", "confidence", "notes"])
    for r in rows:
        w.writerow([
            (r.period_start or r.created_at.date()).isoformat(),
            r.platform, r.metric_key, r.value, r.source, r.confidence, r.notes,
        ])
    return buf.getvalue()

from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from .. import models
from . import analytics as an

OUT_DIR = Path("data/reports")


def build_analytics_pdf(db: Session, user: models.User, from_date, to_date) -> str:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    path = OUT_DIR / f"analytics-{user.id}-{stamp}.pdf"
    ov = an.overview(db, user, from_date, to_date)
    insights = an.insights_text(db, user, from_date, to_date)
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    y = h - 22 * mm
    c.setFont("Helvetica-Bold", 18)
    c.drawString(20 * mm, y, "Creator Analytics Report")
    c.setFont("Helvetica", 10)
    y -= 8 * mm
    c.drawString(20 * mm, y, f"{user.name or user.email}")
    c.drawRightString(w - 20 * mm, y, f"{from_date:%d %b %Y} — {to_date:%d %b %Y}")
    y -= 10 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, "Platform summary")
    y -= 6 * mm
    c.setFont("Helvetica", 9)
    for p in ov["platforms"]:
        if y < 35 * mm:
            c.showPage()
            y = h - 25 * mm
        line = f"{p['label']}: {p.get('followers', 0):,} followers ({p.get('connection_status', 'manual')})"
        c.drawString(22 * mm, y, line[:95])
        y -= 5 * mm
        mets = p.get("metrics") or {}
        for mk, info in mets.items():
            tag = f"[{info['source']}/{info['confidence']}]"
            c.drawString(26 * mm, y, f"{mk}: {info['value']:,.0f} {tag}"[:100])
            y -= 4.5 * mm
        y -= 2 * mm
    y -= 4 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, "Insights (from stored data only)")
    y -= 6 * mm
    c.setFont("Helvetica", 9)
    for line in insights.splitlines():
        if y < 25 * mm:
            c.showPage()
            y = h - 25 * mm
        for chunk in [line[i:i + 100] for i in range(0, len(line), 100)]:
            c.drawString(22 * mm, y, chunk)
            y -= 4.5 * mm
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, 12 * mm, f"Generated {datetime.now():%d %b %Y %H:%M} · Verified vs unverified sources are labelled in-app.")
    c.showPage()
    c.save()
    return str(path)

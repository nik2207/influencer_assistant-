"""Media kit PDF (separate from invoice PDF). Multiple visual templates."""
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

OUT_DIR = Path("data/media-kit-pdf")

SYMS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "AED": "AED "}


def _money(amount: float, currency: str) -> str:
    sym = SYMS.get(currency, f"{currency} ")
    return f"{sym}{amount:,.0f}"


def _header(c: canvas.Canvas, w, h, template: str, title: str):
    if template == "bold":
        c.setFillColorRGB(0.06, 0.29, 0.36)
        c.rect(0, h - 35 * mm, w, 35 * mm, fill=1, stroke=0)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 20)
        c.drawString(20 * mm, h - 22 * mm, title[:70])
        c.setFillColorRGB(0, 0, 0)
        return h - 42 * mm
    if template == "minimal":
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 15 * mm, "MEDIA KIT")
        c.setFont("Helvetica-Bold", 18)
        c.drawString(20 * mm, h - 24 * mm, title[:70])
        return h - 32 * mm
    c.setFont("Helvetica-Bold", 22)
    c.drawString(20 * mm, h - 22 * mm, title[:70])
    c.line(20 * mm, h - 26 * mm, w - 20 * mm, h - 26 * mm)
    return h - 34 * mm


def build_media_kit_pdf(preview: dict, template: str = "classic", avatar_path: str = "") -> str:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    uid = preview.get("creator", {}).get("name", "creator").replace(" ", "-")[:20]
    path = OUT_DIR / f"kit-{uid}-{datetime.now().strftime('%Y%m%d%H%M')}.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    tpl = template if template in ("classic", "minimal", "bold") else "classic"
    cr = preview.get("creator", {})
    title = cr.get("headline") or cr.get("name") or "Media Kit"
    y = _header(c, w, h, tpl, title)

    if avatar_path and Path(avatar_path).exists():
        try:
            c.drawImage(avatar_path, w - 45 * mm, h - 32 * mm, 22 * mm, 22 * mm, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass

    c.setFont("Helvetica", 10)
    y -= 4 * mm
    sub = f"{cr.get('niche', '')} · {cr.get('creator_type', '')} · {cr.get('city', '')}".strip(" ·")
    if sub:
        c.drawString(20 * mm, y, sub[:95])
        y -= 6 * mm
    intro = (cr.get("intro") or "")[:900]
    for line in [intro[i:i + 95] for i in range(0, len(intro), 95)]:
        if y < 30 * mm:
            c.showPage()
            y = h - 25 * mm
        c.drawString(20 * mm, y, line)
        y -= 4.5 * mm

    def section(name):
        nonlocal y
        y -= 4 * mm
        if y < 35 * mm:
            c.showPage()
            y = h - 25 * mm
        c.setFont("Helvetica-Bold", 11)
        c.drawString(20 * mm, y, name)
        y -= 6 * mm
        c.setFont("Helvetica", 9)

    section("Platforms & audience")
    for p in preview.get("platforms") or []:
        line = f"{p.get('label')}: {p.get('handle', '')} — {int(p.get('followers') or 0):,} followers (profile)"
        c.drawString(22 * mm, y, line[:100])
        y -= 4.5 * mm
        for m in (p.get("metrics") or [])[:4]:
            tag = f"[{m.get('source')}/{m.get('confidence')}]"
            c.drawString(26 * mm, y, f"{m.get('metric')}: {m.get('value'):,.0f} {tag}"[:100])
            y -= 4 * mm
        if y < 25 * mm:
            c.showPage()
            y = h - 25 * mm

    if preview.get("rates"):
        section("Rate card")
        for r in preview["rates"]:
            c.drawString(22 * mm, y, f"{r.get('title') or r.get('deliverable')}: {_money(r.get('price', 0), r.get('currency', 'INR'))}"[:100])
            y -= 4.5 * mm

    if preview.get("portfolio"):
        section("Collaborations")
        for item in preview["portfolio"]:
            c.drawString(22 * mm, y, f"{item.get('brand')}: {item.get('summary') or item.get('deliverables', '')}"[:100])
            y -= 4.5 * mm

    if preview.get("samples"):
        section("Content samples")
        for s in preview["samples"]:
            c.drawString(22 * mm, y, f"{s.get('title')} ({s.get('platform')})"[:80])
            y -= 4 * mm
            if s.get("url"):
                c.drawString(26 * mm, y, s["url"][:95])
                y -= 4 * mm

    contact = preview.get("contact") or {}
    if contact.get("email") or contact.get("phone"):
        section("Contact")
        if contact.get("email"):
            c.drawString(22 * mm, y, contact["email"][:95])
            y -= 4.5 * mm
        if contact.get("phone"):
            c.drawString(22 * mm, y, contact["phone"][:40])
            y -= 4.5 * mm

    c.setFont("Helvetica", 7)
    c.drawString(20 * mm, 12 * mm, preview.get("disclaimer", "")[:120])
    c.drawRightString(w - 20 * mm, 12 * mm, f"Generated {datetime.now():%d %b %Y} · Template: {tpl}")
    c.showPage()
    c.save()
    return str(path)

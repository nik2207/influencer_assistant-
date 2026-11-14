"""Campaign ROI — decimal-safe, no double-counting between deals and invoices."""
from __future__ import annotations

import csv
import io
import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..schemas_campaign_roi import CampaignRoiOut, PortfolioRoiSummary, RoiComparePoint, RoiMoney
from . import invoices as inv_svc
from . import llm

Q = Decimal("0.01")
DISCLAIMER = CampaignRoiOut.model_fields["disclaimer"].default


def _d(x) -> Decimal:
    if x is None:
        return Decimal("0")
    return Decimal(str(x)).quantize(Q, rounding=ROUND_HALF_UP)


def _f(d: Decimal | float | int) -> float:
    if not isinstance(d, Decimal):
        d = _d(d)
    return float(d.quantize(Q, rounding=ROUND_HALF_UP))


def _money(amount: Decimal, source: str, label: str = "", is_estimate: bool = False) -> RoiMoney:
    return RoiMoney(amount_inr=_f(amount), source=source, label=label, is_estimate=is_estimate)


def _owned(db: Session, user: models.User, deal_id: int, workspace_id: int | None = None) -> models.Deal:
    deal = db.get(models.Deal, deal_id)
    if not deal:
        raise ValueError("Deal not found")
    if workspace_id is not None:
        if deal.workspace_id != workspace_id:
            raise ValueError("Deal not found")
    elif deal.user_id != user.id:
        raise ValueError("Deal not found")
    return deal


def _invoices_for_deal(db: Session, user: models.User, deal_id: int) -> list[models.Invoice]:
    rows = db.query(models.Invoice).filter_by(user_id=user.id, deal_id=deal_id).all()
    for inv in rows:
        inv_svc.apply_overdue(inv)
    return [i for i in rows if i.status != "cancelled"]


def _invoiced_total(invoices: list[models.Invoice], from_date: Optional[date], to_date: Optional[date]) -> Decimal:
    total = Decimal("0")
    for inv in invoices:
        if inv.status == "draft":
            continue
        if from_date and inv.issue_date and inv.issue_date < from_date:
            continue
        if to_date and inv.issue_date and inv.issue_date > to_date:
            continue
        total += _d(inv.amount_inr)
    return total


def _received_total(db: Session, user: models.User, invoices: list[models.Invoice],
                    from_date: Optional[date], to_date: Optional[date]) -> Decimal:
    ids = [i.id for i in invoices if i.status != "draft"]
    if not ids:
        return Decimal("0")
    pays = db.query(models.InvoicePayment).filter(
        models.InvoicePayment.user_id == user.id,
        models.InvoicePayment.invoice_id.in_(ids),
    ).all()
    total = Decimal("0")
    for p in pays:
        if from_date and p.paid_at < from_date:
            continue
        if to_date and p.paid_at > to_date:
            continue
        total += _d(p.amount_inr)
    return total


def _outstanding_total(invoices: list[models.Invoice]) -> Decimal:
    total = Decimal("0")
    for inv in invoices:
        if inv.status in ("sent", "partially_paid", "overdue"):
            bal = _d(inv.amount_inr) - _d(inv.paid_inr)
            if bal > 0:
                total += bal
    return total


def _expenses(db: Session, user: models.User, deal_id: int,
              from_date: Optional[date], to_date: Optional[date]) -> Decimal:
    q = db.query(models.Expense).filter_by(user_id=user.id, deal_id=deal_id)
    if from_date:
        q = q.filter(models.Expense.spent_on >= from_date)
    if to_date:
        q = q.filter(models.Expense.spent_on <= to_date)
    return sum((_d(e.amount_inr) for e in q.all()), Decimal("0"))


def _engagement(db: Session, user: models.User, deal_id: int) -> Decimal:
    rows = db.query(models.ContentItem).filter_by(user_id=user.id, deal_id=deal_id).all()
    return sum((_d(r.engagement) for r in rows if r.engagement), Decimal("0"))


def _deliverable_counts(db: Session, user: models.User, deal: models.Deal) -> tuple[int, int]:
    published = db.query(models.ContentPlanItem).filter_by(user_id=user.id, deal_id=deal.id, status="published").count()
    content_items = db.query(models.ContentItem).filter_by(user_id=user.id, deal_id=deal.id).count()
    actual = max(published, content_items)
    est = 0
    if deal.deliverables:
        found = re.findall(r"(\d+)\s*(reels?|stories|story|posts?|videos?|shorts)", deal.deliverables.lower())
        est = sum(int(n) for n, _ in found) if found else (1 if deal.deliverables.strip() else 0)
    elif db.query(models.ContentPlanItem).filter_by(user_id=user.id, deal_id=deal.id).count():
        est = db.query(models.ContentPlanItem).filter_by(user_id=user.id, deal_id=deal.id).count()
    return actual, est


def compute_deal_roi(db: Session, user: models.User, deal_id: int,
                     from_date: Optional[date] = None, to_date: Optional[date] = None,
                     workspace_id: int | None = None) -> CampaignRoiOut:
    deal = _owned(db, user, deal_id, workspace_id=workspace_id)
    invoices = _invoices_for_deal(db, user, deal_id)
    gaps: list[str] = []

    invoiced = _invoiced_total(invoices, from_date, to_date)
    received = _received_total(db, user, invoices, from_date, to_date)
    outstanding = _outstanding_total(invoices)

    if invoiced > 0:
        invoiced_money = _money(invoiced, "invoices", "Sum of sent invoice totals")
    elif _d(deal.value_inr) > 0:
        src = "barter_reference" if deal.kind == "barter" else "deal_value_estimate"
        invoiced_money = _money(_d(deal.value_inr), src, "Deal value (no invoice yet)", is_estimate=True)
        gaps.append("no_invoices")
    else:
        invoiced_money = _money(Decimal("0"), "none", "No booked amount")
        gaps.append("no_booked_amount")

    actual_exp = _expenses(db, user, deal_id, from_date, to_date)
    est_prod = _d(getattr(deal, "production_cost_estimate_inr", 0) or 0)
    if est_prod <= 0:
        gaps.append("production_estimate_missing")

    total_cost = actual_exp + est_prod
    net_cash = received - actual_exp
    profit = received - actual_exp - est_prod

    roi_pct = None
    if total_cost > 0:
        roi_pct = _f((profit / total_cost) * Decimal("100"))

    engagement = _engagement(db, user, deal_id)
    actual_del, est_del = _deliverable_counts(db, user, deal)
    cpe = None
    if engagement > 0 and total_cost > 0:
        cpe = _f(total_cost / engagement)
    elif engagement == 0:
        gaps.append("no_engagement")

    rpd = None
    if actual_del > 0 and received > 0:
        rpd = _f(received / Decimal(actual_del))
    elif est_del > 0 and received > 0:
        rpd = _f(received / Decimal(est_del))
        gaps.append("deliverable_count_estimated")

    booked_for_delta = invoiced if invoiced > 0 else _d(deal.value_inr)
    est_vs = {
        "revenue": {
            "estimated_inr": invoiced_money.amount_inr if invoiced_money.is_estimate else _f(invoiced),
            "actual_received_inr": _f(received),
            "delta_inr": _f(received - booked_for_delta),
        },
        "deliverables": {"estimated_count": est_del, "actual_count": actual_del},
    }

    return CampaignRoiOut(
        deal_id=deal.id,
        brand=deal.brand,
        kind=deal.kind,
        status=deal.status,
        invoiced_revenue=invoiced_money,
        received_revenue=_money(received, "invoice_payments", "Sum of recorded payments"),
        outstanding=_money(outstanding, "invoice_balances", "Unpaid invoice balances"),
        actual_expenses=_money(actual_exp, "expenses", "Expenses linked to this deal"),
        estimated_expenses=_money(est_prod, "deal_estimate", "Manual production cost estimate", is_estimate=True),
        total_cost=_money(total_cost, "computed", "Actual expenses + production estimate"),
        net_cash_flow=_money(net_cash, "computed", "Received − actual expenses (cash)"),
        profit_estimate=_money(profit, "computed", "Received − actual − estimated production", is_estimate=est_prod > 0),
        roi_pct=roi_pct,
        cost_per_engagement=cpe,
        revenue_per_deliverable=rpd,
        engagement_total=_f(engagement) if engagement > 0 else None,
        deliverable_count_actual=actual_del,
        deliverable_count_estimated=est_del,
        estimated_vs_actual=est_vs,
        data_gaps=gaps,
        disclaimer=DISCLAIMER,
        invoice_ids=[i.id for i in invoices if i.status != "draft"],
        from_date=from_date,
        to_date=to_date,
    )


def list_campaign_roi(db: Session, user: models.User, brand: str = "",
                      from_date: Optional[date] = None, to_date: Optional[date] = None,
                      status: str = "", limit: int = 50, workspace_id: int | None = None) -> PortfolioRoiSummary:
    q = db.query(models.Deal)
    q = q.filter_by(workspace_id=workspace_id) if workspace_id else q.filter_by(user_id=user.id)
    if brand:
        q = q.filter(models.Deal.brand.ilike(f"%{brand.strip()}%"))
    if status:
        q = q.filter_by(status=status)
    deals = q.order_by(models.Deal.updated_at.desc()).limit(limit).all()
    campaigns = [compute_deal_roi(db, user, d.id, from_date, to_date) for d in deals]
    compare = [
        RoiComparePoint(
            deal_id=c.deal_id, brand=c.brand,
            invoiced_inr=c.invoiced_revenue.amount_inr,
            received_inr=c.received_revenue.amount_inr,
            profit_inr=c.profit_estimate.amount_inr,
            roi_pct=c.roi_pct,
        ) for c in campaigns
    ]
    totals = {
        "invoiced_inr": round(sum(c.invoiced_revenue.amount_inr for c in campaigns), 2),
        "received_inr": round(sum(c.received_revenue.amount_inr for c in campaigns), 2),
        "outstanding_inr": round(sum(c.outstanding.amount_inr for c in campaigns), 2),
        "actual_expenses_inr": round(sum(c.actual_expenses.amount_inr for c in campaigns), 2),
        "profit_estimate_inr": round(sum(c.profit_estimate.amount_inr for c in campaigns), 2),
    }
    return PortfolioRoiSummary(campaigns=campaigns, compare=compare, totals=totals)


def export_csv(summary: PortfolioRoiSummary) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["deal_id", "brand", "kind", "invoiced_inr", "received_inr", "outstanding_inr",
                "actual_expenses_inr", "estimated_expenses_inr", "profit_estimate_inr", "roi_pct",
                "cost_per_engagement", "revenue_per_deliverable", "data_gaps"])
    for c in summary.campaigns:
        w.writerow([
            c.deal_id, c.brand, c.kind,
            c.invoiced_revenue.amount_inr, c.received_revenue.amount_inr, c.outstanding.amount_inr,
            c.actual_expenses.amount_inr, c.estimated_expenses.amount_inr, c.profit_estimate.amount_inr,
            c.roi_pct if c.roi_pct is not None else "",
            c.cost_per_engagement if c.cost_per_engagement is not None else "",
            c.revenue_per_deliverable if c.revenue_per_deliverable is not None else "",
            ";".join(c.data_gaps),
        ])
    return buf.getvalue()


def ai_suggestions(db: Session, user: models.User, deal_id: int) -> dict:
    roi = compute_deal_roi(db, user, deal_id)
    deal = _owned(db, user, deal_id)
    facts = (
        f"Brand: {deal.brand}, kind: {deal.kind}, status: {deal.status}\n"
        f"Invoiced: ₹{roi.invoiced_revenue.amount_inr} ({roi.invoiced_revenue.source})\n"
        f"Received: ₹{roi.received_revenue.amount_inr}\n"
        f"Outstanding: ₹{roi.outstanding.amount_inr}\n"
        f"Actual expenses: ₹{roi.actual_expenses.amount_inr}\n"
        f"Production estimate: ₹{roi.estimated_expenses.amount_inr}\n"
        f"ROI%: {roi.roi_pct}\n"
        f"Gaps: {', '.join(roi.data_gaps) or 'none'}"
    )
    tips = []
    if roi.outstanding.amount_inr > 0:
        tips.append("Follow up on outstanding invoice balances before taking new scope.")
    if "no_invoices" in roi.data_gaps and deal.kind == "paid":
        tips.append("Create and send an invoice so booked revenue matches a persisted record.")
    if roi.actual_expenses.amount_inr > roi.received_revenue.amount_inr > 0:
        tips.append("Expenses exceed cash received — review deal scope or renegotiate.")
    if roi.roi_pct is not None and roi.roi_pct < 20:
        tips.append("Low ROI — consider raising rates or reducing estimated production time.")
    body = {"suggestions": tips, "facts": facts, "is_estimate": True}
    if settings.llm_provider != "openai_compat":
        return {**body, "note": "Rule-based tips from stored records only."}
    prompt = (
        "You advise an Indian creator on deal pricing using ONLY these facts. "
        "Do not invent revenue or engagement. 3 short bullets.\n\n" + facts
    )
    try:
        text = llm.simple_completion(prompt)
        if text:
            body["suggestions"] = [ln.strip("-• ") for ln in text.split("\n") if ln.strip()][:5]
    except Exception:
        pass
    return {**body, "note": "Suggestions are not financial advice. Confirm amounts in Invoices & Expenses."}

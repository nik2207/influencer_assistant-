import contextvars
import json
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..permissions import TOOL_PERMS, require_role

from .. import models
from ..models import STAGES
from ..timeutil import IST, now_ist, parse_dt  # noqa: F401  (re-exported for other modules)
from . import calendar_sync, followups, gmail_sync, logistics, outreach, payments
from . import profile as profile_service
from .calendar_client import CalendarError
from .calendar_sync import find_conflicts  # noqa: F401  (used by routers)
from .gmail_client import GmailError
from . import analytics as analytics_svc
from . import content_planner as content_svc
from . import brand_crm as brand_crm_svc
from . import email_intelligence as email_intel_svc
from . import email_matching as email_match_svc
from . import campaign_roi as campaign_roi_svc

_tool_ctx: contextvars.ContextVar = contextvars.ContextVar("ws_ctx", default=None)

SENSITIVE = {"book_ride"}  # external / third-party actions always need approval
VOICE_FINANCIAL = frozenset({"create_invoice", "record_invoice_payment", "add_expense"})


def _fn(name, description, props, required=()):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": props, "required": list(required)},
    }}


TOOL_SPECS = [
    _fn("add_deal", "Create a brand deal (paid or barter).", {
        "brand": {"type": "string"},
        "kind": {"type": "string", "enum": ["paid", "barter"]},
        "title": {"type": "string"},
        "value_inr": {"type": "number", "description": "Deal or product value in INR"},
        "deliverables": {"type": "string", "description": "For example: 2 reels, 3 stories"},
        "due_date": {"type": "string", "description": "YYYY-MM-DD"},
    }, ["brand"]),
    _fn("list_deals", "List deals, optionally filtered by stage.", {
        "status": {"type": "string", "enum": STAGES}}),
    _fn("update_deal_status", "Move a deal to a new stage.", {
        "deal_id": {"type": "integer"}, "status": {"type": "string", "enum": STAGES}},
        ["deal_id", "status"]),
    _fn("add_event", "Add a shoot, meeting or appointment to the calendar. Reports clashes.", {
        "title": {"type": "string"},
        "start": {"type": "string", "description": "ISO datetime, India time"},
        "end": {"type": "string", "description": "ISO datetime, optional"},
        "location": {"type": "string"},
    }, ["title", "start"]),
    _fn("list_events", "List upcoming events.", {"days": {"type": "integer"}}),
    _fn("book_ride", "Book a cab or a porter (needs user approval).", {
        "kind": {"type": "string", "enum": ["cab", "porter"]},
        "pickup": {"type": "string"}, "drop": {"type": "string"},
        "when": {"type": "string", "description": "ISO datetime, India time"},
    }, ["kind", "pickup", "drop", "when"]),
    _fn("create_invoice", "Create an invoice PDF and payment link for a deal.", {
        "deal_id": {"type": "integer"}, "amount_inr": {"type": "number"}}, ["deal_id"]),
    _fn("draft_pitch", "Draft a pitch email to a brand.", {
        "brand": {"type": "string"}, "note": {"type": "string"}}, ["brand"]),
    _fn("generate_pitch_studio", "Generate 3 pitch variants for a brand (professional, friendly, campaign).", {
        "brand": {"type": "string"}, "goals": {"type": "string"}, "deliverables": {"type": "string"}}, ["brand"]),
    _fn("suggest_brands", "Suggest brands that match the creator's niche.", {}),
    _fn("check_inbox", "Check Gmail for new brand emails (collabs, barter, payments, invites) and list them.", {}),
    _fn("check_followups", "List brand email threads that need a reply or a nudge (checks Gmail first).", {}),
    _fn("sync_calendar", "Sync the local calendar with Google Calendar.", {}),
    _fn("draft_email_reply", "Write a draft reply to a brand email by its id. The draft is only saved, never sent.", {
        "email_id": {"type": "integer"}}, ["email_id"]),
    _fn("list_overdue_invoices", "List invoices that are past due and still unpaid.", {}),
    _fn("record_invoice_payment", "Record a payment received against an invoice (by id or invoice number).", {
        "invoice_id": {"type": "integer"}, "invoice_number": {"type": "string"},
        "amount_inr": {"type": "number"}, "reference": {"type": "string"}},
        ["amount_inr"]),
    _fn("add_expense", "Add a business expense.", {
        "amount_inr": {"type": "number"}, "category": {"type": "string"},
        "description": {"type": "string"}, "spent_on": {"type": "string", "description": "YYYY-MM-DD"},
        "deal_id": {"type": "integer"}, "vendor": {"type": "string"}}, ["amount_inr", "description"]),
    _fn("list_expenses", "List expenses for the current calendar month.", {}),
    _fn("draft_payment_reminder", "Draft a payment reminder email for an overdue invoice (not sent automatically).", {
        "invoice_id": {"type": "integer"}, "invoice_number": {"type": "string"}}),
    _fn("summarize_analytics", "Summarize creator analytics from stored metrics only (no estimates).", {
        "days": {"type": "integer", "description": "Look-back days (default 30)"}}),
    _fn("generate_content_ideas", "Generate content ideas (saved as drafts; never auto-published).", {
        "platform": {"type": "string"}, "count": {"type": "integer"}, "theme": {"type": "string"},
        "deal_id": {"type": "integer"}}),
    _fn("list_content_plan", "List content plan items.", {
        "status": {"type": "string"}, "days": {"type": "integer"}}),
    _fn("content_suggestions", "Personalized content tips from profile and analytics.", {}),
    _fn("list_brand_crm", "List brands in your CRM (deals, pitches, follow-ups aggregated).", {
        "query": {"type": "string"}, "stage": {"type": "string", "enum": STAGES}}),
    _fn("brand_follow_up_suggestions", "Brands that need follow-up (scheduled, inbox, or pitch dates).", {}),
    _fn("brand_relationship_summary", "Relationship summary for one CRM brand (facts only).", {
        "brand_record_id": {"type": "integer"}}, ["brand_record_id"]),
    _fn("get_email_intelligence", "Read structured AI intelligence for a stored brand email (no send).", {
        "email_id": {"type": "integer"}}, ["email_id"]),
    _fn("email_follow_up_recommendations", "List inbox emails that recommend follow-up (suggestions only).", {}),
    _fn("campaign_roi", "Campaign ROI for one deal (stored payments and expenses only).", {
        "deal_id": {"type": "integer"}}, ["deal_id"]),
    _fn("list_campaign_roi", "List campaign ROI for all deals.", {
        "brand": {"type": "string"}}),
]


def deal_dict(d: models.Deal) -> dict:
    return {"id": d.id, "brand": d.brand, "kind": d.kind, "title": d.title, "value_inr": d.value_inr,
            "deliverables": d.deliverables, "status": d.status,
            "due_date": d.due_date.isoformat() if d.due_date else None}


def event_dict(e: models.Event) -> dict:
    return {"id": e.id, "title": e.title, "start": e.start_at.isoformat(timespec="minutes"),
            "end": e.end_at.isoformat(timespec="minutes"), "location": e.location}


def needs_approval(name: str, *, voice: bool = False) -> bool:
    if name in SENSITIVE:
        return True
    if voice and name in VOICE_FINANCIAL:
        return True
    return False


def approval_summary(name: str, args: dict, *, recognized: str = "") -> str:
    if name == "book_ride":
        base = f"Book a {args.get('kind')} from {args.get('pickup')} to {args.get('drop')} at {args.get('when')}"
    elif name == "create_invoice":
        base = f"Create invoice for deal #{args.get('deal_id')}" + (
            f" ({args.get('amount_inr')} INR)" if args.get("amount_inr") else ""
        )
    elif name == "record_invoice_payment":
        base = f"Record payment of {args.get('amount_inr')} INR" + (
            f" for invoice #{args.get('invoice_id')}" if args.get("invoice_id") else ""
        )
    elif name == "add_expense":
        base = f"Add expense {args.get('amount_inr')} INR — {args.get('description') or args.get('category') or 'expense'}"
    else:
        base = f"Run {name}"
    if recognized:
        return f"{base} (from voice: \"{recognized[:180]}\")"
    return base


def _ws_id() -> int | None:
    ctx = _tool_ctx.get()
    return ctx.workspace_id if ctx else None


def _row_ok(row, user: models.User) -> bool:
    if not row:
        return False
    ctx = _tool_ctx.get()
    if ctx and getattr(row, "workspace_id", None) is not None:
        return row.workspace_id == ctx.workspace_id
    return getattr(row, "user_id", None) == user.id


def run_tool(db: Session, user: models.User, name: str, args: dict, ctx=None) -> dict:
    token = None
    if ctx is not None:
        token = _tool_ctx.set(ctx)
        try:
            require_role(ctx.role, TOOL_PERMS.get(name, "agent.use"))
        except HTTPException as exc:
            if token is not None:
                _tool_ctx.reset(token)
            return {"error": exc.detail}
    try:
        return _TOOLS[name](db, user, **args)
    except KeyError:
        return {"error": f"Unknown tool {name}"}
    except TypeError as exc:
        return {"error": f"Bad arguments for {name}: {exc}"}
    except Exception as exc:  # report to the model instead of crashing the turn
        db.rollback()
        return {"error": str(exc)}
    finally:
        if token is not None:
            _tool_ctx.reset(token)


def _add_deal(db, user, brand, kind="paid", title="", value_inr=0, deliverables="", due_date=None):
    due = date.fromisoformat(due_date) if due_date else None
    deal = models.Deal(
        user_id=user.id, workspace_id=_ws_id(), brand=brand, kind=kind, title=title,
        value_inr=value_inr or 0, deliverables=deliverables, due_date=due,
    )
    db.add(deal)
    db.commit()
    return {"deal": deal_dict(deal)}


def _list_deals(db, user, status=None):
    wid = _ws_id()
    q = db.query(models.Deal)
    q = q.filter(models.Deal.workspace_id == wid) if wid else q.filter(models.Deal.user_id == user.id)
    if status:
        q = q.filter(models.Deal.status == status)
    return {"deals": [deal_dict(d) for d in q.order_by(models.Deal.id).all()]}


def _update_deal_status(db, user, deal_id, status):
    if status not in STAGES:
        return {"error": f"Status must be one of {STAGES}"}
    deal = db.get(models.Deal, int(deal_id))
    if not _row_ok(deal, user):
        return {"error": f"No deal #{deal_id}"}
    deal.status = status
    db.commit()
    return {"deal": deal_dict(deal)}


def _add_event(db, user, title, start, end=None, location=""):
    res = calendar_sync.add_event(
        db, user, title, parse_dt(start), parse_dt(end) if end else None, location, workspace_id=_ws_id(),
    )
    return {"event": event_dict(res["event"]), "conflicts": [event_dict(c) for c in res["conflicts"]],
            "google_synced": res["google_synced"], "google_error": res["google_error"]}


def _list_events(db, user, days=7):
    now = now_ist()
    wid = _ws_id()
    q = db.query(models.Event).filter(
        models.Event.start_at >= now - timedelta(hours=1),
        models.Event.start_at <= now + timedelta(days=int(days)),
    )
    if wid:
        q = q.filter(models.Event.workspace_id == wid)
    else:
        q = q.filter(models.Event.user_id == user.id)
    return {"events": [event_dict(e) for e in q.order_by(models.Event.start_at).all()]}


def _book_ride(db, user, kind, pickup, drop, when):
    return logistics.create_booking(db, user, kind, pickup, drop, parse_dt(when))


def _create_invoice(db, user, deal_id, amount_inr=None):
    from . import invoices as inv_svc
    deal = db.get(models.Deal, int(deal_id))
    if not _row_ok(deal, user):
        return {"error": f"No deal #{deal_id}"}
    if inv_svc.duplicate_open_draft(db, user.id, deal.id):
        return {"error": f"A draft invoice already exists for deal #{deal_id}. Open Invoices to send it."}
    inv = inv_svc.invoice_from_deal(db, user, deal)
    if _ws_id() and not inv.workspace_id:
        inv.workspace_id = _ws_id()
    if amount_inr:
        inv.line_items = [{"description": inv.work_description[:200], "quantity": 1, "unit_price": float(amount_inr)}]
    if not inv.line_items or not inv.line_items[0].get("unit_price"):
        return {"error": "This deal has no value yet. Tell me the amount."}
    inv_svc.refresh_amount(inv)
    db.add(inv)
    db.flush()
    inv_svc.assign_number(inv)
    try:
        inv_svc.mark_sent(db, user, inv)
    except ValueError as e:
        return {"error": str(e)}
    deal.status = "payment_pending"
    db.commit()
    return {"invoice": {"id": inv.id, "number": inv.number, "amount_inr": inv.amount_inr,
                        "payment_link": inv.payment_link, "status": inv.status}}


def _draft_pitch(db, user, brand, note=""):
    return {"pitch": outreach.draft_pitch(user, brand, note, profile_service.pitch_context(db, user)),
            "studio_hint": f"Open Brands → Pitch Studio for {brand} to edit three variants."}


def _generate_pitch_studio(db, user, brand, goals="", deliverables=""):
    from . import outreach_studio
    try:
        data = outreach_studio.generate_suggestions(db, user, brand, goals, deliverables)
    except ValueError as e:
        return {"error": str(e)}
    return {**data, "studio_hint": "Go to Brands and click Draft pitch, or open #/brands?studio=" + brand}


def _suggest_brands(db, user):
    return {"brands": outreach.suggest(user)}


def _email_dict(e: models.EmailMessage) -> dict:
    return {"id": e.id, "from": e.sender_name or e.sender_email, "brand": e.brand, "category": e.category,
            "subject": e.subject, "amount_inr": e.amount_inr, "summary": e.summary}


def _check_inbox(db, user):
    try:
        result = gmail_sync.sync(db, user)
    except GmailError as exc:
        return {"error": str(exc)}
    rows = (db.query(models.EmailMessage).filter_by(user_id=user.id, status="new")
            .order_by(models.EmailMessage.received_at.desc()).limit(8).all())
    return {"new_count": len(result["new"]), "emails": [_email_dict(e) for e in rows]}


def _draft_email_reply(db, user, email_id):
    em = db.get(models.EmailMessage, int(email_id))
    if not _row_ok(em, user):
        return {"error": f"No email #{email_id}"}
    return {"email_id": em.id, "draft": gmail_sync.make_draft(db, user, em),
            "note": "Saved as a draft in the Inbox tab. Nothing was sent."}


def _check_followups(db, user):
    try:
        followups.refresh(db, user)
    except GmailError as exc:
        return {"error": str(exc)}
    return {"followups": followups.active_list(db, user)}


def _find_invoice(db, user, invoice_id=None, invoice_number=None):
    if invoice_id:
        inv = db.get(models.Invoice, int(invoice_id))
    elif invoice_number:
        inv = db.query(models.Invoice).filter_by(user_id=user.id, number=str(invoice_number)).first()
    else:
        return None
    if not _row_ok(inv, user):
        return None
    return inv


def _list_overdue_invoices(db, user):
    from . import invoices as inv_svc
    rows = db.query(models.Invoice).filter_by(user_id=user.id).all()
    out = []
    for inv in rows:
        inv_svc.apply_overdue(inv)
        if inv.status == "overdue":
            bal = max(0, round(inv.amount_inr - inv.paid_inr, 2))
            out.append({"id": inv.id, "number": inv.number, "client": inv.client_name, "balance_inr": bal,
                        "due_date": inv.due_date.isoformat() if inv.due_date else None})
    db.commit()
    return {"invoices": out}


def _record_invoice_payment(db, user, amount_inr, invoice_id=None, invoice_number=None, reference=""):
    from . import invoices as inv_svc
    inv = _find_invoice(db, user, invoice_id, invoice_number)
    if not inv:
        return {"error": "Invoice not found. Use the invoice id or number."}
    try:
        pay = inv_svc.record_payment(db, user, inv, float(amount_inr), date.today(), reference=reference or "")
    except ValueError as e:
        return {"error": str(e)}
    db.commit()
    return {"invoice_id": inv.id, "number": inv.number, "status": inv.status, "paid_inr": inv.paid_inr,
            "payment_id": pay.id}


def _add_expense(db, user, amount_inr, description, category="other", spent_on=None, deal_id=None, vendor=""):
    if category not in models.EXPENSE_CATEGORIES:
        return {"error": f"Unknown category. Use one of: {', '.join(models.EXPENSE_CATEGORIES)}"}
    if deal_id:
        deal = db.get(models.Deal, int(deal_id))
        if not _row_ok(deal, user):
            return {"error": f"No deal #{deal_id}"}
    when = date.fromisoformat(spent_on) if spent_on else date.today()
    row = models.Expense(user_id=user.id, spent_on=when, category=category, description=description[:300],
                         amount_inr=float(amount_inr), vendor=vendor or "", deal_id=deal_id)
    db.add(row)
    db.commit()
    return {"expense": {"id": row.id, "amount_inr": row.amount_inr, "category": row.category, "description": row.description}}


def _list_expenses(db, user):
    today = date.today()
    start = today.replace(day=1)
    rows = (db.query(models.Expense).filter(models.Expense.user_id == user.id,
                                            models.Expense.spent_on >= start,
                                            models.Expense.spent_on <= today)
            .order_by(models.Expense.spent_on.desc()).all())
    return {"expenses": [{"id": r.id, "spent_on": r.spent_on.isoformat(), "category": r.category,
                          "description": r.description, "amount_inr": r.amount_inr} for r in rows],
            "total_inr": round(sum(r.amount_inr for r in rows), 2)}


def _draft_payment_reminder(db, user, invoice_id=None, invoice_number=None):
    from . import invoices as inv_svc
    inv = _find_invoice(db, user, invoice_id, invoice_number)
    if not inv:
        return {"error": "Invoice not found."}
    deal = db.get(models.Deal, inv.deal_id) if inv.deal_id else None
    return {"draft": inv_svc.payment_reminder_draft(inv, deal),
            "note": "This is a draft for you to review. Nothing is sent until you send it yourself."}


def _generate_content_ideas(db, user, platform="instagram", count=5, theme="", deal_id=None):
    try:
        return content_svc.generate_ideas(db, user, platform, count or 5, theme or "", "friendly", deal_id)
    except ValueError as exc:
        return {"error": str(exc)}


def _list_content_plan(db, user, status="", days=30):
    from datetime import datetime, timedelta
    to_at = datetime.utcnow() + timedelta(days=max(1, int(days or 30)))
    fr = datetime.utcnow() - timedelta(days=7)
    rows = content_svc.list_items(db, user, status=status or "", from_at=fr, to_at=to_at)
    return {"items": [{"id": r.id, "title": r.title, "status": r.status, "platform": r.platform,
                       "scheduled_at": r.scheduled_at.isoformat() if r.scheduled_at else None} for r in rows[:25]]}


def _content_suggestions(db, user):
    return {"tips": content_svc.suggestions(db, user),
            "note": "Open Content in the app to edit scripts. Nothing is posted automatically."}


def _list_brand_crm(db, user, query="", stage=""):
    rows = brand_crm_svc.list_brands(db, user, q=query or "", stage=stage or "", follow_up=False)
    return {"brands": rows[:30], "note": "Use Brands in the app for notes and scheduling. Nothing is emailed automatically."}


def _brand_follow_up_suggestions(db, user):
    return {"brands": brand_crm_svc.follow_up_suggestions(db, user),
            "note": "Review in Brands → CRM. Gmail drafts still need your approval to send."}


def _get_email_intelligence(db, user, email_id):
    em = db.get(models.EmailMessage, int(email_id))
    if not _row_ok(em, user):
        return {"error": "Email not found"}
    intel = email_intel_svc.public_view(em)
    intel["matches"] = email_match_svc.all_matches(db, user, em)
    return {"email_id": em.id, "intelligence": intel, "note": email_intel_svc.UNVERIFIED_NOTICE}


def _email_follow_up_recommendations(db, user):
    return {"items": email_match_svc.recommendations(db, user), "note": "Review in Inbox. Drafts are not sent automatically."}


def _campaign_roi(db, user, deal_id):
    try:
        return campaign_roi_svc.compute_deal_roi(db, user, int(deal_id)).model_dump()
    except ValueError:
        return {"error": "Deal not found"}


def _list_campaign_roi(db, user, brand=""):
    summary = campaign_roi_svc.list_campaign_roi(db, user, brand=brand or "", limit=25)
    return {"totals": summary.totals, "campaigns": [c.model_dump() for c in summary.campaigns[:10]],
            "note": "Based on invoices, payments and expenses — not estimates unless labeled."}


def _brand_relationship_summary(db, user, brand_record_id):
    try:
        text = brand_crm_svc.relationship_summary(db, user, int(brand_record_id))
    except ValueError:
        return {"error": "Brand not found"}
    return {"summary": text, "brand_record_id": int(brand_record_id)}


def _summarize_analytics(db, user, days=30):
    to = date.today()
    fr = to - timedelta(days=max(1, min(int(days or 30), 365)))
    return {"summary": analytics_svc.insights_text(db, user, fr, to), "from": fr.isoformat(), "to": to.isoformat()}


def _sync_calendar(db, user):
    try:
        pushed = calendar_sync.push_all(db, user)
        pulled = calendar_sync.pull(db, user)
    except (CalendarError, GmailError) as exc:
        return {"error": str(exc)}
    return {"pushed": pushed, **pulled}


_TOOLS = {
    "add_deal": _add_deal, "list_deals": _list_deals, "update_deal_status": _update_deal_status,
    "add_event": _add_event, "list_events": _list_events, "book_ride": _book_ride,
    "create_invoice": _create_invoice, "draft_pitch": _draft_pitch, "generate_pitch_studio": _generate_pitch_studio,
    "suggest_brands": _suggest_brands,
    "check_inbox": _check_inbox, "draft_email_reply": _draft_email_reply,
    "check_followups": _check_followups, "sync_calendar": _sync_calendar,
    "list_overdue_invoices": _list_overdue_invoices, "record_invoice_payment": _record_invoice_payment,
    "add_expense": _add_expense, "list_expenses": _list_expenses, "draft_payment_reminder": _draft_payment_reminder,
    "summarize_analytics": _summarize_analytics,
    "generate_content_ideas": _generate_content_ideas,
    "list_content_plan": _list_content_plan,
    "content_suggestions": _content_suggestions,
    "list_brand_crm": _list_brand_crm,
    "brand_follow_up_suggestions": _brand_follow_up_suggestions,
    "brand_relationship_summary": _brand_relationship_summary,
    "get_email_intelligence": _get_email_intelligence,
    "email_follow_up_recommendations": _email_follow_up_recommendations,
    "campaign_roi": _campaign_roi,
    "list_campaign_roi": _list_campaign_roi,
}


def dumps(obj) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False)

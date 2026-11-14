from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import (JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

STAGES = [
    "lead", "negotiating", "confirmed", "product_received",
    "content_due", "posted", "payment_pending", "done", "cancelled",
]


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(120), default="")
    handle: Mapped[str] = mapped_column(String(120), default="")
    niche: Mapped[str] = mapped_column(String(255), default="")
    followers: Mapped[int] = mapped_column(Integer, default=0)
    city: Mapped[str] = mapped_column(String(120), default="")
    language: Mapped[str] = mapped_column(String(5), default="en")  # en | hi | mr
    upi_vpa: Mapped[str] = mapped_column(String(120), default="")
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    telegram_link_code: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


WORKSPACE_ROLES = ("owner", "admin", "manager", "editor", "finance", "viewer")
MEMBERSHIP_STATUS = ("active", "invited", "removed")
TASK_STATUS = ("open", "in_progress", "done", "cancelled")
ASSIGNMENT_ROLES = ("lead", "contributor", "reviewer")


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    workspace_type: Mapped[str] = mapped_column(String(16), default="creator")  # creator | agency
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    settings: Mapped[dict] = mapped_column(JSON, default=lambda: {})
    marked_for_deletion_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class WorkspaceMembership(Base):
    __tablename__ = "workspace_memberships"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_ws_member"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="editor")
    status: Mapped[str] = mapped_column(String(12), default="active")
    invited_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    joined_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class WorkspaceInvitation(Base):
    __tablename__ = "workspace_invitations"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(16), default="editor")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    invited_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DealAssignment(Base):
    __tablename__ = "deal_assignments"
    __table_args__ = (UniqueConstraint("deal_id", "user_id", name="uq_deal_assignee"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    assignment_role: Mapped[str] = mapped_column(String(16), default="contributor")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class WorkspaceTask(Base):
    __tablename__ = "workspace_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    deal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("deals.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    assignee_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Deal(Base):
    __tablename__ = "deals"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    brand: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(10), default="paid")  # paid | barter
    title: Mapped[str] = mapped_column(String(255), default="")
    value_inr: Mapped[float] = mapped_column(Float, default=0)
    production_cost_estimate_inr: Mapped[float] = mapped_column(Float, default=0)
    deliverables: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="lead")
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    due_reminded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    location: Mapped[str] = mapped_column(String(255), default="")
    reminded: Mapped[bool] = mapped_column(Boolean, default=False)


class Contact(Base):
    __tablename__ = "contacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    brand_record_id: Mapped[Optional[int]] = mapped_column(ForeignKey("brand_records.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    company: Mapped[str] = mapped_column(String(160), default="")
    role: Mapped[str] = mapped_column(String(120), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(40), default="")
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")


INVOICE_STATUSES = ("draft", "sent", "partially_paid", "paid", "overdue", "cancelled")

EXPENSE_CATEGORIES = (
    "travel", "food", "clothing", "makeup", "equipment", "props",
    "software", "accommodation", "other",
)


class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    deal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("deals.id"), nullable=True)
    number: Mapped[str] = mapped_column(String(32), default="")
    amount_inr: Mapped[float] = mapped_column(Float)  # final total (incl. tax, after discount)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    pdf_path: Mapped[str] = mapped_column(String(255), default="")
    payment_link: Mapped[str] = mapped_column(String(500), default="")
    issue_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    creator_name: Mapped[str] = mapped_column(String(160), default="")
    creator_email: Mapped[str] = mapped_column(String(255), default="")
    creator_phone: Mapped[str] = mapped_column(String(40), default="")
    creator_address: Mapped[str] = mapped_column(Text, default="")
    client_name: Mapped[str] = mapped_column(String(160), default="")
    client_email: Mapped[str] = mapped_column(String(255), default="")
    client_address: Mapped[str] = mapped_column(Text, default="")
    campaign: Mapped[str] = mapped_column(String(255), default="")
    deliverables: Mapped[str] = mapped_column(Text, default="")
    work_description: Mapped[str] = mapped_column(Text, default="")
    line_items: Mapped[list] = mapped_column(JSON, default=list)
    discount_inr: Mapped[float] = mapped_column(Float, default=0)
    tax_percent: Mapped[float] = mapped_column(Float, default=0)
    tax_inr: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    paid_inr: Mapped[float] = mapped_column(Float, default=0)
    payment_method: Mapped[str] = mapped_column(String(24), default="")
    payment_reference: Mapped[str] = mapped_column(String(120), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    terms: Mapped[str] = mapped_column(Text, default="")
    signature_text: Mapped[str] = mapped_column(String(120), default="")
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class InvoicePayment(Base):
    __tablename__ = "invoice_payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    amount_inr: Mapped[float] = mapped_column(Float)
    paid_at: Mapped[date] = mapped_column(Date)
    method: Mapped[str] = mapped_column(String(24), default="")
    reference: Mapped[str] = mapped_column(String(120), default="")
    notes: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


OUTREACH_STATUSES = ("draft", "ready", "gmail_saved", "replied")


class OutreachPitch(Base):
    """Saved brand outreach copy. Gmail save does not send mail."""
    __tablename__ = "outreach_pitches"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    brand: Mapped[str] = mapped_column(String(160), index=True)
    category: Mapped[str] = mapped_column(String(80), default="")
    variant: Mapped[str] = mapped_column(String(24), default="professional")
    subject: Mapped[str] = mapped_column(String(300), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    recipient_email: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(16), default="draft")
    deal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("deals.id"), nullable=True)
    follow_up_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    gmail_draft_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    goals: Mapped[str] = mapped_column(String(400), default="")
    deliverables: Mapped[str] = mapped_column(String(400), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Expense(Base):
    __tablename__ = "expenses"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    deal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("deals.id"), nullable=True)
    spent_on: Mapped[date] = mapped_column(Date)
    category: Mapped[str] = mapped_column(String(16), default="other")
    description: Mapped[str] = mapped_column(String(300), default="")
    amount_inr: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    vendor: Mapped[str] = mapped_column(String(160), default="")
    payment_method: Mapped[str] = mapped_column(String(24), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    receipt_path: Mapped[str] = mapped_column(String(255), default="")
    receipt_mime: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(10))  # cab | porter
    pickup: Mapped[str] = mapped_column(String(255))
    drop: Mapped[str] = mapped_column(String(255))
    when_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16), default="confirmed")
    provider: Mapped[str] = mapped_column(String(24), default="mock")
    reference: Mapped[str] = mapped_column(String(40), default="")


class PendingAction(Base):
    __tablename__ = "pending_actions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    requested_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tool: Mapped[str] = mapped_column(String(40))
    args: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[str] = mapped_column(String(500), default="")
    recognized_text: Mapped[str] = mapped_column(String(2000), default="")
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending | executed | rejected
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(10), default="text")  # text | voice
    voice_meta: Mapped[dict] = mapped_column(JSON, default=lambda: {})
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    resource_type: Mapped[str] = mapped_column(String(40), default="")
    resource_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    detail: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class GmailAccount(Base):
    __tablename__ = "gmail_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), default="")
    refresh_token_enc: Mapped[str] = mapped_column(Text, default="")
    access_token_enc: Mapped[str] = mapped_column(Text, default="")
    token_expiry: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EmailMessage(Base):
    """Only business-relevant emails are stored. Everything classified as 'other' is dropped."""
    __tablename__ = "email_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    gmail_id: Mapped[str] = mapped_column(String(64), index=True)
    thread_id: Mapped[str] = mapped_column(String(64), default="")
    message_id_header: Mapped[str] = mapped_column(String(300), default="")
    sender_name: Mapped[str] = mapped_column(String(200), default="")
    sender_email: Mapped[str] = mapped_column(String(255), default="")
    subject: Mapped[str] = mapped_column(String(500), default="")
    snippet: Mapped[str] = mapped_column(String(300), default="")
    body_enc: Mapped[str] = mapped_column(Text, default="")  # encrypted at rest
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    category: Mapped[str] = mapped_column(String(20), default="other")
    confidence: Mapped[float] = mapped_column(Float, default=0)
    brand: Mapped[str] = mapped_column(String(160), default="")
    amount_inr: Mapped[float] = mapped_column(Float, default=0)
    deliverables: Mapped[str] = mapped_column(String(300), default="")
    summary: Mapped[str] = mapped_column(String(400), default="")
    status: Mapped[str] = mapped_column(String(12), default="new")  # new | dismissed
    draft_reply: Mapped[str] = mapped_column(Text, default="")
    gmail_draft_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    deal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("deals.id"), nullable=True)
    brand_record_id: Mapped[Optional[int]] = mapped_column(ForeignKey("brand_records.id"), nullable=True, index=True)
    is_brand_inquiry: Mapped[bool] = mapped_column(Boolean, default=False)
    intelligence_version: Mapped[int] = mapped_column(Integer, default=0)
    intelligence_json: Mapped[dict] = mapped_column(JSON, default=dict)
    intelligence_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    suggested_reply: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CalendarLink(Base):
    """Per-user Google Calendar state. Uses the same Google account as Gmail."""
    __tablename__ = "calendar_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    granted: Mapped[bool] = mapped_column(Boolean, default=False)
    last_pull_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(String(300), default="")


class EventSync(Base):
    """Maps local events to Google Calendar events. source says where the event was created."""
    __tablename__ = "event_syncs"
    __table_args__ = (UniqueConstraint("user_id", "google_event_id", name="uq_event_sync"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    google_event_id: Mapped[str] = mapped_column(String(128))
    event_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(8), default="app")  # app | google
    ignored: Mapped[bool] = mapped_column(Boolean, default=False)


class EventSuggestion(Base):
    """A shoot, meeting or deadline date found inside a brand email. Needs the user's OK."""
    __tablename__ = "event_suggestions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("email_messages.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10), default="event")  # event | deadline
    title: Mapped[str] = mapped_column(String(255))
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending | accepted | dismissed
    event_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FollowUp(Base):
    """Tracks email threads that need attention. One row per email."""
    __tablename__ = "follow_ups"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("email_messages.id"), unique=True, index=True)
    # needs_reply (brand is waiting on you) | awaiting_brand (you are waiting on them) | resolved | dismissed
    state: Mapped[str] = mapped_column(String(16), default="resolved")
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    nudge_draft: Mapped[str] = mapped_column(Text, default="")
    reminded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    snoozed_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class CreatorProfile(Base):
    """Extra creator details. Name, handle, niche, city, language, UPI and follower total
    already live on User and are reused, not duplicated. One row per user."""
    __tablename__ = "creator_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    creator_type: Mapped[str] = mapped_column(String(16), default="influencer")
    bio: Mapped[str] = mapped_column(String(400), default="")
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    languages: Mapped[list] = mapped_column(JSON, default=lambda: ["en"])
    contact_email: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(24), default="")             # private: never sent to the AI
    home_location: Mapped[str] = mapped_column(String(200), default="")    # private: never sent to the AI
    payment_method: Mapped[str] = mapped_column(String(8), default="upi")  # upi | bank | other
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=15)
    invoice_notes: Mapped[str] = mapped_column(String(400), default="")
    gstin: Mapped[str] = mapped_column(String(15), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class SocialAccount(Base):
    """A creator's public channel on one platform. One per platform per user."""
    __tablename__ = "social_accounts"
    __table_args__ = (UniqueConstraint("user_id", "platform", name="uq_social_user_platform"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    platform: Mapped[str] = mapped_column(String(16))
    handle: Mapped[str] = mapped_column(String(60), default="")
    url: Mapped[str] = mapped_column(String(300), default="")
    followers: Mapped[int] = mapped_column(Integer, default=0)
    connection_status: Mapped[str] = mapped_column(String(12), default="manual")  # manual | connected | error
    external_id: Mapped[str] = mapped_column(String(64), default="")
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


METRIC_SOURCES = ("api", "manual", "import", "derived")
ANALYTICS_PLATFORMS = ("instagram", "youtube", "tiktok", "other")
METRIC_KEYS = ("followers", "reach", "impressions", "views", "engagement", "engagement_rate")


class PlatformConnection(Base):
    """OAuth tokens for platform analytics (encrypted). One row per user per platform."""
    __tablename__ = "platform_connections"
    __table_args__ = (UniqueConstraint("user_id", "platform", name="uq_platform_conn"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    platform: Mapped[str] = mapped_column(String(16))
    external_id: Mapped[str] = mapped_column(String(80), default="")
    scopes: Mapped[str] = mapped_column(String(300), default="")
    access_token_enc: Mapped[str] = mapped_column(Text, default="")
    refresh_token_enc: Mapped[str] = mapped_column(Text, default="")
    token_expiry: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="disconnected")  # disconnected | connected | error
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    social_account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("social_accounts.id"), nullable=True, index=True)
    platform: Mapped[str] = mapped_column(String(16), index=True)
    metric_key: Mapped[str] = mapped_column(String(32), index=True)
    value: Mapped[float] = mapped_column(Float)
    period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(String(8), default="manual")
    confidence: Mapped[str] = mapped_column(String(12), default="verified")  # verified | unverified
    deal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("deals.id"), nullable=True)
    content_item_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    notes: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class ContentItem(Base):
    __tablename__ = "content_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    social_account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("social_accounts.id"), nullable=True)
    platform: Mapped[str] = mapped_column(String(16))
    external_id: Mapped[str] = mapped_column(String(80), default="")
    title: Mapped[str] = mapped_column(String(255), default="")
    permalink: Mapped[str] = mapped_column(String(400), default="")
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    deal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("deals.id"), nullable=True)
    views: Mapped[float] = mapped_column(Float, default=0)
    engagement: Mapped[float] = mapped_column(Float, default=0)
    source: Mapped[str] = mapped_column(String(8), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), default="")
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(12), default="pending")
    errors_json: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


CONTENT_STATUSES = ("idea", "draft", "ready", "scheduled", "published")
CONTENT_FORMATS = ("idea", "reel", "youtube", "shorts", "carousel", "caption")
CONTENT_TONES = ("friendly", "professional", "educational", "playful")
DRAFT_SOURCES = ("template", "llm", "manual", "repurpose")


class ContentPlanItem(Base):
    """Planned or in-progress creator content. Nothing is auto-published to social platforms."""
    __tablename__ = "content_plan_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    deal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("deals.id"), nullable=True, index=True)
    event_id: Mapped[Optional[int]] = mapped_column(ForeignKey("events.id"), nullable=True)
    platform: Mapped[str] = mapped_column(String(16), default="instagram", index=True)
    format: Mapped[str] = mapped_column(String(16), default="idea", index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(12), default="idea", index=True)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    language: Mapped[str] = mapped_column(String(5), default="en")
    tone: Mapped[str] = mapped_column(String(16), default="friendly")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(String(500), default="")
    search_text: Mapped[str] = mapped_column(String(600), default="")  # denormalized for simple filters
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ContentDraft(Base):
    """Versioned script/caption bodies for a plan item."""
    __tablename__ = "content_drafts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    plan_item_id: Mapped[int] = mapped_column(ForeignKey("content_plan_items.id"), index=True)
    variant: Mapped[str] = mapped_column(String(24), default="primary")
    body_json: Mapped[dict] = mapped_column(JSON, default=dict)
    caption: Mapped[str] = mapped_column(Text, default="")
    hashtags: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(12), default="template")
    parent_draft_id: Mapped[Optional[int]] = mapped_column(ForeignKey("content_drafts.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


RATE_DELIVERABLES = ("reel", "post", "story", "video", "integration", "other")
MEDIA_KIT_TEMPLATES = ("classic", "minimal", "bold")


class MediaKit(Base):
    """Editable media kit settings. Public view uses frozen snapshot on MediaKitShare only."""
    __tablename__ = "media_kits"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    headline: Mapped[str] = mapped_column(String(120), default="")
    intro: Mapped[str] = mapped_column(String(800), default="")
    pdf_template: Mapped[str] = mapped_column(String(12), default="classic")
    show_rates: Mapped[bool] = mapped_column(Boolean, default=True)
    show_metrics: Mapped[bool] = mapped_column(Boolean, default=True)
    show_contact_email: Mapped[bool] = mapped_column(Boolean, default=True)
    show_phone: Mapped[bool] = mapped_column(Boolean, default=False)
    avatar_path: Mapped[str] = mapped_column(String(255), default="")
    avatar_mime: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class MediaKitRateLine(Base):
    __tablename__ = "media_kit_rate_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    deliverable: Mapped[str] = mapped_column(String(16), default="reel")
    title: Mapped[str] = mapped_column(String(120), default="")
    price: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    notes: Mapped[str] = mapped_column(String(200), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class MediaKitPortfolioItem(Base):
    __tablename__ = "media_kit_portfolio"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id"), index=True)
    summary: Mapped[str] = mapped_column(String(300), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    visible: Mapped[bool] = mapped_column(Boolean, default=True)


class MediaKitSample(Base):
    __tablename__ = "media_kit_samples"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    content_item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("content_items.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    url: Mapped[str] = mapped_column(String(400), default="")
    platform: Mapped[str] = mapped_column(String(16), default="")
    notes: Mapped[str] = mapped_column(String(200), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    visible: Mapped[bool] = mapped_column(Boolean, default=True)


class BrandRecord(Base):
    """Per-user brand CRM record. One row per normalized brand name."""
    __tablename__ = "brand_records"
    __table_args__ = (UniqueConstraint("user_id", "brand_key", name="uq_brand_user_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    brand_key: Mapped[str] = mapped_column(String(160), index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(80), default="")
    website: Mapped[str] = mapped_column(String(300), default="")
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    relationship_summary: Mapped[str] = mapped_column(String(500), default="")
    lead_stage: Mapped[str] = mapped_column(String(24), default="lead")
    next_follow_up: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class BrandNote(Base):
    __tablename__ = "brand_notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    brand_record_id: Mapped[int] = mapped_column(ForeignKey("brand_records.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="general")  # general | negotiation
    body: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class BrandFollowUp(Base):
    """Scheduled CRM follow-up (reminder only — no auto-send)."""
    __tablename__ = "brand_follow_ups"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    brand_record_id: Mapped[int] = mapped_column(ForeignKey("brand_records.id"), index=True)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    notes: Mapped[str] = mapped_column(String(300), default="")
    deal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("deals.id"), nullable=True)
    pitch_id: Mapped[Optional[int]] = mapped_column(ForeignKey("outreach_pitches.id"), nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MediaKitShare(Base):
    """Public link: serves only published_snapshot_json when active."""
    __tablename__ = "media_kit_shares"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    token: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    published_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

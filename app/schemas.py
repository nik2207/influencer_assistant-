from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    name: str = ""


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshIn(BaseModel):
    refresh_token: str


class ProfileIn(BaseModel):
    name: Optional[str] = None
    handle: Optional[str] = None
    niche: Optional[str] = None
    followers: Optional[int] = None
    city: Optional[str] = None
    language: Optional[str] = Field(default=None, pattern="^(en|hi|mr)$")
    upi_vpa: Optional[str] = None


class UserOut(ORM):
    id: int
    email: str
    name: str
    handle: str
    niche: str
    followers: int
    city: str
    language: str
    upi_vpa: str
    telegram_linked: bool = False


class DealIn(BaseModel):
    brand: str
    kind: str = Field(default="paid", pattern="^(paid|barter)$")
    title: str = ""
    value_inr: float = 0
    deliverables: str = ""
    status: str = "lead"
    due_date: Optional[date] = None
    notes: str = ""


class DealPatch(BaseModel):
    brand: Optional[str] = None
    title: Optional[str] = None
    value_inr: Optional[float] = None
    production_cost_estimate_inr: Optional[float] = None
    deliverables: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[date] = None
    notes: Optional[str] = None


class DealOut(ORM):
    id: int
    brand: str
    kind: str
    title: str
    value_inr: float
    production_cost_estimate_inr: float = 0
    deliverables: str
    status: str
    due_date: Optional[date]
    notes: str


class EventIn(BaseModel):
    title: str
    start_at: datetime
    end_at: Optional[datetime] = None
    location: str = ""


class EventOut(ORM):
    id: int
    title: str
    start_at: datetime
    end_at: datetime
    location: str


class ContactIn(BaseModel):
    name: str
    company: str = ""
    role: str = ""
    email: str = ""
    phone: str = ""
    notes: str = ""


class ContactPatch(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    brand_record_id: Optional[int] = None
    email_verified: Optional[bool] = None


class ContactOut(ContactIn, ORM):
    id: int
    brand_record_id: Optional[int] = None
    email_verified: bool = False


class LineItemIn(BaseModel):
    description: str = Field(min_length=1, max_length=300)
    quantity: float = Field(gt=0, le=10000)
    unit_price: float = Field(ge=0)


class InvoiceIn(BaseModel):
    deal_id: Optional[int] = None
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    creator_name: str = ""
    creator_email: str = ""
    creator_phone: str = ""
    creator_address: str = ""
    client_name: str = Field(min_length=1, max_length=160)
    client_email: str = ""
    client_address: str = ""
    campaign: str = ""
    deliverables: str = ""
    work_description: str = ""
    line_items: list[LineItemIn] = Field(default_factory=list)
    discount_inr: float = Field(default=0, ge=0)
    tax_percent: float = Field(default=0, ge=0, le=100)
    currency: str = Field(default="INR", max_length=3)
    notes: str = ""
    terms: str = ""
    signature_text: str = ""


class InvoiceUpdate(BaseModel):
    deal_id: Optional[int] = None
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    creator_name: Optional[str] = None
    creator_email: Optional[str] = None
    creator_phone: Optional[str] = None
    creator_address: Optional[str] = None
    client_name: Optional[str] = Field(default=None, max_length=160)
    client_email: Optional[str] = None
    client_address: Optional[str] = None
    campaign: Optional[str] = None
    deliverables: Optional[str] = None
    work_description: Optional[str] = None
    line_items: Optional[list[LineItemIn]] = None
    discount_inr: Optional[float] = Field(default=None, ge=0)
    tax_percent: Optional[float] = Field(default=None, ge=0, le=100)
    currency: Optional[str] = Field(default=None, max_length=3)
    notes: Optional[str] = None
    terms: Optional[str] = None
    signature_text: Optional[str] = None


class InvoiceOut(ORM):
    id: int
    deal_id: Optional[int]
    number: str
    amount_inr: float
    status: str
    payment_link: str
    paid_inr: float = 0
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    creator_name: str = ""
    creator_email: str = ""
    creator_phone: str = ""
    creator_address: str = ""
    client_name: str = ""
    client_email: str = ""
    client_address: str = ""
    campaign: str = ""
    deliverables: str = ""
    work_description: str = ""
    line_items: list = Field(default_factory=list)
    discount_inr: float = 0
    tax_percent: float = 0
    tax_inr: float = 0
    currency: str = "INR"
    payment_method: str = ""
    payment_reference: str = ""
    notes: str = ""
    terms: str = ""
    signature_text: str = ""
    sent_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    balance_inr: float = 0
    is_overdue: bool = False


class InvoicePaymentIn(BaseModel):
    amount_inr: float = Field(gt=0)
    paid_at: Optional[date] = None
    method: str = ""
    reference: str = ""
    notes: str = ""


class InvoicePaymentOut(ORM):
    id: int
    invoice_id: int
    amount_inr: float
    paid_at: date
    method: str
    reference: str
    notes: str
    created_at: datetime


class FinanceSummaryOut(BaseModel):
    total_invoiced: float
    total_received: float
    outstanding: float
    overdue_count: int
    overdue_amount: float
    expenses: float = 0
    net_cash_flow: float = 0


class ReminderDraftOut(BaseModel):
    draft: str
    invoice_id: int
    note: str = "Review and send this yourself. Nothing is sent automatically."


class ExpenseIn(BaseModel):
    spent_on: date
    category: str = Field(pattern="^(travel|food|clothing|makeup|equipment|props|software|accommodation|other)$")
    description: str = Field(min_length=1, max_length=300)
    amount_inr: float = Field(gt=0)
    currency: str = Field(default="INR", max_length=3)
    vendor: str = ""
    payment_method: str = ""
    deal_id: Optional[int] = None
    notes: str = ""


class OutreachPitchOut(ORM):
    id: int
    brand: str
    category: str = ""
    variant: str
    subject: str
    body: str
    recipient_email: str = ""
    status: str
    deal_id: Optional[int] = None
    follow_up_date: Optional[date] = None
    gmail_draft_id: Optional[str] = None
    goals: str = ""
    deliverables: str = ""
    created_at: datetime
    updated_at: Optional[datetime] = None


class ExpenseOut(ExpenseIn, ORM):
    id: int
    receipt_path: str = ""
    receipt_mime: str = ""
    created_at: datetime
    updated_at: Optional[datetime] = None


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class PendingOut(ORM):
    id: int
    tool: str
    summary: str
    status: str
    args: dict
    recognized_text: str = ""


class ChatOut(BaseModel):
    reply: str
    pending: list[PendingOut] = []
    tools_used: list[str] = []


class VoiceChatOut(ChatOut):
    transcript: str
    detected_language: str = ""
    language_hint: str = ""


class TranscribeOut(BaseModel):
    text: str
    detected_language: str = ""
    language_hint: str = ""


class ChatHistoryLine(BaseModel):
    role: str
    content: str
    source: str = "text"
    detected_language: str = ""


class TranslateIn(BaseModel):
    text: str
    target: str = Field(pattern="^(en|hi|mr)$")


class EmailOut(ORM):
    id: int
    sender_name: str
    sender_email: str
    subject: str
    snippet: str
    received_at: datetime
    category: str
    confidence: float
    brand: str
    amount_inr: float
    deliverables: str
    summary: str
    status: str
    draft_reply: str
    gmail_draft_id: Optional[str]
    deal_id: Optional[int]
    brand_record_id: Optional[int] = None
    is_brand_inquiry: bool = False
    intelligence_version: int = 0
    unverified_notice: str = (
        "AI-extracted fields are suggestions only. Review against the original email before "
        "creating deals or sending replies."
    )


class EmailDetail(EmailOut):
    body: str = ""
    intelligence: dict = Field(default_factory=dict)


class DraftEdit(BaseModel):
    draft_reply: str = Field(max_length=6000)

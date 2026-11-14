from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ToDealIn(BaseModel):
    confirm: bool = False
    apply_intelligence: bool = True
    deal_id: Optional[int] = None  # link to existing instead of create


class LinkBrandIn(BaseModel):
    brand_record_id: int
    confirm: bool = False


class ConfirmIntelligenceIn(BaseModel):
    """User confirms extracted fields; marks them verified in intelligence_json."""
    verify_budget: bool = False
    verify_deliverables: bool = False
    verify_deadlines: bool = False
    verify_payment_terms: bool = False
    verify_collab_kind: bool = False


class IntelligenceOut(BaseModel):
    version: int
    verified: bool
    unverified_notice: str
    inquiry: dict
    collab_kind: str
    budget: dict
    deliverables: list
    deadlines: list
    payment_terms: dict
    summary: str
    suggested_reply: str
    follow_up: dict
    provenance: dict
    matches: Optional[dict] = None

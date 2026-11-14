from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, Field


class BrandUpdateIn(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=160)
    category: Optional[str] = None
    website: Optional[str] = None
    preferences: Optional[dict] = None
    relationship_summary: Optional[str] = Field(default=None, max_length=500)
    lead_stage: Optional[str] = None
    next_follow_up: Optional[date] = None


class BrandCreateIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=160)


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    kind: str = "general"


class FollowUpScheduleIn(BaseModel):
    due_date: date
    notes: str = ""
    deal_id: Optional[int] = None
    pitch_id: Optional[int] = None


class ContactCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    role: str = ""
    email: str = ""
    phone: str = ""
    notes: str = ""
    email_verified: bool = False

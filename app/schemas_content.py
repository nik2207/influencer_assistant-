from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from .models import CONTENT_FORMATS, CONTENT_STATUSES, CONTENT_TONES


class PlanItemIn(BaseModel):
    title: str = Field(default="Untitled", max_length=255)
    platform: str = "instagram"
    format: str = "idea"
    status: str = "idea"
    deal_id: Optional[int] = None
    event_id: Optional[int] = None
    scheduled_at: Optional[datetime] = None
    language: str = "en"
    tone: str = "friendly"
    tags: list[str] = Field(default_factory=list)
    notes: str = ""

    @field_validator("status")
    @classmethod
    def _status(cls, v):
        if v not in CONTENT_STATUSES:
            raise ValueError(f"status must be one of {CONTENT_STATUSES}")
        return v

    @field_validator("format")
    @classmethod
    def _format(cls, v):
        if v not in CONTENT_FORMATS:
            raise ValueError(f"format must be one of {CONTENT_FORMATS}")
        return v

    @field_validator("tone")
    @classmethod
    def _tone(cls, v):
        if v not in CONTENT_TONES:
            raise ValueError(f"tone must be one of {CONTENT_TONES}")
        return v


class PlanItemPatch(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    platform: Optional[str] = None
    format: Optional[str] = None
    status: Optional[str] = None
    deal_id: Optional[int] = None
    event_id: Optional[int] = None
    scheduled_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    language: Optional[str] = None
    tone: Optional[str] = None
    tags: Optional[list[str]] = None
    notes: Optional[str] = None


class PlanItemOut(BaseModel):
    id: int
    deal_id: Optional[int]
    event_id: Optional[int]
    platform: str
    format: str
    title: str
    status: str
    scheduled_at: Optional[datetime]
    published_at: Optional[datetime]
    language: str
    tone: str
    tags: list
    notes: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DraftIn(BaseModel):
    variant: str = "primary"
    body_json: dict = Field(default_factory=dict)
    caption: str = ""
    hashtags: str = ""
    parent_draft_id: Optional[int] = None


class DraftOut(BaseModel):
    id: int
    plan_item_id: int
    variant: str
    body_json: dict
    caption: str
    hashtags: str
    source: str
    parent_draft_id: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


class GenerateIdeasIn(BaseModel):
    platform: str = "instagram"
    count: int = Field(default=5, ge=1, le=12)
    theme: str = ""
    tone: str = "friendly"
    deal_id: Optional[int] = None


class GenerateScriptIn(BaseModel):
    plan_item_id: Optional[int] = None
    format: str
    platform: str = "instagram"
    topic: str = ""
    tone: str = "friendly"
    deal_id: Optional[int] = None

    @field_validator("format")
    @classmethod
    def _format(cls, v):
        if v not in CONTENT_FORMATS:
            raise ValueError(f"format must be one of {CONTENT_FORMATS}")
        return v


class RepurposeIn(BaseModel):
    draft_id: int
    target_format: str
    target_platform: str = "youtube"

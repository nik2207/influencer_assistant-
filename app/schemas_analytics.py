from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from .models import ANALYTICS_PLATFORMS, METRIC_KEYS


class ManualMetricIn(BaseModel):
    platform: str
    metric_key: str
    value: float = Field(ge=0)
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    social_account_id: Optional[int] = None
    deal_id: Optional[int] = None
    notes: str = ""

    @field_validator("platform")
    @classmethod
    def _platform(cls, v):
        if v not in ANALYTICS_PLATFORMS:
            raise ValueError(f"platform must be one of {ANALYTICS_PLATFORMS}")
        return v

    @field_validator("metric_key")
    @classmethod
    def _metric(cls, v):
        if v not in METRIC_KEYS:
            raise ValueError(f"metric_key must be one of {METRIC_KEYS}")
        return v


class ContentItemIn(BaseModel):
    platform: str
    title: str = Field(max_length=255)
    permalink: str = ""
    published_at: Optional[datetime] = None
    views: float = Field(default=0, ge=0)
    engagement: float = Field(default=0, ge=0)
    social_account_id: Optional[int] = None
    deal_id: Optional[int] = None

    @field_validator("platform")
    @classmethod
    def _platform(cls, v):
        if v not in ANALYTICS_PLATFORMS:
            raise ValueError(f"platform must be one of {ANALYTICS_PLATFORMS}")
        return v


class SnapshotOut(BaseModel):
    id: int
    platform: str
    metric_key: str
    value: float
    period_start: Optional[date]
    period_end: Optional[date]
    source: str
    confidence: str
    social_account_id: Optional[int]
    deal_id: Optional[int]
    notes: str
    created_at: datetime

    class Config:
        from_attributes = True


class ContentOut(BaseModel):
    id: int
    platform: str
    title: str
    permalink: str
    published_at: Optional[datetime]
    views: float
    engagement: float
    source: str
    deal_id: Optional[int]

    class Config:
        from_attributes = True

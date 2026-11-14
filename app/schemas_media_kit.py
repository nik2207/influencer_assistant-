from typing import Optional

from pydantic import BaseModel, Field, field_validator

from .models import MEDIA_KIT_TEMPLATES, RATE_DELIVERABLES


class MediaKitIn(BaseModel):
    headline: Optional[str] = Field(default=None, max_length=120)
    intro: Optional[str] = Field(default=None, max_length=800)
    pdf_template: Optional[str] = None
    show_rates: Optional[bool] = None
    show_metrics: Optional[bool] = None
    show_contact_email: Optional[bool] = None
    show_phone: Optional[bool] = None

    @field_validator("pdf_template")
    @classmethod
    def _tpl(cls, v):
        if v is not None and v not in MEDIA_KIT_TEMPLATES:
            raise ValueError(f"template must be one of {MEDIA_KIT_TEMPLATES}")
        return v


class RateLineIn(BaseModel):
    deliverable: str
    title: str = ""
    price: float = Field(ge=0)
    currency: str = "INR"
    notes: str = ""

    @field_validator("deliverable")
    @classmethod
    def _deliv(cls, v):
        if v not in RATE_DELIVERABLES:
            raise ValueError(f"deliverable must be one of {RATE_DELIVERABLES}")
        return v


class RatesIn(BaseModel):
    lines: list[RateLineIn]


class PortfolioItemIn(BaseModel):
    deal_id: int
    summary: str = ""
    visible: bool = True


class PortfolioIn(BaseModel):
    items: list[PortfolioItemIn]


class SampleIn(BaseModel):
    content_item_id: Optional[int] = None
    title: str = ""
    url: str = ""
    platform: str = ""
    notes: str = ""
    visible: bool = True


class SamplesIn(BaseModel):
    items: list[SampleIn]


class PublishIn(BaseModel):
    confirm_public: bool = False

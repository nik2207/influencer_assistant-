"""Validation for the creator profile. Every text field is trimmed, stripped of control characters and length-limited."""
import re
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from .services.personas import CREATOR_TYPES, CURRENCIES, LANGUAGES, PAYMENT_METHODS, PLATFORMS

CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")  # keeps \n and \t
HANDLE_RE = re.compile(r"^[A-Za-z0-9._\-]{1,60}$")
UPI_RE = re.compile(r"^[A-Za-z0-9._\-]{2,64}@[A-Za-z][A-Za-z0-9.\-]{1,63}$")
PHONE_RE = re.compile(r"^\+?[0-9 ()\-]{7,20}$")
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


def clean(v, limit: int, label: str, multiline: bool = False) -> str:
    if v is None:
        return ""
    if not isinstance(v, str):
        raise ValueError(f"{label} must be text")
    v = CTRL.sub("", v).strip()
    if not multiline:
        v = re.sub(r"\s+", " ", v)
    if len(v) > limit:
        raise ValueError(f"{label} must be {limit} characters or fewer")
    return v


class ProfileIn(BaseModel):
    """All fields optional: only the ones sent are changed."""
    name: Optional[str] = None
    handle: Optional[str] = None
    niche: Optional[str] = None
    city: Optional[str] = None
    language: Optional[str] = None
    upi_vpa: Optional[str] = None
    creator_type: Optional[str] = None
    bio: Optional[str] = None
    currency: Optional[str] = None
    languages: Optional[list[str]] = Field(default=None, max_length=3)
    contact_email: Optional[str] = None
    phone: Optional[str] = None
    home_location: Optional[str] = None
    payment_method: Optional[str] = None
    payment_terms_days: Optional[int] = Field(default=None, ge=0, le=120)
    invoice_notes: Optional[str] = None
    gstin: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        v = clean(v, 80, "Display name")
        if not v:
            raise ValueError("Display name can't be empty")
        return v

    @field_validator("handle")
    @classmethod
    def _handle(cls, v):
        v = clean(v, 61, "Handle").lstrip("@")
        if v and not HANDLE_RE.match(v):
            raise ValueError("Handle can use letters, numbers, dots, dashes and underscores only")
        return ("@" + v) if v else ""

    @field_validator("niche")
    @classmethod
    def _niche(cls, v):
        return clean(v, 120, "Niche")

    @field_validator("city")
    @classmethod
    def _city(cls, v):
        return clean(v, 80, "City")

    @field_validator("home_location")
    @classmethod
    def _home(cls, v):
        return clean(v, 200, "Home location")

    @field_validator("bio")
    @classmethod
    def _bio(cls, v):
        return clean(v, 400, "Bio", multiline=True)

    @field_validator("invoice_notes")
    @classmethod
    def _notes(cls, v):
        return clean(v, 400, "Invoice notes", multiline=True)

    @field_validator("language")
    @classmethod
    def _language(cls, v):
        if v not in LANGUAGES:
            raise ValueError("Choose English, Hindi or Marathi")
        return v

    @field_validator("languages")
    @classmethod
    def _languages(cls, v):
        v = list(dict.fromkeys(v or []))
        if not v:
            raise ValueError("Choose at least one language")
        if any(x not in LANGUAGES for x in v):
            raise ValueError("Languages can be English, Hindi or Marathi")
        return v

    @field_validator("creator_type")
    @classmethod
    def _type(cls, v):
        if v not in CREATOR_TYPES:
            raise ValueError("Choose a creator type from the list")
        return v

    @field_validator("currency")
    @classmethod
    def _currency(cls, v):
        v = (v or "").upper()
        if v not in CURRENCIES:
            raise ValueError("Currency must be one of " + ", ".join(CURRENCIES))
        return v

    @field_validator("payment_method")
    @classmethod
    def _method(cls, v):
        if v not in PAYMENT_METHODS:
            raise ValueError("Choose UPI, bank transfer or other")
        return v

    @field_validator("upi_vpa")
    @classmethod
    def _upi(cls, v):
        v = clean(v, 100, "UPI ID")
        if v and not UPI_RE.match(v):
            raise ValueError("UPI ID should look like name@bank")
        return v

    @field_validator("contact_email")
    @classmethod
    def _email(cls, v):
        v = clean(v, 255, "Email").lower()
        if v and not EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address")
        return v

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        v = clean(v, 24, "Phone")
        if v and not PHONE_RE.match(v):
            raise ValueError("Phone can have digits, spaces, +, - and brackets (7 to 20 characters)")
        return v

    @field_validator("gstin")
    @classmethod
    def _gstin(cls, v):
        v = clean(v, 15, "GSTIN").upper()
        if v and not GSTIN_RE.match(v):
            raise ValueError("GSTIN should be 15 characters, like 27ABCDE1234F1Z5")
        return v


class PlatformIn(BaseModel):
    handle: str = ""
    url: str = ""
    followers: int = Field(default=0, ge=0, le=2_000_000_000)

    @field_validator("handle")
    @classmethod
    def _handle(cls, v):
        v = clean(v, 61, "Handle").lstrip("@")
        if not v:
            raise ValueError("Enter the account handle")
        if not HANDLE_RE.match(v):
            raise ValueError("Handle can use letters, numbers, dots, dashes and underscores only")
        return v

    @field_validator("url")
    @classmethod
    def _url(cls, v):
        v = clean(v, 300, "Profile link")
        if not v:
            return ""
        if re.search(r"\s", v):
            raise ValueError("Profile link can't contain spaces")
        p = urlparse(v)
        if p.scheme not in ("http", "https") or not p.hostname:
            raise ValueError("Profile link must start with https://")
        if p.username or p.password:
            raise ValueError("Profile link can't contain a username or password")
        return v


def check_platform_url(platform: str, url: str) -> None:
    """The link must belong to the platform it is saved under (no random sites in a 'YouTube' slot)."""
    if not url:
        return
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    ok = any(host == d or host.endswith("." + d) for d in PLATFORMS[platform]["domains"])
    if not ok:
        label = PLATFORMS[platform]["label"]
        article = "an" if label[0].lower() in "aeiou" else "a"
        raise ValueError(f"That link doesn't look like {article} {label} link")

from urllib.parse import quote

import httpx

from ..config import settings


def upi_link(vpa: str, payee: str, amount: float, note: str) -> str:
    return f"upi://pay?pa={quote(vpa)}&pn={quote(payee)}&am={amount:.2f}&cu=INR&tn={quote(note)}"


def razorpay_link(amount: float, description: str, customer: str) -> str | None:
    if not (settings.razorpay_key_id and settings.razorpay_key_secret):
        return None
    try:
        r = httpx.post(
            "https://api.razorpay.com/v1/payment_links",
            auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
            json={
                "amount": int(round(amount * 100)),
                "currency": "INR",
                "description": description,
                "customer": {"name": customer},
            },
            timeout=20,
        )
        r.raise_for_status()
        return r.json().get("short_url")
    except httpx.HTTPError:
        return None


def make_payment_link(user, amount: float, description: str, customer: str) -> str:
    link = razorpay_link(amount, description, customer)
    if link:
        return link
    vpa = user.upi_vpa or settings.upi_vpa
    if vpa:
        return upi_link(vpa, user.name or "Creator", amount, description)
    return ""

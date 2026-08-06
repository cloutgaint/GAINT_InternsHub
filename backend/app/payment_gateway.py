from __future__ import annotations

import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.request

from .config import settings


class RazorpayError(RuntimeError):
    pass


def ensure_razorpay_configured() -> None:
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise RazorpayError(
            "Razorpay is not configured. Add a Key ID and Key Secret to backend/.env and restart the backend."
        )


def _request(path: str, method: str = "GET", payload: dict | None = None) -> dict:
    ensure_razorpay_configured()
    credentials = base64.b64encode(
        f"{settings.razorpay_key_id}:{settings.razorpay_key_secret}".encode("utf-8")
    ).decode("ascii")
    request = urllib.request.Request(
        f"{settings.razorpay_api_url}{path}",
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8", errors="replace"))
            detail = body.get("error", {}).get("description") or "Razorpay rejected the request"
        except (json.JSONDecodeError, AttributeError):
            detail = "Razorpay rejected the request"
        raise RazorpayError(f"{detail} (HTTP {exc.code})") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RazorpayError(f"Razorpay is currently unavailable: {exc}") from exc


def create_order(
    *,
    amount_rupees: int,
    currency: str,
    receipt: str,
    notes: dict[str, str],
) -> dict:
    if amount_rupees < 1:
        raise RazorpayError("Payment amount must be at least ₹1")
    return _request(
        "/orders",
        method="POST",
        payload={
            "amount": amount_rupees * 100,
            "currency": currency,
            "receipt": receipt[:40],
            "notes": notes,
        },
    )


def fetch_payment(payment_id: str) -> dict:
    return _request(f"/payments/{payment_id}")


def verify_checkout_signature(
    *,
    order_id: str,
    payment_id: str,
    signature: str,
) -> bool:
    ensure_razorpay_configured()
    expected = hmac.new(
        settings.razorpay_key_secret.encode("utf-8"),
        f"{order_id}|{payment_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_webhook_signature(*, raw_body: bytes, signature: str) -> bool:
    if not settings.razorpay_webhook_secret:
        raise RazorpayError("RAZORPAY_WEBHOOK_SECRET is not configured")
    expected = hmac.new(
        settings.razorpay_webhook_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

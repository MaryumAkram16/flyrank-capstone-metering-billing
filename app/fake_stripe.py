"""
FakeStripe — a local stand-in for Stripe test mode.

Real Stripe accounts require a supported-country business entity; Pakistan
isn't on Stripe's, Paddle's, Lemon Squeezy's, or Razorpay's supported-seller
list. This module reproduces Stripe's actual webhook contract so the hard
parts of the integration — signature verification, replay protection, event
processing — are genuinely exercised rather than faked away:

  - Signing scheme matches Stripe's: header is "t=<unix_ts>,v1=<hmac_sha256_hex>"
    over the string "<timestamp>.<raw_payload>", using a shared secret.
  - Events carry an "id" (used for dedup) and a "type"
    (checkout.session.completed, customer.subscription.updated/deleted),
    exactly like Stripe's event objects.

Swapping in real Stripe later means replacing this file and app/checkout.py —
app/webhook_handlers.py and the data model don't change, because they only
ever see a verified, parsed event dict.
"""
import hashlib
import hmac
import json
import time
import uuid
from typing import Optional


class SignatureVerificationError(Exception):
    """Raised when a webhook payload's signature doesn't check out."""


def sign_payload(payload: bytes, secret: str, timestamp: Optional[int] = None) -> str:
    """Build a Stripe-style 'Stripe-Signature' header value for a payload."""
    ts = timestamp if timestamp is not None else int(time.time())
    signed_payload = f"{ts}.{payload.decode()}"
    signature = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
    return f"t={ts},v1={signature}"


def verify_and_parse(
    payload: bytes, sig_header: str, secret: str, tolerance_seconds: int = 300
) -> dict:
    """
    Verify a webhook signature the same way Stripe's own SDK does: reconstruct
    "<timestamp>.<payload>", HMAC-SHA256 it with the shared secret, and compare
    in constant time. Also rejects stale timestamps (replay protection).

    Raises SignatureVerificationError on any failure — a forged secret, a
    tampered payload, a malformed header, or a payload delivered too late.
    """
    try:
        parts = dict(item.split("=", 1) for item in sig_header.split(","))
        timestamp = int(parts["t"])
        signature = parts["v1"]
    except (KeyError, ValueError):
        raise SignatureVerificationError("Malformed Stripe-Signature header")

    signed_payload = f"{timestamp}.{payload.decode()}"
    expected_signature = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_signature, signature):
        raise SignatureVerificationError("Signature does not match payload")

    if abs(time.time() - timestamp) > tolerance_seconds:
        raise SignatureVerificationError("Timestamp outside tolerance — possible replay")

    return json.loads(payload)


def build_event(event_type: str, data_object: dict, event_id: Optional[str] = None) -> dict:
    """Construct a Stripe-shaped event: {id, type, created, data: {object}}."""
    return {
        "id": event_id or f"evt_{uuid.uuid4().hex}",
        "type": event_type,
        "created": int(time.time()),
        "data": {"object": data_object},
    }

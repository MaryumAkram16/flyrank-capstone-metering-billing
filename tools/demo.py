"""
demo.py — runs the §13 six-minute demo flow end-to-end against a running server.

Start the app first (in another terminal):
    uvicorn app.main:app --reload

Then, with the same tenant the seed script created (tenant_id=1, Free plan,
already sitting at 999/1000 API calls):

    python -m tools.demo

Each step prints what it's doing and the raw response, so you can run this
once to rehearse, then narrate the same steps live during the real demo.
"""
import json
import os
import time

import httpx

from app.fake_stripe import build_event, sign_payload

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_fake_test_secret_change_me")
TENANT_ID = int(os.getenv("DEMO_TENANT_ID", "1"))


def step(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def show(resp: httpx.Response) -> None:
    print(f"HTTP {resp.status_code}")
    try:
        print(json.dumps(resp.json(), indent=2))
    except ValueError:
        print(resp.text)


def main() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:

        step("STEP 1 — Drive the tenant to its exact quota boundary")
        print("Tenant is seeded at 999/1000 API calls. This call lands EXACTLY on 1000 — must be allowed.")
        resp = client.post("/generate", json={
            "tenant_id": TENANT_ID,
            "idempotency_key": "demo-boundary-call",
            "usage_type": "api_call",
        })
        show(resp)

        print("\nOne more call now — this one is OVER the limit, must be rejected with 429.")
        resp = client.post("/generate", json={
            "tenant_id": TENANT_ID,
            "idempotency_key": "demo-over-limit-call",
            "usage_type": "api_call",
        })
        show(resp)

        step("STEP 2 — Retry with the SAME idempotency key: usage must not double-count")
        resp = client.post("/generate", json={
            "tenant_id": TENANT_ID,
            "idempotency_key": "demo-boundary-call",  # same key as the allowed call above
            "usage_type": "api_call",
        })
        show(resp)
        print("\nNote 'duplicate: true' and the SAME usage_event_id as Step 1 — one row, not two.")

        step("STEP 3 — Stripe test Checkout (FakeStripe) flips the tenant Free -> Pro")
        resp = client.post("/checkout", json={"tenant_id": TENANT_ID, "plan_name": "Pro"})
        show(resp)
        checkout_id = resp.json()["id"]

        print(f"\nCustomer 'pays' on the hosted page for session {checkout_id}...")
        resp = client.post(f"/fake-checkout/{checkout_id}/pay")
        show(resp)
        payload = resp.json()["payload"]  # raw string — send verbatim, never re-serialize
        signature = resp.json()["stripe_signature"]

        print("\nDelivering the signed webhook to /webhooks/stripe (this is what actually applies it):")
        resp = client.post(
            "/webhooks/stripe",
            content=payload,
            headers={"Content-Type": "application/json", "Stripe-Signature": signature},
        )
        show(resp)

        print("\nGET /usage now shows Pro limits (100,000 calls / 10,000,000 tokens):")
        resp = client.get("/usage", params={"tenant_id": TENANT_ID})
        show(resp)

        step("STEP 4 — Forged webhook is rejected; a replayed real event is ignored")
        print("Sending a checkout.session.completed event signed with the WRONG secret:")
        forged_event = build_event("checkout.session.completed", {"tenant_id": TENANT_ID, "plan_id": 1})
        forged_payload = json.dumps(forged_event).encode()
        forged_signature = sign_payload(forged_payload, "definitely_the_wrong_secret")
        resp = client.post(
            "/webhooks/stripe",
            content=forged_payload,
            headers={"Content-Type": "application/json", "Stripe-Signature": forged_signature},
        )
        show(resp)
        print("-> 400, and the tenant's plan is untouched by this forged event.")

        print("\nReplaying the REAL checkout event from Step 3 a second time:")
        resp = client.post(
            "/webhooks/stripe",
            content=payload,
            headers={"Content-Type": "application/json", "Stripe-Signature": signature},
        )
        show(resp)
        print("-> 'ignored_duplicate' — processed once, not twice.")

        step("STEP 5 — Final GET /usage: used / limit / cost, all adding up exactly")
        resp = client.get("/usage", params={"tenant_id": TENANT_ID})
        show(resp)

        step("Closing line")
        print('"Usage, money, and customer access stay correct under retries, failures, '
              'and real-world conditions."')


if __name__ == "__main__":
    main()

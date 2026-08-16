"""
fake_stripe_cli.py — a local stand-in for the Stripe CLI's `stripe trigger`.

The real Stripe CLI forwards and replays webhook events against localhost
without needing a public URL. This script does the same job against
FakeStripe: it builds a Stripe-shaped event, signs it (or deliberately
doesn't), and POSTs it straight to /webhooks/stripe.

Usage (from the repo root, with the app running on localhost:8000):

    python -m tools.fake_stripe_cli sub_deleted --tenant-id 1
    python -m tools.fake_stripe_cli forge --tenant-id 1 --plan-id 2
    python -m tools.fake_stripe_cli replay --tenant-id 1 --plan-id 2

`replay` sends the SAME event twice in a row to demonstrate dedup.
`forge` signs with the wrong secret to demonstrate the 400 rejection.
For a normal Checkout → Pro upgrade, use POST /checkout then
POST /fake-checkout/{id}/pay (see README) — this CLI is for the
webhook-only demo scenarios.
"""
import argparse
import json
import os

import httpx

from app.fake_stripe import build_event, sign_payload

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_fake_test_secret_change_me")


def send(event: dict, secret: str) -> None:
    payload = json.dumps(event).encode()
    header = sign_payload(payload, secret)
    resp = httpx.post(
        f"{BASE_URL}/webhooks/stripe",
        content=payload,
        headers={"Content-Type": "application/json", "Stripe-Signature": header},
    )
    print(f"HTTP {resp.status_code}")
    print(resp.text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_sub_deleted = sub.add_parser("sub_deleted", help="Cancel a tenant's subscription")
    p_sub_deleted.add_argument("--tenant-id", type=int, required=True)

    p_forge = sub.add_parser("forge", help="Send an event signed with the WRONG secret — expect HTTP 400")
    p_forge.add_argument("--tenant-id", type=int, required=True)
    p_forge.add_argument("--plan-id", type=int, required=True)

    p_replay = sub.add_parser("replay", help="Send the same event twice — second call should be ignored")
    p_replay.add_argument("--tenant-id", type=int, required=True)
    p_replay.add_argument("--plan-id", type=int, required=True)

    args = parser.parse_args()

    if args.command == "sub_deleted":
        event = build_event("customer.subscription.deleted", {"tenant_id": args.tenant_id})
        send(event, STRIPE_WEBHOOK_SECRET)

    elif args.command == "forge":
        event = build_event(
            "checkout.session.completed",
            {"tenant_id": args.tenant_id, "plan_id": args.plan_id},
        )
        print("Sending with a deliberately wrong secret — expect HTTP 400:")
        send(event, "definitely_the_wrong_secret")

    elif args.command == "replay":
        event = build_event(
            "checkout.session.completed",
            {"tenant_id": args.tenant_id, "plan_id": args.plan_id},
            event_id="evt_fixed_for_replay_demo",
        )
        print("First delivery:")
        send(event, STRIPE_WEBHOOK_SECRET)
        print("\nReplaying the exact same event:")
        send(event, STRIPE_WEBHOOK_SECRET)


if __name__ == "__main__":
    main()

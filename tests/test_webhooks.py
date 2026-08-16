import json
import time

import pytest
from sqlmodel import select

from app.fake_stripe import SignatureVerificationError, build_event, sign_payload, verify_and_parse
from app.models import Plan, Subscription, Tenant
from app.webhook_handlers import handle_event

SECRET = "whsec_test_secret"


def test_valid_signature_verifies_and_parses():
    event = build_event("checkout.session.completed", {"tenant_id": 1})
    payload = json.dumps(event).encode()
    header = sign_payload(payload, SECRET)

    parsed = verify_and_parse(payload, header, SECRET)
    assert parsed["id"] == event["id"]


def test_forged_signature_is_rejected():
    """The core of Probe 4: a bad signature must never be accepted."""
    event = build_event("checkout.session.completed", {"tenant_id": 1})
    payload = json.dumps(event).encode()
    forged_header = sign_payload(payload, "wrong_secret")

    with pytest.raises(SignatureVerificationError):
        verify_and_parse(payload, forged_header, SECRET)


def test_tampered_payload_is_rejected():
    event = build_event("checkout.session.completed", {"tenant_id": 1})
    payload = json.dumps(event).encode()
    header = sign_payload(payload, SECRET)  # signed over the ORIGINAL payload

    tampered_payload = json.dumps({**event, "data": {"object": {"tenant_id": 999}}}).encode()

    with pytest.raises(SignatureVerificationError):
        verify_and_parse(tampered_payload, header, SECRET)


def test_stale_timestamp_is_rejected():
    event = build_event("checkout.session.completed", {"tenant_id": 1})
    payload = json.dumps(event).encode()
    old_timestamp = int(time.time()) - 1000
    header = sign_payload(payload, SECRET, timestamp=old_timestamp)

    with pytest.raises(SignatureVerificationError):
        verify_and_parse(payload, header, SECRET, tolerance_seconds=300)


def test_malformed_header_is_rejected():
    event = build_event("checkout.session.completed", {"tenant_id": 1})
    payload = json.dumps(event).encode()

    with pytest.raises(SignatureVerificationError):
        verify_and_parse(payload, "not-a-real-header", SECRET)


def _seed_tenant_on_free(session):
    free = Plan(name="Free", api_call_limit=1000, ai_token_limit=100_000)
    pro = Plan(name="Pro", api_call_limit=100_000, ai_token_limit=10_000_000)
    session.add(free)
    session.add(pro)
    session.commit()
    session.refresh(free)
    session.refresh(pro)

    tenant = Tenant(name="T1")
    session.add(tenant)
    session.commit()
    session.refresh(tenant)

    subscription = Subscription(tenant_id=tenant.id, plan_id=free.id, status="active")
    session.add(subscription)
    session.commit()

    return tenant, free, pro


def test_checkout_completed_event_flips_the_plan(session):
    tenant, free, pro = _seed_tenant_on_free(session)

    event = build_event(
        "checkout.session.completed",
        {"tenant_id": tenant.id, "plan_id": pro.id, "subscription_id": "sub_fake_1"},
    )
    result = handle_event(session, event)
    assert result["status"] == "processed"

    subscription = session.exec(select(Subscription).where(Subscription.tenant_id == tenant.id)).first()
    assert subscription.plan_id == pro.id
    assert subscription.status == "active"


def test_duplicate_event_is_processed_exactly_once(session):
    tenant, free, pro = _seed_tenant_on_free(session)
    event = build_event(
        "checkout.session.completed",
        {"tenant_id": tenant.id, "plan_id": pro.id},
        event_id="evt_fixed_1",
    )

    first = handle_event(session, event)
    second = handle_event(session, event)

    assert first["status"] == "processed"
    assert second["status"] == "ignored_duplicate"

    subscription = session.exec(select(Subscription).where(Subscription.tenant_id == tenant.id)).first()
    assert subscription.plan_id == pro.id  # unchanged by the replay, not reprocessed


def test_subscription_deleted_event_cancels_subscription(session):
    tenant, free, pro = _seed_tenant_on_free(session)
    event = build_event("customer.subscription.deleted", {"tenant_id": tenant.id})

    handle_event(session, event)

    subscription = session.exec(select(Subscription).where(Subscription.tenant_id == tenant.id)).first()
    assert subscription.status == "canceled"


def test_subscription_updated_event_changes_status(session):
    tenant, free, pro = _seed_tenant_on_free(session)
    event = build_event("customer.subscription.updated", {"tenant_id": tenant.id, "status": "past_due"})

    handle_event(session, event)

    subscription = session.exec(select(Subscription).where(Subscription.tenant_id == tenant.id)).first()
    assert subscription.status == "past_due"


def test_unknown_event_type_is_ignored_gracefully(session):
    tenant, free, pro = _seed_tenant_on_free(session)
    event = build_event("some.future.event.type", {"tenant_id": tenant.id})

    result = handle_event(session, event)
    assert result["status"] == "processed"  # accepted, just no-op — never a crash

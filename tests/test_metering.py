from sqlmodel import select

from app.metering import record_usage
from app.models import UsageEvent


def test_records_a_new_usage_event(session):
    event, created = record_usage(
        session, tenant_id=1, idempotency_key="key-1", usage_type="api_call", quantity=1
    )
    assert created is True
    assert event.quantity == 1
    assert event.type == "api_call"


def test_duplicate_idempotency_key_does_not_double_count(session):
    """The heart of the capstone: same request retried == exactly one usage event."""
    event1, created1 = record_usage(
        session, tenant_id=1, idempotency_key="key-1", usage_type="api_call", quantity=1
    )
    event2, created2 = record_usage(
        session, tenant_id=1, idempotency_key="key-1", usage_type="api_call", quantity=1
    )

    assert created1 is True
    assert created2 is False
    assert event1.id == event2.id  # the retry returns the SAME row

    rows = session.exec(
        select(UsageEvent).where(UsageEvent.tenant_id == 1, UsageEvent.idempotency_key == "key-1")
    ).all()
    assert len(rows) == 1  # exactly one row despite two calls


def test_retry_ten_times_still_one_event(session):
    results = [
        record_usage(session, tenant_id=1, idempotency_key="key-x", usage_type="api_call", quantity=5)
        for _ in range(10)
    ]
    created_flags = [created for _, created in results]
    assert created_flags.count(True) == 1
    assert created_flags.count(False) == 9

    rows = session.exec(
        select(UsageEvent).where(UsageEvent.tenant_id == 1, UsageEvent.idempotency_key == "key-x")
    ).all()
    assert len(rows) == 1
    assert rows[0].quantity == 5  # not 50 — never re-summed on retry


def test_same_key_different_tenants_are_independent(session):
    event_a, created_a = record_usage(
        session, tenant_id=1, idempotency_key="shared-key", usage_type="api_call", quantity=1
    )
    event_b, created_b = record_usage(
        session, tenant_id=2, idempotency_key="shared-key", usage_type="api_call", quantity=1
    )
    assert created_a is True
    assert created_b is True
    assert event_a.id != event_b.id  # idempotency is scoped per tenant, not global


def test_different_keys_same_tenant_create_separate_events(session):
    event_a, _ = record_usage(session, 1, "key-a", "api_call", 1)
    event_b, _ = record_usage(session, 1, "key-b", "api_call", 1)
    assert event_a.id != event_b.id

import pytest

from app.metering import record_usage
from app.models import Plan, Subscription, Tenant
from app.quotas import PaymentRequiredError, QuotaExceededError, enforce_quota


def _seed_tenant_with_plan(session, limit=1000, status="active"):
    plan = Plan(name="Free", api_call_limit=limit, ai_token_limit=100_000)
    session.add(plan)
    session.commit()
    session.refresh(plan)

    tenant = Tenant(name="T1")
    session.add(tenant)
    session.commit()
    session.refresh(tenant)

    subscription = Subscription(tenant_id=tenant.id, plan_id=plan.id, status=status)
    session.add(subscription)
    session.commit()

    return tenant, plan


def test_allows_request_that_lands_exactly_on_the_limit(session):
    tenant, plan = _seed_tenant_with_plan(session, limit=1000)
    for i in range(999):
        record_usage(session, tenant.id, f"key-{i}", "api_call", 1)

    # the 1000th call brings the total to exactly 1000 — must be ALLOWED, not rejected
    used, limit = enforce_quota(session, tenant.id, "api_call", 1)
    assert used == 999
    assert limit == 1000


def test_rejects_the_call_that_would_exceed_the_limit(session):
    tenant, plan = _seed_tenant_with_plan(session, limit=1000)
    for i in range(1000):
        record_usage(session, tenant.id, f"key-{i}", "api_call", 1)

    # tenant is already at 1000/1000 — one more call must be rejected with 429
    with pytest.raises(QuotaExceededError):
        enforce_quota(session, tenant.id, "api_call", 1)


def test_just_under_quota_is_allowed(session):
    tenant, plan = _seed_tenant_with_plan(session, limit=1000)
    for i in range(500):
        record_usage(session, tenant.id, f"key-{i}", "api_call", 1)

    used, limit = enforce_quota(session, tenant.id, "api_call", 1)
    assert used == 500
    assert limit == 1000


def test_rejects_when_no_subscription_exists(session):
    tenant = Tenant(name="T2")
    session.add(tenant)
    session.commit()
    session.refresh(tenant)

    with pytest.raises(PaymentRequiredError):
        enforce_quota(session, tenant.id, "api_call", 1)


def test_rejects_when_subscription_is_canceled(session):
    tenant, plan = _seed_tenant_with_plan(session, limit=1000, status="canceled")
    with pytest.raises(PaymentRequiredError):
        enforce_quota(session, tenant.id, "api_call", 1)


def test_ai_tokens_use_the_token_limit_not_the_api_call_limit(session):
    tenant, plan = _seed_tenant_with_plan(session, limit=1000)  # api_call_limit=1000, ai_token_limit=100_000
    used, limit = enforce_quota(session, tenant.id, "ai_tokens", 50_000)
    assert used == 0
    assert limit == 100_000

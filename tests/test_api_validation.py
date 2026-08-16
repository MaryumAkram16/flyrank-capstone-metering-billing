from app.models import Plan, Subscription, Tenant


def _seed_tenant_on_free(session):
    free = Plan(name="Free", api_call_limit=1000, ai_token_limit=100_000)
    session.add(free)
    session.commit()
    session.refresh(free)

    tenant = Tenant(name="T1")
    session.add(tenant)
    session.commit()
    session.refresh(tenant)

    subscription = Subscription(tenant_id=tenant.id, plan_id=free.id, status="active")
    session.add(subscription)
    session.commit()

    return tenant, free


def test_negative_quantity_is_rejected_not_silently_accepted(client, session):
    """
    Regression: a negative quantity was previously accepted, reduced
    used_this_month below its true value (bypassing quota), and produced a
    negative cost — exactly the class of bug the brief warns about
    ("giving away unlimited access, or losing revenue"). Found by manually
    probing the live API while cross-checking against the brief, not caught
    by the service-layer tests alone since they never go through the FastAPI
    request model's validation.
    """
    tenant, _ = _seed_tenant_on_free(session)

    resp = client.post("/generate", json={
        "tenant_id": tenant.id,
        "idempotency_key": "neg-test",
        "usage_type": "api_call",
        "quantity": -500,
    })
    assert resp.status_code == 422  # rejected at the request boundary, never reaches billing logic


def test_zero_quantity_is_rejected(client, session):
    tenant, _ = _seed_tenant_on_free(session)
    resp = client.post("/generate", json={
        "tenant_id": tenant.id,
        "idempotency_key": "zero-test",
        "usage_type": "api_call",
        "quantity": 0,
    })
    assert resp.status_code == 422


def test_negative_token_counts_are_rejected(client, session):
    tenant, _ = _seed_tenant_on_free(session)
    resp = client.post("/generate", json={
        "tenant_id": tenant.id,
        "idempotency_key": "neg-tokens-test",
        "usage_type": "ai_tokens",
        "metadata": {"input_tokens": -1000, "cached_input_tokens": 0, "output_tokens": 0},
    })
    assert resp.status_code == 400
    assert "input_tokens" in resp.json()["detail"]


def test_non_integer_token_count_is_rejected(client, session):
    tenant, _ = _seed_tenant_on_free(session)
    resp = client.post("/generate", json={
        "tenant_id": tenant.id,
        "idempotency_key": "float-tokens-test",
        "usage_type": "ai_tokens",
        "metadata": {"input_tokens": 100.5, "cached_input_tokens": 0, "output_tokens": 0},
    })
    assert resp.status_code == 400


def test_valid_positive_quantity_is_accepted(client, session):
    tenant, _ = _seed_tenant_on_free(session)
    resp = client.post("/generate", json={
        "tenant_id": tenant.id,
        "idempotency_key": "valid-test",
        "usage_type": "api_call",
        "quantity": 5,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["quantity"] == 5
    assert body["cost_micro_dollars"] >= 0


def test_negative_quantity_never_reaches_the_database(client, session):
    """Belt-and-suspenders: after a rejected negative-quantity request, usage is untouched."""
    tenant, _ = _seed_tenant_on_free(session)

    client.post("/generate", json={
        "tenant_id": tenant.id,
        "idempotency_key": "neg-test-2",
        "usage_type": "api_call",
        "quantity": -999,
    })

    resp = client.get("/usage", params={"tenant_id": tenant.id})
    assert resp.status_code == 200
    assert resp.json()["api_calls"]["used"] == 0
    assert resp.json()["cost"]["micro_dollars"] == 0

from sqlmodel import Session, select

from app.models import ProcessedWebhookEvent, Subscription


def is_duplicate_event(session: Session, event_id: str) -> bool:
    return session.get(ProcessedWebhookEvent, event_id) is not None


def mark_processed(session: Session, event_id: str) -> None:
    session.add(ProcessedWebhookEvent(stripe_event_id=event_id))
    session.commit()


def handle_event(session: Session, event: dict) -> dict:
    """
    Apply a verified webhook event. Caller (the route) is responsible for
    signature verification — by the time an event reaches here it's trusted.

    Idempotent: the same event.id processed twice is a no-op the second time.
    """
    event_id = event["id"]
    event_type = event["type"]

    if is_duplicate_event(session, event_id):
        return {"status": "ignored_duplicate", "event_id": event_id, "type": event_type}

    obj = event["data"]["object"]

    if event_type == "checkout.session.completed":
        _handle_checkout_completed(session, obj)
    elif event_type == "customer.subscription.updated":
        _handle_subscription_updated(session, obj)
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(session, obj)
    # Unknown event types are accepted and ignored — same as Stripe recommends,
    # so adding new event types later doesn't break existing webhook delivery.

    mark_processed(session, event_id)
    return {"status": "processed", "event_id": event_id, "type": event_type}


def _get_subscription(session: Session, tenant_id: int) -> Subscription | None:
    return session.exec(select(Subscription).where(Subscription.tenant_id == tenant_id)).first()


def _handle_checkout_completed(session: Session, obj: dict) -> None:
    tenant_id = obj["tenant_id"]
    plan_id = obj["plan_id"]
    fake_subscription_id = obj.get("subscription_id", f"sub_fake_{tenant_id}")

    subscription = _get_subscription(session, tenant_id)
    if subscription is None:
        subscription = Subscription(
            tenant_id=tenant_id,
            plan_id=plan_id,
            stripe_subscription_id=fake_subscription_id,
            status="active",
        )
        session.add(subscription)
    else:
        subscription.plan_id = plan_id
        subscription.stripe_subscription_id = fake_subscription_id
        subscription.status = "active"

    session.commit()


def _handle_subscription_updated(session: Session, obj: dict) -> None:
    tenant_id = obj["tenant_id"]
    subscription = _get_subscription(session, tenant_id)
    if subscription is not None:
        subscription.status = obj.get("status", subscription.status)
        if "plan_id" in obj:
            subscription.plan_id = obj["plan_id"]
        session.commit()


def _handle_subscription_deleted(session: Session, obj: dict) -> None:
    tenant_id = obj["tenant_id"]
    subscription = _get_subscription(session, tenant_id)
    if subscription is not None:
        subscription.status = "canceled"
        session.commit()

import uuid

from sqlmodel import Session, select

from app.models import CheckoutSession, Plan


class CheckoutError(Exception):
    """Raised for any checkout-flow problem — unknown plan, missing/completed session."""


def create_checkout_session(session: Session, tenant_id: int, plan_name: str) -> CheckoutSession:
    plan = session.exec(select(Plan).where(Plan.name == plan_name)).first()
    if plan is None:
        raise CheckoutError(f"No plan named '{plan_name}'")

    checkout_session = CheckoutSession(
        id=f"cs_test_{uuid.uuid4().hex}",
        tenant_id=tenant_id,
        plan_id=plan.id,
        status="open",
    )
    session.add(checkout_session)
    session.commit()
    session.refresh(checkout_session)
    return checkout_session


def complete_checkout_session(session: Session, session_id: str) -> dict:
    """
    Simulates the customer finishing payment on FakeStripe's hosted page.

    This does NOT touch Subscription/Plan directly — it only marks the
    CheckoutSession complete and returns the event payload that "Stripe"
    would deliver. Applying it to the tenant's plan happens exclusively via
    POST /webhooks/stripe, same separation of concerns as real Stripe:
    payment truth lives at the provider, the app mirrors it through verified
    events only.
    """
    checkout_session = session.get(CheckoutSession, session_id)
    if checkout_session is None:
        raise CheckoutError(f"No checkout session '{session_id}'")
    if checkout_session.status == "complete":
        raise CheckoutError(f"Checkout session '{session_id}' was already completed")

    checkout_session.status = "complete"
    session.add(checkout_session)
    session.commit()

    return {
        "tenant_id": checkout_session.tenant_id,
        "plan_id": checkout_session.plan_id,
        "checkout_session_id": checkout_session.id,
        "subscription_id": f"sub_fake_{checkout_session.tenant_id}",
    }

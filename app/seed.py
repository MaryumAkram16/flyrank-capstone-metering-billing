import uuid

from app.db import get_session_direct, init_db
from app.models import Plan, Subscription, Tenant, UsageEvent


def seed() -> None:
    init_db()
    with get_session_direct() as session:
        free = Plan(name="Free", api_call_limit=1000, ai_token_limit=100_000, price_id=None)
        pro = Plan(
            name="Pro",
            api_call_limit=100_000,
            ai_token_limit=10_000_000,
            price_id="price_pro_placeholder",
        )
        session.add(free)
        session.add(pro)
        session.commit()
        session.refresh(free)
        session.refresh(pro)

        tenant = Tenant(name="Demo Tenant")
        session.add(tenant)
        session.commit()
        session.refresh(tenant)

        subscription = Subscription(
            tenant_id=tenant.id, plan_id=free.id, stripe_subscription_id=None, status="active"
        )
        session.add(subscription)
        session.commit()

        # Sit the tenant one call away from its quota, so the boundary is easy to demo.
        for _ in range(999):
            session.add(
                UsageEvent(
                    tenant_id=tenant.id,
                    idempotency_key=str(uuid.uuid4()),
                    type="api_call",
                    quantity=1,
                )
            )
        session.commit()

        print(f"Seeded tenant_id={tenant.id} on Free plan — 999/1000 api_calls used this month.")
        print(f"Plan ids: Free={free.id}, Pro={pro.id}")


if __name__ == "__main__":
    seed()

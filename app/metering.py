import json
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models import UsageEvent


def record_usage(
    session: Session,
    tenant_id: int,
    idempotency_key: str,
    usage_type: str,
    quantity: int,
    metadata: Optional[dict] = None,
) -> tuple[UsageEvent, bool]:
    """
    Record one billable usage event, idempotently.

    Same (tenant_id, idempotency_key) called twice → the second call returns
    the SAME row and does not create a new one. This is what makes retries safe.

    Returns (event, created) where created=False means this was a duplicate.
    """
    existing = session.exec(
        select(UsageEvent).where(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.idempotency_key == idempotency_key,
        )
    ).first()
    if existing is not None:
        return existing, False

    event = UsageEvent(
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        type=usage_type,
        quantity=quantity,
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    session.add(event)
    try:
        session.commit()
    except IntegrityError:
        # Race condition: two requests with the same key committed concurrently.
        # The unique constraint caught it — fetch the winner and return that.
        session.rollback()
        existing = session.exec(
            select(UsageEvent).where(
                UsageEvent.tenant_id == tenant_id,
                UsageEvent.idempotency_key == idempotency_key,
            )
        ).first()
        assert existing is not None, "unique constraint fired but no row found"
        return existing, False

    session.refresh(event)
    return event, True

"""AT-08: event ingestion applies valid events, deduplicates, and logs malformed data."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import Event, Lot, Operator, Slot, SlotType


@pytest.mark.asyncio
async def test_at08_valid_duplicate_and_malformed_events(caplog):
    async with SessionLocal() as db:
        operator = Operator(name="AT08 synthetic", synthetic=True)
        db.add(operator)
        await db.flush()
        lot = Lot(operator_id=operator.id, name="AT08", address="test", timezone="UTC",
            config={}, tariff={}, strategy="first_fit")
        db.add(lot)
        await db.flush()
        slot = Slot(operator_id=operator.id, lot_id=lot.id, slot_code="AT08", floor=0, zone="A",
            slot_type=SlotType.CAR, covered=False, exit_rank=0, ev_only=False,
            accessible_only=False, occupied=False)
        db.add(slot)
        await db.commit()
        lot_id = lot.id
        slot_id = slot.id

    headers = {"X-Event-Api-Key": settings.event_api_key}
    payload = {
        "event_id": f"at08-{uuid4()}",
        "source": "SYNTHETIC-test-source",
        "event_type": "entry",
        "occurred_at": datetime.now(UTC).isoformat(),
        "lot_id": str(lot_id),
        "slot_id": str(slot_id),
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        accepted = await client.post("/events", headers=headers, json=payload)
        duplicate = await client.post("/events", headers=headers, json={**payload, "event_type":"exit"})
        malformed = await client.post("/events", headers=headers, json={**payload, "event_type":"teleport"})

    assert accepted.status_code == 202
    assert accepted.json()["duplicate"] is False
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True
    assert malformed.status_code == 422
    assert "Malformed event payload rejected" in caplog.text
    async with SessionLocal() as db:
        slot_after = await db.scalar(select(Slot).where(Slot.id == slot_id))
        event_count = await db.scalar(select(Event.id).where(Event.operator_id == operator.id))
        assert slot_after is not None and slot_after.occupied is True
        assert event_count is not None

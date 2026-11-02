"""Focused integration checks for billing, tenant role boundaries, and fallback review."""
import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import main
from app.db import SessionLocal
from app.main import app, price
from app.models import (
    AuditLog,
    Booking,
    BookingStatus,
    ExceptionFlag,
    Lot,
    Notification,
    Operator,
    Payment,
    Role,
    Slot,
    SlotType,
    User,
    Vehicle,
)
from app.security import issue_token


@pytest.mark.asyncio
async def test_at01_ten_parallel_api_requests_return_one_hold_and_nine_unavailable():
    async with SessionLocal() as db:
        operator=Operator(name="AT01 api synthetic",synthetic=True); db.add(operator); await db.flush()
        lot=Lot(operator_id=operator.id,name="AT01 API",address="test",timezone="UTC",config={},
            tariff={"free_minutes":0,"hourly":{"car":20}},strategy="first_fit"); db.add(lot); await db.flush()
        slot=Slot(operator_id=operator.id,lot_id=lot.id,slot_code="AT01-ONLY",floor=0,zone="A",slot_type=SlotType.CAR,
            covered=False,exit_rank=0,ev_only=False,accessible_only=False,occupied=False); db.add(slot)
        users=[]; vehicles=[]
        for _ in range(10):
            user=User(operator_id=operator.id,email=f"{uuid4()}@test.invalid",password_hash="x",role=Role.DRIVER,synthetic=True)
            db.add(user); users.append(user)
        await db.flush()
        for index,user in enumerate(users):
            vehicle=Vehicle(operator_id=operator.id,driver_id=user.id,plate_original=f"SYN{index}",plate_normalized=f"SYN{index}",
                vehicle_type=SlotType.CAR,ev=False,accessible=False); db.add(vehicle); vehicles.append(vehicle)
        await db.commit()
        lot_id=str(lot.id); vehicle_ids=[str(vehicle.id) for vehicle in vehicles]; tokens=[issue_token(user) for user in users]
    starts=datetime.now(UTC)+timedelta(days=2); ends=starts+timedelta(hours=1)
    async with AsyncClient(transport=ASGITransport(app=app),base_url="http://test") as client:
        async def reserve(index):
            return await client.post("/bookings",headers={"Authorization":f"Bearer {tokens[index]}"},json={
                "lot_id":lot_id,"vehicle_id":vehicle_ids[index],"starts_at":starts.isoformat(),"ends_at":ends.isoformat(),
                "idempotency_key":f"at01-api-{index}"})
        responses=await asyncio.gather(*(reserve(index) for index in range(10)))
    statuses=[response.status_code for response in responses]
    assert statuses.count(201)==1
    assert statuses.count(409)==9
    assert all(response.json()["detail"]["error"]=="slot_unavailable" for response in responses if response.status_code==409)


def test_at06_preview_and_final_tariff_calculation_match():
    tariff = {"free_minutes": 15, "hourly": {"car": 60}, "daily": {"car": 120}}
    start = datetime(2026, 11, 1, 10, tzinfo=UTC)
    assert price(tariff, "car", start, start + timedelta(hours=1)) == 45
    assert price(tariff, "car", start, start + timedelta(hours=3)) == 120


@pytest.mark.asyncio
async def test_at06_preview_matches_on_time_exit_bill(monkeypatch):
    frozen=datetime(2026,11,1,10,tzinfo=UTC)
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls,tz=None):
            return frozen if tz is not None else frozen.replace(tzinfo=None)
    monkeypatch.setattr(main,"datetime",FrozenDateTime)
    async with SessionLocal() as db:
        operator=Operator(name="AT06 integration synthetic",synthetic=True); db.add(operator); await db.flush()
        driver=User(operator_id=operator.id,email=f"{uuid4()}@test.invalid",password_hash="x",role=Role.DRIVER,synthetic=True)
        attendant=User(operator_id=operator.id,email=f"{uuid4()}@test.invalid",password_hash="x",role=Role.ATTENDANT,synthetic=True)
        db.add_all([driver,attendant]); await db.flush()
        tariff={"free_minutes":0,"hourly":{"car":60},"daily":{"car":320}}
        lot=Lot(operator_id=operator.id,name="AT06",address="test",timezone="UTC",config={},tariff=tariff,strategy="first_fit"); db.add(lot); await db.flush()
        slot=Slot(operator_id=operator.id,lot_id=lot.id,slot_code="AT06",floor=0,zone="A",slot_type=SlotType.CAR,covered=False,exit_rank=0,ev_only=False,accessible_only=False,occupied=True); db.add(slot); await db.flush()
        vehicle=Vehicle(operator_id=operator.id,driver_id=driver.id,plate_original="SYN",plate_normalized="SYN",vehicle_type=SlotType.CAR,ev=False,accessible=False); db.add(vehicle); await db.flush()
        starts=frozen-timedelta(hours=1)
        preview=str(price(tariff,"car",starts,frozen))
        booking=Booking(operator_id=operator.id,driver_id=driver.id,vehicle_id=vehicle.id,lot_id=lot.id,slot_id=slot.id,
            starts_at=starts,ends_at=frozen,status=BookingStatus.CHECKED_IN,held_until=starts,checked_in_at=starts,
            price_preview=60,tariff_snapshot=tariff,strategy="first_fit",allocation_reason="AT06",wasted_rank=0,idempotency_key=f"at06-{uuid4()}")
        db.add(booking); await db.commit(); booking_id=str(booking.id); token=issue_token(attendant)
    async with AsyncClient(transport=ASGITransport(app=app),base_url="http://test") as client:
        response=await client.post(f"/attendant/bookings/{booking_id}/check-out?reason=normal%20exit",headers={"Authorization":f"Bearer {token}"})
    assert response.status_code==200
    assert response.json()["bill"]==preview


@pytest.mark.asyncio
async def test_at07_driver_cannot_read_another_drivers_booking_or_operator_dashboard():
    async with SessionLocal() as db:
        operator = Operator(name="AT07 synthetic", synthetic=True)
        db.add(operator); await db.flush()
        owner = User(operator_id=operator.id,email=f"{uuid4()}@test.invalid",password_hash="x",role=Role.DRIVER,synthetic=True)
        other = User(operator_id=operator.id,email=f"{uuid4()}@test.invalid",password_hash="x",role=Role.DRIVER,synthetic=True)
        manager = User(operator_id=operator.id,email=f"{uuid4()}@test.invalid",password_hash="x",role=Role.MANAGER,synthetic=True)
        attendant=User(operator_id=operator.id,email=f"{uuid4()}@test.invalid",password_hash="x",role=Role.ATTENDANT,synthetic=True)
        auditor=User(operator_id=operator.id,email=f"{uuid4()}@test.invalid",password_hash="x",role=Role.AUDITOR,synthetic=True)
        db.add_all([owner,other,manager,attendant,auditor]); await db.flush()
        lot=Lot(operator_id=operator.id,name="AT07",address="test",timezone="UTC",config={},tariff={},strategy="first_fit"); db.add(lot); await db.flush()
        slot=Slot(operator_id=operator.id,lot_id=lot.id,slot_code="AT07",floor=0,zone="A",slot_type=SlotType.CAR,covered=False,exit_rank=0,ev_only=False,accessible_only=False,occupied=False); db.add(slot); await db.flush()
        vehicle=Vehicle(operator_id=operator.id,driver_id=owner.id,plate_original="SYN",plate_normalized="SYN",vehicle_type=SlotType.CAR,ev=False,accessible=False); db.add(vehicle); await db.flush()
        booking=Booking(operator_id=operator.id,driver_id=owner.id,vehicle_id=vehicle.id,lot_id=lot.id,slot_id=slot.id,
            starts_at=datetime.now(UTC)+timedelta(hours=2),ends_at=datetime.now(UTC)+timedelta(hours=3),status=BookingStatus.CONFIRMED,
            held_until=datetime.now(UTC)+timedelta(hours=1),price_preview=20,tariff_snapshot={},strategy="first_fit",allocation_reason="AT07",wasted_rank=0,idempotency_key=f"at07-{uuid4()}")
        db.add(booking); await db.commit()
        flag=ExceptionFlag(operator_id=operator.id,booking_id=booking.id,flag_type="AT07",status="open"); db.add(flag); await db.commit()
        booking_id=str(booking.id); flag_id=str(flag.id)
        other_token=issue_token(other); manager_token=issue_token(manager); attendant_token=issue_token(attendant); auditor_token=issue_token(auditor)
    async with AsyncClient(transport=ASGITransport(app=app),base_url="http://test") as client:
        denied=await client.get(f"/bookings/{booking_id}",headers={"Authorization":f"Bearer {other_token}"})
        role_denied=await client.get("/operator/dashboard",headers={"Authorization":f"Bearer {other_token}"})
        manager_allowed=await client.get("/operator/dashboard",headers={"Authorization":f"Bearer {manager_token}"})
        attendant_occupancy=await client.get("/operator/occupancy",headers={"Authorization":f"Bearer {attendant_token}"})
        attendant_denied=await client.get("/operator/dashboard",headers={"Authorization":f"Bearer {attendant_token}"})
        auditor_allowed=await client.get("/operator/dashboard",headers={"Authorization":f"Bearer {auditor_token}"})
        auditor_denied=await client.post(f"/operator/flags/{flag_id}/review",headers={"Authorization":f"Bearer {auditor_token}"},json={"decision":"dismiss","reason":"AT07 denial"})
        manager_review=await client.post(f"/operator/flags/{flag_id}/review",headers={"Authorization":f"Bearer {manager_token}"},json={"decision":"dismiss","reason":"AT07 manager review"})
    assert denied.status_code==404
    assert role_denied.status_code==403
    assert manager_allowed.status_code==200 and manager_review.status_code==200
    assert attendant_occupancy.status_code==200 and attendant_denied.status_code==403
    assert auditor_allowed.status_code==200 and auditor_denied.status_code==403


@pytest.mark.asyncio
async def test_at04_at10_checkout_bills_overstay_and_audits_fallback_without_auto_fine():
    async with SessionLocal() as db:
        operator=Operator(name="AT04 AT10 synthetic",synthetic=True); db.add(operator); await db.flush()
        driver=User(operator_id=operator.id,email=f"{uuid4()}@test.invalid",password_hash="x",role=Role.DRIVER,synthetic=True)
        attendant=User(operator_id=operator.id,email=f"{uuid4()}@test.invalid",password_hash="x",role=Role.ATTENDANT,synthetic=True)
        db.add_all([driver,attendant]); await db.flush()
        lot=Lot(operator_id=operator.id,name="AT04",address="test",timezone="UTC",config={},tariff={"free_minutes":0,"hourly":{"car":10},"daily":{"car":100}},strategy="first_fit"); db.add(lot); await db.flush()
        slot=Slot(operator_id=operator.id,lot_id=lot.id,slot_code="AT04",floor=0,zone="A",slot_type=SlotType.CAR,covered=False,exit_rank=0,ev_only=False,accessible_only=False,occupied=True); db.add(slot); await db.flush()
        vehicle=Vehicle(operator_id=operator.id,driver_id=driver.id,plate_original="SYN",plate_normalized="SYN",vehicle_type=SlotType.CAR,ev=False,accessible=False); db.add(vehicle); await db.flush()
        now=datetime.now(UTC)
        booking=Booking(operator_id=operator.id,driver_id=driver.id,vehicle_id=vehicle.id,lot_id=lot.id,slot_id=slot.id,
            starts_at=now-timedelta(hours=2),ends_at=now-timedelta(minutes=30),status=BookingStatus.CHECKED_IN,
            held_until=now-timedelta(hours=1),checked_in_at=now-timedelta(hours=2),price_preview=10,tariff_snapshot=lot.tariff,
            strategy="first_fit",allocation_reason="AT04",wasted_rank=0,idempotency_key=f"at04-{uuid4()}")
        db.add(booking); await db.commit(); booking_id=str(booking.id); operator_id=operator.id; token=issue_token(attendant)
    async with AsyncClient(transport=ASGITransport(app=app),base_url="http://test") as client:
        response=await client.post(f"/attendant/bookings/{booking_id}/check-out?reason=payment%20terminal%20offline&gateway_available=false",headers={"Authorization":f"Bearer {token}"})
    assert response.status_code==200
    result=response.json()
    assert result["fallback"] is True
    assert float(result["bill"])>=10
    async with SessionLocal() as db:
        booking_uuid=UUID(booking_id)
        flag=await db.scalar(select(ExceptionFlag).where(ExceptionFlag.booking_id==booking_uuid))
        notice=await db.scalar(select(Notification).where(Notification.booking_id==booking_uuid,Notification.kind=="overstay_review"))
        payment=await db.scalar(select(Payment).where(Payment.booking_id==booking_uuid))
        audit_row=await db.scalar(select(AuditLog).where(AuditLog.operator_id==operator_id,AuditLog.action=="booking.checked_out"))
        assert flag is not None and notice is not None and payment is not None and audit_row is not None
        assert payment.mode=="ATTENDANT_CASH" and payment.status=="attendant_recorded"
        assert "attendant_pay_at_exit" in (audit_row.details or {}).get("payment_path","")

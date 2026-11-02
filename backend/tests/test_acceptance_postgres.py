"""PostgreSQL acceptance checks. Run against a disposable real Postgres database."""
import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.db import SessionLocal
from app.main import release_expired
from app.models import (
    Booking,
    BookingStatus,
    Lot,
    Operator,
    Role,
    Slot,
    SlotType,
    User,
    Vehicle,
)

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://parkly:parkly@localhost:5432/parkly_test")

@pytest.mark.asyncio
async def test_at01_database_exclusion_allows_exactly_one_parallel_insert():
    engine=create_async_engine(DATABASE_URL)
    slot=uuid4(); operator=uuid4(); user=uuid4(); vehicle=uuid4(); lot=uuid4()
    start=datetime.now(UTC)+timedelta(days=5); end=start+timedelta(hours=1)
    async with engine.begin() as conn:
        await conn.execute(text("""INSERT INTO operators(id,name,synthetic) VALUES (:id,'AT01 synthetic',true)"""),{"id":operator})
        await conn.execute(text("INSERT INTO users(id,operator_id,email,password_hash,role,synthetic) VALUES (:id,:op,:email,'x','driver',true)"""),{"id":user,"op":operator,"email":str(user)+"@test.invalid"})
        await conn.execute(text("INSERT INTO lots(id,operator_id,name,address,timezone,config,tariff,strategy,active) VALUES (:id,:op,'AT01','test','UTC','{}','{}','first_fit',true)"""),{"id":lot,"op":operator})
        await conn.execute(text("INSERT INTO slots(id,operator_id,lot_id,slot_code,floor,zone,slot_type,covered,exit_rank,ev_only,accessible_only,occupied) VALUES (:id,:op,:lot,'AT01',0,'A','car',false,0,false,false,false)"""),{"id":slot,"op":operator,"lot":lot})
        await conn.execute(text("INSERT INTO vehicles(id,operator_id,driver_id,plate_original,plate_normalized,vehicle_type,ev,accessible) VALUES (:id,:op,:user,'SYN','SYN','car',false,false)"""),{"id":vehicle,"op":operator,"user":user})
    async def insert(index):
        try:
            async with engine.begin() as conn:
                await conn.execute(text("""INSERT INTO bookings(id,operator_id,driver_id,vehicle_id,lot_id,slot_id,starts_at,ends_at,status,held_until,price_preview,tariff_snapshot,strategy,allocation_reason,wasted_rank,idempotency_key)
                  VALUES (:id,:op,:user,:vehicle,:lot,:slot,:start,:end,'held',:start,0,'{}','first_fit','test',0,:key)"""),
                  {"id":uuid4(),"op":operator,"user":user,"vehicle":vehicle,"lot":lot,"slot":slot,"start":start,"end":end,"key":f"at01-{index}"})
            return True
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) == "23P01":
                return False
            raise
    results=await asyncio.gather(*(insert(i) for i in range(10)))
    assert sum(results)==1
    await engine.dispose()

@pytest.mark.asyncio
async def test_at02_half_open_range_allows_back_to_back_rejects_overlap():
    engine=create_async_engine(DATABASE_URL)
    slot=uuid4(); operator=uuid4(); user=uuid4(); vehicle=uuid4(); lot=uuid4()
    start=datetime.now(UTC)+timedelta(days=7); end=start+timedelta(hours=1)
    async with engine.begin() as conn:
        await conn.execute(text("INSERT INTO operators(id,name,synthetic) VALUES (:id,'AT02 synthetic',true)"),{"id":operator})
        await conn.execute(text("INSERT INTO users(id,operator_id,email,password_hash,role,synthetic) VALUES (:id,:op,:email,'x','driver',true)"),{"id":user,"op":operator,"email":str(user)+"@test.invalid"})
        await conn.execute(text("INSERT INTO lots(id,operator_id,name,address,timezone,config,tariff,strategy,active) VALUES (:id,:op,'AT02','test','UTC','{}','{}','first_fit',true)"),{"id":lot,"op":operator})
        await conn.execute(text("INSERT INTO slots(id,operator_id,lot_id,slot_code,floor,zone,slot_type,covered,exit_rank,ev_only,accessible_only,occupied) VALUES (:id,:op,:lot,'AT02',0,'A','car',false,0,false,false,false)"),{"id":slot,"op":operator,"lot":lot})
        await conn.execute(text("INSERT INTO vehicles(id,operator_id,driver_id,plate_original,plate_normalized,vehicle_type,ev,accessible) VALUES (:id,:op,:user,'SYN','SYN','car',false,false)"),{"id":vehicle,"op":operator,"user":user})
    async def insert(start_at, end_at, key):
        async with engine.begin() as conn:
            await conn.execute(text("""INSERT INTO bookings(id,operator_id,driver_id,vehicle_id,lot_id,slot_id,starts_at,ends_at,status,held_until,price_preview,tariff_snapshot,strategy,allocation_reason,wasted_rank,idempotency_key)
              VALUES (:id,:op,:user,:vehicle,:lot,:slot,:start,:end,'held',:start,0,'{}','first_fit','test',0,:key)"""),
              {"id":uuid4(),"op":operator,"user":user,"vehicle":vehicle,"lot":lot,"slot":slot,"start":start_at,"end":end_at,"key":key})
    await insert(start,end,"at02-first")
    await insert(end,end+timedelta(hours=1),"at02-back-to-back")
    with pytest.raises(IntegrityError) as exc_info:
        await insert(start+timedelta(minutes=15),end+timedelta(minutes=30),"at02-overlap")
    assert getattr(exc_info.value.orig, "sqlstate", None) == "23P01"
    await engine.dispose()

@pytest.mark.asyncio
async def test_at03_expired_no_show_releases_notifies_and_never_fines():
    now=datetime.now(UTC)
    async with SessionLocal() as db:
        operator=Operator(name="AT03 synthetic",synthetic=True); db.add(operator); await db.flush()
        driver=User(operator_id=operator.id,email=f"{uuid4()}@test.invalid",password_hash="x",role=Role.DRIVER,synthetic=True); db.add(driver)
        lot=Lot(operator_id=operator.id,name="AT03",address="test",timezone="UTC",config={"grace_minutes":10},tariff={},strategy="first_fit"); db.add(lot); await db.flush()
        slot=Slot(operator_id=operator.id,lot_id=lot.id,slot_code="AT03",floor=0,zone="A",slot_type=SlotType.CAR,covered=False,exit_rank=0,ev_only=False,accessible_only=False,occupied=False); db.add(slot); await db.flush()
        vehicle=Vehicle(operator_id=operator.id,driver_id=driver.id,plate_original="SYN",plate_normalized="SYN",vehicle_type=SlotType.CAR,ev=False,accessible=False); db.add(vehicle); await db.flush()
        booking=Booking(operator_id=operator.id,driver_id=driver.id,vehicle_id=vehicle.id,lot_id=lot.id,slot_id=slot.id,
            starts_at=now-timedelta(hours=1),ends_at=now+timedelta(hours=1),status=BookingStatus.HELD,
            held_until=now-timedelta(minutes=1),price_preview=0,tariff_snapshot={},strategy="first_fit",
            allocation_reason="AT03 synthetic",wasted_rank=0,idempotency_key=f"at03-{uuid4()}")
        db.add(booking); await db.commit()
        released=await release_expired(db,operator.id)
        await db.refresh(booking)
        notice=await db.scalar(text("SELECT count(*) FROM notifications WHERE booking_id=:id AND user_id=:user_id AND kind='no_show_released'"),{"id":booking.id,"user_id":driver.id})
        flag_count=await db.scalar(text("SELECT count(*) FROM exception_flags WHERE booking_id=:id"),{"id":booking.id})
        event=await db.scalar(text("SELECT payload FROM events WHERE operator_id=:op AND event_id=:event_id"),{"op":operator.id,"event_id":f"booking-{booking.id}-no-show-released"})
        assert released==1
        assert booking.status==BookingStatus.RELEASED
        assert notice==1
        assert flag_count==0
        assert event["fine_created"] is False
        assert await release_expired(db,operator.id)==0

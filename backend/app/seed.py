"""Create deterministic, visibly synthetic development records."""
import asyncio
import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import (
    Area,
    Booking,
    BookingStatus,
    City,
    ExceptionFlag,
    Lot,
    OccupancySnapshot,
    Operator,
    Role,
    Slot,
    SlotType,
    State,
    User,
    Vehicle,
    Venue,
)
from app.security import hash_password
from app.seed_data.locations_in import GWALIOR_AREAS, OTHER_CITIES, STATES, VENUE_TYPES


async def seed() -> None:
    rng = random.Random(20261101)
    async with SessionLocal() as db:
        seeded_venues = await seed_locations(db)
        existing = await db.scalar(select(Operator).where(Operator.name == "SYNTHETIC demo operator"))
        if existing is not None:
            await ensure_synthetic_flags(db, existing)
            await link_seeded_lots(db, existing, seeded_venues)
            await db.commit()
            print("SYNTHETIC demo data and location reference data already exist; missing rows were added.")
            return
        operator = Operator(name="SYNTHETIC demo operator", synthetic=True)
        db.add(operator); await db.flush()
        types = [SlotType.TWO_WHEELER, SlotType.CAR, SlotType.LARGE, SlotType.EV, SlotType.ACCESSIBLE]
        lots=[]; slots=[]
        for lot_no in range(3):
            area_id, venue_id = seeded_venues[("City Centre", 1) if lot_no == 0 else ("Thatipur", 1) if lot_no == 1 else ("Morar", 1)]
            lot=Lot(operator_id=operator.id,name=f"SYNTHETIC Lot {lot_no+1}",address=f"Demo district {lot_no+1}",timezone="Asia/Kolkata",
                    config={"grace_minutes":10,"max_duration_hours":24,"preferred_exit_rank":1,
                        "repeated_no_show_threshold":3,"long_overstay_minutes":30,"many_cancellations_threshold":3},
                    tariff={"free_minutes":0,"hourly":{"two_wheeler":20,"car":40,"large":60,"ev":45,"accessible":40},"daily":{"two_wheeler":160,"car":320,"large":480,"ev":360,"accessible":320}},strategy=["first_fit","best_fit","scored"][lot_no],area_id=area_id,venue_id=venue_id)
            db.add(lot); await db.flush(); lots.append(lot)
            for i in range(67):
                typ=types[i%len(types)]
                slot=Slot(operator_id=operator.id,lot_id=lot.id,slot_code=f"L{lot_no+1}-{i+1:03}",floor=i//22,zone=chr(65+i//23),slot_type=typ,covered=i%3==0,exit_rank=i%8,ev_only=typ==SlotType.EV,accessible_only=typ==SlotType.ACCESSIBLE)
                db.add(slot); slots.append(slot)
        users=[]
        for i in range(120):
            user=User(operator_id=operator.id,email=f"driver{i+1:03}@synthetic.test",password_hash=hash_password("Synthetic-Demo-Only-2026!"),role=Role.DRIVER,phone=f"+91000000{i:04}",synthetic=True)
            db.add(user); users.append(user)
        await db.flush()
        attendants=[]
        for role,name in [(Role.ATTENDANT,"attendant"),(Role.MANAGER,"manager"),(Role.AUDITOR,"auditor")]:
            u=User(operator_id=operator.id,email=f"{name}@synthetic.test",password_hash=hash_password("Synthetic-Demo-Only-2026!"),role=role,synthetic=True); db.add(u); attendants.append(u)
        vehicles=[]
        for i,user in enumerate(users):
            typ=types[i%3]
            vehicle=Vehicle(operator_id=operator.id,driver_id=user.id,plate_original=f"SYN {i+1:04d}",plate_normalized=f"SYN{i+1:04d}",vehicle_type=typ,ev=typ==SlotType.EV,accessible=typ==SlotType.ACCESSIBLE)
            db.add(vehicle); vehicles.append(vehicle)
        await db.flush()
        now=datetime.now(UTC).replace(minute=0,second=0,microsecond=0)
        for day in range(30):
            base=now-timedelta(days=day+1)
            count=12 if base.weekday()<5 else 8
            for j in range(count):
                user=rng.choice(users); vehicle=vehicles[users.index(user)]; lot=lots[(day+j)%len(lots)]
                lot_slots=[s for s in slots if s.lot_id==lot.id]
                slot=lot_slots[(day*count+j)%len(lot_slots)]
                start=base.replace(hour=rng.choice([8,9,12,16,17,18]))
                end=start+timedelta(hours=rng.choice([1,2,2,3]))
                db.add(Booking(operator_id=operator.id,driver_id=user.id,vehicle_id=vehicle.id,lot_id=lot.id,slot_id=slot.id,
                    starts_at=start,ends_at=end,status=BookingStatus.COMPLETED,held_until=start,checked_in_at=start,checked_out_at=end,
                    price_preview=40,tariff_snapshot=lot.tariff,strategy=lot.strategy,allocation_reason="SYNTHETIC historical sample",wasted_rank=rng.randrange(0,4),idempotency_key=f"seed-{day}-{j}-{user.id}"))
        for day in range(30):
            sample_day=(now-timedelta(days=day+1)).replace(minute=0,second=0,microsecond=0)
            for hour in range(24):
                peak=0.28 if hour in range(8,11) or hour in range(16,20) else 0.0
                weekend_adjustment=-0.08 if sample_day.weekday()>=5 else 0.0
                for lot in lots:
                    capacity=sum(slot.lot_id==lot.id for slot in slots)
                    fraction=min(0.95,max(0.05,0.32+peak+weekend_adjustment+rng.uniform(-0.05,0.05)))
                    db.add(OccupancySnapshot(operator_id=operator.id,lot_id=lot.id,
                        captured_at=sample_day.replace(hour=hour),occupied_count=round(capacity*fraction),
                        capacity=capacity,synthetic=True))
        await ensure_synthetic_flags(db, operator)
        await db.commit()
        print("Seeded 3 SYNTHETIC lots, 201 slots, 120 fictional drivers, 30 days of synthetic bookings.")

async def seed_locations(db) -> dict[tuple[str, int], tuple[uuid.UUID, uuid.UUID]]:
    """Seed deterministic name-only location references and fictional Gwalior venues."""
    states_by_code: dict[str, State] = {}
    for name, code, kind in STATES:
        row = await db.scalar(select(State).where(State.code == code))
        if row is None:
            row = State(id=uuid.uuid5(uuid.NAMESPACE_URL, f"parkly-location:state:{code}"),
                        name=name, code=code, kind=kind, is_seeded=True)
            db.add(row)
            await db.flush()
        states_by_code[code] = row

    cities_by_code_name: dict[tuple[str, str], City] = {}
    for code, state in states_by_code.items():
        city_names = ("Gwalior",) if code == "MP" else OTHER_CITIES.get(code, ())
        for name in city_names:
            row = await db.scalar(select(City).where(City.state_id == state.id,
                func.lower(City.name) == name.lower()))
            if row is None:
                row = City(id=uuid.uuid5(uuid.NAMESPACE_URL, f"parkly-location:city:{code}:{name.lower()}"),
                           state_id=state.id, name=name, is_seeded=True, source="seed", status="active")
                db.add(row)
                await db.flush()
            cities_by_code_name[(code, name)] = row

    gwalior = cities_by_code_name[("MP", "Gwalior")]
    venue_links: dict[tuple[str, int], tuple[uuid.UUID, uuid.UUID]] = {}
    for area_index, name in enumerate(GWALIOR_AREAS):
        area = await db.scalar(select(Area).where(Area.city_id == gwalior.id,
            func.lower(Area.name) == name.lower()))
        if area is None:
            area = Area(id=uuid.uuid5(uuid.NAMESPACE_URL, f"parkly-location:area:MP:Gwalior:{name.lower()}"),
                        city_id=gwalior.id, name=name, is_seeded=True, source="seed", status="active")
            db.add(area)
            await db.flush()
        for number in (1, 2):
            venue_type, display = VENUE_TYPES[(area_index * 2 + number - 1) % len(VENUE_TYPES)]
            venue_name = f"SYNTHETIC {display} - {name} {number}"
            venue = await db.scalar(select(Venue).where(Venue.area_id == area.id,
                func.lower(Venue.name) == venue_name.lower()))
            if venue is None:
                venue = Venue(id=uuid.uuid5(uuid.NAMESPACE_URL,
                    f"parkly-location:venue:MP:Gwalior:{name.lower()}:{number}"),
                    area_id=area.id, name=venue_name, venue_type=venue_type, is_seeded=True,
                    source="seed", status="active", data_label="SYNTHETIC")
                db.add(venue)
                await db.flush()
            venue_links[(name, number)] = (area.id, venue.id)
    return venue_links

async def link_seeded_lots(db, operator: Operator, venue_links: dict) -> None:
    for number, key in enumerate((("City Centre", 1), ("Thatipur", 1), ("Morar", 1)), start=1):
        lot = await db.scalar(select(Lot).where(Lot.operator_id == operator.id,
            Lot.name == f"SYNTHETIC Lot {number}"))
        if lot is not None and lot.area_id is None and lot.venue_id is None:
            lot.area_id, lot.venue_id = venue_links[key]

async def ensure_synthetic_flags(db, operator: Operator) -> None:
    sample_bookings=(await db.scalars(select(Booking).join(User,User.id==Booking.driver_id).where(
        Booking.operator_id==operator.id,User.synthetic.is_(True)).order_by(Booking.created_at).limit(24))).all()
    for index,booking in enumerate(sample_bookings):
        existing=await db.scalar(select(ExceptionFlag.id).where(ExceptionFlag.operator_id==operator.id,
            ExceptionFlag.booking_id==booking.id,ExceptionFlag.synthetic_label.is_not(None)))
        if existing is None:
            db.add(ExceptionFlag(operator_id=operator.id,booking_id=booking.id,
                flag_type="synthetic_overstay" if index<12 else "synthetic_lookalike",status="open",
                synthetic_label="review_signal" if index<12 else "legitimate_lookalike"))

if __name__ == "__main__": asyncio.run(seed())

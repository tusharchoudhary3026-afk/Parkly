import asyncio
import csv
import io
import logging
import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.allocator import Allocation, allocate_slot, is_eligible
from app.config import settings
from app.db import SessionLocal, get_db
from app.forecast import forecast_mean
from app.limiter import SlidingWindowLimiter
from app.models import (
    Area,
    AuditLog,
    Booking,
    BookingStatus,
    City,
    Event,
    ExceptionFlag,
    LocationSuggestion,
    Lot,
    Notification,
    OccupancySnapshot,
    Operator,
    Payment,
    PenaltyDecision,
    Role,
    Slot,
    SlotType,
    State,
    TariffVersion,
    User,
    Vehicle,
    Venue,
)
from app.schemas import (
    AssistedBookingIn,
    BookingExtensionIn,
    BookingIn,
    CancelIn,
    EventIn,
    LocationSuggestionIn,
    LocationSuggestionReviewIn,
    LoginIn,
    LotConfigUpdateIn,
    LotIn,
    LotLocationIn,
    PaymentIn,
    PenaltyIn,
    QRScanIn,
    RegisterIn,
    ReviewIn,
    SimulatedEventIn,
    SlotIn,
    SlotOverrideIn,
    VehicleIn,
)
from app.security import current_user, hash_password, issue_token, require_roles, verify_password

logger = logging.getLogger("parkly.jobs")
no_show_task: asyncio.Task | None = None
rate_limiter=SlidingWindowLimiter()

@asynccontextmanager
async def lifespan(app: FastAPI):
    global no_show_task
    no_show_task = asyncio.create_task(no_show_release_loop())
    try:
        yield
    finally:
        if no_show_task is not None:
            no_show_task.cancel()
            try: await no_show_task
            except asyncio.CancelledError: pass

app = FastAPI(title="Parkly Smart Parking API", version="0.1.0", description="Software-only smart parking. No physical access control or ANPR.", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[settings.web_origin], allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "OPTIONS"], allow_headers=["Authorization", "Content-Type", "X-Event-Api-Key"])

@app.middleware("http")
async def rate_limit_sensitive_routes(request: Request, call_next):
    path=request.url.path
    limits=("auth",10) if path.startswith("/auth/") else ("bookings",30) if path.startswith("/bookings") else ("events",120) if path=="/events" else None
    if limits is not None:
        client=request.client.host if request.client else "unknown"
        if not await rate_limiter.allow(f"{limits[0]}:{client}",limits[1]):
            return JSONResponse(status_code=429,content={"detail":{"error":"rate_limited","message":"Too many requests; retry shortly"}})
    return await call_next(request)

@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    if request.url.path == "/events":
        logger.warning("Malformed event payload rejected", extra={"path":request.url.path,
            "issues":[{"location":list(issue.get("loc", ())),"type":issue.get("type")} for issue in exc.errors()]})
    issues = [{"loc":list(issue.get("loc", ())), "msg":str(issue.get("msg", "Invalid request")),
               "type":str(issue.get("type", "value_error"))} for issue in exc.errors()]
    return JSONResponse(status_code=422, content={"detail":issues})

async def no_show_release_loop():
    while True:
        try:
            async with SessionLocal() as db:
                await release_expired(db)
                await notify_holds_near_expiry(db)
                await persist_hourly_snapshots(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("No-show release job failed; it will retry")
        await asyncio.sleep(15)

async def notify_holds_near_expiry(db: AsyncSession) -> int:
    now=datetime.now(UTC)
    holds=(await db.scalars(select(Booking).where(Booking.status==BookingStatus.HELD,
        Booking.held_until>now,Booking.held_until<=now+timedelta(minutes=2)))).all()
    notified=0
    for booking in holds:
        event_id=f"booking-{booking.id}-hold-reminder"
        if await db.scalar(select(Event.id).where(Event.operator_id==booking.operator_id,Event.event_id==event_id)):
            continue
        db.add(Notification(operator_id=booking.operator_id,user_id=booking.driver_id,booking_id=booking.id,
            kind="hold_expiring",message="Your parking hold expires in two minutes. Confirm it if you still need the space."))
        db.add(Event(operator_id=booking.operator_id,event_id=event_id,source="system.hold_reminder",
            event_type="hold_expiring",occurred_at=now,payload={"booking_id":str(booking.id),"fine_created":False}))
        notified+=1
    if notified: await db.commit()
    return notified

async def release_expired(db: AsyncSession, operator_id: UUID | None = None, actor_id: UUID | None = None) -> int:
    now = datetime.now(UTC)
    query = select(Booking).where(Booking.status == BookingStatus.HELD, Booking.held_until <= now)
    if operator_id is not None:
        query = query.where(Booking.operator_id == operator_id)
    rows = (await db.scalars(query.with_for_update(skip_locked=True))).all()
    for booking in rows:
        booking.status = BookingStatus.RELEASED
        notice = Notification(operator_id=booking.operator_id, user_id=booking.driver_id, booking_id=booking.id,
            kind="no_show_released", message="Your booking hold expired after the grace period. The slot was released. No fine was charged.")
        db.add(notice)
        db.add(Event(operator_id=booking.operator_id, event_id=f"booking-{booking.id}-no-show-released",
            source="system.no_show_job", event_type="no_show_released", occurred_at=now,
            payload={"booking_id":str(booking.id),"fine_created":False}))
        await audit(db, booking.operator_id, "booking.no_show_released", "booking", str(booking.id), actor_id,
            reason="hold grace period elapsed", details={"fine_created":False,"notification":"in_app"})
        lot=await db.scalar(select(Lot).where(Lot.id==booking.lot_id,Lot.operator_id==booking.operator_id))
        threshold=int((lot.config if lot else {}).get("repeated_no_show_threshold",3))
        no_shows=await db.scalar(select(func.count(Booking.id)).where(Booking.operator_id==booking.operator_id,
            Booking.driver_id==booking.driver_id,Booking.status==BookingStatus.RELEASED))
        if no_shows>=threshold:
            db.add(ExceptionFlag(operator_id=booking.operator_id,booking_id=booking.id,flag_type="repeated_no_show",status="open"))
    if rows:
        await db.commit()
    return len(rows)

async def persist_hourly_snapshots(db: AsyncSession) -> int:
    now=datetime.now(UTC).replace(minute=0,second=0,microsecond=0)
    lots=(await db.scalars(select(Lot).where(Lot.active.is_(True)))).all()
    written=0
    for lot in lots:
        latest=await db.scalar(select(OccupancySnapshot.captured_at).where(
            OccupancySnapshot.operator_id==lot.operator_id,OccupancySnapshot.lot_id==lot.id)
            .order_by(OccupancySnapshot.captured_at.desc()).limit(1))
        if latest is not None and latest>=now:
            continue
        slots=(await db.scalars(select(Slot).where(Slot.operator_id==lot.operator_id,Slot.lot_id==lot.id))).all()
        db.add(OccupancySnapshot(operator_id=lot.operator_id,lot_id=lot.id,captured_at=now,
            occupied_count=sum(slot.occupied for slot in slots),capacity=len(slots),synthetic=False))
        written+=1
    if written:
        await db.commit()
    return written

def error(status: int, code: str, message: str):
    return HTTPException(status_code=status, detail={"error": code, "message": message})

async def audit(db: AsyncSession, operator_id: UUID, action: str, entity_type: str, entity_id: str,
                actor_id: UUID | None = None, reason: str | None = None, details: dict | None = None):
    db.add(AuditLog(operator_id=operator_id, actor_id=actor_id, action=action, entity_type=entity_type,
                    entity_id=entity_id, reason=reason, details=details or {}))

async def booking_event(db: AsyncSession, booking: Booking, event_type: str, source: str, details: dict | None = None):
    db.add(Event(operator_id=booking.operator_id,event_id=f"booking-{booking.id}-{event_type}",source=source,
        event_type=event_type,occurred_at=datetime.now(UTC),payload={"booking_id":str(booking.id),**(details or {})}))

def price(tariff: dict, vehicle_type: str, start: datetime, end: datetime) -> Decimal:
    duration = max(0, int((end - start).total_seconds() // 60) - int(tariff.get("free_minutes", 0)))
    rate = Decimal(str(tariff.get("hourly", {}).get(vehicle_type, 0)))
    daily = Decimal(str(tariff.get("daily", {}).get(vehicle_type, 0)))
    hours = Decimal(duration) / Decimal(60)
    raw = min(hours * rate, daily) if daily > 0 else hours * rate
    return raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

@app.get("/health")
async def health(): return {"status": "ok", "payment_mode": "TEST MODE", "data_label": "SYNTHETIC demo seed only"}

@app.post("/auth/register", status_code=201)
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)):
    if not body.consent_accepted: raise error(400,"consent_required","Accept the privacy notice to create an account")
    if await db.scalar(select(User.id).where(func.lower(User.email) == body.email.lower())): raise error(409, "email_exists", "Email is already registered")
    operator = await db.scalar(select(Operator).limit(1))
    if operator is None:
        operator = Operator(name="Parkly Demo Operator", synthetic=True); db.add(operator); await db.flush()
    user = User(operator_id=operator.id, email=body.email.lower(), password_hash=hash_password(body.password), role=Role.DRIVER,consent_at=datetime.now(UTC))
    db.add(user); await db.flush(); await audit(db, operator.id, "user.registered", "user", str(user.id), user.id)
    await db.commit()
    return {"access_token": issue_token(user), "token_type": "bearer", "role": user.role.value}

@app.post("/auth/token")
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash): raise error(401, "invalid_credentials", "Email or password is incorrect")
    return {"access_token": issue_token(user), "token_type": "bearer", "role": user.role.value}

def location_name(value: str) -> str:
    return " ".join(value.split())

def location_result(row, **extra):
    result = {"id": str(row.id), "name": row.name, **extra}
    return result

@app.get("/locations/states")
async def location_states(db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    rows = (await db.scalars(select(State).order_by(func.lower(State.name)).limit(100))).all()
    return [location_result(row, code=row.code, kind=row.kind, is_seeded=row.is_seeded) for row in rows]

@app.get("/locations/states/{state_id}/cities")
async def location_cities(state_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    rows = (await db.scalars(select(City).where(City.state_id == state_id, City.status == "active")
        .order_by(func.lower(City.name)).limit(100))).all()
    return [location_result(row, state_id=str(row.state_id), source=row.source, is_seeded=row.is_seeded) for row in rows]

@app.get("/locations/cities/{city_id}/areas")
async def location_areas(city_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    rows = (await db.scalars(select(Area).join(City, City.id == Area.city_id)
        .where(Area.city_id == city_id, Area.status == "active", City.status == "active")
        .order_by(func.lower(Area.name)).limit(100))).all()
    return [location_result(row, city_id=str(row.city_id), source=row.source, is_seeded=row.is_seeded) for row in rows]

@app.get("/locations/areas/{area_id}/venues")
async def location_venues(area_id: UUID, venue_type: str | None = Query(default=None, pattern="^(mall|building|market|hospital|station|office|other)$"),
                          db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    query = select(Venue).join(Area, Area.id == Venue.area_id).join(City, City.id == Area.city_id).where(
        Venue.area_id == area_id, Venue.status == "active", Area.status == "active", City.status == "active")
    if venue_type:
        query = query.where(Venue.venue_type == venue_type)
    rows = (await db.scalars(query.order_by(func.lower(Venue.name)).limit(100))).all()
    return [location_result(row, area_id=str(row.area_id), venue_type=row.venue_type,
        data_label=row.data_label, source=row.source, is_seeded=row.is_seeded) for row in rows]

@app.get("/locations/search")
async def search_locations(q: str = Query(min_length=2, max_length=80),
                           db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    term = f"%{q.strip()}%"
    results = []
    city_rows = (await db.execute(select(City, State).join(State, State.id == City.state_id)
        .where(City.status == "active", City.name.ilike(term)).order_by(func.lower(City.name)).limit(20))).all()
    for city, state in city_rows:
        results.append({"level":"city","id":str(city.id),"name":city.name,"state_id":str(state.id),
                        "state":state.name,"city_id":str(city.id),"area_id":None,"venue_id":None})
    area_rows = (await db.execute(select(Area, City, State).join(City, City.id == Area.city_id)
        .join(State, State.id == City.state_id).where(Area.status == "active", City.status == "active",
        Area.name.ilike(term)).order_by(func.lower(Area.name)).limit(20))).all()
    for area, city, state in area_rows:
        results.append({"level":"area","id":str(area.id),"name":area.name,"state_id":str(state.id),
                        "state":state.name,"city_id":str(city.id),"city":city.name,"area_id":str(area.id),"venue_id":None})
    venue_rows = (await db.execute(select(Venue, Area, City, State).join(Area, Area.id == Venue.area_id)
        .join(City, City.id == Area.city_id).join(State, State.id == City.state_id)
        .where(Venue.status == "active", Area.status == "active", City.status == "active",
               Venue.name.ilike(term)).order_by(func.lower(Venue.name)).limit(20))).all()
    for venue, area, city, state in venue_rows:
        results.append({"level":"venue","id":str(venue.id),"name":venue.name,"state_id":str(state.id),
            "state":state.name,"city_id":str(city.id),"city":city.name,"area_id":str(area.id),"area":area.name,
            "venue_id":str(venue.id),"venue_type":venue.venue_type,"data_label":venue.data_label})
    return sorted(results, key=lambda item: (item["name"].casefold(), item["level"]))[:20]

@app.post("/locations/suggestions", status_code=201)
async def create_location_suggestion(body: LocationSuggestionIn, db: AsyncSession = Depends(get_db),
                                     user: User = Depends(current_user)):
    if not await rate_limiter.allow(f"location-suggestions:{user.id}", 10, 3600):
        raise error(429, "suggestion_rate_limited", "You can submit up to 10 location suggestions per hour")
    state = await db.scalar(select(State).where(State.id == body.state_id))
    if state is None:
        raise error(404, "state_not_found", "Choose a listed state or union territory")
    city = None
    area = None
    city_name = location_name(body.city_name) if body.city_name else ""
    area_name = location_name(body.area_name) if body.area_name else None
    venue_name = location_name(body.venue_name) if body.venue_name else None
    if body.target_level == "city":
        duplicate = await db.scalar(select(City.id).where(City.state_id == state.id,
            func.lower(City.name) == city_name.casefold()))
        if duplicate:
            raise error(409, "location_duplicate", "That city is already listed")
    elif body.target_level == "area":
        city = await db.scalar(select(City).where(City.id == body.city_id, City.state_id == state.id, City.status == "active"))
        if city is None:
            raise error(404, "city_not_found", "Choose a listed city in the selected state")
        city_name = city.name
        duplicate = await db.scalar(select(Area.id).where(Area.city_id == city.id,
            func.lower(Area.name) == area_name.casefold()))
        if duplicate:
            raise error(409, "location_duplicate", "That area is already listed")
    else:
        area = await db.scalar(select(Area).join(City, City.id == Area.city_id).where(
            Area.id == body.area_id, City.state_id == state.id, Area.status == "active", City.status == "active"))
        if area is None:
            raise error(404, "area_not_found", "Choose a listed area in the selected state")
        city = await db.get(City, area.city_id)
        city_name = city.name
        area_name = area.name
        duplicate = await db.scalar(select(Venue.id).where(Venue.area_id == area.id,
            func.lower(Venue.name) == venue_name.casefold()))
        if duplicate:
            raise error(409, "location_duplicate", "That venue is already listed")
    pending_query = select(LocationSuggestion.id).where(LocationSuggestion.status == "pending",
        LocationSuggestion.target_level == body.target_level, LocationSuggestion.state_id == state.id,
        func.lower(LocationSuggestion.city_name) == city_name.casefold())
    if body.target_level == "city":
        pending_query = pending_query.where(LocationSuggestion.city_id.is_(None),
            func.lower(LocationSuggestion.city_name) == city_name.casefold())
    elif body.target_level == "area":
        pending_query = pending_query.where(LocationSuggestion.city_id == city.id,
            func.lower(LocationSuggestion.area_name) == area_name.casefold())
    else:
        pending_query = pending_query.where(LocationSuggestion.area_id == area.id,
            func.lower(LocationSuggestion.venue_name) == venue_name.casefold())
    if await db.scalar(pending_query):
        raise error(409, "suggestion_duplicate", "A matching location suggestion is already pending review")
    suggestion = LocationSuggestion(submitted_by_user_id=user.id, state_id=state.id,
        city_id=city.id if city else None, area_id=area.id if area else None,
        target_level=body.target_level, city_name=city_name, area_name=area_name,
        venue_name=venue_name, venue_type=body.venue_type,
        note=location_name(body.note) if body.note and body.note.strip() else None)
    db.add(suggestion)
    await db.commit()
    return {"id":str(suggestion.id),"status":"pending","target_level":suggestion.target_level,
        "message":"No parking lots are listed here yet. Your suggestion has been sent for review."}

@app.get("/locations/suggestions")
async def list_location_suggestions(db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    query = select(LocationSuggestion)
    if user.role == Role.MANAGER:
        query = query.where(LocationSuggestion.status == "pending")
    else:
        query = query.where(LocationSuggestion.submitted_by_user_id == user.id)
    rows = (await db.scalars(query.order_by(LocationSuggestion.created_at.desc()).limit(100))).all()
    return [{"id":str(row.id),"target_level":row.target_level,"state_id":str(row.state_id),
        "city_name":row.city_name,"area_name":row.area_name,"venue_name":row.venue_name,
        "venue_type":row.venue_type,"status":row.status,"created_at":row.created_at} for row in rows]

@app.post("/locations/suggestions/{suggestion_id}/review")
async def review_location_suggestion(suggestion_id: UUID, body: LocationSuggestionReviewIn,
                                     db: AsyncSession = Depends(get_db),
                                     user: User = Depends(require_roles(Role.MANAGER))):
    suggestion = await db.scalar(select(LocationSuggestion).where(
        LocationSuggestion.id == suggestion_id).with_for_update())
    if suggestion is None:
        raise error(404, "suggestion_not_found", "Location suggestion was not found")
    if suggestion.status != "pending":
        raise error(409, "suggestion_already_reviewed", "This suggestion has already been reviewed")
    now = datetime.now(UTC)
    if body.decision == "approve":
        if suggestion.target_level == "city":
            row = City(state_id=suggestion.state_id, name=suggestion.city_name, is_seeded=False,
                       source="user_submitted", status="active")
        elif suggestion.target_level == "area":
            row = Area(city_id=suggestion.city_id, name=suggestion.area_name, is_seeded=False,
                       source="user_submitted", status="active")
        else:
            row = Venue(area_id=suggestion.area_id, name=suggestion.venue_name,
                venue_type=suggestion.venue_type, is_seeded=False, source="user_submitted",
                status="active", data_label="USER_SUBMITTED")
        db.add(row)
        await db.flush()
        suggestion.status = "approved"
    else:
        suggestion.status = "rejected"
    suggestion.reviewed_by = user.id
    suggestion.reviewed_at = now
    suggestion.review_reason = body.reason
    await audit(db, user.operator_id, f"location_suggestion.{body.decision}", "location_suggestion",
        str(suggestion.id), user.id, reason=body.reason,
        details={"target_level":suggestion.target_level,"state_id":str(suggestion.state_id)})
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise error(409, "location_duplicate", "A matching location was added before this review") from exc
    return {"id":str(suggestion.id),"status":suggestion.status,"reviewed_at":suggestion.reviewed_at}

@app.get("/lots")
async def lots(vehicle_type: str | None = None, starts_at: datetime | None = None,
               ends_at: datetime | None = None, state_id: UUID | None = None,
               city_id: UUID | None = None, area_id: UUID | None = None,
               venue_id: UUID | None = None, db: AsyncSession = Depends(get_db),
               user: User = Depends(current_user)):
    if (starts_at is None) != (ends_at is None):
        raise error(422,"invalid_window","Provide both starts_at and ends_at")
    if starts_at is not None and (starts_at.tzinfo is None or ends_at.tzinfo is None or ends_at <= starts_at):
        raise error(422,"invalid_window","Provide a valid timezone-aware time window")
    query = select(Lot).where(Lot.operator_id == user.operator_id, Lot.active.is_(True))
    if venue_id is not None:
        query = query.where(Lot.venue_id == venue_id)
    elif area_id is not None:
        query = query.where(Lot.area_id == area_id)
    elif city_id is not None:
        query = query.join(Area, Area.id == Lot.area_id).where(Area.city_id == city_id)
    elif state_id is not None:
        query = query.join(Area, Area.id == Lot.area_id).join(City, City.id == Area.city_id).where(City.state_id == state_id)
    rows = (await db.scalars(query.order_by(func.lower(Lot.name)))).all()
    result = []
    for lot in rows:
        slots = (await db.scalars(select(Slot).where(Slot.lot_id == lot.id, Slot.operator_id == user.operator_id))).all()
        eligible = []
        for slot in slots:
            if slot.occupied or (vehicle_type and not is_eligible(vehicle_type, slot)):
                continue
            if starts_at is not None and ends_at is not None:
                conflict = await db.scalar(select(Booking.id).where(Booking.slot_id==slot.id,
                    Booking.status.in_([BookingStatus.HELD,BookingStatus.CONFIRMED,BookingStatus.CHECKED_IN]),
                    Booking.starts_at < ends_at,Booking.ends_at > starts_at).limit(1))
                if conflict is not None: continue
            eligible.append(slot)
        venue = await db.get(Venue, lot.venue_id) if lot.venue_id else None
        area = await db.get(Area, lot.area_id) if lot.area_id else None
        result.append({"id": str(lot.id), "name": lot.name, "address": lot.address, "available_count": len(eligible),
                       "price_preview": str(price(lot.tariff, vehicle_type or "car", datetime.now(UTC), datetime.now(UTC) + timedelta(hours=1))),
                       "forecast": "ESTIMATE", "tariff": lot.tariff,
                       "area_id":str(lot.area_id) if lot.area_id else None,
                       "area_name":area.name if area else None,
                       "venue_id":str(venue.id) if venue else None,
                       "venue_name":venue.name if venue else None,
                       "venue_data_label":venue.data_label if venue else None})
    return result

@app.get("/lots/{lot_id}/forecast")
async def lot_forecast(lot_id: UUID, target_at: datetime, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    if target_at.tzinfo is None: raise error(422,"invalid_time","Forecast time must include a timezone")
    lot=await db.scalar(select(Lot).where(Lot.id==lot_id,Lot.operator_id==user.operator_id,Lot.active.is_(True)))
    if lot is None: raise error(404,"lot_not_found","Lot was not found")
    rows=(await db.scalars(select(OccupancySnapshot).where(OccupancySnapshot.operator_id==user.operator_id,
        OccupancySnapshot.lot_id==lot.id,OccupancySnapshot.captured_at>=datetime.now(UTC)-timedelta(days=35)))).all()
    rate,sample_size=forecast_mean([{"captured_at":row.captured_at,"occupied_count":row.occupied_count,
        "capacity":row.capacity} for row in rows],target_at)
    return {"lot_id":str(lot.id),"target_at":target_at,"predicted_occupancy_rate":rate,
        "indicator":("likely_full" if rate is not None and rate>=0.8 else "likely_free" if rate is not None else "insufficient_history"),
        "label":"ESTIMATE","sample_size":sample_size,"synthetic_history":any(row.synthetic for row in rows)}

@app.get("/recommendations")
async def recommendations(starts_at: datetime, ends_at: datetime, vehicle_type: str,
                          db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    if starts_at.tzinfo is None or ends_at.tzinfo is None or ends_at<=starts_at:
        raise error(422,"invalid_window","Provide a valid timezone-aware time window")
    try: SlotType(vehicle_type)
    except ValueError: raise error(422,"invalid_vehicle_type","Unsupported vehicle type")
    lots=(await db.scalars(select(Lot).where(Lot.operator_id==user.operator_id,Lot.active.is_(True)))).all()
    candidates=[]
    for lot in lots:
        slots=(await db.scalars(select(Slot).where(Slot.operator_id==user.operator_id,Slot.lot_id==lot.id))).all()
        available=0
        for slot in slots:
            if slot.occupied or not is_eligible(vehicle_type,slot): continue
            conflict=await db.scalar(select(Booking.id).where(Booking.slot_id==slot.id,
                Booking.status.in_([BookingStatus.HELD,BookingStatus.CONFIRMED,BookingStatus.CHECKED_IN]),
                Booking.starts_at<ends_at,Booking.ends_at>starts_at).limit(1))
            if conflict is None: available+=1
        snapshots=(await db.scalars(select(OccupancySnapshot).where(OccupancySnapshot.operator_id==user.operator_id,
            OccupancySnapshot.lot_id==lot.id).order_by(OccupancySnapshot.captured_at.desc()).limit(500))).all()
        rate,sample_size=forecast_mean([{"captured_at":s.captured_at,"occupied_count":s.occupied_count,"capacity":s.capacity} for s in snapshots],starts_at)
        estimate=rate if rate is not None else 1.0-(available/max(len(slots),1))
        amount=price(lot.tariff,vehicle_type,starts_at,ends_at)
        distance=float(lot.config.get("distance_km",0))
        weights=lot.config.get("recommendation_weights",{"price":0.4,"distance":0.3,"availability":0.3})
        score=float(weights.get("price",0.4))*float(amount)+float(weights.get("distance",0.3))*distance+float(weights.get("availability",0.3))*estimate*100
        candidates.append({"lot_id":str(lot.id),"name":lot.name,"available_count":available,"price_preview":str(amount),
            "predicted_occupancy_rate":rate,"forecast_sample_size":sample_size,"distance_km":distance,"score":round(score,3),
            "weights":weights,"label":"ESTIMATE"})
    return {"results":sorted(candidates,key=lambda item:(item["score"],item["name"])),
        "alternative_lots":sorted((item for item in candidates if item["available_count"]>0),key=lambda item:item["score"]),
        "ranking":"lower score is preferred; driver chooses","label":"ESTIMATE"}

@app.post("/vehicles", status_code=201)
async def add_vehicle(body: VehicleIn, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try: kind = SlotType(body.vehicle_type)
    except ValueError: raise error(422, "invalid_vehicle_type", "Unsupported vehicle type")
    norm = re.sub(r"[^A-Z0-9]", "", body.plate.upper())
    vehicle = Vehicle(operator_id=user.operator_id, driver_id=user.id, plate_original=body.plate,
        plate_normalized=norm, vehicle_type=kind, ev=body.ev or kind == SlotType.EV,
        accessible=body.accessible or kind == SlotType.ACCESSIBLE)
    db.add(vehicle); await db.commit(); await db.refresh(vehicle)
    return {"id": str(vehicle.id), "plate": body.plate, "vehicle_type": kind.value}

@app.post("/bookings", status_code=201)
async def create_booking(body: BookingIn, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    prior = await db.scalar(select(Booking).where(Booking.operator_id == user.operator_id, Booking.driver_id == user.id, Booking.idempotency_key == body.idempotency_key))
    if prior: return booking_view(prior)
    lot = await db.scalar(select(Lot).where(Lot.id == body.lot_id, Lot.operator_id == user.operator_id, Lot.active.is_(True)))
    vehicle = await db.scalar(select(Vehicle).where(Vehicle.id == body.vehicle_id, Vehicle.driver_id == user.id, Vehicle.operator_id == user.operator_id))
    if lot is None: raise error(404, "lot_not_found", "Lot was not found")
    if vehicle is None: raise error(404, "vehicle_not_found", "Vehicle was not found")
    max_hours = int(lot.config.get("max_duration_hours", 24))
    if body.ends_at - body.starts_at > timedelta(hours=max_hours): raise error(422, "max_duration", "Requested duration exceeds lot limit")
    if body.starts_at < datetime.now(UTC) - timedelta(minutes=1): raise error(422, "start_in_past", "Start time must be in the future")
    slots = (await db.scalars(select(Slot).where(Slot.lot_id == lot.id, Slot.operator_id == user.operator_id).order_by(Slot.slot_code).with_for_update(skip_locked=True))).all()
    strategy = lot.strategy
    remaining = list(slots)
    allocation: Allocation | None = None
    while remaining:
        allocation = allocate_slot(remaining, vehicle.vehicle_type.value, strategy,
            weights=lot.config.get("strategy_weights"), floor_load=lot.config.get("floor_load"))
        if allocation is None:
            break
        overlap = await db.scalar(select(Booking.id).where(Booking.slot_id == allocation.slot.id,
            Booking.status.in_([BookingStatus.HELD, BookingStatus.CONFIRMED, BookingStatus.CHECKED_IN]),
            Booking.starts_at < body.ends_at, Booking.ends_at > body.starts_at).limit(1))
        if overlap is None:
            break
        remaining = [slot for slot in remaining if slot.id != allocation.slot.id]
    if allocation is None or allocation.slot not in remaining:
        raise error(409, "slot_unavailable", "No eligible slot is available for that time window")
    selected = allocation.slot
    now = datetime.now(UTC)
    hold_minutes = int(lot.config.get("grace_minutes", 10))
    booking = Booking(operator_id=user.operator_id, driver_id=user.id, vehicle_id=vehicle.id, lot_id=lot.id,
        slot_id=selected.id, starts_at=body.starts_at.astimezone(UTC), ends_at=body.ends_at.astimezone(UTC),
        status=BookingStatus.HELD, held_until=now + timedelta(minutes=hold_minutes),
        price_preview=price(lot.tariff, vehicle.vehicle_type.value, body.starts_at, body.ends_at),
        tariff_snapshot=lot.tariff, strategy=strategy, allocation_reason=allocation.explanation,
        wasted_rank=allocation.wasted_rank, idempotency_key=body.idempotency_key)
    db.add(booking); await db.flush()
    await booking_event(db,booking,"held","booking.api",{"slot_id":str(selected.id),"price_preview":str(booking.price_preview)})
    plate_vehicle_ids=(await db.scalars(select(Vehicle.id).where(Vehicle.operator_id==user.operator_id,
        Vehicle.plate_normalized==vehicle.plate_normalized))).all()
    same_plate_overlap=await db.scalar(select(Booking.id).where(Booking.operator_id==user.operator_id,
        Booking.vehicle_id.in_(plate_vehicle_ids),Booking.id!=booking.id,
        Booking.status.in_([BookingStatus.HELD,BookingStatus.CONFIRMED,BookingStatus.CHECKED_IN]),
        Booking.starts_at<body.ends_at,Booking.ends_at>body.starts_at).limit(1))
    if same_plate_overlap is not None:
        db.add(ExceptionFlag(operator_id=user.operator_id,booking_id=booking.id,flag_type="overlapping_plate",status="open"))
    await audit(db, user.operator_id, "booking.held", "booking", str(booking.id), user.id, details={"slot_id":str(selected.id), "price_preview":str(booking.price_preview)})
    try: await db.commit()
    except IntegrityError:
        await db.rollback(); raise error(409, "slot_unavailable", "No eligible slot is available for that time window")
    await db.refresh(booking); return booking_view(booking)

@app.post("/attendant/bookings", status_code=201)
async def assisted_booking(body: AssistedBookingIn, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(Role.ATTENDANT,Role.MANAGER))):
    driver=await db.scalar(select(User).where(func.lower(User.email)==body.driver_email.lower(),User.operator_id==user.operator_id,User.role==Role.DRIVER))
    if driver is None: raise error(404,"driver_not_found","Driver account was not found for this operator")
    request=BookingIn(**body.model_dump(exclude={"driver_email"}))
    result=await create_booking(request,db,driver)
    await audit(db,user.operator_id,"booking.assisted_hold_created","booking",result["id"],user.id,
        details={"driver_id":str(driver.id),"requires_driver_confirmation":True})
    await db.commit()
    return {**result,"assisted_by":str(user.id),"requires_driver_confirmation":True}

@app.get("/attendant/drivers/{email}/vehicles")
async def assisted_driver_vehicles(email: str, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(Role.ATTENDANT,Role.MANAGER))):
    driver=await db.scalar(select(User).where(func.lower(User.email)==email.lower(),User.operator_id==user.operator_id,User.role==Role.DRIVER))
    if driver is None: raise error(404,"driver_not_found","Driver account was not found for this operator")
    vehicles=(await db.scalars(select(Vehicle).where(Vehicle.driver_id==driver.id,Vehicle.operator_id==user.operator_id))).all()
    return [{"id":str(vehicle.id),"plate_masked":f"••••{vehicle.plate_normalized[-3:]}","vehicle_type":vehicle.vehicle_type.value} for vehicle in vehicles]

def booking_view(b: Booking):
    return {"id": str(b.id), "lot_id": str(b.lot_id), "slot_id": str(b.slot_id), "starts_at": b.starts_at,
            "ends_at": b.ends_at, "status": b.status.value, "held_until": b.held_until,
            "price_preview": str(b.price_preview), "strategy": b.strategy, "allocation_reason": b.allocation_reason,
            "payment_mode": "TEST MODE"}

@app.get("/bookings")
async def my_bookings(db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    rows = (await db.scalars(select(Booking).where(Booking.driver_id == user.id, Booking.operator_id == user.operator_id).order_by(Booking.created_at.desc()))).all()
    return [booking_view(b) for b in rows]

@app.get("/bookings/{booking_id}")
async def booking_detail(booking_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    query = select(Booking).where(Booking.id == booking_id, Booking.operator_id == user.operator_id)
    if user.role == Role.DRIVER: query = query.where(Booking.driver_id == user.id)
    booking = await db.scalar(query)
    if booking is None: raise error(404, "booking_not_found", "Booking was not found")
    return booking_view(booking)

@app.get("/bookings/{booking_id}/directions")
async def my_slot_directions(booking_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    booking=await db.scalar(select(Booking).where(Booking.id==booking_id,Booking.operator_id==user.operator_id,Booking.driver_id==user.id))
    if booking is None: raise error(404,"booking_not_found","Booking was not found")
    lot=await db.scalar(select(Lot).where(Lot.id==booking.lot_id,Lot.operator_id==user.operator_id))
    slot=await db.scalar(select(Slot).where(Slot.id==booking.slot_id,Slot.operator_id==user.operator_id))
    if lot is None or slot is None: raise error(404,"slot_not_found","Assigned parking location is unavailable")
    return {"booking_id":str(booking.id),"lot":lot.name,"address":lot.address,"slot_code":slot.slot_code,
        "floor":slot.floor,"zone":slot.zone,"instructions":f"Go to {lot.name}, then floor {slot.floor}, zone {slot.zone}, space {slot.slot_code}.",
        "label":"SOFTWARE-ONLY directions; no live navigation or sensor confirmation"}

@app.post("/bookings/{booking_id}/confirm")
async def confirm(booking_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    b = await db.scalar(select(Booking).where(Booking.id == booking_id, Booking.driver_id == user.id, Booking.operator_id == user.operator_id).with_for_update())
    if b is None: raise error(404, "booking_not_found", "Booking was not found")
    if b.status != BookingStatus.HELD or b.held_until < datetime.now(UTC): raise error(409, "hold_expired", "Booking hold has expired")
    b.status = BookingStatus.CONFIRMED
    await booking_event(db,b,"confirmed","booking.api")
    db.add(Notification(operator_id=b.operator_id,user_id=b.driver_id,booking_id=b.id,kind="booking_confirmed",
        message="Your parking booking is confirmed. See your booking history for the QR pass and slot details."))
    await audit(db, user.operator_id, "booking.confirmed", "booking", str(b.id), user.id); await db.commit()
    return {**booking_view(b), "message": "Confirmed by explicit driver action"}

@app.post("/bookings/{booking_id}/payments", status_code=201)
async def create_test_payment(booking_id: UUID, body: PaymentIn, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    if not body.confirmed:
        raise error(400,"explicit_confirmation_required","Payment requires an explicit driver confirmation")
    prior=await db.scalar(select(Payment).where(Payment.operator_id==user.operator_id,Payment.idempotency_key==body.idempotency_key))
    if prior:
        return {"id":str(prior.id),"status":prior.status,"amount":str(prior.amount),"mode":"TEST MODE"}
    booking=await db.scalar(select(Booking).where(Booking.id==booking_id,Booking.operator_id==user.operator_id,Booking.driver_id==user.id).with_for_update())
    if booking is None: raise error(404,"booking_not_found","Booking was not found")
    if booking.status!=BookingStatus.CONFIRMED: raise error(409,"booking_not_confirmed","Confirm the booking before payment")
    payment=Payment(operator_id=user.operator_id,booking_id=booking.id,amount=booking.price_preview,
        mode=f"SIMULATED_TEST_{body.method.upper()}",status="simulated_success",idempotency_key=body.idempotency_key)
    db.add(payment); await db.flush()
    await audit(db,user.operator_id,"payment.test_succeeded","payment",str(payment.id),user.id,
        details={"mode":"TEST MODE","method":body.method,"amount":str(payment.amount)})
    await db.commit()
    return {"id":str(payment.id),"status":payment.status,"amount":str(payment.amount),"mode":"TEST MODE"}

@app.post("/bookings/{booking_id}/cancel")
async def cancel_booking(booking_id: UUID, body: CancelIn, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    booking=await db.scalar(select(Booking).where(Booking.id==booking_id,Booking.operator_id==user.operator_id,Booking.driver_id==user.id).with_for_update())
    if booking is None: raise error(404,"booking_not_found","Booking was not found")
    if booking.status not in (BookingStatus.HELD,BookingStatus.CONFIRMED): raise error(409,"invalid_state","This booking cannot be cancelled")
    lot=await db.scalar(select(Lot).where(Lot.id==booking.lot_id,Lot.operator_id==user.operator_id))
    booking.status=BookingStatus.CANCELLED
    await booking_event(db,booking,"cancelled","booking.api",{"reason":body.reason})
    await audit(db,user.operator_id,"booking.cancelled","booking",str(booking.id),user.id,body.reason,
        {"refund_percent":(lot.config.get("refund_percent",0) if lot else 0)})
    await db.commit()
    cancellation_threshold=int((lot.config if lot else {}).get("many_cancellations_threshold",3))
    cancellation_count=await db.scalar(select(func.count(Booking.id)).where(Booking.operator_id==user.operator_id,
        Booking.driver_id==user.id,Booking.status==BookingStatus.CANCELLED))
    if cancellation_count>=cancellation_threshold:
        db.add(ExceptionFlag(operator_id=user.operator_id,booking_id=booking.id,flag_type="many_cancellations",status="open"))
        await audit(db,user.operator_id,"booking.cancellation_threshold_flagged","booking",str(booking.id),user.id,
            details={"count":cancellation_count,"threshold":cancellation_threshold})
        await db.commit()
    return {"booking_id":str(booking.id),"status":"cancelled","refund_percent":(lot.config.get("refund_percent",0) if lot else 0),"refund_execution":"not configured"}

@app.post("/bookings/{booking_id}/extend")
async def extend_booking(booking_id: UUID, body: BookingExtensionIn, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    booking=await db.scalar(select(Booking).where(Booking.id==booking_id,Booking.operator_id==user.operator_id,Booking.driver_id==user.id).with_for_update())
    if booking is None: raise error(404,"booking_not_found","Booking was not found")
    if booking.status not in (BookingStatus.CONFIRMED,BookingStatus.CHECKED_IN): raise error(409,"invalid_state","Only confirmed or checked-in bookings can be extended")
    new_end=body.new_ends_at.astimezone(UTC)
    if new_end<=booking.ends_at: raise error(422,"invalid_extension","New end time must be later than the current end")
    lot=await db.scalar(select(Lot).where(Lot.id==booking.lot_id,Lot.operator_id==user.operator_id))
    vehicle=await db.scalar(select(Vehicle).where(Vehicle.id==booking.vehicle_id,Vehicle.operator_id==user.operator_id))
    if lot is None or vehicle is None: raise error(409,"booking_configuration_missing","Booking data is incomplete")
    if new_end-booking.starts_at>timedelta(hours=int(lot.config.get("max_duration_hours",24))): raise error(422,"max_duration","Extension exceeds lot limit")
    conflict=await db.scalar(select(Booking.id).where(Booking.slot_id==booking.slot_id,Booking.id!=booking.id,
        Booking.status.in_([BookingStatus.HELD,BookingStatus.CONFIRMED,BookingStatus.CHECKED_IN]),
        Booking.starts_at<new_end,Booking.ends_at>booking.ends_at).limit(1))
    if conflict is not None: raise error(409,"slot_unavailable","Another booking uses this slot during the extension")
    updated_total=price(booking.tariff_snapshot,vehicle.vehicle_type.value,booking.starts_at,new_end)
    if not body.confirmed:
        return {"booking_id":str(booking.id),"new_ends_at":new_end,"new_price_preview":str(updated_total),"requires_explicit_confirmation":True}
    booking.ends_at=new_end; booking.price_preview=updated_total
    await booking_event(db,booking,"extended","booking.api",{"new_ends_at":new_end.isoformat(),"price":str(updated_total)})
    await audit(db,user.operator_id,"booking.extended","booking",str(booking.id),user.id,details={"new_ends_at":new_end.isoformat(),"price":str(updated_total)})
    await db.commit()
    return {**booking_view(booking),"explicitly_confirmed":True}

@app.post("/bookings/{booking_id}/qr")
async def qr_pass(booking_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    b = await db.scalar(select(Booking).where(Booking.id == booking_id, Booking.driver_id == user.id, Booking.operator_id == user.operator_id))
    if b is None: raise error(404, "booking_not_found", "Booking was not found")
    from jose import jwt
    exp = min(b.ends_at, datetime.now(UTC) + timedelta(hours=12))
    token = jwt.encode({"booking_id": str(b.id), "operator_id": str(user.operator_id), "exp": exp}, settings.jwt_secret, algorithm="HS256")
    return {"qr_token": token, "expires_at": exp}

@app.get("/bookings/{booking_id}/receipt",response_class=HTMLResponse)
async def receipt(booking_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    query=select(Booking).where(Booking.id==booking_id,Booking.operator_id==user.operator_id)
    if user.role==Role.DRIVER: query=query.where(Booking.driver_id==user.id)
    booking=await db.scalar(query)
    if booking is None: raise error(404,"booking_not_found","Booking was not found")
    lot=await db.scalar(select(Lot).where(Lot.id==booking.lot_id,Lot.operator_id==user.operator_id))
    lot_name=(lot.name if lot else "Parking lot").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    return HTMLResponse(f"<!doctype html><html lang='en'><meta charset='utf-8'><title>Parkly receipt</title><h1>Parkly receipt</h1><p>{lot_name}</p><p>Booking {booking.id}</p><p>{booking.starts_at.isoformat()} to {booking.ends_at.isoformat()}</p><p>Total: ₹{booking.price_preview}</p><strong>TEST MODE</strong></html>")

@app.post("/attendant/bookings/{booking_id}/check-in")
async def check_in(booking_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(Role.ATTENDANT, Role.MANAGER))):
    b = await db.scalar(select(Booking).where(Booking.id == booking_id, Booking.operator_id == user.operator_id).with_for_update())
    if b is None: raise error(404, "booking_not_found", "Booking was not found")
    if b.status != BookingStatus.CONFIRMED: raise error(409, "invalid_state", "Booking must be confirmed before entry")
    b.status = BookingStatus.CHECKED_IN; b.checked_in_at = datetime.now(UTC)
    await booking_event(db,b,"checked_in","attendant.api")
    await db.execute(__import__('sqlalchemy').update(Slot).where(Slot.id == b.slot_id).values(occupied=True))
    await audit(db, user.operator_id, "booking.checked_in", "booking", str(b.id), user.id); await db.commit()
    return booking_view(b)

@app.post("/attendant/qr/check-in")
async def check_in_by_qr(body: QRScanIn, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(Role.ATTENDANT, Role.MANAGER))):
    from jose import JWTError, jwt
    try:
        claims=jwt.decode(body.qr_token, settings.jwt_secret, algorithms=["HS256"])
        booking_id=UUID(claims["booking_id"])
        operator_id=UUID(claims["operator_id"])
    except (JWTError, KeyError, ValueError):
        raise error(401,"invalid_qr","QR pass is invalid or expired")
    if operator_id!=user.operator_id: raise error(403,"forbidden","QR pass belongs to another operator")
    return await check_in(booking_id,db,user)

@app.get("/attendant/plate/{plate}/active-booking")
async def lookup_plate_booking(plate: str, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(Role.ATTENDANT,Role.MANAGER))):
    normalized=re.sub(r"[^A-Z0-9]","",plate.upper())
    if len(normalized)<2: raise error(422,"invalid_plate","Enter at least two plate characters")
    vehicles=(await db.scalars(select(Vehicle).where(Vehicle.operator_id==user.operator_id,Vehicle.plate_normalized==normalized))).all()
    vehicle_ids=[vehicle.id for vehicle in vehicles]
    if not vehicle_ids: raise error(404,"vehicle_not_found","No matching vehicle was found")
    bookings=(await db.scalars(select(Booking).where(Booking.operator_id==user.operator_id,Booking.vehicle_id.in_(vehicle_ids),
        Booking.status.in_([BookingStatus.CONFIRMED,BookingStatus.CHECKED_IN])).order_by(Booking.starts_at))).all()
    return [{"booking_id":str(booking.id),"status":booking.status.value,"lot_id":str(booking.lot_id),
        "slot_id":str(booking.slot_id),"plate_masked":f"••••{normalized[-3:]}"} for booking in bookings]

@app.post("/attendant/bookings/{booking_id}/check-out")
async def check_out(booking_id: UUID, reason: str = Query(min_length=3, max_length=200), gateway_available: bool = True,
                    payment_method: str = Query(default="cash", pattern="^(cash|upi)$"),
                    db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(Role.ATTENDANT, Role.MANAGER))):
    b = await db.scalar(select(Booking).where(Booking.id == booking_id, Booking.operator_id == user.operator_id).with_for_update())
    if b is None: raise error(404, "booking_not_found", "Booking was not found")
    if b.status != BookingStatus.CHECKED_IN: raise error(409, "invalid_state", "Booking is not checked in")
    now = datetime.now(UTC); b.checked_out_at = now; b.status = BookingStatus.COMPLETED
    vehicle = await db.scalar(select(Vehicle).where(Vehicle.id == b.vehicle_id, Vehicle.operator_id == user.operator_id))
    if vehicle is None: raise error(409, "vehicle_missing", "Booking vehicle is unavailable")
    total = price(b.tariff_snapshot, vehicle.vehicle_type.value, b.checked_in_at or b.starts_at, now)
    await db.execute(__import__('sqlalchemy').update(Slot).where(Slot.id == b.slot_id).values(occupied=False))
    payment = "gateway_test" if gateway_available else "attendant_pay_at_exit"
    payment_record=Payment(operator_id=b.operator_id,booking_id=b.id,amount=total,
        mode=("SIMULATED_TEST_CHECKOUT" if gateway_available else f"ATTENDANT_{payment_method.upper()}"),
        status=("simulated_success" if gateway_available else "attendant_recorded"),
        reason_code=(None if gateway_available else reason),idempotency_key=f"checkout-{b.id}")
    db.add(payment_record)
    await booking_event(db,b,"checked_out","attendant.api",{"bill":str(total),"payment_path":payment,"reason":reason})
    await audit(db, user.operator_id, "booking.checked_out", "booking", str(b.id), user.id, reason=reason,
                details={"payment_path":payment, "bill":str(total), "gateway_mode":"TEST MODE"})
    if now > b.ends_at:
        overstay_minutes=int((now-b.ends_at).total_seconds()//60)
        lot=await db.scalar(select(Lot).where(Lot.id==b.lot_id,Lot.operator_id==b.operator_id))
        long_threshold=int((lot.config if lot else {}).get("long_overstay_minutes",30))
        flag = ExceptionFlag(operator_id=user.operator_id, booking_id=b.id,
            flag_type="long_overstay" if overstay_minutes>=long_threshold else "overstay", status="open"); db.add(flag)
        db.add(Notification(operator_id=b.operator_id,user_id=b.driver_id,booking_id=b.id,
            kind="overstay_review",message="Your checkout was recorded after the reserved end time. A human reviewer will review the exception; no automatic fine was charged."))
    await db.commit()
    return {"booking_id":str(b.id), "bill":str(total), "receipt":"HTML receipt available", "payment_mode":"TEST MODE",
        "fallback":not gateway_available,"payment_status":payment_record.status,
        "payment_method":payment_method if not gateway_available else "simulated_gateway"}

@app.post("/events", status_code=202)
async def ingest_event(body: EventIn, x_event_api_key: str = Header(default=""), db: AsyncSession = Depends(get_db)):
    source_keys={}
    for entry in settings.event_source_keys.split(","):
        if ":" in entry:
            source,key=entry.split(":",1); source_keys[source.strip()]=key.strip()
    expected=source_keys.get(body.source) if source_keys else settings.event_api_key
    if not expected or x_event_api_key != expected: raise error(401, "invalid_event_key", "Event source key is invalid")
    lot = await db.scalar(select(Lot).where(Lot.id == body.lot_id, Lot.active.is_(True)))
    if lot is None: raise error(404, "lot_not_found", "Lot was not found")
    duplicate = await db.scalar(select(Event.id).where(Event.operator_id == lot.operator_id, Event.event_id == body.event_id))
    if duplicate: return JSONResponse(status_code=200, content={"accepted":True,"duplicate":True})
    if body.slot_id:
        slot = await db.scalar(select(Slot).where(Slot.id == body.slot_id, Slot.lot_id == lot.id, Slot.operator_id == lot.operator_id))
        if slot is None: raise error(422, "invalid_slot", "Slot does not belong to this lot")
        if body.event_type in ("entry", "occupied"): slot.occupied = True
        elif body.event_type in ("exit", "vacated"): slot.occupied = False
    db.add(Event(operator_id=lot.operator_id, event_id=body.event_id, source=body.source, event_type=body.event_type,
                 occurred_at=body.occurred_at, payload=body.model_dump(mode="json")))
    await audit(db, lot.operator_id, "occupancy.event_ingested", "event", body.event_id, details={"source":body.source,"type":body.event_type})
    try: await db.commit()
    except IntegrityError: await db.rollback(); return JSONResponse(status_code=200, content={"accepted":True,"duplicate":True})
    return {"accepted":True,"duplicate":False,"label":"SIMULATED external event source"}

@app.post("/operator/simulated-events", status_code=202)
async def simulated_event(body: SimulatedEventIn, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(Role.MANAGER))):
    lot=await db.scalar(select(Lot).where(Lot.id==body.lot_id,Lot.operator_id==user.operator_id))
    if lot is None: raise error(404,"lot_not_found","Lot was not found")
    slot=await db.scalar(select(Slot).where(Slot.id==body.slot_id,Slot.lot_id==lot.id,Slot.operator_id==user.operator_id))
    if slot is None: raise error(404,"slot_not_found","Slot was not found")
    event=EventIn(event_id=f"sim-{uuid4()}",source="SIMULATED-generator",event_type=body.event_type,
        occurred_at=datetime.now(UTC),lot_id=lot.id,slot_id=slot.id)
    result=await ingest_event(event,settings.event_api_key,db)
    payload=result.body.decode() if isinstance(result,JSONResponse) else result
    if isinstance(payload,str):
        import json
        payload=json.loads(payload)
    return {**payload,"label":"SIMULATED"}

@app.post("/operator/slots/{slot_id}/override")
async def override_slot(slot_id: UUID, body: SlotOverrideIn, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(Role.MANAGER))):
    slot=await db.scalar(select(Slot).where(Slot.id==slot_id,Slot.operator_id==user.operator_id).with_for_update())
    if slot is None: raise error(404,"slot_not_found","Slot was not found")
    slot.occupied=body.occupied
    await audit(db,user.operator_id,"slot.manual_override","slot",str(slot.id),user.id,reason=body.reason_code,details={"occupied":body.occupied})
    await db.commit()
    return {"slot_id":str(slot.id),"occupied":slot.occupied,"reason_code":body.reason_code}

@app.get("/operator/occupancy")
async def occupancy(db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(Role.ATTENDANT, Role.MANAGER, Role.AUDITOR))):
    lots = (await db.scalars(select(Lot).where(Lot.operator_id == user.operator_id))).all()
    result=[]
    for lot in lots:
        slots=(await db.scalars(select(Slot).where(Slot.operator_id == user.operator_id,Slot.lot_id == lot.id))).all()
        groups: dict[tuple[int,str,str],list[Slot]]={}
        for slot in slots: groups.setdefault((slot.floor,slot.zone,slot.slot_type.value),[]).append(slot)
        result.append({"lot":lot.name,"total":len(slots),"occupied":sum(s.occupied for s in slots),
            "available":sum(not s.occupied for s in slots),"by_floor_zone_vehicle_type":[
                {"floor":key[0],"zone":key[1],"vehicle_type":key[2],"capacity":len(items),
                 "occupied":sum(s.occupied for s in items),"available":sum(not s.occupied for s in items)}
                for key,items in groups.items()]})
    return {"label":"LIVE SOFTWARE EVENTS; no sensor detection","lots":result}

@app.post("/operator/lots", status_code=201)
async def create_lot(body: LotIn, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(Role.MANAGER))):
    area_id, venue_id = await resolve_lot_location(db, body.area_id, body.venue_id)
    lot=Lot(operator_id=user.operator_id,name=body.name,address=body.address,timezone=body.timezone,
        config=body.config,tariff=body.tariff,strategy=body.strategy,area_id=area_id,venue_id=venue_id)
    db.add(lot); await db.flush()
    initial_config={"config":body.config,"tariff":body.tariff,"strategy":body.strategy,
        "area_id":str(area_id) if area_id else None,"venue_id":str(venue_id) if venue_id else None}
    db.add(TariffVersion(operator_id=user.operator_id,lot_id=lot.id,version=1,config=initial_config,changed_by=user.id))
    await audit(db,user.operator_id,"lot.created","lot",str(lot.id),user.id,
        details={"area_id":initial_config["area_id"],"venue_id":initial_config["venue_id"],"version":1})
    await db.commit()
    return {"id":str(lot.id),"name":lot.name,"strategy":lot.strategy}

async def resolve_lot_location(db: AsyncSession, area_id: UUID | None, venue_id: UUID | None) -> tuple[UUID | None, UUID | None]:
    if venue_id is not None:
        venue = await db.scalar(select(Venue).where(Venue.id == venue_id, Venue.status == "active"))
        if venue is None:
            raise error(422, "invalid_venue", "Choose an approved listed venue")
        if area_id is not None and area_id != venue.area_id:
            raise error(422, "location_parent_mismatch", "The venue does not belong to the selected area")
        return venue.area_id, venue.id
    if area_id is not None:
        area = await db.scalar(select(Area).where(Area.id == area_id, Area.status == "active"))
        if area is None:
            raise error(422, "invalid_area", "Choose an approved listed area")
    return area_id, None

@app.post("/operator/lots/{lot_id}/slots", status_code=201)
async def create_slots(lot_id: UUID, body: list[SlotIn], db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(Role.MANAGER))):
    if not body or len(body)>500: raise error(422,"invalid_slot_batch","Provide between 1 and 500 slots")
    lot=await db.scalar(select(Lot).where(Lot.id==lot_id,Lot.operator_id==user.operator_id))
    if lot is None: raise error(404,"lot_not_found","Lot was not found")
    existing=set((await db.scalars(select(Slot.slot_code).where(Slot.lot_id==lot_id,Slot.operator_id==user.operator_id))).all())
    codes=[item.slot_code for item in body]
    if len(set(codes))!=len(codes) or existing.intersection(codes): raise error(409,"duplicate_slot_code","Slot codes must be unique within the lot")
    rows=[]
    for item in body:
        try: kind=SlotType(item.slot_type)
        except ValueError: raise error(422,"invalid_slot_type",f"Unsupported slot type: {item.slot_type}")
        rows.append(Slot(operator_id=user.operator_id,lot_id=lot_id,slot_code=item.slot_code,floor=item.floor,zone=item.zone,slot_type=kind,covered=item.covered,exit_rank=item.exit_rank,ev_only=item.ev_only,accessible_only=item.accessible_only))
    db.add_all(rows); await audit(db,user.operator_id,"slots.created","lot",str(lot_id),user.id,details={"count":len(rows)})
    await db.commit()
    return {"created":len(rows)}

@app.post("/operator/jobs/release-expired-holds")
async def release_expired_holds(db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(Role.MANAGER))):
    released=await release_expired(db,user.operator_id,user.id)
    return {"released":released,"fine_created":False,"notice_delivery":"in_app"}

@app.get("/notifications")
async def my_notifications(db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    rows=(await db.scalars(select(Notification).where(Notification.operator_id==user.operator_id,Notification.user_id==user.id).order_by(Notification.created_at.desc()).limit(100))).all()
    return [{"id":str(n.id),"kind":n.kind,"message":n.message,"booking_id":str(n.booking_id) if n.booking_id else None,"created_at":n.created_at,"read":n.read_at is not None} for n in rows]

@app.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    item=await db.scalar(select(Notification).where(Notification.id==notification_id,Notification.operator_id==user.operator_id,Notification.user_id==user.id).with_for_update())
    if item is None: raise error(404,"notification_not_found","Notification was not found")
    if item.read_at is None: item.read_at=datetime.now(UTC); await db.commit()
    return {"id":str(item.id),"read":True}

@app.get("/operator/audit")
async def audit_log(db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(Role.MANAGER, Role.AUDITOR))):
    rows=(await db.scalars(select(AuditLog).where(AuditLog.operator_id == user.operator_id).order_by(AuditLog.created_at.desc()).limit(500))).all()
    return [{"id":str(a.id),"actor_id":str(a.actor_id) if a.actor_id else None,"action":a.action,"entity_type":a.entity_type,"entity_id":a.entity_id,"reason":a.reason,"created_at":a.created_at} for a in rows]

@app.get("/operator/flags")
async def flags(db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(Role.MANAGER, Role.AUDITOR))):
    rows=(await db.scalars(select(ExceptionFlag).where(ExceptionFlag.operator_id == user.operator_id).order_by(ExceptionFlag.created_at.desc()))).all()
    return [{"id":str(f.id),"booking_id":str(f.booking_id),"type":f.flag_type,"status":f.status,"label":"REVIEW REQUIRED; flag is not proof"} for f in rows]

@app.post("/operator/flags/{flag_id}/review")
async def review_flag(flag_id: UUID, body: ReviewIn, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(Role.MANAGER))):
    flag=await db.scalar(select(ExceptionFlag).where(ExceptionFlag.id==flag_id,ExceptionFlag.operator_id==user.operator_id).with_for_update())
    if flag is None: raise error(404,"flag_not_found","Flag was not found")
    flag.status=body.decision; flag.reviewer_id=user.id; flag.reviewer_reason=body.reason
    await audit(db,user.operator_id,"flag.reviewed","flag",str(flag.id),user.id,body.reason,{"decision":body.decision})
    await db.commit(); return {"id":str(flag.id),"status":flag.status,"reviewer_reason":flag.reviewer_reason}

@app.post("/operator/flags/{flag_id}/penalty", status_code=201)
async def record_reviewed_penalty(flag_id: UUID, body: PenaltyIn, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(Role.MANAGER))):
    if not body.confirmed:
        raise error(400,"explicit_confirmation_required","A manager must explicitly confirm the reviewed decision")
    flag=await db.scalar(select(ExceptionFlag).where(ExceptionFlag.id==flag_id,ExceptionFlag.operator_id==user.operator_id).with_for_update())
    if flag is None: raise error(404,"flag_not_found","Flag was not found")
    if flag.status!="escalate" or flag.reviewer_id is None:
        raise error(409,"human_review_required","Review and escalate the flag before recording a penalty")
    prior=await db.scalar(select(PenaltyDecision).where(PenaltyDecision.operator_id==user.operator_id,PenaltyDecision.booking_id==flag.booking_id))
    if prior is not None: raise error(409,"penalty_already_recorded","A penalty decision already exists for this booking")
    booking=await db.scalar(select(Booking).where(Booking.id==flag.booking_id,Booking.operator_id==user.operator_id))
    if booking is None: raise error(404,"booking_not_found","Booking was not found")
    notice=Notification(operator_id=user.operator_id,user_id=booking.driver_id,booking_id=booking.id,
        kind="human_reviewed_penalty",message=f"A manager reviewed your {flag.flag_type} exception. Decision: {body.reason}. Amount: ₹{body.amount:.2f}.")
    db.add(notice); await db.flush()
    decision=PenaltyDecision(operator_id=user.operator_id,booking_id=booking.id,reviewer_id=user.id,notice_id=notice.id,reason=body.reason,amount=body.amount)
    db.add(decision); await audit(db,user.operator_id,"penalty.human_approved","booking",str(booking.id),user.id,body.reason,{"amount":body.amount,"flag_id":str(flag.id)})
    await db.commit()
    return {"id":str(decision.id),"status":"human_reviewed","amount":str(decision.amount),"notification":"in_app"}

@app.get("/operator/dashboard")
async def operator_dashboard(start_at: datetime | None = None, end_at: datetime | None = None,
                             db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(Role.MANAGER,Role.AUDITOR))):
    if (start_at is None)!=(end_at is None) or (start_at is not None and (start_at.tzinfo is None or end_at.tzinfo is None or end_at<=start_at)):
        raise error(422,"invalid_window","Provide a valid timezone-aware dashboard date range")
    booking_query=select(Booking).where(Booking.operator_id==user.operator_id)
    snapshot_query=select(OccupancySnapshot).where(OccupancySnapshot.operator_id==user.operator_id)
    if start_at is not None:
        booking_query=booking_query.where(Booking.starts_at>=start_at,Booking.starts_at<end_at)
        snapshot_query=snapshot_query.where(OccupancySnapshot.captured_at>=start_at,OccupancySnapshot.captured_at<end_at)
    bookings=(await db.scalars(booking_query)).all()
    completed=[b for b in bookings if b.status==BookingStatus.COMPLETED]
    occupancy=(await db.scalars(snapshot_query)).all()
    utilization_by_lot: dict[str,list[float]]={}
    for snapshot in occupancy:
        utilization_by_lot.setdefault(str(snapshot.lot_id),[]).append(snapshot.occupied_count/max(1,snapshot.capacity))
    by_hour: dict[str,list[float]]={}
    for snap in occupancy:
        key=snap.captured_at.strftime("%a %H")
        by_hour.setdefault(key,[]).append(snap.occupied_count/max(1,snap.capacity))
    strategies={}
    for b in bookings:
        key=(str(b.lot_id),b.strategy)
        bucket=strategies.setdefault(key,{"n":0,"wasted_rank_total":0})
        bucket["n"]+=1; bucket["wasted_rank_total"]+=b.wasted_rank
    lots=(await db.scalars(select(Lot).where(Lot.operator_id==user.operator_id))).all()
    slots=(await db.scalars(select(Slot).where(Slot.operator_id==user.operator_id))).all()
    occupancy_by_location=[]
    for lot in lots:
        lot_slots=[slot for slot in slots if slot.lot_id==lot.id]
        groups: dict[tuple[int,str,str],list[Slot]]={}
        for slot in lot_slots:
            key=(slot.floor,slot.zone,slot.slot_type.value)
            groups.setdefault(key,[]).append(slot)
        occupancy_by_location.extend({"lot_id":str(lot.id),"lot":lot.name,"floor":key[0],"zone":key[1],
            "vehicle_type":key[2],"capacity":len(items),"occupied":sum(item.occupied for item in items),
            "available":sum(not item.occupied for item in items)} for key,items in groups.items())
    peak_hours=sorted(({"weekday_hour":key,"mean_occupancy_rate":sum(vals)/len(vals),"n":len(vals)}
        for key,vals in by_hour.items()),key=lambda item:item["mean_occupancy_rate"],reverse=True)[:5]
    return {"label":"SYNTHETIC demo data is labelled; occupancy is software recorded",
        "date_range":{"start_at":start_at,"end_at":end_at},
        "revenue_total":str(sum((b.price_preview for b in completed),Decimal(0))),
        "revenue_sample_size":len(completed),"completed_bookings":len(completed),
        "average_completed_duration_minutes":round(sum(((b.checked_out_at or b.ends_at)-(b.checked_in_at or b.starts_at)).total_seconds()/60 for b in completed)/max(1,len(completed)),1),
        "average_duration_sample_size":len(completed),"peak_hours":peak_hours,"occupancy_by_location":occupancy_by_location,
        "occupancy_by_weekday_hour":[{"weekday_hour":key,"mean_occupancy_rate":round(sum(vals)/len(vals),4),"n":len(vals)} for key,vals in sorted(by_hour.items())],
        "allocation_strategy_kpis":[{"lot_id":key[0],"strategy":key[1],"n":value["n"],
            "utilization_rate":round(sum(utilization_by_lot.get(key[0],[]))/max(1,len(utilization_by_lot.get(key[0],[]))),4),
            "utilization_sample_size":len(utilization_by_lot.get(key[0],[])),
            "mean_wasted_rank":round(value["wasted_rank_total"]/value["n"],3)} for key,value in sorted(strategies.items())]}

@app.get("/operator/export/bookings.csv")
async def export_bookings_csv(db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(Role.MANAGER,Role.AUDITOR))):
    bookings=(await db.scalars(select(Booking).where(Booking.operator_id==user.operator_id).order_by(Booking.created_at))).all()
    stream=io.StringIO(); writer=csv.writer(stream)
    writer.writerow(["booking_id","status","starts_at","ends_at","price_preview","strategy","wasted_rank","data_label"])
    for b in bookings: writer.writerow([b.id,b.status.value,b.starts_at.isoformat(),b.ends_at.isoformat(),b.price_preview,b.strategy,b.wasted_rank,"SYNTHETIC/DEMO where seeded"])
    return PlainTextResponse(stream.getvalue(),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=parkly-bookings.csv"})

@app.get("/operator/export/revenue.csv")
async def export_revenue_csv(db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(Role.MANAGER,Role.AUDITOR))):
    bookings=(await db.scalars(select(Booking).where(Booking.operator_id==user.operator_id,Booking.status==BookingStatus.COMPLETED).order_by(Booking.checked_out_at))).all()
    stream=io.StringIO(); writer=csv.writer(stream); writer.writerow(["booking_id","checked_out_at","amount","currency","status","data_label"])
    for booking in bookings: writer.writerow([booking.id,booking.checked_out_at.isoformat() if booking.checked_out_at else "",booking.price_preview,"INR","recorded_demo_bill","SYNTHETIC/DEMO where seeded"])
    return PlainTextResponse(stream.getvalue(),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=parkly-revenue.csv"})

@app.get("/operator/export/audit.csv")
async def export_audit_csv(db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(Role.MANAGER,Role.AUDITOR))):
    rows=(await db.scalars(select(AuditLog).where(AuditLog.operator_id==user.operator_id).order_by(AuditLog.created_at))).all()
    stream=io.StringIO(); writer=csv.writer(stream); writer.writerow(["created_at","actor_id","action","entity_type","entity_id","reason","data_label"])
    for row in rows: writer.writerow([row.created_at.isoformat(),row.actor_id or "",row.action,row.entity_type,row.entity_id,row.reason or "","SYNTHETIC/DEMO where seeded"])
    return PlainTextResponse(stream.getvalue(),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=parkly-audit.csv"})

@app.put("/operator/lots/{lot_id}/configuration")
async def update_lot_configuration(lot_id: UUID, body: LotConfigUpdateIn, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(Role.MANAGER))):
    lot=await db.scalar(select(Lot).where(Lot.id==lot_id,Lot.operator_id==user.operator_id).with_for_update())
    if lot is None: raise error(404,"lot_not_found","Lot was not found")
    latest=await db.scalar(select(func.max(TariffVersion.version)).where(TariffVersion.operator_id==user.operator_id,TariffVersion.lot_id==lot.id))
    version=(latest or 0)+1
    lot.config=body.config; lot.tariff=body.tariff; lot.strategy=body.strategy
    fields_set = body.model_fields_set
    if "area_id" in fields_set or "venue_id" in fields_set:
        next_area = body.area_id if "area_id" in fields_set else lot.area_id
        next_venue = body.venue_id if "venue_id" in fields_set else lot.venue_id
        if "area_id" in fields_set and "venue_id" not in fields_set and next_venue is not None:
            current_venue = await db.get(Venue, next_venue)
            if current_venue is None or current_venue.area_id != next_area:
                next_venue = None
        lot.area_id, lot.venue_id = await resolve_lot_location(db, next_area, next_venue)
    version_config={"config":body.config,"tariff":body.tariff,"strategy":body.strategy,
        "area_id":str(lot.area_id) if lot.area_id else None,"venue_id":str(lot.venue_id) if lot.venue_id else None}
    db.add(TariffVersion(operator_id=user.operator_id,lot_id=lot.id,version=version,config=version_config,changed_by=user.id))
    await audit(db,user.operator_id,"lot.configuration_updated","lot",str(lot.id),user.id,
        details={"version":version,"strategy":body.strategy,"area_id":version_config["area_id"],"venue_id":version_config["venue_id"]})
    await db.commit(); return {"lot_id":str(lot.id),"version":version,"strategy":lot.strategy}

@app.put("/operator/lots/{lot_id}/location")
async def update_lot_location(lot_id: UUID, body: LotLocationIn, db: AsyncSession = Depends(get_db),
                              user: User = Depends(require_roles(Role.MANAGER))):
    lot = await db.scalar(select(Lot).where(Lot.id == lot_id, Lot.operator_id == user.operator_id).with_for_update())
    if lot is None:
        raise error(404, "lot_not_found", "Lot was not found")
    area_id, venue_id = await resolve_lot_location(db, body.area_id, body.venue_id)
    latest = await db.scalar(select(func.max(TariffVersion.version)).where(
        TariffVersion.operator_id == user.operator_id, TariffVersion.lot_id == lot.id))
    lot.area_id, lot.venue_id = area_id, venue_id
    version = (latest or 0) + 1
    snapshot = {"config":lot.config,"tariff":lot.tariff,"strategy":lot.strategy,
        "area_id":str(area_id) if area_id else None,"venue_id":str(venue_id) if venue_id else None}
    db.add(TariffVersion(operator_id=user.operator_id, lot_id=lot.id, version=version,
        config=snapshot, changed_by=user.id))
    await audit(db, user.operator_id, "lot.location_updated", "lot", str(lot.id), user.id,
        details={"version":version,"area_id":snapshot["area_id"],"venue_id":snapshot["venue_id"]})
    await db.commit()
    return {"lot_id":str(lot.id),"version":version,"area_id":snapshot["area_id"],"venue_id":snapshot["venue_id"]}

@app.get("/operator/lots/{lot_id}/configuration/history")
async def lot_configuration_history(lot_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(Role.MANAGER,Role.AUDITOR))):
    if await db.scalar(select(Lot.id).where(Lot.id==lot_id,Lot.operator_id==user.operator_id)) is None: raise error(404,"lot_not_found","Lot was not found")
    rows=(await db.scalars(select(TariffVersion).where(TariffVersion.operator_id==user.operator_id,TariffVersion.lot_id==lot_id).order_by(TariffVersion.version.desc()))).all()
    return [{"version":r.version,"configuration":r.config,"changed_by":str(r.changed_by),"created_at":r.created_at} for r in rows]

@app.post("/notifications/mock/{booking_id}", status_code=202)
async def mock_external_notification(booking_id: UUID, channel: str = Query(pattern="^(email|sms|whatsapp)$"), db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    booking=await db.scalar(select(Booking).where(Booking.id==booking_id,Booking.operator_id==user.operator_id,Booking.driver_id==user.id))
    if booking is None: raise error(404,"booking_not_found","Booking was not found")
    await audit(db,user.operator_id,"notification.mock_dispatched","booking",str(booking.id),user.id,details={"channel":channel,"delivery":"SIMULATED; no external message sent"})
    await db.commit()
    return {"status":"SIMULATED","channel":channel,"message":"Demo notification recorded; no external message was sent."}

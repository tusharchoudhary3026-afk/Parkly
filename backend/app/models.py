import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase): pass

class Role(str, enum.Enum):
    DRIVER = "driver"
    ATTENDANT = "attendant"
    MANAGER = "manager"
    AUDITOR = "auditor"

class SlotType(str, enum.Enum):
    TWO_WHEELER = "two_wheeler"
    CAR = "car"
    LARGE = "large"
    EV = "ev"
    ACCESSIBLE = "accessible"

class BookingStatus(str, enum.Enum):
    HELD = "held"
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    RELEASED = "released"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    COMPLETED = "completed"

class Operator(Base):
    __tablename__ = "operators"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)

class State(Base):
    """Shared geographic reference data; intentionally has no operator_id."""
    __tablename__ = "location_states"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(8), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    is_seeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

class City(Base):
    """Shared approved city reference; unreviewed submissions stay in LocationSuggestion."""
    __tablename__ = "location_cities"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    state_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("location_states.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    is_seeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="seed")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")

class Area(Base):
    """Shared approved area reference; unreviewed submissions stay in LocationSuggestion."""
    __tablename__ = "location_areas"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    city_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("location_cities.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    is_seeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="seed")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")

class Venue(Base):
    """Shared approved venue reference; unreviewed submissions stay in LocationSuggestion."""
    __tablename__ = "location_venues"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    area_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("location_areas.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    venue_type: Mapped[str] = mapped_column(String(24), nullable=False)
    is_seeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="seed")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    data_label: Mapped[str] = mapped_column(String(24), nullable=False, default="SYNTHETIC")
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6))

class LocationSuggestion(Base):
    """Private-to-submitter queue row until a manager explicitly approves it."""
    __tablename__ = "location_suggestions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submitted_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    state_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("location_states.id"), nullable=False, index=True)
    city_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("location_cities.id"), index=True)
    area_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("location_areas.id"), index=True)
    target_level: Mapped[str] = mapped_column(String(12), nullable=False)
    city_name: Mapped[str] = mapped_column(String(80), nullable=False)
    area_name: Mapped[str | None] = mapped_column(String(80))
    venue_name: Mapped[str | None] = mapped_column(String(80))
    venue_type: Mapped[str | None] = mapped_column(String(24))
    note: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    operator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("operators.id"), index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role, name="user_role", values_callable=lambda choices: [item.value for item in choices]), default=Role.DRIVER)
    phone: Mapped[str | None] = mapped_column(String(32))
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class Lot(Base):
    __tablename__ = "lots"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    operator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("operators.id"), index=True)
    area_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("location_areas.id"), index=True)
    venue_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("location_venues.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    address: Mapped[str] = mapped_column(String(300))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    tariff: Mapped[dict] = mapped_column(JSONB, default=dict)
    strategy: Mapped[str] = mapped_column(String(24), default="first_fit")
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class Slot(Base):
    __tablename__ = "slots"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    operator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("operators.id"), index=True)
    lot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lots.id"), index=True)
    slot_code: Mapped[str] = mapped_column(String(32))
    floor: Mapped[int] = mapped_column(Integer, default=0)
    zone: Mapped[str] = mapped_column(String(32), default="A")
    slot_type: Mapped[SlotType] = mapped_column(Enum(SlotType, name="slot_type", values_callable=lambda choices: [item.value for item in choices]))
    covered: Mapped[bool] = mapped_column(Boolean, default=False)
    exit_rank: Mapped[int] = mapped_column(Integer, default=0)
    ev_only: Mapped[bool] = mapped_column(Boolean, default=False)
    accessible_only: Mapped[bool] = mapped_column(Boolean, default=False)
    occupied: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("lot_id", "slot_code"),)

class Vehicle(Base):
    __tablename__ = "vehicles"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    operator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("operators.id"), index=True)
    driver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    plate_original: Mapped[str] = mapped_column(String(24))
    plate_normalized: Mapped[str] = mapped_column(String(24), index=True)
    vehicle_type: Mapped[SlotType] = mapped_column(Enum(SlotType, name="vehicle_type", values_callable=lambda choices: [item.value for item in choices]))
    ev: Mapped[bool] = mapped_column(Boolean, default=False)
    accessible: Mapped[bool] = mapped_column(Boolean, default=False)

class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    operator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("operators.id"), index=True)
    driver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"))
    lot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lots.id"), index=True)
    slot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("slots.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[BookingStatus] = mapped_column(Enum(BookingStatus, name="booking_status", values_callable=lambda choices: [item.value for item in choices]), index=True)
    held_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    price_preview: Mapped[float] = mapped_column(Numeric(10, 2))
    tariff_snapshot: Mapped[dict] = mapped_column(JSONB)
    strategy: Mapped[str] = mapped_column(String(24))
    allocation_reason: Mapped[str] = mapped_column(Text)
    wasted_rank: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("operator_id", "idempotency_key", name="uq_booking_idem"),)
    idempotency_key: Mapped[str] = mapped_column(String(128))

class Event(Base):
    __tablename__ = "events"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    operator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("operators.id"), index=True)
    event_id: Mapped[str] = mapped_column(String(128))
    source: Mapped[str] = mapped_column(String(100))
    event_type: Mapped[str] = mapped_column(String(40))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("operator_id", "event_id"),)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    operator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("operators.id"), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class ExceptionFlag(Base):
    __tablename__ = "exception_flags"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    operator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("operators.id"), index=True)
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id"), index=True)
    flag_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="open")
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewer_reason: Mapped[str | None] = mapped_column(Text)
    synthetic_label: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    operator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("operators.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    booking_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bookings.id"), index=True)
    kind: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class OccupancySnapshot(Base):
    __tablename__ = "occupancy_snapshots"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    operator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("operators.id"), index=True)
    lot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lots.id"), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    occupied_count: Mapped[int] = mapped_column(Integer)
    capacity: Mapped[int] = mapped_column(Integer)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)

class TariffVersion(Base):
    __tablename__ = "tariff_versions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    operator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("operators.id"), index=True)
    lot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lots.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    config: Mapped[dict] = mapped_column(JSONB)
    changed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("lot_id", "version"),)

class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    operator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("operators.id"), index=True)
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id"), index=True)
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    mode: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24))
    reason_code: Mapped[str | None] = mapped_column(String(40))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("operator_id", "idempotency_key"),)

class PenaltyDecision(Base):
    __tablename__ = "penalty_decisions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    operator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("operators.id"), index=True)
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id"), index=True)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    notice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("notifications.id"))
    reason: Mapped[str] = mapped_column(Text)
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

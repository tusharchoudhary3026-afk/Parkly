import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    consent_accepted: bool

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class VehicleIn(BaseModel):
    plate: str = Field(min_length=2, max_length=24)
    vehicle_type: str
    ev: bool = False
    accessible: bool = False
    @field_validator("plate")
    @classmethod
    def plate_valid(cls, value: str) -> str:
        cleaned = re.sub(r"\s+", " ", value.strip())
        if not cleaned: raise ValueError("plate is required")
        return cleaned

class BookingIn(BaseModel):
    lot_id: UUID
    vehicle_id: UUID
    starts_at: datetime
    ends_at: datetime
    idempotency_key: str = Field(min_length=8, max_length=128)
    @model_validator(mode="after")
    def valid_window(self):
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None: raise ValueError("timezone offset is required")
        if self.ends_at <= self.starts_at: raise ValueError("end must be after start")
        return self

class AssistedBookingIn(BookingIn):
    driver_email: EmailStr

class PaymentIn(BaseModel):
    confirmed: bool
    method: str = Field(pattern="^(upi|card)$")
    idempotency_key: str = Field(min_length=8, max_length=128)

class BookingExtensionIn(BaseModel):
    new_ends_at: datetime
    confirmed: bool = False
    @field_validator("new_ends_at")
    @classmethod
    def extension_time_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None: raise ValueError("timezone offset is required")
        return value

class CancelIn(BaseModel):
    reason: str = Field(min_length=3, max_length=200)

class EventIn(BaseModel):
    event_id: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=100)
    event_type: str = Field(pattern="^(entry|exit|occupied|vacated)$")
    occurred_at: datetime
    lot_id: UUID
    slot_id: UUID | None = None
    plate: str | None = Field(default=None, max_length=24)

    @field_validator("occurred_at")
    @classmethod
    def event_time_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must include a timezone")
        return value

class ReviewIn(BaseModel):
    decision: str = Field(pattern="^(dismiss|warn|escalate)$")
    reason: str = Field(min_length=3, max_length=500)

class PenaltyIn(BaseModel):
    amount: float = Field(gt=0, le=100000)
    reason: str = Field(min_length=3, max_length=500)
    confirmed: bool

class LotConfigUpdateIn(BaseModel):
    config: dict
    tariff: dict
    strategy: str = Field(pattern="^(first_fit|best_fit|scored)$")
    area_id: UUID | None = None
    venue_id: UUID | None = None

    @field_validator("config")
    @classmethod
    def config_values_valid(cls, value: dict) -> dict:
        for key, low, high in (("grace_minutes",0,120),("max_duration_hours",1,168),
            ("repeated_no_show_threshold",2,100),("long_overstay_minutes",1,1440),
            ("many_cancellations_threshold",2,100)):
            if key in value and (not isinstance(value[key],int) or not low<=value[key]<=high):
                raise ValueError(f"{key} must be between {low} and {high}")
        return value

    @field_validator("tariff")
    @classmethod
    def tariff_values_valid(cls, value: dict) -> dict:
        if not isinstance(value.get("free_minutes",0),int) or value.get("free_minutes",0)<0:
            raise ValueError("free_minutes must be a non-negative integer")
        for section in ("hourly","daily"):
            rates=value.get(section,{})
            if not isinstance(rates,dict) or any(float(rate)<0 for rate in rates.values()):
                raise ValueError(f"{section} rates must be non-negative numbers")
        return value

class QRScanIn(BaseModel):
    qr_token: str = Field(min_length=20, max_length=2048)

class SlotOverrideIn(BaseModel):
    occupied: bool
    reason_code: str = Field(min_length=3, max_length=40, pattern="^[a-z0-9_-]+$")

class SimulatedEventIn(BaseModel):
    lot_id: UUID
    slot_id: UUID
    event_type: str = Field(pattern="^(entry|exit|occupied|vacated)$")

class LotIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    address: str = Field(min_length=3, max_length=300)
    timezone: str = Field(default="UTC", max_length=64)
    config: dict = Field(default_factory=lambda: {"grace_minutes": 10, "max_duration_hours": 24})
    tariff: dict = Field(default_factory=lambda: {"free_minutes": 0, "hourly": {}, "daily": {}})
    strategy: str = Field(default="first_fit", pattern="^(first_fit|best_fit|scored)$")
    area_id: UUID | None = None
    venue_id: UUID | None = None

    @field_validator("config")
    @classmethod
    def lot_config_values_valid(cls, value: dict) -> dict:
        return LotConfigUpdateIn.config_values_valid(value)

    @field_validator("tariff")
    @classmethod
    def lot_tariff_values_valid(cls, value: dict) -> dict:
        return LotConfigUpdateIn.tariff_values_valid(value)

class SlotIn(BaseModel):
    slot_code: str = Field(min_length=1, max_length=32)
    floor: int = Field(default=0, ge=0, le=100)
    zone: str = Field(default="A", min_length=1, max_length=32)
    slot_type: str
    covered: bool = False
    exit_rank: int = Field(default=0, ge=0, le=10000)
    ev_only: bool = False
    accessible_only: bool = False

class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

class LocationSuggestionIn(BaseModel):
    state_id: UUID
    target_level: str = Field(pattern="^(city|area|venue)$")
    city_id: UUID | None = None
    area_id: UUID | None = None
    city_name: str | None = Field(default=None, min_length=2, max_length=80)
    area_name: str | None = Field(default=None, min_length=2, max_length=80)
    venue_name: str | None = Field(default=None, min_length=2, max_length=80)
    venue_type: str | None = Field(default=None, pattern="^(mall|building|market|hospital|station|office|other)$")
    note: str | None = Field(default=None, max_length=500)

    @field_validator("city_name", "area_name", "venue_name")
    @classmethod
    def safe_location_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = re.sub(r"\s+", " ", value.strip())
        if not 2 <= len(cleaned) <= 80 or "_" in cleaned or not re.fullmatch(r"[\w\s&.,'()-]+", cleaned, flags=re.UNICODE):
            raise ValueError("Use 2-80 letters, numbers, spaces, and & . , ' - ( ) only")
        return cleaned

    @model_validator(mode="after")
    def fields_match_target_level(self):
        if self.target_level == "city":
            if not self.city_name or self.city_id or self.area_id or self.area_name or self.venue_name:
                raise ValueError("A city suggestion needs only a city name and state")
        elif self.target_level == "area":
            if not self.city_id or not self.area_name or self.area_id or self.venue_name or self.venue_type:
                raise ValueError("An area suggestion needs a city and area name")
        elif self.target_level == "venue" and (not self.area_id or not self.venue_name or not self.venue_type):
            raise ValueError("A venue suggestion needs an area, venue name, and venue type")
        return self

class LocationSuggestionReviewIn(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def clean_review_reason(cls, value: str) -> str:
        cleaned = re.sub(r"\s+", " ", value.strip())
        if len(cleaned) < 3:
            raise ValueError("A review reason is required")
        return cleaned

class LotLocationIn(BaseModel):
    area_id: UUID | None = None
    venue_id: UUID | None = None

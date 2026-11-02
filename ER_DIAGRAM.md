# Database ER outline

```mermaid
erDiagram
  OPERATOR ||--o{ USER : scopes
  OPERATOR ||--o{ LOT : owns
  LOT ||--o{ SLOT : contains
  USER ||--o{ VEHICLE : registers
  USER ||--o{ BOOKING : makes
  VEHICLE ||--o{ BOOKING : assigned
  SLOT ||--o{ BOOKING : reserved
  BOOKING ||--o{ EXCEPTION_FLAG : raises
  BOOKING ||--o{ PAYMENT : records
  BOOKING ||--o{ NOTIFICATION : informs
  BOOKING ||--o{ EVENT : tracks
  BOOKING ||--o{ PENALTY_DECISION : reviews
  OPERATOR ||--o{ OCCUPANCY_SNAPSHOT : snapshots
  LOT ||--o{ TARIFF_VERSION : versions
  USER ||--o{ NOTIFICATION : receives
  USER ||--o{ PENALTY_DECISION : decides
  OPERATOR ||--o{ EVENT : scopes
  OPERATOR ||--o{ AUDIT_LOG : scopes
  USER ||--o{ AUDIT_LOG : acts
  OPERATOR ||--o{ VEHICLE : scopes
  OPERATOR ||--o{ BOOKING : scopes
  OPERATOR ||--o{ SLOT : scopes
  STATE ||--o{ CITY : contains
  CITY ||--o{ AREA : contains
  AREA ||--o{ VENUE : contains
  AREA o|--o{ LOT : locates
  VENUE o|--o{ LOT : locates
  USER ||--o{ LOCATION_SUGGESTION : submits
```

`STATE`, `CITY`, `AREA`, and `VENUE` are shared reference data and intentionally have no `operator_id`; a `LOCATION_SUGGESTION` is visible to its submitter and authorized managers only. Lots remain tenant-owned, with optional approved `area_id` and `venue_id` references. PostgreSQL `btree_gist` exclusion on `slot_id` and the half-open `tstzrange(starts_at, ends_at, '[)')` prevents overlaps while permitting back-to-back reservations. Active held, confirmed, and checked-in bookings participate in the exclusion.

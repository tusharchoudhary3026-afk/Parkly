# Software requirements and implementation plan

## Roles

Driver: manage own vehicles, discover lots, request and confirm bookings, view own booking history and QR pass. Attendant: check in/out and use manual fallback. Manager: configure lots, tariffs, and strategies; review flags. Auditor: read scoped audit data. Server checks role and ownership on every protected operation.

## Inputs and outputs

Inputs include credentials, vehicle type and optional plate, lot and time window, idempotency key, generic occupancy events, payment fallback reason, and reviewer action/reason. Outputs include eligible availability, exact tariff preview, booking and allocation explanation, check-in/out state, receipt, occupancy, forecasts labelled ESTIMATE, and append-only audit events.

## Functional requirements

See `CHECKLIST.md` for all 100 PDF feature numbers and current state. The core booking path uses timezone-aware UTC timestamps, half-open windows, idempotency keys, and PostgreSQL exclusion protection. No automatic penalties are allowed. Event ingestion is vendor-neutral and does not assert sensor accuracy.

## Failure handling and non-functional requirements

Validation errors use HTTP status codes and structured `detail.error` values for application errors. Conflicting allocations return `409 slot_unavailable`. Postgres is required for the exclusion constraint and concurrency guarantee. Auth uses Argon2 password hashes and JWT bearer tokens. Production TLS, at-rest encryption, rate limiting, retention, and legal compliance are provider or governance settings and remain unverified.

## Sprint plan

1. Foundation and bookings (Modules 1–2): schema, authentication, account/lot setup, booking concurrency, AT-01–03.
2. Allocation and entry/exit (Modules 3–4): strategies, explanations, QR, attendant and event API.
3. Pricing, billing, and test payment (Module 5).
4. Driver app, dashboard, audit, accessibility, exports (Modules 8–9).
5. Forecast/recommendations, flags/review, security, and AT-01–10 (Modules 6–7, 10).

The planned sprint work is implemented for the PDF's BUILD scope. The PostgreSQL acceptance suite, backend lint, frontend production build/typecheck, and local Compose startup have passed; see `TEST_REPORT.md`. These results validate the local demo, not production provider settings or independent accessibility, privacy, exception-label, and full tenant-security reviews.

## Location discovery extension (outside numbered PDF scope)

The driver can select State → City → Area → Venue, search approved location names, and submit a missing place for review. Defaults are Madhya Pradesh → Gwalior. Reference locations are shared data without `operator_id`; lots remain operator-scoped and only lots with inventory can be booked. User suggestions are private to the submitter until a manager approves or rejects with a reason; the decision is audited. This extension is implemented by migration `0005_location_hierarchy.py` and covered by AT-11–14. See `DATASET_CARD.md` for synthetic/reference-data limitations.

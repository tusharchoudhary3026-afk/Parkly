# PDF scope implementation status

This inventory tracks the PDF's BUILD scope. Source implementation and automated acceptance checks are complete for the included software-only demo. PDF PHASE 2, ROADMAP, and REMOVED items stay out of scope. Deployment assurance and independent human review remain external items listed below.

## Implemented and acceptance-tested

- **1–7:** operator lots, slot/vehicle types and eligibility attributes, plate normalization, account registration/login, consent timestamp, demo notification stub, grace/max-duration configuration.
- **11–18:** time-window availability, hold and explicit confirmation, PostgreSQL overlap protection/idempotency, park-now flow, no-show release/notice/no-fine, booking extension preview/confirmation, cancellation/refund rule reporting, overstay billing/notice/review flag.
- **22–28:** First-Fit, Best-Fit, weighted scoring, per-lot strategy, wasted-rank metric, eligibility guard, allocation explanation; shared by reservation allocation. AT-05 compares identical seeded demand in separate pools over several seeds.
- **32–38:** expiring signed QR pass, attendant check-in/out and assisted-booking APIs/UI, software occupancy, idempotent generic event ingestion and malformed-event logs, visibly SIMULATED event generation, manager occupancy override with reason and audit, driver My Slot directions.
- **42–47:** tariff calculator/snapshot, exact booking preview and explicit confirmation, checkout bill, HTML receipt, idempotent TEST MODE payments, attendant payment fallback and audit reason.
- **53–57:** occupancy snapshot job and synthetic history, pandas weekday/hour baseline, frozen last-week MAE evaluator, ESTIMATE-labelled forecast and rule-based ranked/alternative lot recommendations.
- **62–64:** configurable flags for repeated no-shows, long overstay, repeated cancellations, and overlapping plate bookings; 12 synthetic signal examples and 12 lookalikes; manager review queue, dismiss/warn/escalate actions, separately confirmed human decision and driver notice. No automatic fine path exists. Synthetic labels are not independently verified, so they do not establish precision/recall.
- **69–75:** staff occupancy view by lot/floor/zone/vehicle type, revenue/duration/weekday-hour/strategy KPI dashboard with date ranges and sample sizes, manager configuration and tariff revision API/UI/history, append-only audit trigger, operator-scoped bookings/revenue/audit CSV exports.
- **79–84:** responsive driver and attendant journey, date-aware lot availability, installable PWA shell and icon, booking history, receipt/payment/cancel controls, in-app notice list, visible TEST MODE/ESTIMATE/SYNTHETIC labels, accessible labels and focus states.
- **86:** email/SMS/WhatsApp delivery stub returns a visible SIMULATED result and records an audit event; it sends nothing externally.
- **89, 92–96:** role dependencies and tenant scoping on covered APIs, validation, process-local rate limits, consent record, Compose setup, database tenant keys.

## Still incomplete or deployment-dependent

- **62:** independent human review/double-labeling of exception examples and a defensible false-positive/false-negative report.
- **84:** automated accessibility audit and keyboard/screen-reader browser review.
- **90–91:** TLS and encryption at rest must be configured and verified at the hosting/database provider; local Compose cannot establish these claims.
- **93:** formal privacy review and staff-facing plate masking review.
- **96:** full route-by-route tenant-isolation security audit.

## Acceptance tests

AT-01–10 passed in the current-source PostgreSQL suite: 11 tests, with AT-04 and AT-10 covered by the same checkout test and AT-06 covering preview-to-checkout integration. Ruff passed, and the final frontend production build/typecheck passed. Manual browser testing is still needed for attendant, manager, and auditor journeys, especially a manager-reviewed penalty decision.

The latest fresh backend image rebuild did not complete: pip rejected a downloaded package because its SHA-256 differed from the expected hash. Hash checking was not bypassed. The complete current-source test suite did pass using the existing test image with the backend source mounted. A clean dependency-image rebuild and local `docker compose up --build` remain to be confirmed once package downloads are trustworthy.

Synthetic staff accounts created by the local seed are documented in `README.md`; never use those demo credentials in a deployed environment.

## Location discovery extension (EXTENSION; beyond numbered PDF scope)

The implementation adds shared state, city, area, and venue reference data; optional lot location assignments; hierarchical `/locations/*` discovery; and authenticated suggestions that stay private until a manager approves them with a reason. Approvals/rejections are audited. Pending suggestions never create bookable lots. AT-11–14 pass in `backend/tests/test_location_acceptance.py`; the combined suite passed **15 tests**. Migration `0005_location_hierarchy` passed against a fresh database and was applied to the existing local database; running the seed twice completed without duplicate rows.

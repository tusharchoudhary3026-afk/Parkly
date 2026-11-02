# API specification notes

Interactive OpenAPI: `/docs` (Swagger UI) and `/openapi.json` when the API is running.

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/auth/register` | Public | Register driver account |
| POST | `/auth/token` | Public | Obtain bearer JWT |
| GET | `/lots` | Authenticated | List scoped lots and hourly preview |
| GET | `/locations/states` | Authenticated | List active shared state/UT reference data |
| GET | `/locations/states/{state_id}/cities` | Authenticated | List active cities within a state |
| GET | `/locations/cities/{city_id}/areas` | Authenticated | List active areas within a city |
| GET | `/locations/areas/{area_id}/venues` | Authenticated | List approved venues within an area |
| GET | `/locations/search?q=...` | Authenticated | Search approved locations and return hierarchy context |
| POST | `/locations/suggestions` | Authenticated | Submit a private location suggestion; it is not bookable pending review |
| GET | `/locations/suggestions` | Authenticated / manager | Read own suggestions, or all pending suggestions as a manager |
| POST | `/locations/suggestions/{id}/review` | Manager | Approve or reject with a required reason and audit entry |
| GET | `/lots/{id}/forecast` | Authenticated | Weekday/hour baseline occupancy estimate with sample size |
| GET | `/recommendations` | Authenticated | Rank available and alternative lots; driver remains in control |
| POST | `/vehicles` | Driver | Register owned vehicle |
| POST | `/bookings` | Driver | Hold eligible slot with idempotency key |
| GET | `/bookings` | Driver | Own booking history |
| GET | `/bookings/{id}` | Driver/staff | Own booking or operator-scoped detail |
| POST | `/bookings/{id}/confirm` | Owning driver | Explicitly confirm active hold |
| POST | `/bookings/{id}/payments` | Owning driver | Record an idempotent simulated TEST MODE payment after explicit confirmation |
| POST | `/bookings/{id}/cancel` | Owning driver | Cancel a hold/booking and report configured refund percentage (no real refund) |
| POST | `/bookings/{id}/extend` | Owning driver | Preview or explicitly confirm a conflict-checked extension |
| GET | `/bookings/{id}/receipt` | Owning driver/staff | Render an HTML booking receipt |
| POST | `/bookings/{id}/qr` | Owning driver | Issue expiring signed pass |
| GET | `/bookings/{id}/directions` | Owning driver | Show assigned lot, floor, zone, and space code |
| GET | `/attendant/plate/{plate}/active-booking` | Attendant/manager | Find an active reservation by plate; returns masked plate |
| POST | `/attendant/bookings` | Attendant/manager | Create an assisted driver hold that still needs driver confirmation |
| GET | `/attendant/drivers/{email}/vehicles` | Attendant/manager | List this operator's driver vehicles with masked plates |
| POST | `/attendant/bookings/{id}/check-in` | Attendant/manager | Mark confirmed booking entered |
| POST | `/attendant/qr/check-in` | Attendant/manager | Verify signed, expiring QR pass and check in |
| POST | `/attendant/bookings/{id}/check-out` | Attendant/manager | Complete exit and record bill/fallback reason |
| POST | `/events` | Event key | Ingest idempotent generic occupancy event |
| POST | `/operator/simulated-events` | Manager | Emit a clearly SIMULATED occupancy event |
| POST | `/operator/slots/{id}/override` | Manager | Override occupancy with reason code and audit entry |
| GET | `/operator/occupancy` | Staff | Occupancy counts by lot |
| GET | `/operator/dashboard` | Manager/auditor | Revenue, duration, occupancy grid, strategy KPIs with sample sizes |
| GET | `/operator/export/bookings.csv` | Manager/auditor | Export operator-scoped booking records |
| GET | `/operator/export/revenue.csv` | Manager/auditor | Export completed booking revenue records |
| GET | `/operator/export/audit.csv` | Manager/auditor | Export operator-scoped audit entries |
| PUT | `/operator/lots/{id}/configuration` | Manager | Update configuration and append a numbered tariff/config revision |
| GET | `/operator/lots/{id}/configuration/history` | Manager/auditor | Read tariff/config revision history |
| POST | `/operator/lots` | Manager | Create a lot and its config |
| PUT | `/operator/lots/{id}/location` | Manager | Assign an approved venue/area and append a config revision |
| POST | `/operator/lots/{id}/slots` | Manager | Create 1–500 slots |
| POST | `/operator/jobs/release-expired-holds` | Manager | Idempotently release expired holds and create in-app notices |
| GET | `/notifications` | Authenticated user | Read only the caller's in-app notices |
| POST | `/notifications/{id}/read` | Owning user | Mark one of the caller's notices read |
| GET | `/operator/audit` | Manager/auditor | Read append-only audit entries |
| GET | `/operator/flags` | Manager/auditor | Read human review queue |
| POST | `/operator/flags/{id}/review` | Manager | Dismiss, warn, or escalate with reason |
| POST | `/operator/flags/{id}/penalty` | Manager | Record a separately confirmed, human-reviewed decision and notify the driver; never automatic |
| POST | `/notifications/mock/{booking_id}` | Owning driver | Record a visibly SIMULATED email/SMS/WhatsApp delivery attempt |

Application errors have `{ "detail": { "error": "code", "message": "human-readable message" } }`. FastAPI request validation errors use its standard structured 422 response. Event payload and authentication details are in `EVENT_API.md`.

`GET /lots` accepts optional `state_id`, `city_id`, `area_id`, and `venue_id` filters. The most specific supplied location filter is applied. State, city, area, and venue reference data are shared across operators; lots remain operator-scoped. This location picker and suggestion workflow is an extension beyond the numbered PDF requirements.

# PDF feature checklist

This is the final disposition of all 100 numbered PDF items. **BUILD** scope is implemented in the software-only demo. Acceptance tests verify the critical booking, allocation, billing, role, event, and forecast flows; they do not replace a manual review of every UI control. **MOCK** items are visibly simulated. PHASE 2, ROADMAP, and REMOVED items are excluded by the PDF.

| PDF classification | Feature numbers | Project disposition |
|---|---|---|
| BUILD | 1–5, 7 | Implemented: operator, lot and slot setup; vehicle eligibility; driver accounts, login, and consent; configurable booking limits. |
| MOCK | 6 | Implemented as a clearly labelled notification delivery simulation; no message is sent externally. |
| BUILD | 11–18 | Implemented: time-window search and holds, overlap/idempotency protection, park-now, no-show release, extension, cancellation, and overstay billing/review flow. |
| BUILD | 22–28 | Implemented: First-Fit, Best-Fit, scored allocation, eligibility checks, strategy selection, wasted-rank metrics, and explanations. |
| BUILD | 32–35, 37–38 | Implemented: expiring QR passes, attendant check-in/out, occupancy events and updates, manager override/audit, and driver directions. |
| MOCK | 36 | Implemented as visibly SIMULATED event generation. |
| BUILD | 42–45, 47 | Implemented: tariff preview/snapshot, checkout billing, receipt, and audited attendant fallback. |
| MOCK | 46 | Implemented as a TEST MODE payment simulator; no real payment is collected. |
| BUILD | 53–57 | Implemented: occupancy snapshots, weekday/hour baseline, frozen holdout evaluation, labelled estimates, lot recommendations, and alternatives. |
| BUILD | 62–64 | Implemented: configurable review signals, manager review actions, and separately confirmed human penalty decision. No automatic fines. Independent labels and real-world precision/recall are not established. |
| BUILD | 69–75 | Implemented: occupancy breakdown, date-filtered KPIs, configuration/tariff history, append-only audit, and bookings/revenue/audit CSV exports. |
| BUILD | 79–84 | Implemented: responsive driver and attendant experiences, PWA shell, booking history, notifications, payment/receipt controls, and accessibility labels/focus states. Manual accessibility review remains. |
| MOCK | 86 | Implemented as a labelled notification simulation with audit record; it does not send SMS/WhatsApp/email. |
| BUILD | 89, 92, 94–95 | Implemented: role/tenant checks, validation, rate limits, consent capture, and Docker Compose packaging. |
| BUILD | 90–91 | Deployment-dependent: TLS and database encryption at rest must be configured and verified with the hosting/database provider; local demo does not claim these controls. |
| BUILD | 93 | Consent and plate masking support are implemented. Formal privacy review and verification across all staff screens, logs, and exports remain. |
| BUILD | 96 | Tenant scoping is implemented and covered by role/ownership acceptance checks. A full route-by-route security audit remains. |
| PHASE 2 | 8–9, 19–20, 29–30, 48–49, 58–59, 65–66, 76–77, 85, 87, 97–99 | Excluded from this delivery per the PDF. |
| ROADMAP | 10, 21, 31, 39–41, 50–51, 60, 67, 78, 88, 100 | Excluded from this delivery per the PDF. |
| REMOVED | 52, 61, 68 | Excluded from this delivery per the PDF. |

## Extension beyond numbered PDF scope

| Classification | Work | Project disposition |
|---|---|---|
| EXTENSION | State → city → area → venue discovery; shared India/Gwalior starter reference data; private user suggestions with manager review; approved venue assignment to operator lots | Implemented and verified with migration `0005_location_hierarchy.py`, fresh and existing database upgrades, idempotent seeding, and AT-11–14. |

## Verification

- PostgreSQL acceptance suite: **15 passed, 1 upstream deprecation warning** across PDF flows and the location extension. See [TEST_REPORT.md](TEST_REPORT.md) for evidence.
- Backend lint: Ruff 0.17.3 reports **All checks passed**.
- Frontend: Next.js production build and TypeScript check **passed**.
- Local runtime: Compose services start; website on port 3000 and API docs on port 8000 returned HTTP 200.

These checks establish a local demo, not production readiness. Human accessibility/privacy/security reviews and provider-managed encryption checks listed above are still required before making those claims.

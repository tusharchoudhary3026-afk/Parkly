# Acceptance test report

This report records completed checks against the current source. Historical attempts are retained below where useful; the latest results are called out explicitly.

Non-acceptance static check: Python source compilation completed successfully with the bundled Python runtime. JSON parsing succeeded for the frontend package manifest, TypeScript config, and PWA manifest. These checks do not exercise application behavior.

| ID | Result | Evidence / notes |
|---|---|---|
| AT-01 | PASS | Final current-source Compose suite: PostgreSQL exclusion constraint allowed exactly one concurrent booking. |
| AT-02 | PASS | Final current-source Compose suite: back-to-back intervals succeeded and overlap was rejected. |
| AT-03 | PASS | Final current-source Compose suite: no-show release, in-app notice, no-fine event, and repeat-run idempotency. |
| AT-04 | PASS | Final current-source Compose suite: overstay checkout produced a bill and review notice. |
| AT-05 | PASS | Final current-source Compose suite: identical demand, independent pools, five seeds, eligibility assertions; printed sample sizes and rank spreads. |
| AT-06 | PASS | Final current-source Compose suite: free-minute/daily-cap boundaries and preview-to-on-time-checkout bill match passed. |
| AT-07 | PASS | Final current-source Compose suite: cross-driver denial, manager/auditor dashboard access, attendant occupancy access, and role denials passed. |
| AT-08 | PASS | Final current-source Compose suite: valid event, duplicate idempotency, malformed event response and log. |
| AT-09 | PASS | Final current-source Compose suite: frozen last-week baseline MAE 0.0287, n=504. |
| AT-10 | PASS | Final current-source Compose suite: unavailable gateway fallback audited; overstay notice created without automatic payment/fine. |

Latest Sprint 1 acceptance run (user-provided terminal output): **3 passed, 1 warning in 1.19s** using the mounted latest backend. AT-01 through AT-03 passed against the real PostgreSQL test service. The remaining warning is Passlib importing Python's deprecated `crypt` module. Pytest's asyncio fixture scope is now explicitly set to `function`; rerun to confirm only the Passlib warning remains. No result is claimed for backend type checking or later acceptance tests.

Earlier current-source acceptance run (Codex Docker output): **9 passed, 1 warning in 6.78s** against PostgreSQL after the migration and test-loop fixes. The warning is the upstream Passlib `crypt` deprecation.

Backend lint/type-check attempt: the initial install could not find mypy. A later Ruff-only install succeeded, and Ruff ran against the mounted backend. It reported **98 findings, auto-fixed 36, and left 62**. The remaining findings were mostly FastAPI dependency defaults and executable-bit warnings from the mounted Windows files, plus broad exception handling in two tests. I added narrow Ruff ignores for the FastAPI patterns and Windows file-mode false positives, and changed the tests to expect PostgreSQL exclusion violations specifically. Ruff must be rerun to verify these changes. Mypy remains unrun.

Ruff verification retry (user-provided terminal output): **not run**. Pip rejected the downloaded wheel because its SHA-256 did not match the expected hash. Hash verification was not bypassed; Ruff did not execute in this attempt. Use Ruff's official container image for verification instead.

Backend lint (user-provided terminal output): **PASS**. Ruff 0.17.3 official container reported `All checks passed!` on `app` and `tests` after the auto-fixes and remaining finding changes. Backend mypy type-check remains unrun.

Final Ruff run after current-source changes: **PASS**, `All checks passed!`.

Latest Compose image rebuild (user-provided terminal output): pytest was not reached because the API image build timed out during pip dependency installation. The Dockerfile now installs runtime requirements from a separate cached layer with longer timeout/retries, and the test service installs only pytest runtime tools. The following no-build, mounted-source run passed all three Sprint 1 tests.

Frontend TypeScript check (user-provided terminal output): **PASS**. `docker compose run --build --rm --no-deps web npm run typecheck` ran `tsc --noEmit` and returned to the prompt without diagnostics or errors.

Final frontend rebuild/typecheck after the current UI changes: **PASS**. Next.js production build completed and `tsc --noEmit` returned without errors.

Latest current-source PostgreSQL acceptance run: **11 passed, 1 warning in 3.89s**. AT-01 exercised ten concurrent API booking requests; AT-06 verified the preview and on-time checkout bill match; AT-07 checked driver, manager, attendant, and auditor access; AT-04/10 checked overstay billing and audited attendant cash fallback without an automatic fine. AT-05 offered 500 arrivals per strategy across five seeds, allocated 100 per run and reported 400 unavailable per run against the 100-slot fixture; eligible-only allocation assertions passed. AT-09 synthetic baseline MAE was 0.0287 with n=504. The warning is Passlib's upstream use of Python's deprecated `crypt` module.

Final confirmation run on 2026-11-01: **11 passed, 1 warning in 3.08s** against PostgreSQL using the current backend mounted into the test container. The warning is Passlib's upstream Python `crypt` deprecation. Ruff again reported `All checks passed!`; the frontend Docker production build and `tsc --noEmit` both passed. After Compose restart, `/` and `/docs` returned HTTP 200. The API runtime used the cached image with the current `backend` source mounted; the earlier clean runtime-image rebuild remains blocked by a package-wheel checksum mismatch, which was not bypassed.

Latest clean Ruff run used the official Ruff 0.17.3 container: **PASS** (`All checks passed!`). Latest frontend Docker rebuild, Next.js production build, and TypeScript check: **PASS**. A separate fresh backend image rebuild failed because the downloaded `pycparser` wheel's SHA-256 did not match the expected hash; no hash bypass was used. The acceptance tests passed with the already available test image and current backend mounted into it.

## Location discovery extension verification (2026-11-02)

- Combined PostgreSQL acceptance suite: **15 passed, 1 warning in 5.55s**. AT-11 through AT-14 cover seeded reference data/order/idempotence, location filters and operator scope, suggestion validation/privacy/rate limits/review audit, and authentication/role access. Existing PDF suite checks also passed. The only warning is Passlib's upstream use of Python's deprecated `crypt` module.
- Migration `0005_location_hierarchy`: **PASS** on a newly created empty PostgreSQL database; recorded head `0005_location_hierarchy` and created all five location tables. **PASS** on the existing local database.
- Demo seed: ran twice on the existing local database; both invocations completed and reported existing synthetic/reference data with no duplicate errors.
- Ruff 0.17.3: **PASS**, `All checks passed!` on `backend/app` and `backend/tests`.
- Frontend Docker build, Next.js production build, and TypeScript check: **PASS**.
- Earlier runtime screenshot evidence confirms the normal one-hour booking journey. A new manual browser review of the location picker and manager suggestion review has not been performed during this verification pass.
- Local runtime after rebuilding/recreating API and web: **PASS**, homepage `/` and API docs `/docs` both returned HTTP 200; Compose reported API, web, and database running/healthy.
- Browser automation reached the sign-in form, but its attempted sign-in request returned HTTP 422 before entering the location picker. No browser-level location-picker claim is made; the API acceptance tests cover the cascade data and permissions.

The fresh migration guard is required because the historical `0001_initial` migration calls `Base.metadata.create_all()`; it recognizes a complete schema created by that legacy behavior while creating the location schema for already-migrated databases. Historical migrations were not edited.

Manual booking demo review (user-provided browser screenshots): the first attempt was blocked because the date was in the past and the time inputs were incomplete. The form was updated to default to a future one-hour window and enforce valid ranges. The later screenshot shows a confirmed booking in history for SYNTHETIC Lot 1, with the one-hour ₹40 charge displayed. The core browser booking journey therefore completed manually; the intermediate price-preview screen was not captured as separate evidence.

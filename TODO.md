# Receipts Hub Flutter TODO
## Product scope — 20 August 2026
Receipts Hub ships as a **commercial, hosted, multi-tenant product** with real accounts and household join/approval. This supersedes the private-LAN / shared-PIN / single-household scope still described in [REQUIREMENTS.md](REQUIREMENTS.md) §1.3 and in the "Later hosted phase" section below: that phase is now the MVP. See [the MVP UI/UX plan](docs/mvp-ui-ux-plan.md) §1 for the authoritative first-run journey.

The pooled anonymous price index stays out of the MVP. Comparison argues only from the household's own confirmed receipts plus published quotes, each named.

## UI/UX status — 20 August 2026
Trust pass complete: **no fabricated data reaches any surface.** `lib/core/data/demo_data.dart` is deleted, its 36 references across five production screen files are gone, and `grep -r "DemoData" lib/` returns nothing. Sample data now lives in `test/fixtures/household_fixture.dart` and is injected by tests only.

Removed in that pass: the invented basket-savings headline on Home and Insights, the fabricated six-month collection chart, the hardcoded `[2860, 2730, 2490]` "live basket quote", demo-derived receipt line-item verdicts, the fake `TOTAL $148.72` receipt shown in place of the real photograph, the scripted processing timer that opened sample receipt `r-1006`, the `demo://` capture pages, the invented Account contribution counts, the "Simulate offline" control, and the first-run consent panel for a price index that will not exist at launch.

Real receipt photographs now render, authenticated, via `MobileApi.receiptImageUrl` + `imageHeaders` (previously written but never called), addressed as `/receipts/:id/photo` with per-page navigation.

Verified: `flutter analyze` clean, **47 Flutter tests pass** (was 30 passing / 14 failing after the fixtures were pulled out; the 6 Welcome goldens that had been failing since 20 August are fixed at the cause — a third CTA added without its sibling spacing, clipping the body — not re-baselined around).

Still outstanding before release: the route guard and session restore, host-side receipt delete, receipt detail wiring (line items, tax, balance, warnings, duplicate state and the missing-date outcome all still dropped by `toDomainReceipt`), hosted identity and households, live comparison evidence, HTTPS-only manifest, real release signing, and physical-device validation.

See [MVP release checklist](docs/mvp-release-checklist.md) for the exact handoff and backup procedure.

Build an Android-first Flutter client that reuses the existing FastAPI, SQLite,
OCR, background-job, and analytics service on the Windows host. Keep the current
web interface working while the native client is introduced.

## Frontend execution status — 15 August 2026

- [x] Create a runnable Android Flutter client in `apps/receipts_hub`.
- [x] Implement the handoff's twelve primary surfaces and six overlay states.
- [x] Add real Android camera/gallery acquisition and deterministic frontend
  processing, retry, manual-entry, and review flows.
- [x] Add 16 comparison-rule tests, 7 widget/accessibility tests, 8 golden tests,
  and an Android-emulator integration smoke test.
- [x] Produce a verified debug APK and frontend setup/architecture guides.
- [x] Connect the UI to live authentication, upload/OCR, receipt, shopping, and
  analytics APIs. Completed 16 August 2026; see the live integration status
  section below.

## Live integration status — 16 August 2026

The capture-to-ledger loop now runs end to end against a real host. Verified by
starting the FastAPI service on an isolated database and driving the exact call
sequence the Flutter client makes: a synthetic receipt photo was uploaded, read
by real OCR (`Coles`, `$19.00`, 3 line items), corrected, filed, and then
appeared in the ledger list, Home totals, and Insights. 21 of 21 checks passed.

Suites: **77 Python tests** and **44 Flutter tests** green, `flutter analyze`
clean. The two pre-existing Python failures are fixed — one was a stubbed API
auth path, the other a date-dependent test that broke when the month rolled over.

- [x] Extract Jinja logic into a shared service layer (`grocery_home/services.py`);
  HTML and JSON routes now call the same receipt, shopping, analytics and job code.
- [x] Replace the placeholder API auth with real bearer tokens reusing the
  existing signed-session format and PIN throttle. Rotating the PIN revokes
  issued tokens; the API reads only the `Authorization` header, so it needs no
  CSRF token while the web UI keeps its cookie + CSRF protection.
- [x] Fix a security bug found by the new tests: a failed PIN attempt rolled back
  its own throttle counter, so the API could be brute forced regardless of the
  configured limit.
- [x] Complete the `/api/v1` surface: bootstrap, receipts list/detail/correct,
  multipart uploads, five-stage job progress, retry, authenticated receipt
  images, shopping CRUD with optimistic concurrency, insights, settings.
- [x] Restore a versioned OpenAPI document at `/api/v1/openapi.json`
  (16 documented paths) with Swagger UI at `/api/v1/docs`.
- [x] Apply the merchant-and-total filing gate in shared code, so an undated
  receipt files and stays visible but is held out of dated analytics.
- [x] Back Collections with the existing line-item categories rather than a
  second taxonomy.
- [x] Wire the Flutter client to the live API: typed client with envelope
  unwrapping and typed failures, wire models, repository, Riverpod state,
  real connection/sign-in, upload-and-poll capture flow, session restore.
- [x] Add 21 Python API contract tests and 13 Flutter client tests.
- [ ] End-to-end test on a physical Android phone over the LAN.
- [ ] Verify the Docker stack (`docker compose config`, then `docker compose up`). Not attempted: Docker is
  not installed on this host; compose path quoting was hardened for the space-containing backend directory.
- [ ] Performance profile: receipt list, comparisons, OCR timing.

## Backend & Containerization Status — 17 August 2026

Delivered: Complete specification, Docker setup, containerization guide, API contract, Pydantic schemas, and /api/v1 routes.

- [x] Create [REQUIREMENTS.md](REQUIREMENTS.md): 400+ line spec covering frontend UX principles,
  backend scalability, containerization strategy, and MVP success criteria.
- [x] Define `/api/v1` contract in [docs/api.md](receipts%20-%20grocery%20home/docs/api.md):
  7 core resources (auth, receipts, uploads, shopping, insights, rivals, backup), error codes,
  response envelopes, pagination, authentication strategy.
- [x] Create [Dockerfile](receipts%20-%20grocery%20home/Dockerfile): Multi-stage build, slim base,
  non-root user, health checks, OCR support.
- [x] Create [docker-compose.yml](docker-compose.yml): Single-service MVP stack with persistent volumes
  and health checks; ready for LAN deployment.
- [x] Create [.dockerignore](receipts%20-%20grocery%20home/.dockerignore): Excludes build artifacts,
  venv, tests, secrets.
- [x] Write [docs/docker.md](docs/docker.md): 500+ line containerization guide covering MVP build/run,
  development workflow, LAN deployment, production tweaks, CI/CD, troubleshooting, backup/recovery.
- [x] Create `grocery_home/api_schemas.py`: 350+ lines of Pydantic models for all /api/v1 endpoints
  (35+ models covering auth, receipts, uploads, shopping, insights, collections, backups).
- [x] Create `grocery_home/api.py`: Core /api/v1 routes (health check, auth/pin, bootstrap, receipts CRUD,
  shopping list CRUD, insights, with request validation and error handling).
- [x] Integrate `/api/v1` router into `app.py` lifespan via `include_router()`.
- [x] Extract existing Jinja logic into shared service layer (reuse for both HTML and JSON).
- [x] Wire Flutter app to real `/api/v1` endpoints (replace mock data).
- [ ] Test Docker stack locally; verify `docker compose config` and `docker compose up` work end-to-end.
  Blocked: Docker is not installed on this host. Compose path quoting was hardened for the space-containing backend directory.
- [ ] End-to-end test on physical Android phone on LAN (capture → upload → OCR → confirm → view).
  The same flow is verified against a live host over HTTP; only the physical
  device leg is outstanding.
- [x] Regression test: 77 Python tests pass (was 56, including 21 new API
  contract tests). Both pre-existing failures fixed.
- [ ] Performance profile: Receipt list, comparisons, OCR timing.

## Source documents

- [Existing Grocery Home backend](receipts%20-%20grocery%20home/README.md)
- [Receipts Hub product description](receipts%20hub/app.md)
- [Flutter design handoff](receipts%20hub/Design%20System%20-%20flutter/design_handoff_receipts_hub_flutter/README.md)
- [Repository Flutter skill](.agents/skills/flutter-expert/SKILL.md)
- [general Flutter skill](.agents/skills)


The Flutter handoff's README and Dart files are authoritative for UI behaviour
and design tokens. Use the HTML prototype as a visual reference rather than as
production code.

## Working assumptions

- The first release targets Android phones on the trusted private LAN.
- FastAPI performs OCR, persistence, jobs, analytics, and backups.
- The MVP is single-household and online-only; Flutter does not get a local
  database or offline mutation queue yet.
- Store money as integer cents, exchange dates as ISO values, and derive totals,
  spreads, and verdicts rather than persisting duplicate calculations.
- Personal accounts, the anonymous shared price index, and remote access require
  a later hosted HTTPS backend.

## 0. Protect the starting point

- [ ] Establish working version-control history for the workspace. The backend has its own `.git`; the workspace root still needs a repository initialized and an initial source-only commit.
- [x] Exclude private receipts, runtime databases, secrets, `.venv`, build output,
  and generated caches from version control via the root `.gitignore` and backend ignore rules.
- [ ] Back up the active SQLite database and managed receipt directory. Runtime data was located at `%LOCALAPPDATA%\GroceryHome`; use the documented stop-copy-restore procedure before release.
- [x] Run and record the existing Python baseline using a writable test
  temporary directory. Baseline on 16 August 2026 was 54 passed / 2 failed;
  both failures are now fixed and the suite stands at 77 passed.

## 1. Scaffold the Flutter app

- [x] Create the runnable project at `apps/receipts_hub` with the installed stable
  Flutter SDK and Material 3.
- [x] Use feature-based modules with separate data, domain, presentation, and
  Riverpod provider layers.
- [x] Add Riverpod for state, GoRouter for navigation, Dio for HTTP, and secure
  storage for the session token.
- [x] Add `flutter analyze`, unit tests, widget tests, and coverage commands to the
  development workflow.

## 2. Promote the design handoff

- [x] Import `app_theme.dart`, `models.dart`, and `price_comparison.dart`; correct
  their package imports without changing the comparison rules.
- [x] Bundle the available Noto Sans TTF files and map the `Display` family to
  Noto Sans until a separate approved display font exists.
- [x] Implement reusable themed buttons, fields, cards, chips, marks, app bars,
  navigation, loading states, and error states.
- [x] Add golden tests for Sage, Clay, and Olive in light and dark modes at the
  390 x 844 reference viewport.

## 3. Add the mobile API

- [x] Add a versioned `/api/v1` JSON layer alongside the current Jinja routes.
- [x] Extract shared application services so HTML and JSON routes use the same
  receipt, shopping, analytics, and job logic.
- [x] Cover session/bootstrap, home, receipts, authenticated images, multipart
  uploads, job progress/retry, shopping, insights, and settings.
- [x] Restore a versioned OpenAPI document and define Pydantic response models,
  pagination, typed field errors, and stable status mappings.
- [x] Preserve the handoff's merchant-and-total filing gate; keep undated receipts
  out of dated analytics and price contribution until a date is supplied.

## 4. Connect and authenticate

- [x] Reuse the PIN throttle and signed session format through bearer-token API
  authentication while retaining cookie and CSRF authentication for the web UI.
- [x] Store the token in platform secure storage and handle `401`, `429`, token
  expiry, PIN rotation, and logout.
- [x] Build editable server URL and PIN setup with private-LAN guidance.
- [x] Wire the health check and recovery for a sleeping host or changed LAN
  address. Connection checks `/api/v1/health` first, so an unreachable host
  never reads as a wrong PIN.
- [x] Configure Android camera, gallery, network, and trusted-LAN cleartext access;
  never require public port forwarding.

## 5. Ship the capture-to-ledger vertical slice

- [x] Build first connection, Home, Receipts, Capture, Processing, receipt
  edit/view, and photo-zoom surfaces.
- [x] Support one-to-five ordered local photos, camera denial with gallery
  fallback, deterministic processing, retry, and manual-entry preview states.
- [x] Wire authenticated photo delivery, multipart upload progress, and real job
  stages from the host API, including retry/manual fallback that preserves one
  uploaded draft.
- [x] Implement uncertain-field markers, line-item editing, the balance strip,
  duplicate handling, filing validation, and outcome-specific toasts.
- [ ] Verify on a physical Android phone that a receipt can be captured, OCR'd,
  corrected, filed, and displayed from the existing household database.
  Verified over HTTP against a live host; the physical device leg remains.

## 6. Reach current feature parity

- [x] Build shopping-list entry, completion, deletion, and merchant-quote preview
  interactions against demo state.
- [x] Wire the shared shopping list, suggestions, and optimistic-concurrency
  handling to the host API. A stale edit returns `409 VERSION_CONFLICT` and the
  client reloads rather than overwriting another device's change.
- [x] Build spend trends, product history, basic insights, settings, and relevant
  loading/empty/error states.
- [x] Wire live analytics from the host (`/api/v1/insights`, `/api/v1/bootstrap`).
- [ ] Wire export and backup status from the host; both remain web-only.
- [x] Build Collections using the handoff's demo categories.
- [x] Define the relationship between Collections and the backend's existing
  line-item categories: a Collection is a view of a category, keyed by a
  normalised category identifier, so there is only one categorisation to keep
  correct.

## 7. Add the v5 comparison experience

- [ ] Introduce merchant metadata, pack sizes, provenance, freshness, confidence,
  price bands, outliers, and multi-retailer coverage in migrations and APIs.
- [x] Unit-test all seven comparison invariants, newest-first purchase history,
  confirmed-price coverage, mixed pack sizes, and missing basket quotes.
- [x] Build Item, Rivals, comparison verdict, and multi-merchant List preview
  surfaces using deterministic evidence fixtures.
- [ ] Replace preview evidence with real supported API data.
- [x] Keep weak or incomplete evidence visible without allowing it to drive a
  crown, range, verdict, or savings claim; label every quote with source and
  freshness.
- [ ] Replace illustrative retailer/stock fixtures with supported live sources
  before treating those previews as household facts.

## 8. Harden and release

- [x] Keep the Python regression and API contract suites green (77 passed).
- [x] Confirm the current frontend with clean `flutter analyze`, unit, widget,
  golden, integration, and coverage runs.
- [x] Add sampled Home-screen checks for 44 px icon targets and 12 px text, plus
  390 x 844 golden coverage.
- [ ] Complete broader semantics, contrast, reduced-motion, text-scaling,
  smaller-phone, and origin-aware-back checks on physical devices. See the [MVP UI/UX plan](docs/mvp-ui-ux-plan.md) for the release bar and device test script.
- [ ] Profile camera, charts, receipt lists, image rendering, and any optional
  on-device inference; remove jank and unnecessary Riverpod rebuilds before release.
- [x] Produce a debug APK plus Markdown setup and frontend architecture guides.
- [ ] Produce a signed release APK plus host upgrade, backup, and troubleshooting
  guides after live API integration. The MVP release checklist and backup procedure
  are documented; signing and a tested host upgrade remain outstanding.

## MVP completion gate

The MVP is complete when a fresh Android installation can connect to the private
host, authenticate, capture a multi-page receipt, observe real processing,
recover from failure, review and confirm the result, and see it reflected in
Home, Receipts, Insights, and the shopping list without regressing the web app.

## Later hosted phase

- [ ] Design personal accounts and household membership. See [multi-user architecture](docs/multi-user-architecture.md): managed OIDC identity, explicit memberships, stable household IDs, join requests with owner/admin approval, roles, invitations, and tenant-scoped services.
- [ ] Move shared services to HTTPS, Postgres, and private object storage. Production uses a configured service URL rather than asking users for an API IP; the target environment configuration and migration sequence are documented. Keep authoritative receipt inference server-side initially; optional phone ONNX inference is limited to capture guidance/drafts until benchmarked.
- [ ] Implement consent, anonymised price-report aggregation, moderation,
  regional partitioning, contribution history, and an offline outbox.

## Documentation convention

Use Markdown for plans, architecture decisions, API contracts, setup guides,
testing notes, release checklists, and progress reports. Update the relevant
`.md` file in the same change as the code or decision it documents.

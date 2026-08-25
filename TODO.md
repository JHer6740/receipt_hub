# Receipts Hub Flutter TODO
## Product scope — 20 August 2026
Receipts Hub ships as a **commercial, hosted, multi-tenant product** with real accounts and household join/approval. This supersedes the private-LAN / shared-PIN / single-household scope still described in [REQUIREMENTS.md](REQUIREMENTS.md) §1.3 and in the "Later hosted phase" section below: that phase is now the MVP. See [the MVP UI/UX plan](docs/mvp-ui-ux-plan.md) §1 for the authoritative first-run journey.

The pooled anonymous price index stays out of the MVP. Comparison argues only from the household's own confirmed receipts plus published quotes, each named.

## UI/UX status — 20 August 2026
Trust pass complete: **no fabricated data reaches any surface.** `lib/core/data/demo_data.dart` is deleted, its 36 references across five production screen files are gone, and `grep -r "DemoData" lib/` returns nothing. Sample data now lives in `test/fixtures/household_fixture.dart` and is injected by tests only.

Removed in that pass: the invented basket-savings headline on Home and Insights, the fabricated six-month collection chart, the hardcoded `[2860, 2730, 2490]` "live basket quote", demo-derived receipt line-item verdicts, the fake `TOTAL $148.72` receipt shown in place of the real photograph, the scripted processing timer that opened sample receipt `r-1006`, the `demo://` capture pages, the invented Account contribution counts, the "Simulate offline" control, and the first-run consent panel for a price index that will not exist at launch.

Real receipt photographs now render, authenticated, via `MobileApi.receiptImageUrl` + `imageHeaders` (previously written but never called), addressed as `/receipts/:id/photo` with per-page navigation.

Verified: `flutter analyze` clean, **48 Flutter tests pass** (was 30 passing / 14 failing after the fixtures were pulled out; the 6 Welcome goldens that had been failing since 20 August are fixed at the cause — a third CTA added without its sibling spacing, clipping the body — not re-baselined around), **79 backend tests pass** (was 77).

## Front door and household flow — 20 August 2026

The product no longer asks anyone for a host address or a PIN.

- [x] Service URL is build-time config (`lib/core/config/app_config.dart`, `--dart-define=RECEIPTS_HUB_API_BASE_URL`).
- [x] Real account front door at `/create-account` and `/sign-in` (`lib/features/auth/`), with validation, password reveal, and reset request. Welcome's two CTAs used to open the same host-and-PIN screen.
- [x] Household step at `/household` (`lib/features/household/household_choice_screen.dart`): create one, join one that exists, or open an existing membership. Auth lands here, not in the ledger — an account is not a ledger.
- [x] Joining is a request, not access: pending requests render as pending with a withdraw action, and `/household/join` calls the service instead of a 450 ms `Future.delayed`.
- [x] Capture refuses to open the camera without a household (`capture-needs-household`), because a receipt has to be filed into one.
- [x] Host-and-PIN moved to `/developer/connection`, reachable only from a debug build via `developerToolsProvider`; compiled out of release by `kDebugMode` and switchable off by `AppConfig.allowHostOverride`.
- [x] Removed the duplicate `/household/members` route registration.

## Section A — review reads server truth — 20 August 2026

- [x] `ReceiptViewScreen` and `ReceiptEditScreen` read full detail (`receiptWithDetailProvider`), not the list summary. Every live receipt used to render "No line items were read.", `$0.00` tax and no reference.
- [x] Domain models carry what the service sends: `LineItem.unit/needsReview/category`, `Receipt.dated/warnings/duplicateOfId/serverBalanceDifferenceCents/detailLoaded`.
- [x] The missing-date outcome is renderable at last — `toDomainReceipt` used to substitute today's date, so the interface could not tell a date was absent.
- [x] Per-line OCR uncertainty shown inline ("Check this line"), not in a `Tooltip` unreachable on touch.
- [x] Server warnings, duplicate notice and server-computed balance surfaced.
- [x] Date and time are pickers. Free text was parsed strictly with a silent fallback, so `15/08/2026` reverted the date with no message.
- [x] Money fields refuse unparseable input. `1.2.3` used to file `$0.00`.
- [x] Filing keeps each line's unit instead of rewriting every line to `each`.
- [x] `DELETE /api/v1/receipts/{id}` added; the client awaits it and rolls back on failure. "Receipt deleted" was false and the row returned on refresh.
- [x] Un-ticking a shopping item works — the client sent `status: completed` unconditionally.
- [x] Upload polling has a 3-minute budget and a cancel; it used to reschedule forever against an unreachable service.
- [x] `collection_id` is derived from line-item categories (`services.receipt_collection`). It was hardcoded `None`, so every live receipt was permanently "Unfiled" and Collections could never populate.
- [x] The edit draft is a `Notifier` that reads its seed once, so a background refresh no longer discards edits in progress.

## Section B — flow integrity — 21 August 2026

- [x] **Route guard and splash.** `createAppRouter` takes a `readState` callback and redirects: public routes stay open, a signed-out deep link goes to `/welcome`, a restoring session holds on `/splash`, and an account with no household resolves to `/household`. Passing no `readState` disables the guard, which is what widget tests want.
- [x] **Household approval works.** `lib/features/household/household_members_screen.dart` lists members and pending requests with the requester's email and the role they would get, and wires approve / decline / remove to the service. Reachable from Account's new **People** row. The old screen was orphaned and rendered a hardcoded `['Alex Morgan']`, so requests could not be approved by anyone.
- [x] **`lib/ui_ux_revision/` is gone.** The join screen moved to `lib/features/household/household_join_screen.dart` and lost its `Mvp` prefix; the mock admin screen was deleted.
- [x] **Unsaved-changes guard.** `PopScope` on the review screen asks before discarding a corrected receipt, on the back button and on system back. A blank manual draft is still discarded silently, which is right.
- [x] **Capture tray.** Thumbnails of each captured page, drag to reorder, per-page remove with a 44px target and an Undo that puts the page back where it was. Replaces a "Page N" chip whose only affordance was a sub-44px "Clear" that wiped everything with no undo.
- [x] **"Open settings" opens settings** via `permission_handler`, falling back to a camera retry if the platform refuses. Pinned to `permission_handler: 11.3.1` — 14.0.0 needs a newer Gradle Kotlin DSL than this project uses.
- [x] **Ledger at scale.** `receiptListProvider` pages from the service (30 at a time, infinite scroll), debounces search by 350 ms, filters by merchant and attention **server-side**, drops stale responses by generation, and shows one count instead of two that disagreed.
- [x] **Preferences persist.** `shared_preferences` is actually used now: colourway, dark mode, keep-photos and larger-text survive a restart. `largerText` scales text via `MediaQuery.textScaler`, clamped on top of the platform setting rather than replacing it — it used to be a switch that changed nothing.
- [x] **Offline is detected.** `connectivity_plus` is wired; losing the network shows the banner and regaining it refreshes. It only ever reports *definitely* offline, since an interface being up does not mean the service is reachable.
- [x] **One currency formatter.** `lib/core/format/money.dart` is the single implementation; `app_components` re-exports it and the pricing engine delegates to it. The two used to disagree above $1,000 on the same card.
- [x] **Shopping suggestions render.** The service's predictions were parsed into state and never shown. Accept and dismiss are wired, and the `409 VERSION_CONFLICT` message now appears in the list with a dismiss action instead of being swallowed.
- [x] **Shell safe-area fixed.** The offline banner moved above the navigation bar; at the top it rendered under the status bar and the inset was applied twice because every child screen nests its own `Scaffold` and `AppBar`.
- [x] **Nav highlighting fixed.** `AppShell` maps `/collections`, `/rivals` and `/items` to Insights and reports *no* selection on Account and household routes, instead of lighting Home for everything it did not recognise.
- [x] Verified: `flutter analyze` clean, **51 Flutter tests pass** (3 new: signed-out deep link, restoring session, and Account reaching approvals).

**Not verified on device.** The emulator's package service is wedged (`pm` returns `Broken pipe`) after running out of storage earlier, so section B has not been seen running. Cold boot or wipe the AVD before the next device check — this is separate from the physical-device run below.

## NEXT SESSION — section C: hosted identity, tenancy, comparison

The largest block, and it gates the front door: until auth lands, the account
flow cannot complete and the developer PIN path is the only way in. Security
surface, so it needs tests, not just routes. Design already written in
[multi-user architecture](docs/multi-user-architecture.md).

- [ ] `users`, `household_memberships`, `household_join_requests` tables plus migrations; roles `owner`/`admin`/`member`/`viewer`.
- [ ] Relax `CheckConstraint id = 1` on `households` — it is a singleton today.
- [ ] `POST /api/v1/auth/register | login | refresh | verify-email | reset-password`, and `DELETE /api/v1/auth/account`.
- [ ] `GET/POST /api/v1/households`, `POST|DELETE .../join-requests`, `GET .../members`, `POST .../join-requests/{id}/approve|decline`, `DELETE .../members/{id}`. The Flutter client already calls these shapes (`MobileApi.households`, `createHousehold`, `requestToJoinHousehold`, `cancelJoinRequest`).
- [ ] Scope **every** household read server-side. Add a cross-tenant denial test: a member of household A must not read household B.
- [ ] HTTPS + Postgres + private object storage for receipt images.
- [ ] Comparison evidence: merchant metadata, pack sizes, provenance, freshness, confidence, price bands, outliers, multi-retailer coverage. Then `GET /api/v1/rivals`, `/items/{product_key}`, `/shopping/quotes`. `PriceVerdict`, `MerchantComparison` and `RivalsResponse` already exist in `api_schemas.py` with no routes.
- [ ] Bind `comparisonBasketProvider` to those endpoints. The engine at `lib/core/pricing/price_comparison.dart` and its 16 invariant tests are correct — only the data source changes. The seven invariants must survive.

## NEXT SESSION — section D: commercial release

- [ ] Remove `android:usesCleartextTraffic="true"` from the manifest; HTTPS only.
- [ ] Real release signing — `android/app/build.gradle.kts` still uses `signingConfigs.getByName("debug")`. **Needs you:** you must own the keystore, and its passwords must not enter this public repo. Wire Gradle to read `key.properties`/env and keep it ignored.
- [ ] `https://` App Links, so email verification and password-reset links open the app. **Needs you:** a domain and a hosted `assetlinks.json`.
- [ ] Account deletion and data export (both absent; `grep -r "export\|csv\|Share" lib/` returns nothing). Depends on the section C endpoints.
- [ ] Privacy policy and terms links. **Needs you:** legal review — not text to invent.
- [ ] Crash and error reporting. **Needs you:** a provider account/DSN.
- [ ] Rate limiting and abuse protection on the new auth routes.
- [ ] Decide the launch market: currency is hard-locked to `en_AU` (`app_components.dart`, `prefixText: r'$ '` in three places) and every `DateFormat` call omits a locale, so dates render `en_US` regardless of device. Fine for an AU-only launch — state it rather than discover it.

## NEXT SESSION — open decisions

- [ ] **Merge Home and Insights?** They are ~70% the same screen — both render month total, delta, six-month chart and collections. Merging frees the nav slot Account currently lacks (Account is reachable only from Home's app-bar icon, and `AppShell._selectedIndex` returns 0 for `/account`, `/collections` and `/household`).
- [ ] **Should `analysis/` and `parsed/` be published?** Both are git-ignored right now because this repo is public and they are derived from 103 real receipts (752 line items, association rules, spend statistics). Un-ignore only deliberately.
- [ ] Still deferred by choice: `LedgerScaffold`, `PriceVerdict` and `ItemMark` from `.interface-design/system.md` are specified but absent; the four near-identical list rows (min-heights 76/72/64/56) are not consolidated; full localisation is out.

## Physical-device validation — the one thing left by design

- [ ] Run the capture-to-ledger script on a physical Android phone: install → sign in → choose household → multi-page capture → upload → OCR → retry/manual fallback → review → file → Home/Receipts/Insights/List. Then repeat with TalkBack and large text on a 320–360 dp device. The script in [the MVP UI/UX plan](docs/mvp-ui-ux-plan.md) has duplicated step numbers (steps 4–8 collide with 6–8) and needs renumbering.

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

# Receipts Hub: how the phone and the host fit together

This describes the live integration between the Flutter client in
`apps/receipts_hub` and the FastAPI host in `receipts - grocery home`. It covers
the shape of the seam, the decisions behind it, and how to run the whole thing
yourself.

## The shape

```
Flutter (Android)                         FastAPI host (Windows PC, private LAN)
─────────────────                         ──────────────────────────────────────
screens                                   Jinja routes  ──┐
   │ read state                                            ├── grocery_home/services.py
state/app_state.dart                      /api/v1 routes ──┘   (all household logic)
   │ calls                                        │
data/receipts_repository.dart                     ├── SQLite
   │ maps JSON → domain                           ├── OCR + background worker
network/mobile_api.dart  ──── HTTP ──────────────►└── analytics snapshots
network/api_models.dart
```

Two rules keep this honest:

1. **One implementation of household logic.** `grocery_home/services.py` holds
   everything that is not transport: money parsing, the filing gate, duplicate
   detection, the shopping list's concurrency rule, job progress, and the
   analytics refresh. The Jinja routes and the `/api/v1` routes are both thin
   layers over it, so the web UI and the phone can never drift apart in
   behaviour. A route parses its own encoding, calls a service, and renders.

2. **One place where JSON becomes domain objects.** Screens never touch
   `MobileApi`. `api_models.dart` mirrors the wire format closely enough that a
   contract change is a compile error, and `receipts_repository.dart` translates
   into the interface's own models.

## Authentication

The phone uses the **same signed session token** the browser gets in its cookie,
presented as `Authorization: Bearer <token>`.

- `POST /api/v1/auth/pin` exchanges the household PIN for a token, subject to
  the existing PIN throttle.
- The token is stored in Android's secure storage and restored on launch, so a
  paired phone does not ask for the PIN again.
- The API reads **only** the `Authorization` header and ignores cookies. Because
  browsers never attach that header automatically, the JSON API needs no CSRF
  token, while the web UI keeps its cookie + CSRF protection unchanged.
- Rotating the PIN bumps `Household.session_generation`, which revokes every
  issued token — phones included. There is no separate revocation table.

There is a subtlety worth knowing about if you touch the auth path: the PIN
throttle records a failed attempt **in the request's own transaction**. Raising
an HTTP error before committing rolls that record back, which silently disables
the throttle. `authenticate_with_pin` commits the counter before raising, and
`test_wrong_pin_is_rejected_then_throttled` exists to keep it that way.

## The filing gate

A receipt files on **merchant and total**. A date is not required.

An undated receipt is filed, visible, and editable — but `eligible_receipts` in
`analytics.py` excludes receipts without a purchase date, so it cannot move a
dated trend or contribute a price observation until someone supplies the date.
The API reports this as `dated: false` on every receipt payload, and the client
shows it without blocking the save.

This is one rule in one place: both the web review form and `PATCH
/api/v1/receipts/{id}` call `services.confirm_receipt`.

## Capture to ledger

```
capture screen                 POST /api/v1/uploads          (multipart, 1–5 photos)
   │ paths                        │
upload_flow.dart ────────────────►│ 201 { batch_id }
   │ polls every 900ms            │
   │                          GET /api/v1/uploads/{batch_id}
   │                              │ { status, detail_status, stages[5], can_retry }
   │ settles                      │
   └─► /receipts/{id}/edit ───► PATCH /api/v1/receipts/{id}   (corrections)
                                  │
                              refresh: bootstrap + receipts + shopping + insights
```

`CaptureFlowController` owns this. Points that matter in a house with a sleeping
PC and patchy wifi:

- The capture tray is cleared **only after** the photos reach the host, so a
  failed upload never loses the pictures.
- A host that briefly drops off the network does not fail the batch; polling
  keeps going and the screen recovers by itself.
- `POST /api/v1/uploads/{batch_id}/retry` re-reads the photos already on the
  host. Nobody is asked to photograph a receipt twice, and manual entry
  continues against the same uploaded draft.
- A duplicate opens the existing receipt for viewing rather than asking for a
  correction that would change nothing.

## Receipt photos are private

Images are served by `GET /api/v1/receipts/{id}/image?page=N`, which requires the
bearer token and streams from the managed receipt directory with
`Cache-Control: private, no-store`. Paths are resolved and checked against the
receipt root, so a crafted `storage_key` cannot escape it. There is no public or
guessable static path for household receipts.

## The shared list and concurrency

Two phones share one list. Every list item carries a `version`; edits send back
the version the device last read. A mismatch returns `409 VERSION_CONFLICT`, and
the client reloads instead of overwriting the other person's change. The Flutter
side applies edits optimistically for responsiveness and reconciles with the
host's copy when the write lands.

## Collections

A Collection is a **view of the backend's existing line-item categories**, keyed
by a normalised category identifier — not a second taxonomy. `bootstrap` and
`insights` return identical collection payloads, and a category rename stays
consistent everywhere because there is only one categorisation to keep correct.

## Error envelope

Every `/api/v1` response uses one shape:

```json
{ "success": true, "data": { }, "error": null,
  "timestamp": "...", "trace_id": "abc12345" }
```

Failures carry `error.code`, `error.message`, and `error.details`. When the host
rejects a specific input it names it as `details.field`, so the client can point
at the offending control. The client turns HTTP status into an `ApiFailureKind`
so the interface can respond differently to a wrong PIN, a throttled attempt, an
expired session, and an unreachable host — four situations that look identical if
you only check "did it fail".

`/api/v1/openapi.json` documents all 16 endpoints; Swagger UI is at
`/api/v1/docs`.

## Running it

Host:

```powershell
cd "receipts - grocery home"
.\.venv\Scripts\python.exe -m grocery_home.cli setup     # one time: sets the PIN
.\start_grocery_home.ps1                                  # serves on 0.0.0.0:8000
```

Phone (same trusted network):

```bash
cd apps/receipts_hub
flutter run
```

On first launch choose **I already have an account**, enter the host address
(`http://<host-lan-ip>:8000`) and the household PIN. The client checks
`/api/v1/health` before asking the host to authenticate, so a sleeping PC is
reported as a network problem rather than a wrong PIN.

The Android emulator reaches the host PC at `http://10.0.2.2:8000`, which is the
default in the address field.

## Tests

```bash
# Host: 77 tests, including 21 /api/v1 contract tests
cd "receipts - grocery home"
.\.venv\Scripts\python.exe -m pytest tests -q --basetemp=.pytest_tmp_mvp

# Client: 44 tests, including 13 API client tests against a fake transport
cd apps/receipts_hub
flutter analyze && flutter test
```

`tests/test_api_v1.py` covers the envelope, bearer auth and revocation, the
capture flow, the filing gate, and list concurrency.
`test/core/mobile_api_test.dart` covers the client half: token handling, the
four failure kinds, and that filing omits the date when a receipt has none.

## What is not wired yet

Stated plainly so nobody mistakes a preview for a household fact:

- **Comparison evidence** (Item, Rivals, basket quotes) still renders the
  handoff's deterministic fixtures. Real multi-retailer prices need merchant
  metadata, pack sizes, provenance and freshness in the schema first.
- **Export and backup** remain web-only; the client reports them as unavailable.
- **The shared price index** needs the later hosted phase, so
  `/api/v1/settings` returns `sharing_available: false` rather than implying a
  capability this LAN build does not have.
- **Docker** has not been verified on this machine (Docker is not installed).
- **A physical Android device** has not run the loop; it is verified against a
  live host over HTTP.

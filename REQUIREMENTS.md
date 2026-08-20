# Receipts Hub — Product & Technical Requirements

**Version 5 (MVP)** · August 2026  
**Frontend**: Flutter mobile-first (Android primary) + existing FastAPI web UI  
**Backend**: FastAPI, SQLite (MVP) → PostgreSQL (hosted phase)  
**Deployment**: Private LAN (MVP) → HTTPS hosted (later phase)

---

## 1. Product Requirements

### 1.1 Core User Loop

The app follows a fixed seven-step flow:

```
Capture → Read → Review → File → Aggregate → Compare → Act
```

1. **Capture**: Photograph receipt (single or multi-page)
2. **Read**: On-device OCR + merchant/date/total extraction
3. **Review**: User confirms or corrects; app flags uncertain fields
4. **File**: Auto-sorted into user collections; one-tap re-filing
5. **Aggregate**: Collection totals, monthly totals, six-month trends
6. **Compare**: Repurchased items gain price history and rival merchant set
7. **Act**: Switch merchant, add to list, or knowingly stay put

### 1.2 Key Principles

- **Chore ≤ 30 seconds**: Capture through filing must be fast enough to form a habit.
- **Never bare comparisons**: Every "cheapest" claim includes cost to drive (time + distance).
- **Competition earns loyalty**: App shows what each merchant wins on beyond price; no "enemies."
- **Personal + pooled**: User accounts are private; confirmed prices feed a shared index.
- **Grounded in reality**: Comparisons use actual purchase history, not searches or catalogues.

### 1.3 MVP Scope

**Revised 20 August 2026: Receipts Hub ships as a commercial, hosted, multi-tenant product.** The private-LAN, shared-PIN, single-household scope previously described here is withdrawn — what §1.4 called the "later hosted phase" is the MVP.

- Hosted service over HTTPS; multi-tenant, with server-side household scoping
- Personal accounts with real identity: registration, email verification, password reset, session restore and expiry
- Households with explicit membership: create, join by request, owner/admin approval, roles, revoke, and a switcher
- **Zero configuration.** A user never sees or enters a service address, and never sees a PIN
- Online-only; no offline mutation queue or local database for Flutter
- Comparison drawn from the household's own confirmed receipts plus published quotes, every price naming its source
- Commercial obligations in scope: account deletion, data export, privacy policy and terms, crash reporting, real release signing

### 1.4 Out of MVP scope

- **The pooled anonymous price index.** Hosting unblocks it technically, but the blockers in `receipts hub/app.md` §14 stand — no moderation of bad reports, no merchant dispute path, no regional partitioning — and pooling customers' price data raises consent questions that are not yet resolved. `/api/v1/settings` reports `sharing_available: false`, and the UI must stay silent about sharing until it is true
- Regional price partitioning and contribution history
- Offline outbox for mobile
- Push notifications and tablet layouts

---

## 2. Frontend Requirements — Intuitive Experience

### 2.1 Design Principles

- **Accessibility-first**: WCAG 2.1 AA minimum (contrast, keyboard, screen readers)
- **Fast and responsive**: < 100 ms interaction feedback on receipt list; < 500 ms OCR progress
- **Forgiving errors**: Clear recovery paths; no silent failures
- **Material Design 3**: Using Flutter Material library; consistent across light/dark/high-contrast
- **Reusable components**: Six production themes (Sage, Clay, Olive, etc.) in light/dark modes
- **Platform-native**: Android camera/gallery use native APIs; never web-view fallback

### 2.2 UI/UX Requirements

#### 2.2.1 Capture Experience
- Viewfinder with edge guides and real-time receipt detection overlay
- Shutter + torch toggles
- Multi-page support: each tap appends a page with running page count
- Camera denial gracefully falls back to gallery picker
- Progress feedback for each processing stage (upload, detect, read, extract, file)

#### 2.2.2 Review & Edit
- Inline editable fields for merchant, date, total, tax, line items
- Balance strip: reconciles line-item sum against stated total
- Uncertain-field badges: visual flags for low-confidence extractions
- Duplicate detection: warns on potential re-uploads; preserves one draft
- Save blocked until merchant + total supplied; footer names what's missing

#### 2.2.3 Ledger (Receipt History)
- Newest-first list with infinite scroll / pagination
- "Attention only" filter for receipts needing review
- Merchant search with debounced autocomplete
- Tap-to-view: receipt detail with price verdicts ("$0.30 over Coburg")
- Collection chip: one-tap reassign to another collection
- Swipe-to-delete confirmation overlay

#### 2.2.4 Comparisons
- **Rivals screen**: Merchant vs. merchant on user's basket
  - Spread (total price difference) prominently displayed
  - Bar chart: three merchants on identical basket
  - What each merchant "wins on" (e.g., open till 9 PM, butcher counter)
  - Hourly rate converter: "20 km away × $0.42/km ÷ 2-week frequency = +$0.12/item"
  
- **Item detail**: Single-product price history
  - Purchase date, merchant, price, pack size, confidence badge
  - Newest-first chronology
  - Retailer badges (Woolworths, Coles, Aldi/IGA)
  - No crown or verdict unless evidence is strong (≥ 3 confirmed prices)
  
- **Shopping List**:
  - Multi-merchant quotes side-by-side
  - Cheapest outlined
  - Coverage stat: "12/16 items priced" (from user's own receipts)
  - Add / check / delete with optimistic concurrency

#### 2.2.5 Insights
- Month total + six-month bar chart
- Collections ranked by spend delta
- Product trends: price direction (↑ ↓ ↔) by category
- Export option (CSV + charts)

#### 2.2.6 Account & Sharing
- First-run onboarding: explainer + sharing consent switch
- Sharing status: "Your prices help X other shoppers; they help you with Y quotes"
- Contribution counts: "Confirmed prices: 143" "Shared this month: 28"
- Settings: server URL, PIN change, logout, backup restore

### 2.3 Loading & Error States

- **Loading**: Skeleton loaders for receipt list; animated progress bars for processing
- **Empty states**: Contextual messages + action buttons (e.g., "No receipts yet → Capture one")
- **Errors**: User-facing messages ("Network unavailable"; "PIN expired") + Recovery buttons
- **Connectivity**: Health check on app resume; handle server sleep / LAN changes gracefully
- **Retry**: Automatic backoff for transient failures; manual retry for deterministic errors

### 2.4 Performance Targets

| Operation | Target | Notes |
|-----------|--------|-------|
| Receipt list load | < 2 s (100 items) | Pagination or virtualization |
| Capture to review | < 3 s | On-device OCR + upload |
| Comparison query | < 500 ms | 3 merchants, 20 items |
| App start | < 2 s | From cold |
| Golden tests | 100% pass | 390×844 viewport + light/dark/high-contrast |

---

## 3. Backend Requirements — Scalable & Maintainable

### 3.1 Architecture Principles

- **Layered & modular**: Data (DB/ORM), Domain (business logic), API (HTTP/JSON)
- **Async-first**: FastAPI async handlers; non-blocking I/O throughout
- **Stateless services**: Each server instance identical; no sticky sessions (for hosted phase)
- **Graceful degradation**: If price service is slow, still serve receipts; never block on external APIs
- **Audit & security**: Every mutation logged; PII redacted; session tokens signed and short-lived

### 3.2 API Contract (`/api/v1`)

#### 3.2.1 Core Resource Endpoints

```
POST   /api/v1/auth/pin           → { session_token, expires_at }
GET    /api/v1/bootstrap           → { household, totals, collections, settings }
GET    /api/v1/receipts            → [ Receipt ] (paginated, filters)
POST   /api/v1/receipts            → { id, upload_key, processing_stages }
GET    /api/v1/receipts/:id        → Receipt (full detail + line items + verdicts)
PATCH  /api/v1/receipts/:id        → Receipt (merchant, date, total, items editable)
GET    /api/v1/receipts/:id/image/:page → JPEG/PNG
DELETE /api/v1/receipts/:id        → { status: "deleted" }

POST   /api/v1/uploads/:key        → Multipart; { job_id, stage, progress }
GET    /api/v1/uploads/:key/status → { stage, progress, errors, result }

GET    /api/v1/shopping            → [ ShoppingItem ] (with live quotes)
POST   /api/v1/shopping            → { id, item, quantity, merchant }
PATCH  /api/v1/shopping/:id        → { status: "checked" | "unchecked" | "deleted" }

GET    /api/v1/insights            → { month_total, trends, product_history, anomalies }
GET    /api/v1/rivals/:item_id     → { item, merchants, spread, verdicts }

GET    /api/v1/settings            → { server_url, backup_status, sharing_consent }
PATCH  /api/v1/settings            → { sharing_consent, backup_schedule }
POST   /api/v1/backup              → { job_id, expires_at }
GET    /api/v1/backup/:job_id      → ZIP archive or { status: "in-progress" }

DELETE /api/v1/auth                → { status: "logged_out" }
```

#### 3.2.2 Response Envelopes & Errors

All responses MUST follow a predictable shape:

```json
{
  "success": true,
  "data": { ... },
  "timestamp": "2026-08-16T12:34:56Z",
  "trace_id": "abc123"
}
```

Or on error:

```json
{
  "success": false,
  "error": {
    "code": "RECEIPT_NOT_FOUND",
    "message": "Receipt with ID xyz not found",
    "details": { "receipt_id": "xyz" },
    "timestamp": "2026-08-16T12:34:56Z",
    "trace_id": "abc123"
  }
}
```

Defined error codes:
- `INVALID_PIN` (401)
- `UNAUTHORIZED` (401)
- `RECEIPT_NOT_FOUND` (404)
- `UPLOAD_IN_PROGRESS` (409)
- `VALIDATION_ERROR` (422) + field errors
- `RATE_LIMITED` (429)
- `SERVER_ERROR` (500)

#### 3.2.3 Pagination

```json
{
  "success": true,
  "data": {
    "items": [ ... ],
    "pagination": {
      "total": 143,
      "limit": 20,
      "offset": 0,
      "has_more": true
    }
  }
}
```

#### 3.2.4 Authentication & Session

- **Bearer token**: `Authorization: Bearer <session_token>`
- **Token format**: Signed JWT or opaque + server-side validation
- **Expiry**: 24 hours; client refreshes on 401
- **PIN throttle**: After 3 failures, block for 60 seconds; increase exponentially
- **Secure storage**: Flutter stores token in platform secure storage (Keychain/Keystore)

### 3.3 Data Model & Persistence

#### 3.3.1 Core Tables

| Table | Fields | Notes |
|-------|--------|-------|
| `households` | id, name, pin_hash, session_secret, settings, created, updated | Single-household MVP |
| `receipts` | id, household_id, merchant, date, total, tax, status, created, updated | ISO date; money as cents |
| `receipt_items` | id, receipt_id, product, qty, unit, price_per_unit, total, category, confidence | Line items; linked to product index |
| `upload_batches` | id, household_id, job_id, status, stage, progress, error_detail, expires_at | Tracks processing |
| `upload_files` | id, batch_id, file_path, checksum, page_count, metadata | One row per JPEG/page |
| `shopping_items` | id, household_id, product, quantity, unit, merchant_choice, status, created | Persistent list |
| `price_quotes` | id, product_id, household_id, merchant, price, date, pack_size, source | Historical prices |
| `analytics_snapshot` | id, household_id, snapshot_date, total_month, category_breakdown, json_data | Cached / indexed |
| `sessions` | token, household_id, created, expires | Short-lived |

#### 3.3.2 Derived / Cached

- `analytics_snapshot`: Rebuilt on each receipt confirm; exposes total, by-category spend, trends
- `product_identity`: Normalized product name + pack size + merchant; used for comparison
- `price_verdicts`: Computed on-demand from `price_quotes` + user's purchase history

### 3.4 Service Architecture

```
FastAPI Router (api/v1/)
├── Auth Service (PIN, session, token validation)
├── Receipt Service (CRUD, filing, balance validation)
├── Upload Service (multipart, job tracking, OCR queueing)
├── Shopping Service (CRUD, optimization, suggestions)
├── Comparison Service (product identity, price history, verdicts, rankings)
├── Analytics Service (aggregations, trends, anomalies)
├── Price Service (refresh, cache, merchant endpoints)
└── Backup Service (archive creation, restore, scheduling)

Database Layer
├── SQLAlchemy ORM (models, sessions, transactions)
├── Migrations (Alembic, versioned schema)
└── Connection pooling (async SQLAlchemy engine)

Background Jobs
├── Single worker (Uvicorn async task)
├── OCR queueing
├── Price refresh (weekly Woolworths API)
└── Analytics rebuild (on receipt confirm)
```

### 3.5 Scalability & Performance

#### 3.5.1 MVP (Single Server, Private LAN)

- **Concurrency**: 10–20 concurrent household connections
- **Database**: SQLite with WAL mode (write-ahead logging) for concurrent reads
- **Caching**: In-memory `analytics_snapshot` refreshed on mutate
- **Job queue**: Single async worker; OCR tasks queued; price refresh runs weekly off-hours
- **Image storage**: Filesystem (C:\receipts\ or similar); symlink backups

#### 3.5.2 Hosted Phase (PostgreSQL, Load Balanced)

- **Database**: PostgreSQL 15+ with read replicas
- **Async workers**: Separate Celery/RQ queue for OCR, price refresh, analytics
- **Cache layer**: Redis for `analytics_snapshot`, session tokens, rate-limit counters
- **Object storage**: S3 or equivalent for receipt images (lifecycle policies for deletion)
- **CDN**: CloudFront or equivalent for receipt image delivery
- **Monitoring**: Prometheus metrics, structured JSON logs, distributed tracing (OpenTelemetry)
- **Replicas**: 3 app servers behind load balancer; zero downtime deployments

#### 3.5.3 Performance Targets

| Operation | SLA | Notes |
|-----------|-----|-------|
| Receipt list (100 items) | p95 < 500 ms | DB index on (household_id, date DESC) |
| Receipt detail + verdicts | p95 < 1 s | Join with price_quotes; cache verdicts |
| Comparison query (3 × 20) | p95 < 500 ms | Redis cache verdicts by product_id + merchant |
| Upload + OCR | < 60 s | Async job; real-time progress via WebSocket or polling |
| Analytics rebuild | < 5 s | Denormalized snapshot; rebuild on receipt confirm only |

### 3.6 Security & Compliance

#### 3.6.1 Authentication & Authorization

- **PIN-based**: Throttled, bcrypt-hashed, server-side only
- **Session tokens**: Short-lived (24 h), signed, revoked on PIN change
- **CSRF**: Double-submit for web UI; None for API (stateless bearer token)
- **Secrets**: Session signing key stored in database after initial generation; never in code

#### 3.6.2 Data Privacy

- **PII redaction**: User names, emails (if added) never logged; log only household_id + action
- **Receipt images**: Encrypted at rest; access only via authenticated user + image_id
- **Price pooling**: Anonymized; no linked household identity
- **Retention**: Backup deletion configurable; receipts retained by user policy

#### 3.6.3 Network & Transport

- **MVP (Private LAN)**: Cleartext HTTP allowed; Flutter config disables cert pinning for 192.168.x.x
- **Hosted phase**: HTTPS only; TLS 1.3; HSTS headers; cert pinning on mobile

### 3.7 Testing & Quality

- **Unit tests**: 80%+ coverage on business logic (comparison rules, calculations)
- **Integration tests**: API contract tests; upload flow; OCR pipeline
- **End-to-end tests**: Flutter mobile app + FastAPI; Android emulator smoke test
- **Regression tests**: Preserved Python baseline from existing Grocery Home (55+ tests)
- **Static analysis**: `dart analyze`, `pylint`, `mypy`; `flutter test --coverage`

---

## 4. Containerization & Deployment

### 4.1 Docker Strategy

**MVP deployment:**
- Single `Dockerfile` for FastAPI backend
- `docker-compose.yml` orchestrating app + SQLite volume
- `.dockerignore` excluding `.venv`, `build/`, `node_modules`, `.git`
- Health check endpoint: `GET /health` → `{ status: "ok" }`

**Hosted deployment:**
- Separate images for app, background worker, migration runner
- PostgreSQL and Redis as separate services
- Kubernetes or Docker Swarm for orchestration
- Private registry for images; no hardcoded secrets

### 4.2 MVP Docker Compose Stack

```yaml
services:
  fastapi:
    build: ./receipts\ -\ grocery\ home
    ports:
      - "8000:8000"
    volumes:
      - ./receipts\ -\ grocery\ home/data:/app/data  # SQLite, images
    environment:
      - GROCERY_HOME_HOUSEHOLD_PIN=****  # Configured at setup
      - GROCERY_HOME_DATA_DIR=/app/data
    healthcheck:
      test: curl -f http://localhost:8000/health
      interval: 30s
      timeout: 10s
      retries: 3
```

### 4.3 Dockerfile Structure

```dockerfile
FROM python:3.12-slim
WORKDIR /app

# Dependencies
COPY receipts\ -\ grocery\ home/pyproject.toml .
RUN pip install --no-cache-dir -e .[ocr]

# Source
COPY receipts\ -\ grocery\ home/grocery_home ./grocery_home

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Run
CMD ["uvicorn", "grocery_home.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 4.4 Build & Deploy Process

1. **Local development**: `python -m uvicorn grocery_home.app:app --reload`
2. **Docker build**: `docker build -t receipts-hub-backend .`
3. **Run container**: `docker run -p 8000:8000 -v ./data:/app/data receipts-hub-backend`
4. **Compose stack**: `docker-compose up --build`
5. **CI/CD**: GitHub Actions (or similar) build + push to registry on merge
6. **Deployment**: Manual `docker pull` + `docker-compose up -d` (MVP) or Kubernetes deploy (hosted)

---

## 5. Success Criteria — MVP Gate

✓ **Frontend intuitive:**
- Capture to file: ≤ 30 seconds
- Golden tests: 100% pass on 390×844 + light/dark modes
- Flutter analyze: clean
- 31+ unit/widget/golden tests pass; integration test passes on Android emulator
- Accessibility: WCAG 2.1 AA on sampled screens (Home, Capture, Item detail)

✓ **Backend scalable:**
- `/api/v1` endpoints defined and documented (OpenAPI)
- PIN → session token flow works end-to-end
- Upload + OCR job tracking works with real-time progress
- Receipt CRUD, shopping list, and comparisons functional
- All 55 existing Python tests pass (no regression)
- Dockerfile builds and container runs locally
- `docker-compose up` brings full stack online with data persistence
- Health check endpoint responds 2xx under load

✓ **Integration:**
- Fresh Android installation connects to private host via LAN
- User authenticates with PIN
- Capture multi-page receipt → observe real OCR processing
- Correct receipt if needed → confirm → see in Home, Receipts, Insights, Shopping List
- No regression in web app (existing Jinja routes still work)

---

## 6. Documentation & Handoff

Each milestone updates relevant `.md` files in the same commit as code:

- **Backend**: [API contract](./receipts%20-%20grocery%20home/docs/api.md) · [Architecture](./receipts%20-%20grocery%20home/docs/architecture.md) · [Setup](./receipts%20-%20grocery%20home/README.md)
- **Frontend**: [Flutter README](./apps/receipts_hub/README.md) · [Architecture](./apps/receipts_hub/docs/frontend-architecture.md)
- **Deployment**: [Containerization guide](./docs/docker.md) · [LAN setup](./docs/lan-setup.md)
- **Testing**: [Test strategy](./docs/testing.md) · [Regression baseline](./receipts%20-%20grocery%20home/docs/tests.md)
- **Progress**: [TODO.md](./TODO.md) · [Verification record](./apps/receipts_hub/docs/verification.md)

---

## 7. Timeline Estimate

| Phase | Effort | Gate |
|-------|--------|------|
| **Backend `/api/v1` + auth** | 3 weeks | PIN → token, bootstrap, CRUD endpoints |
| **Upload + OCR integration** | 2 weeks | Multipart, job tracking, progress streaming |
| **Shopping + Insights + Comparison** | 3 weeks | Live data wired, verdicts computed |
| **Containerization + deployment** | 1 week | Docker compose stack, CI/CD, LAN docs |
| **Integration testing** | 2 weeks | End-to-end, physical phone test, regression suite |
| **Hardening & release** | 1 week | Performance profiling, semantic tests, release build |
| **Hosted migrations (later)** | 4 weeks | PostgreSQL, Redis, load balancer, Kubernetes |

---

## References

- [Product description](./receipts%20hub/app.md)
- [Flutter design handoff](./receipts%20hub/Design%20System%20-%20flutter/design_handoff_receipts_hub_flutter/README.md)
- [Existing Grocery Home README](./receipts%20-%20grocery%20home/README.md)
- [Flutter app README](./apps/receipts_hub/README.md)
- [TODO tracking](./TODO.md)

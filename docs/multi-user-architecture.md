# Multi-user production architecture
## Purpose
This document defines the migration from the local shared-household PIN to scalable account-based authentication. It is intended for the hosted phase, after private-LAN testing.

The core recommendation is:

> Use a managed identity provider for authentication, PostgreSQL for tenant-aware application data, and private object storage for receipt images. Keep authorization in FastAPI.

Recommended initial stack:

- FastAPI for API and application authorization
- Supabase Auth or Auth0 for identity, OAuth/OIDC, email verification, and recovery
- PostgreSQL for production persistence
- S3-compatible private object storage for receipt files
- Redis-backed workers for OCR and analytics jobs when traffic requires it
- Flutter using OAuth/OIDC with PKCE and secure token storage
- Optional Android ONNX runtime only for non-authoritative capture guidance in the first MVP
Do not implement password storage, password reset, OAuth, MFA, or email verification in the application itself.

## Target tenancy model
The current application has one implicit household protected by one shared PIN. Production should use explicit users, households, and memberships:

```text
User
 └── HouseholdMembership
      └── Household
           ├── Receipts
           ├── Receipt items
           ├── Shopping items
           ├── Analytics
           ├── Uploads
           └── Background jobs
```

A user may belong to multiple households. A household may contain multiple users. A household has a non-secret, human-readable `household_id` or join code that users can enter to request access. The ID identifies a household but is never authentication; access begins only after an owner or admin approves the request.

## Required database model
Create these tables:

```text
users
- id
- auth_provider_subject
- email
- display_name
- created_at
- disabled_at
households
- id
- name
- timezone
- currency
- created_by_user_id
- created_at
household_memberships
- id
- household_id
- user_id
- role              owner | admin | member | viewer
- status            invited | active | revoked
- created_at
- accepted_at
household_join_requests
- id
- household_id
- requester_user_id
- requested_role
- status            pending | approved | declined | cancelled
- message
- created_at
- reviewed_at
- reviewed_by_user_id
household_invitations
- id
- household_id
- invited_email
- role
- token_hash
- expires_at
- accepted_at
- invited_by_user_id
```

Add `household_id` to every household-owned table, including receipts, upload batches, upload files, receipt items, shopping items, analytics snapshots, price data, and background jobs. Add `created_by_user_id` where user-level audit or attribution is useful.

Use foreign keys, non-null constraints after migration, and indexes beginning with:

- `(household_id, created_at)`
- `(household_id, purchase_date)`
- `(household_id, status)`
- `(household_id, product_key)`

## Authentication and authorization
The identity provider proves who the user is. FastAPI decides what that user may access.

Flutter should support:

- Account creation
- Email verification
- Login and logout
- Password reset
- Google/Apple login where appropriate
- Refresh-token rotation
- Account deletion
- Secure token storage
Requests should use:

```http
Authorization: Bearer <access_token>
```

FastAPI must validate the JWT signature using the provider JWKS, then validate issuer, audience, expiry, and required claims. Resolve the provider subject to the local `users` record.

Never trust `user_id` or `household_id` supplied as an authorization claim by the client. The server must check active membership for the selected household on every request.

Use explicit permission helpers rather than scattered role checks:

```python
require_household_member(user, household_id)
require_household_role(user, household_id, {"owner", "admin"})
require_permission(user, household_id, "receipt:edit")
```

Initial roles:

| Role | Access |
|---|---|
| `owner` | Full access, including household deletion |
| `admin` | Manage members and household settings |
| `member` | Create and edit receipts, uploads, and shopping items |
| `viewer` | Read-only access |

## Household selection, join requests, and API shape
The application should use a configured HTTPS service URL in production. Normal users must never enter an API IP address. A host URL may exist only in a developer/diagnostic configuration path for local testing. The service should expose health and configuration status without revealing secrets.

After login, return the user's available households:

```http
GET /api/v1/me
GET /api/v1/me/households
```

Household-owned resources should be explicitly scoped:

```text
GET  /api/v1/households/{household_id}/receipts
POST /api/v1/households/{household_id}/uploads
GET  /api/v1/households/{household_id}/shopping
GET  /api/v1/households/{household_id}/insights
```

Add household and join-request endpoints:

```text
POST   /api/v1/households
GET    /api/v1/households/{household_id}
PATCH  /api/v1/households/{household_id}
GET    /api/v1/households/{household_id}/members
PATCH  /api/v1/households/{household_id}/members/{user_id}
DELETE /api/v1/households/{household_id}/members/{user_id}

POST   /api/v1/households/join-requests
GET    /api/v1/me/join-requests
DELETE /api/v1/me/join-requests/{request_id}
GET    /api/v1/households/{household_id}/join-requests
POST   /api/v1/households/{household_id}/join-requests/{request_id}/approve
POST   /api/v1/households/{household_id}/join-requests/{request_id}/decline
# Optional direct invitation flow
POST   /api/v1/households/{household_id}/invitations
```

A join request is created using the non-secret household ID or join code. The server must return only safe household summary information until approval. Owners/admins can approve or decline pending requests; approval creates an active membership. A request must be idempotent for the same user and household while a pending request exists.

Return `403` for an authenticated user without permission. Use `404` where exposing the existence of another tenant's resource would leak information.

Every service method should receive explicit tenant context:

```python
def list_receipts(session, *, household_id, user_id):
    require_permission(user_id, household_id, "receipt:view")
    return session.scalars(
        select(Receipt)
        .where(Receipt.household_id == household_id)
        .order_by(Receipt.purchase_date.desc())
    ).all()
```

Avoid unscoped methods such as `list_receipts(session)`.

## Inference placement and privacy
For the first hosted MVP, keep authoritative receipt inference on the server. The phone can perform image capture, rotation, compression, receipt-region detection, and quality checks locally. A small ONNX model on Android is reasonable for immediate framing guidance, but it should produce only a hint or draft.

Keep OCR text extraction, merchant/date/total/line-item parsing, duplicate detection, balance validation, filing gates, and analytics on the host. The server must revalidate all client-produced fields and never trust client confidence, totals, categories, or duplicate decisions.

A full on-device OCR model should be considered later only if measured requirements justify the added APK size, device variance, battery use, memory pressure, model-version management, and duplicate implementation. Evaluate it against a versioned receipt set for field accuracy, latency, memory, battery, thermal behaviour, and fallback rate. Retain server OCR as the authoritative fallback even if local OCR is introduced.

If local inference is added, maintain a versioned model manifest, feature flag, telemetry with privacy controls, and a clear UI distinction between `Draft` and `Confirmed by server`. Offline inference must never imply that a receipt has been saved or filed.

## Storage and background processing
Receipt images must be private objects, not predictable public files in the application directory. Store object metadata in PostgreSQL:

```text
receipt_files
- id
- household_id
- receipt_id
- object_key
- content_type
- content_length
- content_sha256
- created_by_user_id
```

FastAPI should verify membership and receipt ownership before streaming an image or creating a short-lived signed URL. Never put storage credentials in Flutter.

When OCR traffic increases, move processing to Redis-backed workers or a managed queue. Include `household_id`, `created_by_user_id`, `receipt_id`, and an idempotency key in every job. This prevents cross-tenant processing and duplicate uploads.

A single FastAPI instance, PostgreSQL, private object storage, and one worker is enough for the first hosted release. Do not introduce microservices until measured load requires them.

## Migration from the current PIN system
The current `Household` model is a singleton and contains `pin_hash` and `session_generation`; `PinAttempt` supports shared-PIN throttling. Treat this as a temporary local authentication mode.

Migration sequence:

1. Add `User`, `HouseholdMembership`, `HouseholdJoinRequest`, and `HouseholdInvitation`.
2. Add a stable, non-secret human-readable `household_id` or join code to each household.
3. Add nullable `household_id` columns to all household-owned tables.
3. Create one household representing the existing data.
4. Create the first owner user and membership.
5. Backfill all existing records to that household.
6. Add foreign keys and non-null constraints.
7. Remove the singleton check and shared-PIN columns.
8. Add idempotent join-request workflow, owner/admin approval, notifications, and audit events.
9. Replace PIN sessions with OIDC/JWT authentication.
10. Migrate SQLite data to PostgreSQL and receipt files to private object storage.
11. Keep a tested rollback and backup before each migration.

Do not maintain two authorization models permanently. A short migration period is acceptable, but production should have one source of truth.

## Environment configuration
The current local `.env.example` should remain local-only. For hosted production, use provider credentials, PostgreSQL, private storage, and a queue:

```dotenv
# Identity provider
AUTH_ISSUER_URL=https://your-project.supabase.co/auth/v1
AUTH_AUDIENCE=authenticated
AUTH_JWKS_URL=https://your-project.supabase.co/auth/v1/.well-known/jwks.json
# Database
DATABASE_URL=postgresql+psycopg://receipts_hub:change-me@db.example.com:5432/receipts_hub
# Private object storage
STORAGE_PROVIDER=s3
S3_ENDPOINT_URL=
S3_BUCKET=receipts-hub-private
S3_REGION=ap-southeast-2
S3_ACCESS_KEY_ID=
S3_SECRET_ACCESS_KEY=

# Application
GROCERY_HOME_HOST=0.0.0.0
GROCERY_HOME_PORT=8000
GROCERY_HOME_SECURE_COOKIES=true
GROCERY_HOME_ALLOWED_ORIGINS=https://app.example.com
GROCERY_HOME_ENVIRONMENT=production
# Background jobs
REDIS_URL=redis://redis:6379/0
```

In production, secrets must come from a secret manager rather than a committed `.env` file. If the API uses provider-signed JWTs exclusively, `GROCERY_HOME_SESSION_SECRET` is not required for API authentication. Keep an application session secret only if browser cookie sessions remain.

For local testing, the PIN may remain behind an explicit mode:

```dotenv
GROCERY_HOME_AUTH_MODE=local_pin
```

Hosted deployments must use:

```dotenv
GROCERY_HOME_AUTH_MODE=oidc
```

The service should fail fast in OIDC mode if issuer, audience, JWKS, PostgreSQL, or private-storage configuration is missing.

## Delivery phases
### Phase 1: Tenant boundaries
- Add tenant tables and `household_id` columns.
- Add request-scoped authenticated-user and household context.
- Add authorization helpers.
- Add cross-household access tests for every resource.
- Keep the PIN only for local development.

### Phase 2: Managed authentication
- Configure Supabase Auth or Auth0.
- Add Flutter signup, verification, login, reset, logout, and token refresh.
- Add JWT validation and `/me` endpoints.
- Add household creation, selection, stable household ID entry, join requests, owner/admin approval, notifications, and membership management.

### Phase 3: Production persistence
- Move to PostgreSQL and add Alembic migrations.
- Move receipt files to private object storage.
- Add tenant-aware indexes and backup/restore procedures.

### Phase 4: Scale processing
- Move OCR and analytics to queue-backed workers.
- Add idempotency for upload and confirmation requests.
- Add per-user and per-IP rate limits.
- Add audit logs for authentication, invitations, receipt changes, exports, and deletion.

### Phase 5: Production hardening
- Add MFA or passkeys.
- Add household export and deletion workflows.
- Encrypt backups.
- Add monitoring, error reporting, load tests, and migration rollback drills.
- Complete privacy, consent, and regional data-retention requirements.

## Decision summary
The important change is not simply replacing the PIN with email login. It is replacing implicit singleton ownership with explicit tenant ownership, then putting managed identity in front of it:

> Managed identity provider + explicit household membership + PostgreSQL tenant boundaries + private object storage.

This supports account creation, multiple users per household, multiple households per user, controlled roles, secure data isolation, and future growth without prematurely splitting the system into microservices.

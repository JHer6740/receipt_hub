# Receipts Hub `/api/v1` — API Specification

**Status**: MVP specification for backend implementation  
**Audience**: Backend developers, API consumers (Flutter app)  
**Generated**: 2026-08-16

---

## Overview

This document defines the JSON API contract for the Receipts Hub backend (`/api/v1`). The API uses:

- **Transport**: HTTP 1.1 + TLS (hosted phase) / Cleartext (MVP private LAN)
- **Auth**: Bearer token (JWT or opaque) + PIN-based signup
- **Serialization**: JSON; timestamps in ISO 8601 UTC
- **Money**: Integer cents (e.g., `5999` = $59.99)
- **Errors**: Structured error envelopes with machine-readable codes
- **Pagination**: Offset/limit model for list endpoints

---

## 1. Authentication & Session

### 1.1 POST /api/v1/auth/pin

**Request:**
```json
{
  "pin": "1234"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "session_token": "eyJhbGc...",
    "token_type": "Bearer",
    "expires_in": 86400,
    "expires_at": "2026-08-17T12:34:56Z"
  },
  "timestamp": "2026-08-16T12:34:56Z",
  "trace_id": "abc123"
}
```

**Response (401 Unauthorized):**
```json
{
  "success": false,
  "error": {
    "code": "INVALID_PIN",
    "message": "PIN is incorrect. 2 attempts remaining before throttle.",
    "details": {
      "attempts_remaining": 2,
      "throttle_seconds": 0
    },
    "timestamp": "2026-08-16T12:34:56Z",
    "trace_id": "abc123"
  }
}
```

**Response (429 Too Many Requests):**
```json
{
  "success": false,
  "error": {
    "code": "RATE_LIMITED",
    "message": "Too many failed PIN attempts. Try again in 60 seconds.",
    "details": {
      "retry_after_seconds": 60
    },
    "timestamp": "2026-08-16T12:34:56Z",
    "trace_id": "abc123"
  }
}
```

### 1.2 DELETE /api/v1/auth

Logout (invalidate session token).

**Request:**
```
Authorization: Bearer <session_token>
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "status": "logged_out"
  },
  "timestamp": "2026-08-16T12:34:56Z",
  "trace_id": "abc123"
}
```

---

## 2. Bootstrap & Settings

### 2.1 GET /api/v1/bootstrap

Fetch initial app state on launch (household info, current totals, collections, settings).

**Request:**
```
Authorization: Bearer <session_token>
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "household": {
      "name": "Smiths",
      "created_at": "2026-01-15T10:00:00Z"
    },
    "totals": {
      "month_total": 451230,
      "month_trend": [
        { "month": "2026-05", "total": 451230 },
        { "month": "2026-06", "total": 468900 },
        { "month": "2026-07", "total": 440100 },
        { "month": "2026-08", "total": 451230 }
      ]
    },
    "collections": [
      {
        "id": "col-001",
        "name": "Everyday",
        "icon": "🛒",
        "month_total": 382100,
        "month_delta_percent": 2.3
      },
      {
        "id": "col-002",
        "name": "Household",
        "icon": "🏠",
        "month_total": 69130,
        "month_delta_percent": -1.5
      }
    ],
    "settings": {
      "sharing_consent": true,
      "preferred_merchants": ["woolworths", "coles", "aldi"],
      "backup_enabled": false,
      "last_backup": null
    }
  },
  "timestamp": "2026-08-16T12:34:56Z",
  "trace_id": "abc123"
}
```

### 2.2 GET /api/v1/settings

Fetch full settings.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "household_name": "Smiths",
    "sharing_consent": true,
    "sharing_stats": {
      "contributed_prices": 143,
      "shared_this_month": 28,
      "merchants_supported": 3
    },
    "preferred_merchants": ["woolworths", "coles", "aldi"],
    "backup_enabled": false,
    "backup_schedule": "weekly",
    "last_backup_at": null,
    "last_backup_size_bytes": 0
  },
  "timestamp": "2026-08-16T12:34:56Z",
  "trace_id": "abc123"
}
```

### 2.3 PATCH /api/v1/settings

Update settings.

**Request:**
```json
{
  "sharing_consent": true,
  "backup_enabled": true,
  "backup_schedule": "weekly",
  "preferred_merchants": ["woolworths", "coles", "aldi"]
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "status": "updated",
    "sharing_consent": true,
    "backup_enabled": true
  },
  "timestamp": "2026-08-16T12:34:56Z",
  "trace_id": "abc123"
}
```

---

## 3. Receipts

### 3.1 GET /api/v1/receipts

List receipts (paginated, newest first).

**Query Parameters:**
- `limit` (int, default 20, max 100)
- `offset` (int, default 0)
- `attention_only` (bool, default false) — only receipts needing review
- `merchant` (string, optional) — filter by merchant
- `start_date` (ISO date, optional) — inclusive
- `end_date` (ISO date, optional) — inclusive

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "rcpt-001",
        "merchant": "Woolworths Coburg",
        "date": "2026-08-16",
        "total": 12345,
        "status": "confirmed",
        "collection_id": "col-001",
        "collection_name": "Everyday",
        "image_count": 2,
        "attention_required": false,
        "created_at": "2026-08-16T12:34:56Z"
      },
      {
        "id": "rcpt-002",
        "merchant": "Coles Carlton",
        "date": "2026-08-15",
        "total": 8765,
        "status": "needs_review",
        "collection_id": "col-001",
        "collection_name": "Everyday",
        "image_count": 1,
        "attention_required": true,
        "created_at": "2026-08-15T14:22:10Z"
      }
    ],
    "pagination": {
      "total": 143,
      "limit": 20,
      "offset": 0,
      "has_more": true
    }
  },
  "timestamp": "2026-08-16T12:34:56Z",
  "trace_id": "abc123"
}
```

### 3.2 POST /api/v1/receipts

Initiate a receipt upload.

**Request:**
```json
{
  "image_count": 2
}
```

**Response (201 Created):**
```json
{
  "success": true,
  "data": {
    "receipt_id": "rcpt-new-001",
    "upload_batch_id": "batch-new-001",
    "upload_urls": [
      {
        "page": 1,
        "upload_url": "https://...",
        "expires_at": "2026-08-16T13:34:56Z"
      },
      {
        "page": 2,
        "upload_url": "https://...",
        "expires_at": "2026-08-16T13:34:56Z"
      }
    ]
  },
  "timestamp": "2026-08-16T12:34:56Z",
  "trace_id": "abc123"
}
```

### 3.3 PUT /api/v1/receipts/:id/image/:page

Upload a receipt page image.

**Request:**
- Content-Type: `image/jpeg` or `image/png`
- Body: binary image data

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "receipt_id": "rcpt-new-001",
    "page": 1,
    "upload_status": "received",
    "processing_job_id": "job-001"
  },
  "timestamp": "2026-08-16T12:34:56Z",
  "trace_id": "abc123"
}
```

After all pages are uploaded, the client can poll `/api/v1/uploads/:batch_id/status` to track OCR progress.

### 3.4 GET /api/v1/receipts/:id

Fetch receipt detail with all line items and price verdicts.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "rcpt-001",
    "merchant": "Woolworths Coburg",
    "merchant_confidence": 0.95,
    "date": "2026-08-16",
    "date_confidence": 1.0,
    "total": 12345,
    "total_confidence": 1.0,
    "tax": 1234,
    "tax_confidence": 0.85,
    "status": "confirmed",
    "collection_id": "col-001",
    "collection_name": "Everyday",
    "image_count": 2,
    "image_urls": [
      { "page": 1, "url": "https://...", "expires_at": "2026-08-23T12:34:56Z" },
      { "page": 2, "url": "https://...", "expires_at": "2026-08-23T12:34:56Z" }
    ],
    "balance": {
      "line_items_sum": 11111,
      "stated_total": 12345,
      "difference": 1234,
      "reconciled": false
    },
    "line_items": [
      {
        "id": "item-001",
        "product": "Milk 2L",
        "quantity": 2,
        "unit": "unit",
        "unit_price": 2450,
        "total_price": 4900,
        "category": "dairy",
        "confidence": 0.98,
        "product_id": "prod-milk-2l-woolworths",
        "price_verdict": {
          "vs_other_merchants": "lowest",
          "savings": 150,
          "comparison_detail": "$2.45 vs Coles $2.60 vs Aldi $2.75"
        }
      },
      {
        "id": "item-002",
        "product": "Bread",
        "quantity": 1,
        "unit": "unit",
        "unit_price": 3200,
        "total_price": 3200,
        "category": "bakery",
        "confidence": 0.65,
        "product_id": null,
        "price_verdict": null
      }
    ],
    "created_at": "2026-08-16T12:34:56Z",
    "updated_at": "2026-08-16T12:35:10Z"
  },
  "timestamp": "2026-08-16T12:34:56Z",
  "trace_id": "abc123"
}
```

### 3.5 PATCH /api/v1/receipts/:id

Update receipt (merchant, date, total, tax, line items, collection).

**Request:**
```json
{
  "merchant": "Woolworths Coburg",
  "date": "2026-08-16",
  "total": 12345,
  "tax": 1234,
  "collection_id": "col-001",
  "line_items": [
    {
      "id": "item-001",
      "product": "Milk 2L",
      "quantity": 2,
      "unit": "unit",
      "unit_price": 2450,
      "total_price": 4900,
      "category": "dairy"
    }
  ]
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "rcpt-001",
    "status": "confirmed",
    "merchant": "Woolworths Coburg",
    "date": "2026-08-16",
    "total": 12345
  },
  "timestamp": "2026-08-16T12:34:56Z",
  "trace_id": "abc123"
}
```

### 3.6 DELETE /api/v1/receipts/:id

Delete receipt (soft delete; preserves audit trail).

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "receipt_id": "rcpt-001",
    "status": "deleted"
  },
  "timestamp": "2026-08-16T12:34:56Z",
  "trace_id": "abc123"
}
```

---

## 4. Upload Progress Tracking

### 4.1 GET /api/v1/uploads/:batch_id/status

Poll OCR job progress.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "batch_id": "batch-new-001",
    "receipt_id": "rcpt-new-001",
    "status": "in_progress",
    "current_stage": "reading",
    "stages": [
      { "name": "upload", "status": "complete", "progress": 100 },
      { "name": "detect", "status": "complete", "progress": 100 },
      { "name": "read", "status": "in_progress", "progress": 45 },
      { "name": "extract", "status": "pending", "progress": 0 },
      { "name": "file", "status": "pending", "progress": 0 }
    ],
    "errors": null
  },
  "timestamp": "2026-08-16T12:34:56Z",
  "trace_id": "abc123"
}
```

**Response on error (200 OK):**
```json
{
  "success": true,
  "data": {
    "batch_id": "batch-new-001",
    "receipt_id": "rcpt-new-001",
    "status": "failed",
    "current_stage": "read",
    "errors": {
      "detail": "OCR confidence too low (0.25 < 0.5 threshold)",
      "recovery": "Please use 'Enter manually' to add line items."
    }
  },
  "timestamp": "2026-08-16T12:34:56Z",
  "trace_id": "abc123"
}
```

---

## 5. Shopping List

### 5.1 GET /api/v1/shopping

Fetch shopping list with live merchant quotes.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "shop-001",
        "product": "Milk 2L",
        "quantity": 2,
        "unit": "unit",
        "status": "pending",
        "created_at": "2026-08-14T10:00:00Z",
        "quotes": [
          {
            "merchant": "Woolworths",
            "price_per_unit": 2450,
            "total_price": 4900,
            "pack_size": "2L",
            "confidence": "confirmed",
            "source": "your_receipts",
            "date": "2026-08-16"
          },
          {
            "merchant": "Coles",
            "price_per_unit": 2600,
            "total_price": 5200,
            "pack_size": "2L",
            "confidence": "confirmed",
            "source": "your_receipts",
            "date": "2026-08-10"
          }
        ],
        "cheapest": "Woolworths",
        "savings": 150,
        "coverage": 2
      }
    ],
    "summary": {
      "total_items": 1,
      "pending": 1,
      "checked": 0,
      "total_lowest_spend": 4900
    }
  },
  "timestamp": "2026-08-16T12:34:56Z",
  "trace_id": "abc123"
}
```

### 5.2 POST /api/v1/shopping

Add item to shopping list.

**Request:**
```json
{
  "product": "Milk 2L",
  "quantity": 2,
  "unit": "unit"
}
```

**Response (201 Created):**
```json
{
  "success": true,
  "data": {
    "id": "shop-001",
    "product": "Milk 2L",
    "quantity": 2,
    "status": "pending"
  },
  "timestamp": "2026-08-16T12:34:56Z",
  "trace_id": "abc123"
}
```

### 5.3 PATCH /api/v1/shopping/:id

Update item status (check/uncheck/delete).

**Request:**
```json
{
  "status": "checked"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "shop-001",
    "status": "checked"
  },
  "timestamp": "2026-08-16T12:34:56Z",
  "trace_id": "abc123"
}
```

---

## 6. Insights & Comparisons

### 6.1 GET /api/v1/insights

Fetch analytics summary (month total, trends, product history).

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "month_total": 451230,
    "month_trend": [
      { "month": "2026-05", "total": 451230 },
      { "month": "2026-06", "total": 468900 },
      { "month": "2026-07", "total": 440100 },
      { "month": "2026-08", "total": 451230 }
    ],
    "collections": [
      {
        "id": "col-001",
        "name": "Everyday",
        "month_total": 382100,
        "month_delta_percent": 2.3
      }
    ],
    "product_history": [
      {
        "product": "Milk 2L",
        "product_id": "prod-milk-2l-woolworths",
        "purchase_count": 8,
        "avg_price": 2450,
        "price_trend": "stable",
        "price_direction": "→",
        "category": "dairy"
      }
    ]
  },
  "timestamp": "2026-08-16T12:34:56Z",
  "trace_id": "abc123"
}
```

### 6.2 GET /api/v1/rivals/:product_id

Fetch price comparison for a single product across merchants.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "product": {
      "id": "prod-milk-2l-woolworths",
      "name": "Milk 2L",
      "category": "dairy"
    },
    "your_basket_spread": 150,
    "merchants": [
      {
        "merchant": "Woolworths",
        "price": 2450,
        "pack_size": "2L",
        "confidence": "confirmed",
        "purchase_date": "2026-08-16",
        "wins_on": ["open till 9pm", "butcher counter"],
        "distance_km": 2,
        "hourly_cost": 0.12
      },
      {
        "merchant": "Coles",
        "price": 2600,
        "pack_size": "2L",
        "confidence": "confirmed",
        "purchase_date": "2026-08-10",
        "wins_on": ["fuel discounts"],
        "distance_km": 5,
        "hourly_cost": 0.30
      }
    ],
    "verdict": "Woolworths is lowest"
  },
  "timestamp": "2026-08-16T12:34:56Z",
  "trace_id": "abc123"
}
```

---

## 7. Backup

### 7.1 POST /api/v1/backup

Trigger a backup export.

**Response (201 Created):**
```json
{
  "success": true,
  "data": {
    "job_id": "backup-001",
    "status": "in_progress",
    "expires_at": "2026-08-17T12:34:56Z"
  },
  "timestamp": "2026-08-16T12:34:56Z",
  "trace_id": "abc123"
}
```

### 7.2 GET /api/v1/backup/:job_id

Poll or fetch backup archive.

**Response (200 OK — in progress):**
```json
{
  "success": true,
  "data": {
    "job_id": "backup-001",
    "status": "in_progress",
    "progress_percent": 35
  },
  "timestamp": "2026-08-16T12:34:56Z",
  "trace_id": "abc123"
}
```

**Response (200 OK — complete, returns ZIP):**
```
Content-Type: application/zip
Content-Disposition: attachment; filename="receipts-hub-backup-2026-08-16.zip"
...binary...
```

---

## 8. Collections

### 8.1 GET /api/v1/collections

Fetch all collections.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "col-001",
        "name": "Everyday",
        "icon": "🛒",
        "month_total": 382100,
        "receipt_count": 47,
        "month_delta_percent": 2.3
      }
    ]
  },
  "timestamp": "2026-08-16T12:34:56Z",
  "trace_id": "abc123"
}
```

### 8.2 POST /api/v1/collections

Create a new collection.

**Request:**
```json
{
  "name": "Household",
  "icon": "🏠"
}
```

**Response (201 Created):**
```json
{
  "success": true,
  "data": {
    "id": "col-new-001",
    "name": "Household",
    "icon": "🏠"
  },
  "timestamp": "2026-08-16T12:34:56Z",
  "trace_id": "abc123"
}
```

---

## 9. Error Codes

| Code | HTTP | Meaning |
|------|------|---------|
| `INVALID_PIN` | 401 | PIN is incorrect |
| `UNAUTHORIZED` | 401 | Session token invalid, expired, or missing |
| `RECEIPT_NOT_FOUND` | 404 | Receipt ID does not exist |
| `UPLOAD_IN_PROGRESS` | 409 | Cannot delete/modify during upload |
| `VALIDATION_ERROR` | 422 | Field validation failed (details in `details.fields`) |
| `RATE_LIMITED` | 429 | PIN throttled or API rate limit exceeded |
| `SERVER_ERROR` | 500 | Unexpected server error |
| `SERVICE_UNAVAILABLE` | 503 | OCR or price service temporarily unavailable |

---

## 10. Implementation Notes

### Timestamps
- All timestamps are ISO 8601 UTC (e.g., `2026-08-16T12:34:56Z`)
- Client should expect and handle fractional seconds (`.000Z`)

### Money
- All monetary amounts are **integer cents**
- Example: `5999` = $59.99
- Never use floating-point for money

### Collections
- Auto-created collections: "Everyday", "Household"
- User can create additional collections
- Collection deletion cascades to receipts (soft delete)

### Concurrency
- Use optimistic locking on receipt updates: `ETag` header + `If-Match`
- Shopping list updates use last-write-wins for MVP

### Rate Limiting
- PIN: 3 attempts, then 60s throttle (exponential backoff per attempt after)
- API: 100 req/min per session token (higher for app, lower for web)

### CORS
- MVP: No CORS (private LAN, same-origin)
- Hosted: CORS headers for mobile + web

### Health Check
- **GET /health** → `{ status: "ok", timestamp: "..." }`
- Used by Docker healthcheck and load balancers

---

## 11. Schema Changes & Migrations

The backend should use Alembic (SQLAlchemy migration tool) to track schema versions:

```bash
alembic init alembic
alembic revision --autogenerate -m "Add initial schema"
alembic upgrade head
```

All schema changes are backward-compatible until a major version bump.

---

## 12. OpenAPI / Swagger

Generate OpenAPI spec automatically from FastAPI app:

```
GET /openapi.json  → OpenAPI 3.1 spec
GET /docs          → Swagger UI
GET /redoc         → ReDoc
```

These are available for development/testing; disabled in production.

---

## References

- Main requirements: [REQUIREMENTS.md](../REQUIREMENTS.md)
- Backend architecture: `docs/architecture.md` (TBD)
- Frontend integration guide: [Flutter README](../apps/receipts_hub/README.md)

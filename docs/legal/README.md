# Legal page drafts

Drafts of the five public pages required by
[the legal and privacy handover](../../receipt_hub_legal_privacy_handover_requirements.md)
§3.

| File | Requirement | Publish at |
|---|---|---|
| [privacy-policy.md](privacy-policy.md) | LEGAL-001 | `/privacy` |
| [terms-of-service.md](terms-of-service.md) | LEGAL-002 | `/terms` |
| [privacy-choices.md](privacy-choices.md) | LEGAL-003 | `/privacy/choices` |
| [account-deletion.md](account-deletion.md) | LEGAL-004 | `/account/delete` |
| [cookies.md](cookies.md) | LEGAL-005 | `/cookies` |

## Status

**These are drafts. Do not publish them without legal review.** The handover
document says the same thing in its own header, and it is right: a privacy
policy is a binding representation about behaviour, and getting it wrong is
worse than not having one.

Two rules were followed while writing them, and should be followed when
editing:

1. **Every statement describes what the system does today**, not what it is
   planned to do. Where a capability does not exist, the draft says so rather
   than describing it in the future tense as though it were live. The handover
   is explicit that "the public policy must match real retention behaviour"
   (§13) — the same applies to every other claim.
2. **Nothing in §31 "Open decisions" has been invented.** Those appear as
   `{{PLACEHOLDER}}` tokens. A page with an unresolved placeholder is not ready
   to publish.

## Placeholders to resolve

| Token | What it is | Where the answer comes from |
|---|---|---|
| `{{OPERATOR_LEGAL_NAME}}` | The legal entity operating Receipt Hub | §31 |
| `{{OPERATOR_TRADING_NAME}}` | Public-facing name, if different | §31 |
| `{{OPERATOR_ADDRESS}}` | Business address for privacy correspondence | §31 |
| `{{PRIVACY_EMAIL}}` | Privacy contact address | §31 |
| `{{SUPPORT_EMAIL}}` | General support address | §31 |
| `{{PUBLIC_DOMAIN}}` | Public domain the service runs on | §31 |
| `{{HOSTING_LOCATION}}` | Where the server physically is (city, country) | §31 |
| `{{BACKUP_RETENTION}}` | How long backups are kept before rotating out | §31, and must match reality |
| `{{LOG_RETENTION}}` | How long request/security logs are kept | §31, and must match reality |
| `{{GOVERNING_LAW_STATE}}` | Australian state or territory for governing law | §31 |
| `{{EFFECTIVE_DATE}}` | Date the published version takes effect | Set at publication |

## Facts these drafts rely on

Stated here so a reviewer can check them against the code rather than taking
them on trust. If any of these changes, the drafts change.

- **OCR runs on the server, locally.** `grocery_home/ocr.py` uses RapidOCR via
  ONNX Runtime on the host. Receipt images and their text are not sent to any
  OCR or AI provider. There is no LLM in the pipeline.
- **There is no analytics provider.** No SDK, no event collection.
- **There is no crash-reporting provider.** `lib/core/data/error_reporter.dart`
  keeps the last 20 errors in memory on the device and sends nothing.
- **There is no advertising SDK and no tracking.**
- **There is no email delivery.** Password reset accepts an address and reports
  success but sends nothing; email verification is not implemented. So there
  is no transactional or marketing email, and nothing to opt out of yet.
- **There are no paid plans and no payment provider.**
- **Receipt data is shared within a household.** This is the product's purpose:
  a household is a shared ledger, and approved members see each other's filed
  receipts. It is not shared between households, and there is no cross-user
  price pooling — `/api/v1/settings` reports `sharing_available: false`.
- **A Woolworths price-lookup capability exists** (`grocery_home/prices.py`)
  that would send product descriptions and SKUs — never images — to
  Woolworths. It is **not currently reachable from the API or web app**. The
  drafts therefore do not describe it as active. If it is switched on, the
  privacy policy must be updated before that ships.
- **Storage is a single self-hosted server**: SQLite for the database, the
  local filesystem for receipt images. Cloudflare proxies traffic and
  terminates TLS.
- **Authentication is first-party**: email and password, hashed with argon2id.
  No third-party identity provider.

## Known gaps against the handover

Things the drafts had to work around, and which are product work rather than
wording:

- **§GLOBAL-002 Correction** — receipt fields can be corrected in the app, but
  account details (name, email) cannot be edited. The drafts point people at
  the privacy email for that, which is honest but is not self-service.
- **§GLOBAL-005 Delete all receipt data** — receipts can be deleted one at a
  time; there is no "delete all my receipts but keep my account" action.
- **§DELETE-003 Backup lifecycle** — backups are currently a documented manual
  `tar` (see [deployment](../deployment.md) §7), so deletion does not
  propagate into them on a defined schedule. `{{BACKUP_RETENTION}}` cannot be
  answered honestly until that is automated.
- **§GLOBAL-009 Privacy request log** — no log exists.
- **§SEC-002 Encryption at rest** — the database and receipt images sit on the
  host filesystem. Whether that is encrypted depends on the disk, so the
  drafts describe it as depending on the host rather than claiming it.
- **§AI-005 Output accuracy** — covered in the Terms, and the app already
  marks low-confidence fields, so this one is genuinely met.

# Receipt Hub Legal, Privacy and App Store Handover

**Document type:** Product, legal and engineering requirements handover  
**Product:** Receipt Hub  
**Last reviewed:** 25 August 2026  
**Primary market:** Australia  
**Target distribution:** Web, Apple App Store, Google Play  
**Target international baseline:** Australia, EU/EEA, UK, United States, Canada, New Zealand, Singapore, Brazil, India, Japan and South Korea

> This document is an implementation handover and compliance checklist. It is not a substitute for final legal review before commercial launch.

---

## 1. Purpose

Receipt Hub stores and processes receipts for users.

A receipt may reveal personal information such as:

- Name.
- Email address.
- Merchant.
- Store location.
- Purchase date and time.
- Purchased items.
- Purchase amount.
- Loyalty identifiers.
- Payment method fragments.
- Delivery or billing address.
- Tax information.
- Notes added by the user.
- Images, PDFs and other uploaded documents.
- OCR and AI-derived receipt data.

Receipt Hub should therefore be designed as a privacy-sensitive application, even if the Australian business initially falls below the Privacy Act small-business threshold.

The implementation goal is to use one strong global privacy baseline rather than maintaining weak and strong versions by country.

---

# 2. Product assumptions

This handover assumes Receipt Hub includes or may include:

- User accounts.
- Email authentication.
- Receipt image or PDF uploads.
- Camera capture.
- OCR.
- AI-assisted extraction or categorisation.
- Cloud storage.
- Search.
- Receipt history.
- Data export.
- Analytics.
- Crash reporting.
- Transactional email.
- Optional marketing email.
- Free and paid plans.
- Apple App Store distribution.
- Google Play distribution.
- Web access.

If the final product differs, update the policies, app-store declarations and data inventory.

---

# 3. Required public legal pages

Receipt Hub should publish the following pages.

## LEGAL-001. Privacy Policy

**Priority:** Required.

Create:

`/privacy`

The policy must be publicly accessible without login.

It should state:

- Legal/business identity operating Receipt Hub.
- Contact details.
- Privacy contact email.
- Categories of personal information collected.
- Sources of information.
- How information is collected.
- Purposes for collection and processing.
- Lawful bases where applicable.
- How information is stored.
- Categories of service providers and subprocessors.
- Whether data is disclosed overseas.
- Countries or regions where overseas recipients are likely located where required.
- Retention periods or retention criteria.
- User access rights.
- User correction rights.
- User deletion rights.
- Data portability/export rights where applicable.
- Consent withdrawal process where applicable.
- Objection and restriction rights where applicable.
- Complaint process.
- Marketing preferences.
- Cookie/tracking practices.
- Security practices at an appropriate high level.
- Account deletion procedure.
- Data deletion procedure.
- How legally required retention is handled.
- Policy update process.
- Effective date and last updated date.

### Australian requirement

If Receipt Hub is an APP entity under the Privacy Act 1988, APP 1 requires a clearly expressed and up-to-date privacy policy.

Most Australian small businesses with annual turnover of A$3 million or less are not covered by the Privacy Act, but exceptions exist.

Receipt Hub should still implement an APP-style Privacy Policy from launch because:

- Apple requires a Privacy Policy.
- Google Play requires a Privacy Policy.
- International privacy regimes may apply.
- Receipt data is privacy-sensitive.
- The business may later cross the Australian threshold.

---

## LEGAL-002. Terms of Service

**Priority:** Required for product risk management.

Create:

`/terms`

Terms should cover:

- Who operates Receipt Hub.
- Acceptance of terms.
- Eligibility to use the service.
- Account responsibilities.
- Authentication and account security.
- User responsibility for uploaded content.
- User ownership of receipt content.
- Limited licence granted to Receipt Hub to process uploaded content solely to provide and operate the service.
- Prohibited use.
- OCR limitations.
- AI extraction limitations.
- No guarantee extracted receipt data is error-free.
- User responsibility to verify important extracted information.
- Storage and availability limitations.
- Backups.
- Service changes.
- Account suspension and termination.
- User-requested account deletion.
- Paid plans.
- Billing.
- Renewal.
- Cancellation.
- Refund handling.
- Intellectual property.
- Third-party services.
- Liability limitations only to the extent permitted by law.
- Australian Consumer Law protections.
- Governing law.
- Dispute/contact process.
- Changes to the Terms.
- Effective date.

### Important

Do not attempt to contract out of Australian Consumer Law guarantees or other rights that cannot legally be excluded.

---

## LEGAL-003. Privacy Choices

**Priority:** Required product capability, public page recommended.

Create:

`/privacy/choices`

Provide clear actions for:

- Access my data.
- Export my data.
- Correct my data.
- Delete individual receipts.
- Delete all receipt data.
- Delete my account.
- Withdraw consent where applicable.
- Marketing preferences.
- Contact privacy support.

This page can also be used as Apple's optional Privacy Choices URL.

---

## LEGAL-004. Account Deletion Web Page

**Priority:** Required for Google Play account-based apps.

Create:

`/account/delete`

It must:

- Clearly identify Receipt Hub.
- Explain how account deletion is requested.
- Explain which data is deleted.
- Explain any data retained and why.
- Explain the retention period where data must remain.
- Avoid requiring the mobile app to begin the web deletion process.

Google Play requires an external web resource for deletion when the app allows account creation.

---

## LEGAL-005. Cookie and Tracking Notice

**Priority:** Conditional.

Required when the web product uses cookies or similar technologies that require consent in the user's jurisdiction.

Implement:

`/cookies`

and a cookie/privacy preference interface where applicable.

Avoid non-essential advertising tracking unless the business has a strong reason to add it.

---

# 4. In-app legal navigation

Add:

`Settings > Legal`

with links to:

- Privacy Policy.
- Terms of Service.
- Privacy Choices.
- Delete Account.
- Cookie Settings where relevant.
- Contact Support.

Add:

`Settings > Privacy`

with:

- Export My Data.
- Delete Receipt.
- Delete All Receipt Data.
- Delete Account.
- Marketing Preferences.
- Analytics Preferences where applicable.

---

# 5. Apple App Store requirements

## APPLE-001. Privacy Policy URL

**Required.**

A publicly accessible Privacy Policy URL must be supplied in App Store Connect.

The Privacy Policy must also be easily accessible inside the app.

---

## APPLE-002. App Privacy declarations

**Required.**

Complete the App Privacy section in App Store Connect.

Declare all relevant data collected by:

- Receipt Hub.
- Analytics SDKs.
- Crash-reporting SDKs.
- Authentication SDKs.
- Cloud services where applicable.
- Advertising SDKs if ever introduced.
- Any other embedded third-party SDK.

Declarations must remain consistent with actual behaviour and the Privacy Policy.

Potential Apple data categories for Receipt Hub include:

- Email address.
- Name, if collected.
- Photos or videos for receipt images.
- Other user content.
- Purchase history.
- Device identifiers.
- Product interaction.
- Diagnostics.
- Coarse location if derived or stored.
- Payment information only if Receipt Hub itself receives it.

Do not declare payment information collected by an external payment processor if Receipt Hub never receives it, subject to Apple's current definitions.

---

## APPLE-003. Account deletion

**Required when the app supports account creation.**

Users must be able to initiate full account deletion inside the app.

Recommended location:

`Settings > Account > Delete Account`

Deletion must cover:

- Account record.
- Associated receipt files.
- OCR data.
- Derived receipt data.
- User settings.
- Stored identifiers.
- Other personal data not legally required to be retained.

Temporary deactivation alone is insufficient.

---

## APPLE-004. Privacy manifests

Audit all Apple-platform dependencies for required privacy manifests and required-reason API declarations.

Maintain:

`PrivacyInfo.xcprivacy`

where applicable.

Review third-party SDK changes before each release.

---

## APPLE-005. Tracking

Do not track users across apps or websites for advertising.

If tracking is ever introduced, review Apple's AppTrackingTransparency requirements before release.

Preferred Receipt Hub position:

**No cross-app advertising tracking.**

---

# 6. Google Play requirements

## GOOGLE-001. Privacy Policy

**Required.**

Provide a valid Privacy Policy:

- In the Play Console listing.
- Inside the app.
- On a public webpage.

The policy must match actual app behaviour.

---

## GOOGLE-002. Data Safety form

**Required.**

Complete the Google Play Data Safety form.

Declare:

- Data collected.
- Data shared.
- Purposes.
- Security practices.
- Account deletion availability.
- Relevant data retention behaviour.

Audit third-party SDK behaviour before answering.

---

## GOOGLE-003. In-app account deletion

**Required when users create accounts.**

Provide a readily discoverable in-app path.

Recommended:

`Settings > Account > Delete Account`

---

## GOOGLE-004. External deletion resource

**Required when users create accounts.**

Provide a public web URL entered into Play Console.

Recommended:

`https://<domain>/account/delete`

---

## GOOGLE-005. Secure transmission

Use modern encrypted transport for personal and sensitive user data.

Requirement:

- HTTPS/TLS for all production API traffic.
- No plaintext receipt transfer.
- No production secrets embedded in client applications.

---

# 7. Australian privacy requirements

## AU-001. Privacy Act assessment

Before launch and annually thereafter, determine whether the operating entity is covered by the Privacy Act 1988.

The small-business threshold is generally A$3 million annual turnover or less, but exceptions apply.

Record the assessment internally.

Even if exempt, Receipt Hub should voluntarily follow the core APP privacy controls in this document.

---

## AU-002. APP-style Privacy Policy

Implement regardless of initial small-business status.

At minimum document:

- Types of personal information.
- Collection methods.
- Uses.
- Disclosures.
- Access.
- Correction.
- Complaints.
- Overseas disclosures.

---

## AU-003. Collection notice

A Privacy Policy alone is not always a substitute for a notice at collection.

Add short contextual notices when information is collected.

Examples:

### Registration

"Receipt Hub uses your email address to create and secure your account. See our Privacy Policy."

### Receipt upload

"Your receipt is uploaded and processed to store it and extract receipt information. See our Privacy Policy."

### Optional analytics

Explain the collection before enabling analytics where consent is required.

---

## AU-004. Data minimisation

Collect only information required for Receipt Hub functionality.

Do not collect:

- Contacts.
- Precise GPS location.
- Advertising IDs.
- Unrelated profile attributes.

unless a documented product requirement exists.

---

## AU-005. Data security

Take reasonable technical and organisational steps to protect personal information.

See the security requirements in this document.

---

## AU-006. Destruction and de-identification

When personal information is no longer required and no legal retention requirement applies:

- Delete it, or
- Properly de-identify it.

---

## AU-007. Overseas disclosures

Maintain an up-to-date register of overseas service providers.

The Privacy Policy should describe likely overseas disclosures where required.

Examples:

- Cloud hosting.
- OCR.
- AI processing.
- Transactional email.
- Analytics.
- Error monitoring.
- Customer support.

---

## AU-008. Data breach response

Create and maintain a written incident response procedure.

If Receipt Hub becomes subject to the Australian Notifiable Data Breaches scheme, assess suspected eligible data breaches and follow OAIC notification requirements.

Internal target:

- Security incident triage immediately.
- Privacy/security owner notified promptly.
- Formal breach assessment started promptly.
- Use a 72-hour internal escalation target for serious incidents because several international regimes use short notification windows.

---

## AU-009. Marketing

Separate transactional communications from marketing.

Marketing systems must support:

- Consent or other lawful basis where required.
- Sender identification.
- Unsubscribe.
- Suppression list.
- No resubscription without valid basis.

---

# 8. Global privacy baseline

Receipt Hub should provide the following privacy controls to all users, regardless of country.

This simplifies implementation and reduces regional branching.

## GLOBAL-001. Access

Users must have a process to obtain the personal data Receipt Hub holds about them.

---

## GLOBAL-002. Correction

Users must be able to correct inaccurate account information and extracted receipt data where practical.

---

## GLOBAL-003. Export

Provide an export function.

Recommended format:

```text
receipt-hub-export.zip
├── account.json
├── receipts.csv
├── receipts.json
└── receipt-files/
    ├── ...
```

Export should include:

- Account data.
- Receipt metadata.
- OCR/extracted data.
- User-added data.
- Original receipt files where appropriate.

---

## GLOBAL-004. Receipt deletion

A user must be able to delete an individual receipt.

Deletion must remove or schedule deletion of:

- Original image/PDF.
- OCR text.
- Extracted fields.
- Search indexes.
- Generated thumbnails.
- Derived receipt data.
- Links to that receipt in active application databases.

Backups should expire under a documented backup-retention schedule.

---

## GLOBAL-005. Delete all receipt data

Provide an option to delete all receipts without requiring account deletion.

---

## GLOBAL-006. Account deletion

Account deletion should delete all account-associated personal data except records retained for a documented legal reason.

Do not silently retain user receipts after account deletion.

---

## GLOBAL-007. Consent withdrawal

Where processing relies on consent, provide a method to withdraw it.

Withdrawal should be as easy as giving consent.

---

## GLOBAL-008. Marketing opt-out

Provide an unsubscribe mechanism and account-level marketing preference.

---

## GLOBAL-009. Privacy request log

Maintain an internal record of privacy requests.

Store:

- Request ID.
- Request type.
- Received date.
- Jurisdiction if known.
- Verification state.
- Status.
- Completion date.
- Data retained due to legal requirements.
- Internal notes.

Do not keep unnecessary copies of identity documents used for verification.

---

# 9. International coverage

## European Union / EEA

Design for GDPR.

Requirements include:

- Determine lawful basis for each processing purpose.
- Transparent privacy notice.
- Data minimisation.
- Purpose limitation.
- Retention limits.
- Access rights.
- Rectification.
- Erasure.
- Restriction where applicable.
- Portability where applicable.
- Objection where applicable.
- Consent withdrawal where consent is used.
- Appropriate international transfer mechanism where required.
- Processor agreements.
- Security safeguards.
- Data breach process.
- Data Protection Impact Assessment when processing creates high risk.

Receipt Hub should avoid relying on consent for core functionality when another lawful basis is more appropriate.

---

## United Kingdom

Use the same core architecture as the EU baseline.

Also assess:

- UK GDPR.
- Data Protection Act 2018.
- PECR for cookies and electronic marketing.
- UK international transfer requirements.

---

## United States

There is no single general federal privacy law equivalent to GDPR covering every consumer app.

Implement the global user-rights model and separately assess state privacy-law thresholds.

At minimum prepare for:

- Access/know.
- Correction.
- Deletion.
- Data portability.
- Opt-out rights where sale, sharing or targeted advertising occurs.
- Sensitive-data restrictions where applicable.

Preferred Receipt Hub policy:

- Do not sell personal data.
- Do not sell receipt history.
- Do not share receipt history for cross-context behavioural advertising.
- Do not use receipt contents to build advertising profiles.

This significantly reduces state privacy complexity.

---

## Canada

Design to PIPEDA-style fair information principles and applicable provincial laws.

Maintain:

- Identified purposes.
- Appropriate consent.
- Limited collection.
- Limited use/disclosure/retention.
- Accuracy.
- Safeguards.
- Openness.
- Access.
- Complaint process.

---

## New Zealand

Design to the Privacy Act 2020 and its 13 privacy principles.

Pay particular attention to:

- Necessity/minimisation.
- Collection notices.
- Storage/security.
- Access.
- Correction.
- Overseas disclosure.

---

## Singapore

Design to PDPA obligations, including:

- Accountability.
- Notification of purposes.
- Consent where required.
- Purpose limitation.
- Accuracy.
- Protection.
- Retention limitation.
- Transfer limitation.
- Access/correction.
- Breach response.

---

## Brazil

Design to LGPD principles.

Provide:

- Transparent processing purposes.
- Rights request process.
- Access.
- Correction.
- Deletion where applicable.
- Portability where applicable.
- Consent withdrawal where applicable.
- Sharing information.
- Security practices.
- Appropriate international-transfer handling.

---

## India

Track implementation of India's Digital Personal Data Protection Act and associated rules.

The product architecture should already support:

- Clear privacy notices.
- Consent where required.
- Withdrawal.
- User rights.
- Security safeguards.
- Retention/deletion.
- Processor/vendor governance.

Recheck the current commencement status and rules before India launch.

---

## Japan

Assess APPI before launch.

Architecture should support:

- Purpose specification.
- Appropriate collection/use.
- Security.
- Vendor oversight.
- Access/correction/deletion procedures where applicable.
- Cross-border transfer disclosures/controls where applicable.

---

## South Korea

Treat South Korea as a higher-review market.

Before launch, conduct a specific PIPA review covering:

- Privacy notice.
- Consent flows.
- Cross-border transfers.
- User rights.
- Destruction/retention.
- Vendor processing.
- Security.
- Breach requirements.
- Local representative requirements where applicable.

---

# 10. Receipt data architecture

Separate core data classes.

Recommended logical structure:

```text
users
receipt_originals
receipt_extracted_data
receipt_items
receipt_tags
user_preferences
consents
privacy_requests
audit_events
subscriptions
```

## DATA-001. Account data

Examples:

- User ID.
- Email.
- Name if required.
- Authentication provider.
- Account creation date.
- Account state.
- Subscription state.

Do not store plaintext passwords.

---

## DATA-002. Receipt original

Store original uploads separately from extracted structured data.

Metadata:

- Receipt ID.
- Owner user ID.
- Storage object key.
- MIME type.
- File size.
- Hash.
- Created date.
- Deletion state.

---

## DATA-003. Extracted receipt data

Examples:

- Merchant.
- Store.
- Date.
- Time.
- Currency.
- Subtotal.
- Tax.
- Total.
- Item lines.
- Category.
- Loyalty identifier if extracted.
- Payment method fragment if extracted.

Only retain fields required by the product.

---

## DATA-004. Derived and AI data

Track which values were:

- OCR extracted.
- AI inferred.
- User corrected.
- Manually entered.

Recommended metadata:

```json
{
  "source": "ocr|ai|user",
  "model_or_processor": "provider/version",
  "confidence": 0.97,
  "processed_at": "ISO-8601"
}
```

Avoid storing model prompts containing more receipt data than necessary.

---

# 11. AI and OCR requirements

## AI-001. Purpose limitation

Receipt content should be sent to OCR/AI providers only for functions requested by the user or required to provide Receipt Hub.

---

## AI-002. No training by default

Preferred requirement:

**Receipt Hub must not use private user receipt content to train general-purpose AI models by default.**

Where a third-party AI/OCR provider is used, choose configurations and contractual terms that prevent training on Receipt Hub content where available.

---

## AI-003. Provider disclosure

List AI/OCR providers in the internal vendor register.

The Privacy Policy should describe the provider category and processing purpose.

---

## AI-004. Minimise payloads

Only transmit the data needed for the requested operation.

If an operation only requires OCR text, do not send the original image again.

---

## AI-005. Output accuracy

Treat OCR and AI extraction as fallible.

UI should let users correct extracted values.

Do not present extracted financial information as guaranteed accurate.

---

# 12. Vendor and subprocessor register

Maintain a private internal register.

Recommended fields:

| Field | Purpose |
|---|---|
| Provider | Vendor name |
| Service | Hosting, OCR, email, analytics, etc. |
| Data processed | Exact categories |
| Purpose | Why the vendor receives it |
| Hosting regions | Countries/regions |
| Retention | Vendor retention |
| Training use | Whether content is used for model training |
| DPA | Data Processing Agreement status |
| SCC/transfer mechanism | If required |
| Security review | Date/status |
| Delete support | Whether deletion propagates |
| Contract owner | Internal owner |
| Last reviewed | Review date |

Review before introducing any SDK or external API.

---

# 13. Data retention schedule

Receipt Hub needs an explicit retention schedule.

Initial proposed policy:

| Data | Proposed retention |
|---|---|
| Active account data | While account remains active |
| Active receipt originals | Until user deletes them or account is deleted |
| Extracted receipt data | Same lifecycle as associated receipt |
| Deleted receipt active copies | Delete promptly through deletion queue |
| Deleted account active data | Delete promptly through deletion workflow |
| Backups | Expire on defined rotating backup schedule |
| Security logs | Defined limited security period |
| Transaction records required by law | Required legal period only |
| Marketing suppression record | Retain minimum data required to honour opt-out |
| Privacy request audit record | Limited compliance retention period |

Do not publish exact periods until engineering confirms what the system supports.

The public policy must match real retention behaviour.

---

# 14. Deletion architecture

## DELETE-001. Soft-delete is not final deletion

A database flag such as:

`deleted = true`

is only an intermediate state.

A deletion worker must remove data from active systems.

---

## DELETE-002. Cascading deletion

Account deletion workflow should locate associated:

- Account record.
- Receipt objects.
- Receipt database rows.
- Receipt items.
- OCR text.
- AI-derived data.
- Tags.
- Search indexes.
- Thumbnails.
- Cached copies.
- Personalisation data.
- Analytics identifiers where deletion APIs support it.
- Customer-support data where appropriate.
- Third-party processor data where required.

---

## DELETE-003. Backup lifecycle

Do not attempt unsafe live deletion from immutable backups.

Instead:

- Remove data from active systems.
- Prevent restoration into production without deletion replay.
- Let backup copies expire under the documented backup schedule.
- Document this behaviour in internal policy and, where appropriate, public retention language.

---

## DELETE-004. Deletion status

Recommended user states:

- Requested.
- Confirmed.
- Processing.
- Completed.
- Partially retained for legal requirement.

Never show "completed" while active primary-system copies remain undeleted.

---

# 15. Security requirements

## SEC-001. Encryption in transit

Use TLS for all production network traffic.

---

## SEC-002. Encryption at rest

Use encryption at rest for:

- Databases.
- Object storage.
- Backups.

Use managed cloud encryption where appropriate.

---

## SEC-003. Passwords

If Receipt Hub stores passwords:

- Use a reputable password hashing algorithm.
- Never store plaintext passwords.
- Never log passwords.

Prefer established authentication providers or well-reviewed authentication libraries.

---

## SEC-004. Secrets

Secrets must not be:

- Committed to source control.
- Embedded in web bundles.
- Embedded in mobile apps if they grant server privileges.
- Written to logs.

Use a secret manager or protected environment configuration.

---

## SEC-005. Object storage

Receipt objects must not be public by default.

Use:

- Private buckets/containers.
- Server-authorised access.
- Short-lived signed URLs where appropriate.
- Ownership checks before returning an object.

---

## SEC-006. Authorization

Every receipt read, update, export or delete operation must verify ownership or valid authorised access.

Do not trust a receipt ID supplied by the client.

---

## SEC-007. Logging

Never intentionally log:

- Full receipt images.
- Full OCR payloads.
- Authentication tokens.
- Passwords.
- Full payment credentials.

Redact personal data from application logs.

---

## SEC-008. Production access

Restrict employee/administrator access to production receipt data.

Implement:

- Least privilege.
- MFA.
- Access logging.
- Role-based permissions.
- Removal of access when no longer required.

---

## SEC-009. Dependency management

Maintain:

- Dependency updates.
- Vulnerability scanning.
- SDK inventory.
- Mobile SDK privacy review.
- Patch process.

---

## SEC-010. Backups

Test restoration.

Document:

- Backup frequency.
- Encryption.
- Access.
- Retention.
- Recovery procedure.
- Deletion replay procedure.

---

# 16. Analytics requirements

## ANALYTICS-001. Minimise analytics

Prefer privacy-minimised analytics.

Do not send receipt contents, merchant names, purchased items or totals to analytics systems unless there is a documented need and appropriate disclosure.

---

## ANALYTICS-002. Event design

Good:

```text
receipt_upload_completed
receipt_ocr_completed
receipt_deleted
export_requested
```

Avoid:

```text
receipt_uploaded_woolworths_163.42
user_bought_medication_x
receipt_items=[...]
```

---

## ANALYTICS-003. Advertising

Preferred launch configuration:

**No third-party advertising SDK.**

**No sale of receipt data.**

**No cross-context behavioural advertising using receipt data.**

---

# 17. Payments and subscriptions

If Receipt Hub offers paid digital features:

## BILLING-001. Store billing review

Before launch, confirm current Apple and Google billing rules for each target country.

Do not assume one global billing rule because store rules and regional exceptions change.

---

## BILLING-002. Subscription disclosure

Clearly display:

- Price.
- Currency.
- Billing period.
- Trial terms.
- Renewal.
- Cancellation procedure.
- Feature changes after cancellation.

---

## BILLING-003. Payment data

Prefer payment processors so Receipt Hub does not directly handle full payment-card credentials.

Do not store full card details unless there is a strong business requirement and appropriate payment-security compliance has been implemented.

---

# 18. Children and age handling

Before launch, decide whether Receipt Hub is:

1. General audience.
2. Intended for adults.
3. Intended for children or families.

Do not accidentally market the product as child-directed without reviewing child privacy and app-store rules.

If children are a target audience, conduct a separate legal review for:

- Australia.
- US COPPA.
- UK Children's Code.
- EU child-consent requirements.
- Google Play Families rules.
- Apple Kids category requirements.
- Other launch countries.

---

# 19. Consumer protection

## CONSUMER-001. Accuracy claims

Do not claim OCR or AI extraction is perfect.

Use language such as:

"Review extracted receipt information before relying on it."

---

## CONSUMER-002. Data durability claims

Do not promise permanent or indestructible storage.

If Receipt Hub markets itself as receipt storage, maintain reasonable backup and recovery controls.

---

## CONSUMER-003. Pricing

Prices, trials, renewal and cancellation conditions must be clear before purchase.

Avoid hidden fees and misleading trial design.

---

## CONSUMER-004. Australian Consumer Law

Terms and product flows must preserve statutory consumer rights.

---

# 20. Privacy UX requirements

## UX-001. Signup

Display links to:

- Terms of Service.
- Privacy Policy.

Avoid forcing consent for unrelated marketing as a condition of account creation.

---

## UX-002. Receipt upload

Display a short privacy notice before or during first receipt upload.

---

## UX-003. Permission prompts

Only ask for device permissions when needed.

Examples:

Camera permission only when the user selects camera capture.

Photo permission only when the user selects an image from their library, subject to platform APIs.

---

## UX-004. Delete receipt

Receipt deletion must be accessible from the receipt interface.

---

## UX-005. Delete account

Account deletion must be easy to find.

Recommended:

`Settings > Account > Delete Account`

Do not hide deletion behind a support ticket if direct deletion is practical.

---

## UX-006. Export

Recommended:

`Settings > Privacy > Export My Data`

---

# 21. Backend privacy endpoints

Suggested API design:

```http
GET    /api/v1/me
PATCH  /api/v1/me

GET    /api/v1/privacy/export
POST   /api/v1/privacy/export

DELETE /api/v1/receipts/{receiptId}
DELETE /api/v1/privacy/receipts
DELETE /api/v1/account

GET    /api/v1/privacy/preferences
PATCH  /api/v1/privacy/preferences
```

For asynchronous exports/deletion:

```http
POST /api/v1/privacy/requests
GET  /api/v1/privacy/requests/{requestId}
```

Example request:

```json
{
  "type": "account_deletion"
}
```

---

# 22. Consent and preference model

Do not store one ambiguous `accepted=true` field for every purpose.

Recommended:

```text
user_consents
- id
- user_id
- consent_type
- policy_version
- granted
- timestamp
- source
```

Potential consent types:

- terms_acceptance.
- marketing_email.
- optional_analytics.
- optional_ai_feature where consent is the selected legal basis.
- cookie categories.

Keep legally distinct purposes separate.

---

# 23. Policy versioning

## POLICY-001

Store:

- Privacy Policy version.
- Terms version.
- Effective date.

For material Terms changes, determine whether renewed acceptance is required.

Do not require users to "consent" to a Privacy Policy merely because it describes processing. Use consent only where consent is the applicable basis.

---

# 24. Breach response plan

Create an internal file such as:

`SECURITY_INCIDENT_RESPONSE.md`

Minimum process:

1. Detect or receive report.
2. Preserve relevant evidence.
3. Contain the incident.
4. Determine systems and data affected.
5. Determine affected users.
6. Determine affected countries.
7. Assess harm and notification obligations.
8. Notify regulators/users where required.
9. Remediate cause.
10. Document decisions.
11. Conduct post-incident review.

Maintain emergency contacts for:

- Hosting provider.
- Authentication provider.
- Database provider.
- OCR/AI provider.
- Email provider.
- Legal/privacy adviser.

---

# 25. Internal documentation required

Create and maintain:

```text
/legal/privacy-policy.md
/legal/terms-of-service.md
/legal/subprocessors.md
/legal/data-retention.md
/legal/privacy-request-procedure.md
/security/incident-response.md
/security/access-control.md
/security/backup-recovery.md
/security/vendor-review.md
/compliance/data-inventory.md
/compliance/app-store-privacy-mapping.md
```

These filenames are examples.

---

# 26. Data inventory requirement

Before public launch, create an inventory with one row for every data type.

Example:

| Data | Source | Purpose | Storage | Shared with | Retention | Delete path | Export path |
|---|---|---|---|---|---|---|---|
| Email | User | Account/login | DB | Auth/email provider | Account life | Account deletion | account.json |
| Receipt image | User | Receipt storage/OCR | Object storage | OCR provider | Until deleted | Receipt/account deletion | ZIP |
| OCR text | Derived | Search/extraction | DB | AI provider if used | Receipt life | Receipt/account deletion | JSON |
| Merchant | Derived/user | Receipt organisation | DB | None by default | Receipt life | Receipt/account deletion | CSV/JSON |

No production data collection should exist without an inventory entry.

---

# 27. App-store privacy mapping

Maintain one mapping between real application behaviour and store declarations.

Example:

| Internal data | Apple declaration | Google Data Safety | Privacy Policy |
|---|---|---|---|
| Email | Contact Info | Personal info | Account information |
| Receipt image | Photos/User Content | Photos/files or relevant category | Receipt content |
| OCR text | User Content | Relevant app data category | Extracted receipt information |
| Crash diagnostics | Diagnostics | App info/performance | Diagnostic information |
| Usage analytics | Product Interaction | App activity | Usage information |

Review the mapping whenever:

- A new SDK is introduced.
- A new data field is collected.
- A new AI provider is introduced.
- Analytics changes.
- Advertising changes.
- Authentication changes.
- A new app feature launches.

---

# 28. Launch blocker requirements

Receipt Hub should not launch publicly until all applicable items below are complete.

## Legal

- [ ] Operating legal entity identified.
- [ ] Privacy contact established.
- [ ] Privacy Policy published.
- [ ] Terms of Service published.
- [ ] Privacy Choices page published.
- [ ] Account deletion web page published.
- [ ] Data retention policy approved.
- [ ] Subprocessor list completed.
- [ ] Australian Privacy Act applicability assessed.
- [ ] International launch regions confirmed.
- [ ] Final legal review completed before paid/global launch.

## Product

- [ ] In-app Privacy Policy link.
- [ ] In-app Terms link.
- [ ] Delete receipt function.
- [ ] Delete all receipt data function.
- [ ] In-app account deletion.
- [ ] External account deletion flow.
- [ ] Data export.
- [ ] Marketing preference.
- [ ] Relevant consent controls.
- [ ] Collection notices.

## Backend

- [ ] Cascading deletion implemented.
- [ ] Object-store deletion implemented.
- [ ] OCR/derived-data deletion implemented.
- [ ] Search-index deletion implemented.
- [ ] Backup expiration documented.
- [ ] Export implemented.
- [ ] Privacy-request audit trail implemented.
- [ ] Vendor deletion behaviour tested.

## Security

- [ ] TLS everywhere.
- [ ] Encryption at rest.
- [ ] Private receipt storage.
- [ ] Authorisation tests for receipt ownership.
- [ ] Production MFA.
- [ ] Least-privilege access.
- [ ] Secret management.
- [ ] Logs reviewed for personal data.
- [ ] Dependency/security scanning.
- [ ] Backup restore tested.
- [ ] Incident response procedure written.

## Apple

- [ ] Privacy Policy URL supplied.
- [ ] Privacy Policy accessible in app.
- [ ] App Privacy declarations completed.
- [ ] Third-party SDK privacy behaviour audited.
- [ ] Account deletion available in app.
- [ ] Privacy manifests reviewed.
- [ ] Tracking behaviour reviewed.
- [ ] Store declarations match production behaviour.

## Google Play

- [ ] Privacy Policy URL supplied.
- [ ] Privacy Policy accessible in app.
- [ ] Data Safety form completed.
- [ ] Account deletion available in app.
- [ ] External deletion page supplied.
- [ ] Third-party SDK behaviour included in declarations.
- [ ] Store declarations match production behaviour.

---

# 29. Recommended product position

To reduce privacy and regulatory risk, Receipt Hub should adopt these product principles.

1. User receipts are private by default.
2. Do not sell user personal information.
3. Do not sell receipt or purchase history.
4. Do not share receipt history for behavioural advertising.
5. Do not use receipt contents for advertising profiles.
6. Do not use private receipts to train general-purpose AI models by default.
7. Collect the minimum information required.
8. Let users export their information.
9. Let users delete individual receipts.
10. Let users delete all receipts.
11. Let users delete their account.
12. Encrypt stored receipt data.
13. Keep receipt storage private.
14. Review every third-party SDK before release.
15. Keep privacy disclosures synchronised with actual code.

---

# 30. Implementation priority

## P0. Before any public beta

- Privacy Policy.
- Terms.
- Privacy contact.
- Secure authentication.
- Private receipt storage.
- HTTPS/TLS.
- Receipt deletion.
- Account deletion.
- External deletion page.
- Data inventory.
- Vendor register.
- Apple privacy mapping.
- Google Data Safety mapping.
- Incident response plan.

## P1. Before commercial launch

- Full data export.
- Privacy Choices page.
- Data retention automation.
- Backup deletion lifecycle.
- Formal privacy-request workflow.
- Country launch review.
- Final legal review.
- Subscription legal/billing review.

## P2. Ongoing

- Annual privacy review.
- Quarterly vendor/SDK review.
- Policy update when data practices change.
- App-store privacy declaration review for every major release.
- Security dependency updates.
- Incident-response exercises.
- Privacy Act threshold/applicability review.

---

# 31. Open decisions for the Receipt Hub team

The next owner needs answers to these before finalising the Privacy Policy.

- [ ] What legal entity owns and operates Receipt Hub?
- [ ] What is the public domain?
- [ ] What is the privacy contact email?
- [ ] What cloud provider is used?
- [ ] Which region stores receipt images?
- [ ] Which region stores databases?
- [ ] Which authentication provider is used?
- [ ] Which OCR provider is used?
- [ ] Is an AI model/provider used after OCR?
- [ ] Does any AI/OCR vendor retain inputs?
- [ ] Does any provider train on submitted data?
- [ ] Which analytics provider is used?
- [ ] Which crash-reporting provider is used?
- [ ] Which email provider is used?
- [ ] Which payment provider is used?
- [ ] Is there an advertising SDK?
- [ ] Are cookies used on the website?
- [ ] Are non-essential analytics enabled by default?
- [ ] How long are backups retained?
- [ ] How long are security logs retained?
- [ ] Which countries will the app launch in first?
- [ ] Are users under 18 a target audience?
- [ ] Will users upload receipts only, or other financial documents too?
- [ ] Will Receipt Hub ingest receipts from email accounts?
- [ ] Will Receipt Hub connect to bank or financial accounts?
- [ ] Will receipt data ever be shared between users or organisations?

Any "yes" answer involving email ingestion, bank data, financial-account integrations, advertising, children, or document types beyond receipts should trigger another privacy review.

---

# 32. Primary source register

These sources should be checked again immediately before store submission because platform rules and privacy laws change.

## Australia

OAIC, Australian Privacy Principles:

https://www.oaic.gov.au/privacy/australian-privacy-principles/read-the-australian-privacy-principles

OAIC, APP 1:

https://www.oaic.gov.au/privacy/australian-privacy-principles/australian-privacy-principles-guidelines/chapter-1-app-1-open-and-transparent-management-of-personal-information

OAIC, Small business:

https://www.oaic.gov.au/privacy/privacy-guidance-for-organisations-and-government-agencies/organisations/small-business

OAIC, Guide to developing an APP privacy policy:

https://www.oaic.gov.au/privacy/privacy-guidance-for-organisations-and-government-agencies/more-guidance/guide-to-developing-an-app-privacy-policy

OAIC, Notifiable Data Breaches:

https://www.oaic.gov.au/privacy/notifiable-data-breaches

ACCC, consumer contracts:

https://www.accc.gov.au/consumers/buying-products-and-services/contracts

ACMA, spam rules:

https://www.acma.gov.au/avoid-sending-spam

---

## Apple

App Review Guidelines:

https://developer.apple.com/app-store/review/guidelines/

App Privacy Details:

https://developer.apple.com/app-store/app-privacy-details/

Manage App Privacy:

https://developer.apple.com/help/app-store-connect/manage-app-information/manage-app-privacy

Account deletion:

https://developer.apple.com/support/offering-account-deletion-in-your-app

Privacy manifests:

https://developer.apple.com/documentation/bundleresources/adding-a-privacy-manifest-to-your-app-or-third-party-sdk

---

## Google Play

User Data policy:

https://support.google.com/googleplay/android-developer/answer/10144311

Account deletion:

https://support.google.com/googleplay/android-developer/answer/13327111

Data Safety:

https://support.google.com/googleplay/android-developer/answer/10787469

---

## European Union

European Commission, data-protection rights:

https://commission.europa.eu/law/law-topic/data-protection/data-protection-eu_en

GDPR text:

https://eur-lex.europa.eu/eli/reg/2016/679/oj

---

## United Kingdom

ICO:

https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/

Cookies and similar technologies:

https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/guide-to-pecr/cookies-and-similar-technologies/

---

## United States, California

California Privacy Protection Agency:

https://cppa.ca.gov/

California consumer privacy information:

https://oag.ca.gov/privacy/ccpa

---

## Canada

Office of the Privacy Commissioner of Canada:

https://www.priv.gc.ca/en/privacy-topics/privacy-laws-in-canada/the-personal-information-protection-and-electronic-documents-act-pipeda/

---

## New Zealand

Office of the Privacy Commissioner:

https://www.privacy.org.nz/privacy-act-2020/privacy-principles/

---

## Singapore

Personal Data Protection Commission:

https://www.pdpc.gov.sg/

---

## Brazil

Autoridade Nacional de Proteção de Dados:

https://www.gov.br/anpd/

---

## India

Ministry of Electronics and Information Technology:

https://www.meity.gov.in/

---

## Japan

Personal Information Protection Commission:

https://www.ppc.go.jp/en/

---

## South Korea

Personal Information Protection Commission:

https://www.pipc.go.kr/eng/

---

# 33. Handover summary

The next developer should treat privacy as part of the Receipt Hub data model, not as a page added at the end.

The core implementation requirement is:

**A user must know what Receipt Hub stores, why it stores it, who receives it, how long it remains, how to export it, and how to delete it. The application must technically perform what the published policy promises.**

The highest-priority engineering areas are:

- Data inventory.
- Private receipt storage.
- Strong access control.
- Data minimisation.
- Full receipt deletion.
- Full account deletion.
- Data export.
- Vendor governance.
- AI/OCR privacy controls.
- App-store declarations.
- Incident response.
- Policy-to-code consistency.

Before launch, perform one final audit comparing:

```text
Actual production code
        ↓
Data inventory
        ↓
Vendor register
        ↓
Privacy Policy
        ↓
Apple App Privacy
        ↓
Google Data Safety
```

All six should describe the same real data practices.

# Receipts Hub MVP UI/UX plan
## Purpose
This document defines the UI and UX preparation required to move Receipts Hub from a verified frontend/live-API build into a usable MVP release. It is focused on the Android-first capture-to-ledger journey and deliberately excludes later hosted features such as public price sharing, advanced retailer coverage, and offline mutation queues.

## MVP product promise
A new user should be able to install the app, connect to the host, authenticate, capture a receipt, understand what the app is doing, recover from a failure, correct uncertain OCR, file the receipt, and find the result in Home, Receipts, Insights, and List.

The experience should feel:

- Calm rather than operationally noisy
- Trustworthy about OCR uncertainty and financial totals
- Fast for the common path
- Recoverable when camera, network, OCR, or host processing fails
- Explicit about what is saved and what is still a draft
- Accessible on small Android phones and with large text
## Current baseline
The Flutter client already has the core surfaces, Material 3 theme, camera/gallery acquisition, live API integration, review states, shopping, analytics, Riverpod state, and automated tests. The remaining UI/UX work is release hardening rather than a redesign.

The MVP must preserve the design handoff tokens and behaviour. Use the HTML prototype only as a visual reference; production behaviour belongs in the Flutter implementation.

## On-device inference recommendation
Do **not** move the complete receipt inference pipeline to the phone for the first hosted MVP. Use a hybrid pipeline:

1. The phone captures, crops, rotates, compresses, and validates receipt images locally.
2. The phone may run a small ONNX receipt-region detector locally to improve framing and provide immediate capture guidance.
3. The host performs authoritative OCR, receipt parsing, duplicate detection, persistence, and analytics.
4. The user reviews and confirms the server result before filing.

The current backend already uses an OCR stack with ONNX Runtime/RapidOCR support. Replacing that pipeline with a phone model would add model distribution, Android hardware variance, battery and memory constraints, model-version compatibility, and a second inference implementation before the MVP has physical-device evidence.

### What may run locally
Suitable early on-device tasks are:

- Receipt edge/region detection
- Blur, glare, darkness, and resolution checks
- Perspective correction and image rotation
- Thumbnail generation and upload-size reduction
- Optional coarse quality score for capture guidance
These tasks improve responsiveness without creating a second source of truth. Local output should be treated as a hint, not a filed receipt.

### What should remain authoritative on the host
Keep these on the host for the MVP:

- OCR text extraction
- Merchant, date, total, tax, and line-item parsing
- Currency and locale interpretation
- Balance validation and filing gates
- Duplicate detection
- Analytics and price-history updates
The server must always revalidate any fields or hints received from the device. Never trust client-produced totals, categories, confidence values, or duplicate decisions.

### When to add full on-device OCR
Consider a full ONNX/mobile OCR path only after measuring the hosted flow and defining a supported device baseline. It should be justified by a clear requirement such as poor connectivity, privacy-sensitive deployments, upload-cost reduction, or unacceptable capture latency. Before adopting it, compare the phone model against the server using a versioned receipt evaluation set and track merchant accuracy, total accuracy, line-item accuracy, latency, battery, memory, APK size, and thermal behaviour.

If introduced later, use a versioned model manifest and retain server fallback:

```text
capture
  ├── local quality/detection hint
  ├── optional local OCR draft
  └── server OCR and validation (authoritative)
```

The UI must label a local result as `Draft`, show confidence and uncertainty, and explain that filing requires server confirmation. Offline inference should not silently imply that data has been saved.

## Primary MVP journeys
### 1. First run, account, and household access
The production MVP must not ask ordinary users to enter an API IP address. The app should connect to a configured application environment or use a branded HTTPS service URL. Host configuration may remain available only in a hidden developer/diagnostic area for testing and support.

1. Welcome explains the value in one sentence and offers `Create account` and `Sign in`.
2. Account creation uses the managed identity provider and supports email verification, password reset, and secure session restoration.
3. After authentication, show the user's household choices:
   - `Create a household`
   - `Join a household`
   - Existing households the user already belongs to
4. `Join a household` accepts a human-readable household ID or join code. Explain that submitting it sends a request and does not grant access immediately.
5. Show a pending state with the household name when the server confirms the request. The user can cancel a pending request where supported.
6. Owners and admins see `People` or `Household members` in Account. They can review pending requests and choose `Approve` or `Decline`, with the role shown before approval.
7. After approval, notify the requester and make the household available in the household switcher. If declined, explain that access was not granted without exposing private household data.
8. If the user has one active household, enter Home after the access state is resolved. If there are several, require an explicit household selection.
9. Connection health is checked automatically against the configured service. Show distinct states for service unavailable, authentication failure, pending household access, and healthy service.

The local testing PIN and editable host URL remain developer-only compatibility paths and must not appear in the normal production onboarding journey.

Acceptance criteria:

- A normal user never needs to know or enter an API IP address.
- A user always knows whether the issue is service availability, authentication, or household access.
- Join requests are clearly separate from membership; entering an ID alone never grants access.
- Owners/admins can approve or decline requests from a clear, accessible review screen.
- The join code/household ID is never treated as a secret or as authentication.
- Every action has a visible loading state and cannot be submitted repeatedly.
- Error messages state the next action in plain language.
- Developer diagnostics do not expose bearer tokens or other secrets in logs.

### 2. Capture
1. Capture explains that one receipt may contain one to five ordered pages.
2. Camera is the primary action; gallery is the fallback.
3. Show page count, reorder affordance, remove action, and a clear `Continue` action.
4. Camera denial must not dead-end the user: offer gallery and Android settings.
5. Before upload, show a confirmation preview with page thumbnails and total page count.

Acceptance criteria:

- Every thumbnail has a stable key and an accessible label such as `Receipt page 2 of 3`.
- Destructive remove actions require an obvious confirmation or immediate undo.
- The user can abandon a draft without accidentally filing it.
- Upload progress remains visible while the app is in the foreground.

### 3. Processing
Processing should describe real stages rather than display an indefinite spinner:

```text
Uploading photos
Reading receipt
Checking totals
Preparing review
```

Show a short explanation that processing may take time. Polling must have a timeout and a recovery path.

Failure states must offer:

- `Retry` using the retained uploaded draft
- `Enter manually`
- `Save draft` where supported
- `Back to receipts`

Never make the user recapture images merely because OCR failed.

### 4. Review and file
The review screen is the trust boundary. Make the following prominent:

- Merchant
- Purchase date
- Total
- Line items
- Uncertain-field markers
- Balance or reconciliation status
- Duplicate warning
- Filing outcome
Uncertain fields must be explained inline: `Check this value; OCR confidence is low.` Avoid colour-only indicators. The total must use integer cents in the data layer and a consistent local currency display in the UI.

The primary action should change with state:

- `Review receipt` while required fields are unresolved
- `File receipt` when the merchant and total gate passes
- `Saved with missing date` when the receipt is valid but excluded from dated analytics
- `Already filed` for duplicates
After filing, show a confirmation that names where the receipt can be found: Home, Receipts, and Insights when dated.

## Navigation and information architecture
Keep the five-destination shell already implemented. The MVP hierarchy should remain shallow:

```text
Household switcher → active household and pending access status
Home
Receipts → receipt detail → photo zoom
Capture → processing → review
Collections / Insights
List
Account → household members, join requests, connection status, theme, sign out, help
```

Rules:

- Preserve origin-aware back navigation from receipt detail, comparison, and photo zoom.
- Do not hide essential capture or review actions behind overflow menus.
- Keep Home focused on current totals, recent receipts, and the next useful action.
- Receipts is the source of truth for the complete ledger and attention states.
- Insights is explanatory; it must not imply precision beyond the available data.
- List must clearly distinguish active, completed, dismissed, and suggested items.
- Account must show the active household, membership role, pending join requests or approvals, service connection state, last successful sync, and sign-out.
- Owners/admins must have an accessible member-management screen with pending requests, requester identity, requested household, requested role, approval, decline, and revoke actions.
- Users belonging to multiple households need a prominent household switcher; switching must refresh all household-scoped data before showing it as current.

## State and feedback requirements
Every API-backed screen needs four deliberate states:

| State | Required UI |
|---|---|
| Loading | Skeleton or progress indicator that preserves layout context |
| Empty | Explanation plus a relevant next action |
| Error | Plain-language cause, retry action, and safe fallback |
| Ready | Content with refresh and visible last-updated context where relevant |

Use snackbars or toasts only for short-lived confirmation. Persistent problems belong in the page content. Never report a successful local action before the server confirms it.

For optimistic shopping-list edits, show the pending state and revert or reload on `409 VERSION_CONFLICT`. Explain that another device changed the item rather than silently discarding the user's edit.

## Visual and interaction standards
- Preserve Sage, Clay, and Olive themes in light and dark mode.
- Keep minimum touch targets at 44 x 44 logical pixels.
- Keep body text at least 12 px in the supported reference layouts; do not solve density by shrinking text.
- Use semantic colour plus icon, label, or shape for status.
- Keep primary actions visually dominant and in predictable positions.
- Use `const` widgets and stable list keys to reduce rebuilds.
- Avoid motion that is required to understand a state; support reduced-motion preferences.
- Avoid large blocking animations during upload or OCR.
- Ensure keyboard focus order follows visual order.
- Keep system back behaviour safe: confirm only when a draft would be lost.

## Accessibility release bar
Test the full app with:

- Android large-font and text-scaling settings
- TalkBack traversal and meaningful labels
- Keyboard navigation where available
- Contrast in all three colourways and both brightness modes
- Reduced motion
- 320–360 dp width devices
- Landscape or constrained-height layouts where supported
- Touch targets around camera, remove, edit, retry, file, and navigation controls
Required semantics examples:

```text
Capture page 1 of 3
Remove receipt page 2
Merchant, needs review
Receipt total, 19 dollars
Retry processing
File receipt
```

Do not communicate uncertainty, duplicate status, or filing eligibility by colour alone.

## Error-copy guidelines
Use this format:

```text
What happened
What the user can do next
```

Examples:

- `The host could not be reached. Check that the computer is awake and that your phone is on the same Wi-Fi network.`
- `The receipt was uploaded, but reading it failed. Retry without taking the photos again, or enter the details manually.`
- `This receipt is missing a date. It is saved and visible, but it will not affect dated insights until you add one.`
- `Another device changed this shopping item. We reloaded the latest version so you do not overwrite it.`

Do not show stack traces, raw HTTP errors, bearer tokens, local paths, or implementation terminology to end users.

## MVP validation plan
### Automated checks
Maintain and extend the existing suites with focused assertions for:

- Welcome, account creation, sign-in, household selection, and health-check error branches
- Household ID entry, join-request submission, pending state, cancellation, approval, decline, and membership refresh
- Camera denial and gallery fallback
- One-to-five ordered pages and removal
- Upload progress and processing-stage labels
- Local image quality/detection hints do not block a usable manual capture path
- Any optional on-device ONNX result is labelled as a draft and never treated as authoritative
- Timeout, retry, manual entry, and retained draft behaviour
- Uncertain merchant, date, total, and line-item markers
- Filing gate, duplicate outcome, and missing-date outcome
- Auth expiry and sign-out navigation
- Shopping `409 VERSION_CONFLICT` recovery
- Semantics, labels, minimum touch targets, and text scaling
- Light/dark golden coverage for critical states
### Physical-device test script
Run this script on at least one small Android phone and one current Android phone:

1. Install a fresh build.
2. Confirm the fresh install uses the configured service without asking for an API IP address.
3. Create or sign in to an account and verify session restoration after restarting the app.
4. Enter a valid household ID, submit a join request, and confirm that pending access does not expose household data.
5. As an owner/admin, approve the request; confirm the requester sees the household and can enter Home.
6. Test decline, cancellation, revocation, and switching between two households.
7. Try an unavailable service and confirm the recovery copy.
8. Deny camera permission, use gallery fallback, and open Android settings.
6. Capture two or more pages, reorder them, remove one, and continue.
7. Verify upload progress and each real processing stage.
8. Force or simulate an OCR failure; retry without recapture.
9. Use manual entry and verify the draft remains identifiable.
10. Correct an uncertain field, file the receipt, and confirm it appears in Home and Receipts.
11. Add a missing date and verify the dated analytics explanation.
12. Add, complete, edit, and delete a shopping item; test stale edit recovery.
13. Enable large text and TalkBack and repeat the core capture/review path.
14. Use Android back from every detail and draft screen.

Record device model, Android version, app version, host version, network type, result, and defect ID.

### Performance targets for MVP
These are practical release targets, not hard product guarantees:

- First meaningful screen after launch: under 2 seconds on a typical device when the host is reachable
- Health check response: under 1 second on the local LAN in normal conditions
- Capture preview should remain responsive while thumbnails are prepared
- No visible jank while scrolling a 100-receipt list
- Upload progress should update at least every 500 ms while bytes are moving
- Receipt images should be downsampled for list thumbnails and loaded lazily
- OCR duration should be measured by page count, image size, and host processing stage
## MVP release checklist
Before signing off the UI/UX:

- [ ] Fresh install reaches a useful first-run state without asking for an API IP address.
- [ ] Account creation, sign-in, verification, reset, and session restore work.
- [ ] Household creation and household switching work.
- [ ] Household ID join requests remain pending until an owner/admin approves them.
- [ ] Owners/admins can approve, decline, and revoke membership.
- [ ] Connection errors distinguish service availability, authentication, and household-access failures.
- [ ] Multi-page capture works with camera and gallery fallback.
- [ ] Processing failure can retry or switch to manual entry without recapture.
- [ ] Optional local ONNX inference, if enabled, does not prevent capture on unsupported or low-memory devices.
- [ ] Server OCR remains authoritative and local drafts are clearly labelled.
- [ ] Review clearly identifies uncertain values and the filing gate.
- [ ] Missing-date receipts explain their analytics treatment.
- [ ] Duplicate receipts explain the outcome without data loss.
- [ ] Home, Receipts, Insights, and List reflect a newly filed receipt.
- [ ] Auth expiry safely returns the user to sign-in without losing a draft.
- [ ] Empty, loading, error, and ready states are implemented for every live screen.
- [ ] TalkBack, large text, contrast, reduced motion, and small-width checks pass.
- [ ] Physical-device capture-to-ledger script passes.
- [ ] Performance measurements are recorded and regressions addressed.
- [ ] Signed release build is installed and smoke-tested.

## Out of MVP scope
Do not delay the MVP for these items:

- Offline mutation queues
- Multi-device conflict resolution beyond shopping optimistic concurrency
- Public accounts or anonymous price aggregation
- Real retailer inventory guarantees
- Advanced comparison evidence and multi-retailer coverage
- Push notifications
- Tablet-specific layouts
- Full export and backup controls in Flutter while they remain web-only
## Definition of UI/UX ready
The UI/UX is ready when a first-time user can complete the capture-to-ledger journey without developer explanation, every failure state offers a recoverable next action, financial uncertainty is visible and understandable, and the experience remains usable with accessibility settings enabled on a physical Android device.

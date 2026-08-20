# MVP UI/UX revision
This folder contains the production-oriented account and household-access UI described in `docs/mvp-ui-ux-plan.md`.

## Included production routes
- `/household/join` — enter a non-secret household ID/join code and request access.
- `/household/members` — owner/admin review of pending requests with approve/decline actions.

These screens use the shared Receipts Hub design system: Material 3 theme, typography, spacing, colours, `ReceiptAppMark`, and `LedgerCard`.

**Status: not reachable from the product, and not yet functional.** Correcting an earlier claim in this file that they were reachable from Welcome and Account:

- Account's `Members` row never navigated to `/household/members`; it only raised a toast. That row has since been removed.
- Welcome's `Join a household` button reached `/household/join` *before authentication*, and its `Not now` action then went to `/home`, entering the ledger with no session. That button has been removed.
- `/household/members` is still registered twice in `app_router.dart` and navigated to from nowhere.
- Neither screen calls an API. The join request is a `Future.delayed`, and the pending-request list is a hardcoded `['Alex Morgan']`.

They also still live at `lib/ui_ux_revision/` with `Mvp` class prefixes, which contradicts the acceptance bar below. Both are addressed when the household endpoints land.

## Run the standalone UI/UX revision
From `apps/receipts_hub`:

```powershell
flutter run -d emulator-5554 -t ui_ux_revision/main.dart
```

This entrypoint starts directly at `/household/join`, uses the real app theme and router, disables session restoration, and does not call the live API. The request and approval actions remain local until the household endpoints are connected.The household-access experience is now presented as a normal product flow rather than a developer preview. It is reachable through Welcome and Account navigation, uses the shared design system, and contains no preview controls or developer-only copy.

The current repository implementation uses local state while the authenticated household API is completed. Before release, replace that state with server responses and keep the same loading, empty, error, retry, and success behaviour.

## Production acceptance bar
- No `Preview`, `MVP`, `dev`, IP-address, or PIN language in the normal flow.
- Join requests clearly show pending access until approved.
- Owners/admins can review the requester and approve or decline.
- Loading, validation, empty, success, and error states are accessible.
- Cross-household data is never shown before membership approval.
- Live API errors must be rendered as actionable user-facing copy, never raw exceptions.

# Receipts Hub Flutter

Android-first Flutter frontend for turning household receipts into a calm spend
ledger, shopping list, and evidence-based merchant comparison.

## Current status

The app is a verified, navigable **frontend demo**. It includes first run,
connection, Android camera/gallery capture, processing states, receipt review,
Home, Receipts, Collections, Insights, Rivals, Item comparison, List, and
Account. Riverpod state and the price-comparison engine are functional, but all
ledger content comes from in-memory `DemoData` and resets when the process
restarts.

The connection form currently validates an address and PIN locally; it does not
contact the Python host. `MobileApi` defines the future session boundary, but the
required `/api/v1` backend is pending. Camera and gallery acquisition are real
on Android; upload, OCR, server persistence, authenticated images, and live
analytics are simulated or not yet wired.

## Included frontend features

- Material 3 interface with Sage, Clay, and Olive colorways in light and dark.
- Noto Sans assets, receipt-ledger components, tabular prices, and accessible
  navigation targets.
- GoRouter navigation with a five-destination app shell and origin-aware detail
  routes.
- Riverpod-managed demo receipts, shopping items, capture state, sharing, and
  theme preferences.
- Android camera/gallery page acquisition with one-to-five ordered pages,
  permission recovery, torch control, and gallery fallback.
- Receipt search, review/edit previews, comparison screens, shopping-list
  interactions, offline preview, and loading/failure states.
- Evidence-safe item and basket comparisons with unit tests for weak data,
  provenance, mixed packs, consent, and incomplete coverage.

See [Frontend architecture](docs/frontend-architecture.md) for boundaries and
business rules.

## Prerequisites

- Flutter stable 3.41 or newer; this project targets Dart 3.11 or newer.
- Android Studio or Android command-line tools with an Android SDK and accepted
  licenses. The current workstation uses Android SDK 36.1.
- An Android emulator or a USB-debuggable Android phone.
- PowerShell for the commands below when developing on Windows.

Check the toolchain before setup:

```powershell
flutter --version
flutter doctor -v
flutter doctor --android-licenses
flutter devices
```

Flutter is installed locally on the current workstation at the following path,
but the location is machine-specific. Use the `flutter` command from `PATH`
whenever possible.

```powershell
$FlutterCmd = "C:\Users\joebr\SDK's\flutter\bin\flutter.bat"
& $FlutterCmd --version
```

## Run the app

From the repository root:

```powershell
Set-Location .\apps\receipts_hub
flutter pub get
flutter run
```

If Flutter finds more than one target, use `flutter devices`, then pass the
reported identifier with `flutter run -d DEVICE_ID`.

The demo starts at `/welcome`. The default host address,
`http://10.0.2.2:8000`, is the Android emulator alias for the development
machine. A physical phone needs the host's private LAN address instead. This
does not activate backend integration yet.

The Android manifest allows cleartext traffic for a trusted private LAN and
declares network, camera, and gallery permissions. Do not expose the host with
public port forwarding or use the cleartext setup on an untrusted network.

## Analyze, test, and build

Run these commands from `apps/receipts_hub`:

```powershell
flutter analyze
flutter test
flutter test --coverage
flutter build apk --debug
flutter test integration_test\app_smoke_test.dart -d emulator-5554
```

Run the comparison contract suite alone with:

```powershell
flutter test test\core\price_comparison_test.dart
```

The debug APK is written to
`build\app\outputs\flutter-apk\app-debug.apk`. A signed release APK is not part
of the current frontend-only milestone.

## Project map

```text
lib/
  app.dart                     MaterialApp, router, and active theme
  core/
    data/                      deterministic demo fixtures
    design/                    tokens, themes, and shared components
    models/                    receipt and price domain models
    network/                   pending /api/v1 session client boundary
    pricing/                   evidence-safe comparison engine
    routing/                   GoRouter route graph
    state/                     Riverpod application and theme state
    widgets/                   shared application shell
  features/                    account, capture, compare, ledger,
                               onboarding, receipts, and shopping UI
test/core/                     comparison and domain-rule tests
docs/                          architecture notes
```

## Verification checklist

- [x] `flutter doctor -v` reports no blocking Android issue.
- [x] `flutter analyze` completes with no issue.
- [x] `flutter test` and `flutter test --coverage` pass.
- [x] `flutter build apk --debug` produces `app-debug.apk`.
- [x] An emulator launch reaches Welcome, Connect, Home, every shell tab, and a
  mutable shopping-list flow.
- [x] Automated tests cover ordered capture state, receipt review, navigation,
  mutable demo state, evidence rules, and reference-screen rendering.
- [ ] Add direct widget coverage for processing failure/manual fallback and the
  photo-zoom route when those flows are connected to live job/image contracts.
- [ ] Verify real camera/gallery acquisition and the complete host flow on a
  physical Android phone.
- [x] Sage, Clay, and Olive are checked in both light and dark mode at the
  390 x 844 reference viewport.
- [x] Weak/outlier prices stay visible but never receive a crown or savings
  claim, and every displayed price names its source and freshness.
- [x] The trusted-LAN warning and pending `/api/v1` limitation remain visible in
  developer documentation until the backend is connected.

## Related documentation

- [Workspace TODO](../../TODO.md)
- [Verification record](docs/verification.md)
- [Flutter design handoff](../../receipts%20hub/Design%20System%20-%20flutter/design_handoff_receipts_hub_flutter/README.md)
- [Interface system](../../.interface-design/system.md)

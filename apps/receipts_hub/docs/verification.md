# Frontend verification record

Verified on 15 August 2026 using Flutter 3.41.3, Dart 3.11.1, Android SDK 36.1,
and the `Medium_Phone_API_36.1` Android emulator.

## Automated results

| Check | Result |
| --- | --- |
| `flutter analyze` | Passed with no issues |
| `flutter test --coverage` | Passed: 31 tests |
| Comparison contract suite | Passed: 16 tests |
| Widget/accessibility suite | Passed: 7 tests |
| Golden suite | Passed: 8 tests |
| Android emulator smoke test | Passed: 1 integration test |
| `flutter build apk --debug` | Passed |

The LCOV report records 1,834 of 2,994 executable lines, or 61.3% line
coverage. Coverage is a diagnostic, not a release-quality score; camera plugin
behavior and the pending server adapter still require device/contract tests.

The emulator smoke test covers first run, local connection setup, Home, every
primary bottom-navigation destination, and a shopping-list mutation. Golden
images cover all six colorway/brightness combinations plus Home and Item at the
390 x 844 reference viewport.

## Debug artifact

- Path: `build/app/outputs/flutter-apk/app-debug.apk`
- Size: 201,930,126 bytes
- SHA-256: `373AE5934310AD5FF8515CF2DDD55E86E8D320573C79E3318239445E311483A9`

This is a universal debug build, not a signed release artifact.

## Deliberate exclusions

The verified milestone does not claim live PIN authentication, health checks,
multipart upload, OCR, authenticated receipt images, server persistence, real
analytics, supported retailer/stock feeds, or offline mutation sync. It also
does not replace physical-phone camera, accessibility, performance, and full
host-flow checks.

See the [workspace TODO](../../../TODO.md) for the remaining backend and release
gates and [frontend architecture](frontend-architecture.md) for the integration
boundary.

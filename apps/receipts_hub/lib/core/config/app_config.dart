// Where this build talks to.
//
// A hosted product ships knowing its own service address. Asking a customer to
// type one — as the old connection screen did — leaks a deployment detail into
// the product and cannot work for anyone who is not on the same LAN as a
// machine they own.
//
// Override at build time:
//   flutter build apk --dart-define=RECEIPTS_HUB_API_BASE_URL=https://api.example.com

abstract final class AppConfig {
  /// The service this build uses. HTTPS in every real deployment.
  static const apiBaseUrl = String.fromEnvironment(
    'RECEIPTS_HUB_API_BASE_URL',
    defaultValue: 'https://api.receiptshub.app',
  );

  /// Whether a host address may be entered by hand.
  ///
  /// Development and support only, and gated on the build being a debug build
  /// as well, so a release APK has no path to it at all.
  static const allowHostOverride = bool.fromEnvironment(
    'RECEIPTS_HUB_ALLOW_HOST_OVERRIDE',
    defaultValue: true,
  );
}

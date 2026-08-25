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
  /// Overridden per build; the default is the current deployment target
  /// (a Raspberry Pi behind Cloudflare). See `docs/deployment.md`.
  static const apiBaseUrl = String.fromEnvironment(
    'RECEIPTS_HUB_API_BASE_URL',
    defaultValue: 'https://receipts.aacu-church.org',
  );

  /// Where the privacy policy and terms live.
  ///
  /// Left blank by default on purpose: an app store listing and a paid product
  /// both require these, and shipping a dead link is worse than showing
  /// nothing. The Account screen hides the rows until they are set.
  static const privacyPolicyUrl = String.fromEnvironment(
    'RECEIPTS_HUB_PRIVACY_URL',
  );

  static const termsUrl = String.fromEnvironment('RECEIPTS_HUB_TERMS_URL');

  static const supportEmail = String.fromEnvironment(
    'RECEIPTS_HUB_SUPPORT_EMAIL',
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

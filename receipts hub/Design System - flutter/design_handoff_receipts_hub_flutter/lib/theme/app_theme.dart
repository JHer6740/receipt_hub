// app_theme.dart — Receipts Hub design tokens as Flutter ThemeData.
// Ported verbatim from the HTML prototype's CSS custom properties.
// Three colourways x light/dark. Sage light is the default.

import 'package:flutter/material.dart';

@immutable
class AppColors extends ThemeExtension<AppColors> {
  final Color background;      // --background-default
  final Color surface;         // --background-paper-elevation-1
  final Color divider;         // --divider
  final Color textPrimary;     // --text-primary
  final Color textSecondary;   // --text-secondary
  final Color actionHover;     // --action-hover
  final Color actionSelected;  // --action-selected
  final Color primary;         // --primary-main
  final Color onPrimary;       // --primary-contrast
  final Color error;           // --error-main
  final Color warnBg;          // --gh-warn-bg
  final Color warnFg;          // --gh-warn-fg
  final Color inputBorder;     // --gh-input-bd
  final Color good;            // derived: positive / savings
  final Color warn;            // derived: caution

  const AppColors({
    required this.background,
    required this.surface,
    required this.divider,
    required this.textPrimary,
    required this.textSecondary,
    required this.actionHover,
    required this.actionSelected,
    required this.primary,
    required this.onPrimary,
    required this.error,
    required this.warnBg,
    required this.warnFg,
    required this.inputBorder,
    required this.good,
    required this.warn,
  });

  // ---- Sage (default) ----
  static const sageLight = AppColors(
    background: Color(0xFFF5EAD8),
    surface: Color(0xFFFDF8EE),
    divider: Color(0x24201E1D),
    textPrimary: Color(0xFF201E1D),
    textSecondary: Color(0xFF6F6455),
    actionHover: Color(0x0D201E1D),
    actionSelected: Color(0x12201E1D),
    primary: Color(0xFF5F6F47),
    onPrimary: Color(0xFFFDF8EE),
    error: Color(0xFFA8432F),
    warnBg: Color(0xFFF2E2CD),
    warnFg: Color(0xFF5C3A17),
    inputBorder: Color(0x38201E1D),
    good: Color(0xFF4C6B33),
    warn: Color(0xFF8A5A1E),
  );

  static const sageDark = AppColors(
    background: Color(0xFF1C1813),
    surface: Color(0xFF272118),
    divider: Color(0x29F1E8D8),
    textPrimary: Color(0xFFF1E8D8),
    textSecondary: Color(0xADF1E8D8),
    actionHover: Color(0x0FF1E8D8),
    actionSelected: Color(0x14F1E8D8),
    primary: Color(0xFFA2B47F),
    onPrimary: Color(0xFF1C1813),
    error: Color(0xFFE0917D),
    warnBg: Color(0xFF3B2A1C),
    warnFg: Color(0xFFF0C99F),
    inputBorder: Color(0x42F1E8D8),
    good: Color(0xFFA8C47E),
    warn: Color(0xFFE0B071),
  );

  // ---- Clay ----
  static const clayLight = AppColors(
    background: Color(0xFFF7ECDC),
    surface: Color(0xFFFFFAF3),
    divider: Color(0x243A2618),
    textPrimary: Color(0xFF2B1F16),
    textSecondary: Color(0xFF7D6552),
    actionHover: Color(0x0D3A2618),
    actionSelected: Color(0x123A2618),
    primary: Color(0xFFB4602C),
    onPrimary: Color(0xFFFFFAF3),
    error: Color(0xFF9D3423),
    warnBg: Color(0xFFECDCC4),
    warnFg: Color(0xFF5A3512),
    inputBorder: Color(0x383A2618),
    good: Color(0xFF4C6B33),
    warn: Color(0xFF8A5A1E),
  );

  static const clayDark = AppColors(
    background: Color(0xFF1E1712),
    surface: Color(0xFF2B211A),
    divider: Color(0x29F4E7D8),
    textPrimary: Color(0xFFF4E7D8),
    textSecondary: Color(0xA8F4E7D8),
    actionHover: Color(0x0FF4E7D8),
    actionSelected: Color(0x14F4E7D8),
    primary: Color(0xFFE09257),
    onPrimary: Color(0xFF1E1712),
    error: Color(0xFFE08D78),
    warnBg: Color(0xFF3D2A1C),
    warnFg: Color(0xFFF2CCA9),
    inputBorder: Color(0x42F4E7D8),
    good: Color(0xFFA8C47E),
    warn: Color(0xFFE0B071),
  );

  // ---- Olive ----
  static const oliveLight = AppColors(
    background: Color(0xFFF4F1E6),
    surface: Color(0xFFFDFCF7),
    divider: Color(0x211E221A),
    textPrimary: Color(0xFF1E221A),
    textSecondary: Color(0xFF6B7062),
    actionHover: Color(0x0D1E221A),
    actionSelected: Color(0x121E221A),
    primary: Color(0xFF3D4A2F),
    onPrimary: Color(0xFFFDFCF7),
    error: Color(0xFF8E3A2A),
    warnBg: Color(0xFFE8E3CF),
    warnFg: Color(0xFF4A3C1C),
    inputBorder: Color(0x331E221A),
    good: Color(0xFF4C6B33),
    warn: Color(0xFF8A5A1E),
  );

  static const oliveDark = AppColors(
    background: Color(0xFF16180F),
    surface: Color(0xFF212418),
    divider: Color(0x26ECEADB),
    textPrimary: Color(0xFFECEADB),
    textSecondary: Color(0xA8ECEADB),
    actionHover: Color(0x0FECEADB),
    actionSelected: Color(0x14ECEADB),
    primary: Color(0xFFB6C78E),
    onPrimary: Color(0xFF16180F),
    error: Color(0xFFDC8F7A),
    warnBg: Color(0xFF33301D),
    warnFg: Color(0xFFE2DCAE),
    inputBorder: Color(0x3DECEADB),
    good: Color(0xFFA8C47E),
    warn: Color(0xFFE0B071),
  );

  @override
  AppColors copyWith({
    Color? background, Color? surface, Color? divider, Color? textPrimary,
    Color? textSecondary, Color? actionHover, Color? actionSelected,
    Color? primary, Color? onPrimary, Color? error, Color? warnBg,
    Color? warnFg, Color? inputBorder, Color? good, Color? warn,
  }) => AppColors(
    background: background ?? this.background,
    surface: surface ?? this.surface,
    divider: divider ?? this.divider,
    textPrimary: textPrimary ?? this.textPrimary,
    textSecondary: textSecondary ?? this.textSecondary,
    actionHover: actionHover ?? this.actionHover,
    actionSelected: actionSelected ?? this.actionSelected,
    primary: primary ?? this.primary,
    onPrimary: onPrimary ?? this.onPrimary,
    error: error ?? this.error,
    warnBg: warnBg ?? this.warnBg,
    warnFg: warnFg ?? this.warnFg,
    inputBorder: inputBorder ?? this.inputBorder,
    good: good ?? this.good,
    warn: warn ?? this.warn,
  );

  @override
  AppColors lerp(ThemeExtension<AppColors>? other, double t) {
    if (other is! AppColors) return this;
    return AppColors(
      background: Color.lerp(background, other.background, t)!,
      surface: Color.lerp(surface, other.surface, t)!,
      divider: Color.lerp(divider, other.divider, t)!,
      textPrimary: Color.lerp(textPrimary, other.textPrimary, t)!,
      textSecondary: Color.lerp(textSecondary, other.textSecondary, t)!,
      actionHover: Color.lerp(actionHover, other.actionHover, t)!,
      actionSelected: Color.lerp(actionSelected, other.actionSelected, t)!,
      primary: Color.lerp(primary, other.primary, t)!,
      onPrimary: Color.lerp(onPrimary, other.onPrimary, t)!,
      error: Color.lerp(error, other.error, t)!,
      warnBg: Color.lerp(warnBg, other.warnBg, t)!,
      warnFg: Color.lerp(warnFg, other.warnFg, t)!,
      inputBorder: Color.lerp(inputBorder, other.inputBorder, t)!,
      good: Color.lerp(good, other.good, t)!,
      warn: Color.lerp(warn, other.warn, t)!,
    );
  }
}

/// Type scale. 'display' is the heading face (serif-ish display in the
/// prototype); everything else is Noto Sans. Tabular figures are REQUIRED
/// on every price, total and delta — the app is full of aligned columns.
class AppText {
  static const _tabular = [FontFeature.tabularFigures()];

  static const displayXL = TextStyle(fontFamily: 'Display', fontSize: 42, height: 1.15, letterSpacing: -0.42);
  static const displayL  = TextStyle(fontFamily: 'Display', fontSize: 38, height: 1.15, letterSpacing: -0.38);
  static const displayM  = TextStyle(fontFamily: 'Display', fontSize: 30, height: 1.2,  letterSpacing: -0.30);
  static const displayS  = TextStyle(fontFamily: 'Display', fontSize: 24, height: 1.2,  letterSpacing: -0.24);
  static const screenTitle = TextStyle(fontFamily: 'Display', fontSize: 22, height: 1.25);

  static const bodyL     = TextStyle(fontSize: 16, height: 1.4);
  static const body      = TextStyle(fontSize: 15, height: 1.4);
  static const bodyS     = TextStyle(fontSize: 14, height: 1.45);
  static const caption   = TextStyle(fontSize: 13, height: 1.5);
  static const captionS  = TextStyle(fontSize: 12, height: 1.45);

  /// Section headers: 12px, w500, 0.6px tracking, UPPERCASE.
  static const sectionLabel = TextStyle(fontSize: 12, fontWeight: FontWeight.w500, letterSpacing: 0.6);

  /// Button label — matches ODS: 15px / w500 / 0.46px.
  static const button = TextStyle(fontSize: 15, fontWeight: FontWeight.w500, letterSpacing: 0.46);

  static TextStyle numeric(TextStyle base) => base.copyWith(fontFeatures: _tabular);
}

class AppRadii {
  static const card = 20.0;       // comparison card, verdict panels
  static const sheet = 28.0;      // the raised content sheet (top corners only)
  static const field = 14.0;      // text inputs
  static const chip = 999.0;      // pills, buttons, badges
  static const mark = 11.0;       // 38px merchant mark
  static const markLarge = 14.0;  // 52px item mark
}

class AppSpacing {
  static const gutter = 24.0;     // screen horizontal padding
  static const cardPad = 16.0;
  static const rowMinHeight = 56.0;
  static const tapTarget = 44.0;  // never smaller
  static const navHeight = 56.0;
  static const editFooterClearance = 190.0; // bottom padding in edit mode
}

ThemeData buildTheme(AppColors c, Brightness brightness) {
  return ThemeData(
    useMaterial3: true,
    brightness: brightness,
    scaffoldBackgroundColor: c.background,
    fontFamily: 'NotoSans',
    colorScheme: ColorScheme.fromSeed(
      seedColor: c.primary,
      brightness: brightness,
    ).copyWith(
      primary: c.primary,
      onPrimary: c.onPrimary,
      surface: c.surface,
      error: c.error,
    ),
    dividerColor: c.divider,
    splashFactory: InkRipple.splashFactory,
    extensions: [c],
  );
}

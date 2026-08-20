import 'package:flutter/material.dart';

enum AppColorway { sage, clay, olive }

@immutable
class AppColors extends ThemeExtension<AppColors> {
  const AppColors({
    required this.background,
    required this.surface,
    required this.surfaceMuted,
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

  final Color background;
  final Color surface;
  final Color surfaceMuted;
  final Color divider;
  final Color textPrimary;
  final Color textSecondary;
  final Color actionHover;
  final Color actionSelected;
  final Color primary;
  final Color onPrimary;
  final Color error;
  final Color warnBg;
  final Color warnFg;
  final Color inputBorder;
  final Color good;
  final Color warn;

  static const sageLight = AppColors(
    background: Color(0xFFF5EAD8),
    surface: Color(0xFFFDF8EE),
    surfaceMuted: Color(0xFFF1E3CF),
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
    surfaceMuted: Color(0xFF30281E),
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

  static const clayLight = AppColors(
    background: Color(0xFFF7ECDC),
    surface: Color(0xFFFFFAF3),
    surfaceMuted: Color(0xFFF2DECA),
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
    surfaceMuted: Color(0xFF35281E),
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

  static const oliveLight = AppColors(
    background: Color(0xFFF4F1E6),
    surface: Color(0xFFFDFCF7),
    surfaceMuted: Color(0xFFE7E4D5),
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
    surfaceMuted: Color(0xFF2A2D20),
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

  static AppColors resolve(AppColorway colorway, Brightness brightness) {
    return switch ((colorway, brightness)) {
      (AppColorway.sage, Brightness.light) => sageLight,
      (AppColorway.sage, Brightness.dark) => sageDark,
      (AppColorway.clay, Brightness.light) => clayLight,
      (AppColorway.clay, Brightness.dark) => clayDark,
      (AppColorway.olive, Brightness.light) => oliveLight,
      (AppColorway.olive, Brightness.dark) => oliveDark,
    };
  }

  @override
  AppColors copyWith({
    Color? background,
    Color? surface,
    Color? surfaceMuted,
    Color? divider,
    Color? textPrimary,
    Color? textSecondary,
    Color? actionHover,
    Color? actionSelected,
    Color? primary,
    Color? onPrimary,
    Color? error,
    Color? warnBg,
    Color? warnFg,
    Color? inputBorder,
    Color? good,
    Color? warn,
  }) {
    return AppColors(
      background: background ?? this.background,
      surface: surface ?? this.surface,
      surfaceMuted: surfaceMuted ?? this.surfaceMuted,
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
  }

  @override
  AppColors lerp(covariant AppColors? other, double t) {
    if (other == null) return this;
    return AppColors(
      background: Color.lerp(background, other.background, t)!,
      surface: Color.lerp(surface, other.surface, t)!,
      surfaceMuted: Color.lerp(surfaceMuted, other.surfaceMuted, t)!,
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

abstract final class AppText {
  static const _tabular = <FontFeature>[FontFeature.tabularFigures()];

  static const displayXL = TextStyle(
    fontFamily: 'Display',
    fontSize: 42,
    height: 1.15,
    letterSpacing: -0.42,
    fontWeight: FontWeight.w600,
  );
  static const displayL = TextStyle(
    fontFamily: 'Display',
    fontSize: 38,
    height: 1.15,
    letterSpacing: -0.38,
    fontWeight: FontWeight.w600,
  );
  static const displayM = TextStyle(
    fontFamily: 'Display',
    fontSize: 30,
    height: 1.2,
    letterSpacing: -0.30,
    fontWeight: FontWeight.w600,
  );
  static const displayS = TextStyle(
    fontFamily: 'Display',
    fontSize: 24,
    height: 1.2,
    letterSpacing: -0.24,
    fontWeight: FontWeight.w600,
  );
  static const screenTitle = TextStyle(
    fontFamily: 'Display',
    fontSize: 22,
    height: 1.25,
    fontWeight: FontWeight.w600,
  );
  static const bodyL = TextStyle(
    fontFamily: 'NotoSans',
    fontSize: 16,
    height: 1.4,
  );
  static const body = TextStyle(
    fontFamily: 'NotoSans',
    fontSize: 15,
    height: 1.4,
  );
  static const bodyS = TextStyle(
    fontFamily: 'NotoSans',
    fontSize: 14,
    height: 1.45,
  );
  static const caption = TextStyle(
    fontFamily: 'NotoSans',
    fontSize: 13,
    height: 1.5,
  );
  static const captionS = TextStyle(
    fontFamily: 'NotoSans',
    fontSize: 12,
    height: 1.45,
  );
  static const sectionLabel = TextStyle(
    fontFamily: 'NotoSans',
    fontSize: 12,
    fontWeight: FontWeight.w600,
    letterSpacing: 0.6,
  );
  static const button = TextStyle(
    fontFamily: 'NotoSans',
    fontSize: 15,
    fontWeight: FontWeight.w600,
    letterSpacing: 0.18,
  );

  static TextStyle numeric(TextStyle base) =>
      base.copyWith(fontFeatures: _tabular);
}

abstract final class AppRadii {
  static const card = 20.0;
  static const sheet = 28.0;
  static const field = 14.0;
  static const chip = 999.0;
  static const mark = 11.0;
  static const markLarge = 14.0;
}

abstract final class AppSpacing {
  static const gutter = 24.0;
  static const cardPad = 16.0;
  static const rowMinHeight = 56.0;
  static const tapTarget = 44.0;
  static const navHeight = 56.0;
  static const editFooterClearance = 190.0;
}

ThemeData buildTheme(AppColors colors, Brightness brightness) {
  final scheme =
      ColorScheme.fromSeed(
        seedColor: colors.primary,
        brightness: brightness,
      ).copyWith(
        primary: colors.primary,
        onPrimary: colors.onPrimary,
        surface: colors.surface,
        onSurface: colors.textPrimary,
        error: colors.error,
        outline: colors.inputBorder,
        outlineVariant: colors.divider,
        surfaceContainerLowest: colors.surface,
        surfaceContainerLow: colors.surfaceMuted,
        surfaceContainer: colors.surfaceMuted,
        surfaceContainerHigh: colors.surfaceMuted,
      );
  final base = ThemeData(
    useMaterial3: true,
    brightness: brightness,
    colorScheme: scheme,
    scaffoldBackgroundColor: colors.background,
    fontFamily: 'NotoSans',
    dividerColor: colors.divider,
    materialTapTargetSize: MaterialTapTargetSize.padded,
    splashFactory: InkRipple.splashFactory,
    extensions: <ThemeExtension<dynamic>>[colors],
  );
  final textTheme = base.textTheme
      .copyWith(
        displayLarge: AppText.displayXL,
        displayMedium: AppText.displayL,
        displaySmall: AppText.displayM,
        headlineMedium: AppText.displayS,
        headlineSmall: AppText.screenTitle,
        titleMedium: AppText.bodyL.copyWith(fontWeight: FontWeight.w600),
        bodyLarge: AppText.bodyL,
        bodyMedium: AppText.body,
        bodySmall: AppText.bodyS,
        labelLarge: AppText.button,
        labelMedium: AppText.caption,
        labelSmall: AppText.captionS,
      )
      .apply(bodyColor: colors.textPrimary, displayColor: colors.textPrimary);

  OutlineInputBorder inputBorder(Color color, [double width = 1]) =>
      OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppRadii.field),
        borderSide: BorderSide(color: color, width: width),
      );

  return base.copyWith(
    textTheme: textTheme,
    appBarTheme: AppBarTheme(
      backgroundColor: colors.background,
      foregroundColor: colors.textPrimary,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      centerTitle: false,
      titleTextStyle: AppText.screenTitle.copyWith(color: colors.textPrimary),
    ),
    cardTheme: CardThemeData(
      color: colors.surface,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppRadii.card),
        side: BorderSide(color: colors.divider),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: colors.surface,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 15),
      hintStyle: AppText.body.copyWith(color: colors.textSecondary),
      labelStyle: AppText.bodyS.copyWith(color: colors.textSecondary),
      border: inputBorder(colors.inputBorder),
      enabledBorder: inputBorder(colors.inputBorder),
      focusedBorder: inputBorder(colors.primary, 1.5),
      errorBorder: inputBorder(colors.error),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(AppSpacing.tapTarget, 52),
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
        shape: const StadiumBorder(),
        textStyle: AppText.button,
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(AppSpacing.tapTarget, 52),
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
        foregroundColor: colors.textPrimary,
        side: BorderSide(color: colors.inputBorder),
        shape: const StadiumBorder(),
        textStyle: AppText.button,
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        minimumSize: const Size(AppSpacing.tapTarget, AppSpacing.tapTarget),
        foregroundColor: colors.primary,
        textStyle: AppText.button,
      ),
    ),
    chipTheme: base.chipTheme.copyWith(
      backgroundColor: colors.surface,
      selectedColor: colors.actionSelected,
      side: BorderSide(color: colors.divider),
      shape: const StadiumBorder(),
      labelStyle: AppText.caption.copyWith(color: colors.textPrimary),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
    ),
    navigationBarTheme: NavigationBarThemeData(
      height: AppSpacing.navHeight,
      elevation: 0,
      backgroundColor: colors.surface,
      surfaceTintColor: Colors.transparent,
      indicatorColor: colors.actionSelected,
      labelTextStyle: WidgetStatePropertyAll(
        AppText.captionS.copyWith(
          color: colors.textPrimary,
          fontWeight: FontWeight.w600,
        ),
      ),
      iconTheme: WidgetStateProperty.resolveWith(
        (states) => IconThemeData(
          color: states.contains(WidgetState.selected)
              ? colors.primary
              : colors.textSecondary,
          size: 22,
        ),
      ),
    ),
    bottomSheetTheme: BottomSheetThemeData(
      backgroundColor: colors.surface,
      surfaceTintColor: Colors.transparent,
      modalBackgroundColor: colors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(
          top: Radius.circular(AppRadii.sheet),
        ),
      ),
      showDragHandle: true,
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: colors.surface,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppRadii.card),
      ),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: colors.textPrimary,
      contentTextStyle: AppText.bodyS.copyWith(color: colors.surface),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppRadii.field),
      ),
    ),
    progressIndicatorTheme: ProgressIndicatorThemeData(
      color: colors.primary,
      linearTrackColor: colors.divider,
    ),
    dividerTheme: DividerThemeData(
      color: colors.divider,
      space: 1,
      thickness: 1,
    ),
    pageTransitionsTheme: const PageTransitionsTheme(
      builders: <TargetPlatform, PageTransitionsBuilder>{
        TargetPlatform.android: FadeForwardsPageTransitionsBuilder(),
        TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
      },
    ),
  );
}

extension ThemeContext on BuildContext {
  AppColors get appColors => Theme.of(this).extension<AppColors>()!;
}

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:receipts_hub/app.dart';
import 'package:receipts_hub/core/design/app_theme.dart';
import 'package:receipts_hub/core/routing/app_router.dart';
import 'package:receipts_hub/features/onboarding/onboarding_screens.dart';

import 'fixtures/household_fixture.dart';

Future<void> setPhoneSurface(WidgetTester tester) async {
  tester.view.physicalSize = const Size(390, 844);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

Future<ByteData> loadMaterialIcons() async {
  final separator = Platform.pathSeparator;
  var flutterCacheDirectory = File(Platform.resolvedExecutable).parent;
  while (!flutterCacheDirectory.path.toLowerCase().endsWith(
    '${separator}cache',
  )) {
    final parent = flutterCacheDirectory.parent;
    if (parent.path == flutterCacheDirectory.path) {
      throw StateError('Could not locate the Flutter SDK cache.');
    }
    flutterCacheDirectory = parent;
  }
  final font = File(
    '${flutterCacheDirectory.path}${separator}artifacts${separator}material_fonts${separator}materialicons-regular.otf',
  );
  final bytes = await font.readAsBytes();
  return bytes.buffer.asByteData(bytes.offsetInBytes, bytes.lengthInBytes);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    final notoSans = FontLoader('NotoSans')
      ..addFont(rootBundle.load('assets/fonts/NotoSans-Light.ttf'))
      ..addFont(rootBundle.load('assets/fonts/NotoSans-Regular.ttf'))
      ..addFont(rootBundle.load('assets/fonts/NotoSans-Medium.ttf'))
      ..addFont(rootBundle.load('assets/fonts/NotoSans-SemiBold.ttf'))
      ..addFont(rootBundle.load('assets/fonts/NotoSans-Bold.ttf'));
    final display = FontLoader('Display')
      ..addFont(rootBundle.load('assets/fonts/NotoSans-SemiBold.ttf'));
    final materialIcons = FontLoader('MaterialIcons')
      ..addFont(loadMaterialIcons());
    await Future.wait(<Future<void>>[
      notoSans.load(),
      display.load(),
      materialIcons.load(),
    ]);
  });

  for (final colorway in AppColorway.values) {
    for (final brightness in Brightness.values) {
      testWidgets('welcome ${colorway.name} ${brightness.name} golden', (
        tester,
      ) async {
        await setPhoneSurface(tester);
        final colors = AppColors.resolve(colorway, brightness);
        await tester.pumpWidget(
          ProviderScope(
            overrides: releaseSurfaceOverrides(),
            child: MaterialApp(
              debugShowCheckedModeBanner: false,
              theme: buildTheme(colors, brightness),
              home: const RepaintBoundary(
                key: Key('golden-boundary'),
                child: WelcomeScreen(),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
        await expectLater(
          find.byKey(const Key('golden-boundary')),
          matchesGoldenFile(
            'goldens/welcome_${colorway.name}_${brightness.name}.png',
          ),
        );
      });
    }
  }

  testWidgets('home reference golden', (tester) async {
    await goldenRoute(tester, '/home', 'goldens/home_sage_light.png');
  });

  testWidgets('item comparison reference golden', (tester) async {
    await goldenRoute(
      tester,
      '/items/Full%20cream%20milk?from=insights',
      'goldens/item_comparison_sage_light.png',
    );
  });

  testWidgets('home without a household golden', (tester) async {
    // The state a real fresh install lands on. Worth a baseline of its own:
    // this is what used to be filled with sample money.
    await goldenRoute(
      tester,
      '/home',
      'goldens/home_signed_out_sage_light.png',
      household: false,
    );
  });
}

/// Render one route at the reference viewport and compare it to a baseline.
Future<void> goldenRoute(
  WidgetTester tester,
  String location,
  String goldenPath, {
  bool household = true,
}) async {
  await setPhoneSurface(tester);
  final router = createAppRouter(initialLocation: location);
  addTearDown(router.dispose);
  await tester.pumpWidget(
    ProviderScope(
      overrides: household ? householdOverrides() : releaseSurfaceOverrides(),
      child: RepaintBoundary(
        key: const Key('golden-boundary'),
        child: ReceiptsHubApp(router: router),
      ),
    ),
  );
  await tester.pumpAndSettle();
  await expectLater(
    find.byKey(const Key('golden-boundary')),
    matchesGoldenFile(goldenPath),
  );
}

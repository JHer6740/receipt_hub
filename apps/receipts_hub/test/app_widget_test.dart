import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:receipts_hub/app.dart';
import 'package:receipts_hub/core/routing/app_router.dart';
import 'package:receipts_hub/features/onboarding/splash_screen.dart';
import 'package:receipts_hub/core/models/models.dart';
import 'package:receipts_hub/core/state/app_state.dart';

import 'fixtures/household_fixture.dart';

/// Pump the app at [location] with a loaded household behind it.
///
/// The household comes from `test/fixtures`, never from the app: shipping a
/// sample ledger inside `lib/` is what put invented money on real screens.
Future<GoRouter> pumpHub(
  WidgetTester tester, {
  required String location,
  bool household = true,
}) async {
  tester.view.physicalSize = const Size(390, 844);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  final router = createAppRouter(initialLocation: location);
  addTearDown(router.dispose);
  await tester.pumpWidget(
    ProviderScope(
      overrides: household ? householdOverrides() : releaseSurfaceOverrides(),
      child: ReceiptsHubApp(router: router),
    ),
  );
  await tester.pumpAndSettle();
  return router;
}

void main() {
  testWidgets('first run explains the product and leads to sign-in', (
    tester,
  ) async {
    await pumpHub(tester, location: '/welcome', household: false);

    expect(find.text('Your receipts,\nworth something to you'), findsOneWidget);
    expect(find.text('Photograph the receipt'), findsOneWidget);

    // No consent is asked for a shared price index that will not exist at
    // launch, and there is no way into the ledger before signing in.
    expect(find.byType(Switch), findsNothing);
    expect(find.text('Join a household'), findsNothing);

    // No host address, no PIN, no talk of a home computer: an account.
    expect(find.textContaining('host'), findsNothing);
    expect(find.text('Developer: connect to a host'), findsNothing);

    await tester.tap(find.text('Get started'));
    await tester.pumpAndSettle();
    expect(find.text('Create your account'), findsOneWidget);
    expect(find.byKey(const Key('email-field')), findsOneWidget);
    expect(find.byKey(const Key('password-field')), findsOneWidget);
  });

  testWidgets('a household with no data renders a state, never a zero total', (
    tester,
  ) async {
    await pumpHub(tester, location: '/home', household: false);

    // Not signed in: Home must not present an empty ledger as this month's
    // spending, and must not show sample figures either.
    expect(find.byKey(const Key('gate-sign-in')), findsOneWidget);
    expect(find.byKey(const Key('home-month-total')), findsNothing);
  });

  testWidgets('bottom navigation opens List and item entry is interactive', (
    tester,
  ) async {
    await pumpHub(tester, location: '/home');

    await tester.tap(find.text('List').last);
    await tester.pumpAndSettle();
    expect(find.text('TO BUY · 2'), findsOneWidget);

    await tester.enterText(find.byKey(const Key('add-item-field')), 'Coffee');
    await tester.tap(find.byTooltip('Add item'));
    await tester.pump();
    expect(find.text('Coffee'), findsOneWidget);
    expect(find.text('TO BUY · 3'), findsOneWidget);

    await tester.tap(find.widgetWithText(CheckboxListTile, 'Coffee'));
    await tester.pump();
    expect(find.text('PICKED UP · 2'), findsOneWidget);
  });

  testWidgets('capture needs a household before it will open the camera', (
    tester,
  ) async {
    await pumpHub(tester, location: '/capture', household: false);

    // Receipts are filed into a household, so there is nothing to capture
    // until the account is in one.
    expect(find.byKey(const Key('capture-needs-household')), findsOneWidget);
    expect(find.bySemanticsLabel('Take photo'), findsNothing);
  });

  testWidgets(
    'the shutter reports a missing camera instead of queueing a page',
    (tester) async {
      await pumpHub(tester, location: '/capture');

      expect(find.text('Read'), findsNothing);
      await tester.tap(find.bySemanticsLabel('Take photo'));
      await tester.pumpAndSettle();

      // No camera means no photo. This used to append a `demo://` page that
      // could never upload.
      expect(
        find.text('The camera is not ready. Import from your gallery instead.'),
        findsOneWidget,
      );
      expect(find.text('Page 1'), findsNothing);
      expect(find.text('Read'), findsNothing);
    },
  );

  testWidgets('receipt search and attention filter expose useful states', (
    tester,
  ) async {
    await pumpHub(tester, location: '/receipts');

    expect(find.text('Woolworths Coburg'), findsOneWidget);
    await tester.enterText(
      find.byKey(const ValueKey<String>('receipt-search')),
      'ALDI',
    );
    await tester.pump();
    expect(find.text('ALDI Brunswick'), findsOneWidget);
    expect(find.text('Woolworths Coburg'), findsNothing);

    await tester.enterText(
      find.byKey(const ValueKey<String>('receipt-search')),
      'No such shop',
    );
    await tester.pump();
    expect(find.text('No receipts match'), findsOneWidget);
  });

  testWidgets('review marks uncertain fields and names what filing needs', (
    tester,
  ) async {
    await pumpHub(tester, location: '/receipts/r-1006/edit');

    expect(find.text('Review suggested'), findsOneWidget);
    expect(find.byTooltip('Lower-confidence field'), findsNWidgets(2));

    // This receipt's line items are $1.00 short of its stated total, so the
    // balance is flagged and filing is offered without being blocked.
    expect(find.textContaining('short of the receipt total'), findsOneWidget);
    expect(find.text('File anyway'), findsOneWidget);

    // Remove the merchant and the action names only what is missing.
    await tester.enterText(
      find.byKey(const ValueKey<String>('merchant-r-1006')),
      '',
    );
    await tester.pump();
    expect(find.text('Add a merchant'), findsOneWidget);
  });

  testWidgets('every comparison price names source and freshness', (
    tester,
  ) async {
    await pumpHub(tester, location: '/items/Full%20cream%20milk?from=insights');

    await tester.scrollUntilVisible(
      find.text('Your receipts'),
      260,
      scrollable: find.byType(Scrollable).last,
    );
    expect(find.text('Your receipts'), findsWidgets);
    expect(find.text('Published'), findsOneWidget);
    expect(find.text('6 shoppers'), findsWidgets);
    expect(find.textContaining('seen '), findsWidgets);
    expect(find.text('Best value'), findsOneWidget);

    await tester.ensureVisible(find.text('Everywhere 5'));
    await tester.tap(find.text('Everywhere 5'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('Too few reports to rely on'),
      260,
      scrollable: find.byType(Scrollable).last,
    );
    expect(find.text('Too few reports to rely on'), findsOneWidget);
    expect(find.text('One report looks off — not counted'), findsOneWidget);
  });

  testWidgets('comparison without coverage refuses to make a claim', (
    tester,
  ) async {
    // No comparison evidence: Rivals must say so rather than argue from
    // whatever it can find.
    await pumpHub(tester, location: '/rivals', household: false);
    expect(find.byKey(const Key('rivals-no-coverage')), findsOneWidget);
  });

  testWidgets('a signed-out deep link cannot reach the ledger', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    // There was no redirect at all, so /home opened for anyone who linked to
    // it and `onboardingComplete` was written four times and read never.
    final router = createAppRouter(
      initialLocation: '/home',
      readState: () =>
          const AppState(receipts: <Receipt>[], shopping: <ShoppingEntry>[]),
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(
      ProviderScope(
        overrides: releaseSurfaceOverrides(),
        child: ReceiptsHubApp(router: router),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Your receipts,\nworth something to you'), findsOneWidget);
    expect(find.byType(NavigationBar), findsNothing);
  });

  testWidgets('a restoring session waits instead of showing first run', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final router = createAppRouter(
      initialLocation: '/home',
      readState: () => const AppState(
        receipts: <Receipt>[],
        shopping: <ShoppingEntry>[],
        connection: HubConnection.connecting,
      ),
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(
      ProviderScope(
        overrides: releaseSurfaceOverrides(),
        child: ReceiptsHubApp(router: router),
      ),
    );
    await tester.pumpAndSettle();

    // Holding on the splash, not bouncing a signed-in person to the door.
    expect(find.byType(SplashScreen), findsOneWidget);
    expect(find.text('Get started'), findsNothing);
  });

  testWidgets('account offers a way in to approving join requests', (
    tester,
  ) async {
    await pumpHub(tester, location: '/account');

    // Account used to carry a "Members" row that only raised a toast, so a
    // join request could not be approved by anybody.
    expect(find.byKey(const Key('account-people')), findsOneWidget);
    await tester.tap(find.byKey(const Key('account-people')));
    await tester.pumpAndSettle();
    expect(find.text('People'), findsWidgets);
  });

  testWidgets(
    'reference layout keeps navigation, text and targets accessible',
    (tester) async {
      await pumpHub(tester, location: '/home');

      expect(tester.getSize(find.byType(NavigationBar)).height, 56);
      for (final button in find.byType(IconButton).evaluate()) {
        final renderBox = button.renderObject as RenderBox?;
        if (renderBox != null && renderBox.hasSize) {
          expect(renderBox.size.width, greaterThanOrEqualTo(44));
          expect(renderBox.size.height, greaterThanOrEqualTo(44));
        }
      }
      for (final paragraph in tester.renderObjectList<RenderParagraph>(
        find.byType(RichText),
      )) {
        final size = paragraph.text.style?.fontSize;
        if (size != null) expect(size, greaterThanOrEqualTo(12));
      }
    },
  );
}

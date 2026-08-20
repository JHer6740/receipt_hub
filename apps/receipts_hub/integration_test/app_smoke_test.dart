import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:receipts_hub/app.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('first run reaches every primary ledger destination', (
    tester,
  ) async {
    await tester.pumpWidget(
      const ProviderScope(child: ReceiptsHubApp()),
    );
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.text('Get started'));
    await tester.tap(find.text('Get started'));
    await tester.pumpAndSettle();
    expect(find.text('Receipts Hub'), findsOneWidget);

    await tester.tap(find.text('Receipts').last);
    await tester.pumpAndSettle();
    expect(find.text('Search merchants'), findsOneWidget);

    await tester.tap(find.text('Insights').last);
    await tester.pumpAndSettle();
    expect(find.text('EVERY COLLECTION, AUGUST'), findsOneWidget);

    await tester.tap(find.text('List').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('add-item-field')), 'Coffee');
    await tester.tap(find.byTooltip('Add item'));
    await tester.pump();
    expect(find.text('Coffee'), findsOneWidget);
  });
}

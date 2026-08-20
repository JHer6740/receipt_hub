// A deterministic household for widget and golden tests.
//
// This data used to live in `lib/core/data/demo_data.dart` and was seeded into
// the running app, which is how invented money reached Home, Insights, the
// ledger and the comparison screens of a real household. It belongs here: the
// app ships with an empty ledger and tests supply their own.

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:receipts_hub/core/models/models.dart';
import 'package:receipts_hub/core/network/api_models.dart' as wire;
import 'package:receipts_hub/core/state/app_state.dart';
import 'package:receipts_hub/features/compare/comparison_data.dart';
import 'package:receipts_hub/features/developer/host_connection_screen.dart';

abstract final class HouseholdFixture {
  /// A fixed clock so assertions do not drift with the calendar.
  static final DateTime now = DateTime.utc(2026, 8, 15, 10, 30);

  static const collections = <SpendCollection>[
    SpendCollection(
      key: 'groceries',
      name: 'Groceries',
      monthCents: 42837,
      receiptCount: 12,
      deltaPct: -8,
    ),
    SpendCollection(
      key: 'home',
      name: 'Home',
      monthCents: 12840,
      receiptCount: 3,
      deltaPct: 14,
    ),
    SpendCollection(
      key: 'health',
      name: 'Health',
      monthCents: 7649,
      receiptCount: 4,
      deltaPct: -3,
    ),
    SpendCollection(
      key: 'travel',
      name: 'Travel',
      monthCents: 4620,
      receiptCount: 2,
      deltaPct: 6,
    ),
  ];

  static final receipts = <Receipt>[
    Receipt(
      id: 'r-1007',
      merchant: 'Woolworths Coburg',
      purchasedAt: DateTime.utc(2026, 8, 14, 18, 42),
      txnRef: '843921',
      collectionKey: 'groceries',
      status: ReceiptStatus.confirmed,
      totalCents: 14872,
      taxCents: 913,
      items: const <LineItem>[
        LineItem(id: 'l-1', name: 'Full cream milk 1 L', qty: 1, lineCents: 520),
        LineItem(id: 'l-2', name: 'Sourdough loaf', qty: 1, lineCents: 750),
        LineItem(
          id: 'l-3',
          name: 'Free range eggs 12 pack',
          qty: 1,
          lineCents: 890,
        ),
        LineItem(
          id: 'l-4',
          name: 'Fruit and vegetables',
          qty: 1,
          lineCents: 6912,
        ),
        LineItem(
          id: 'l-5',
          name: 'Pantry and household',
          qty: 1,
          lineCents: 4800,
        ),
      ],
      pageImagePaths: const <String>['receipt_1007_page_1.jpg'],
    ),
    Receipt(
      id: 'r-1006',
      merchant: 'ALDI Brunswick',
      purchasedAt: DateTime.utc(2026, 8, 12, 17, 15),
      txnRef: 'A-20156',
      collectionKey: 'groceries',
      status: ReceiptStatus.review,
      totalCents: 8635,
      taxCents: 432,
      items: const <LineItem>[
        LineItem(id: 'l-6', name: 'Weekly groceries', qty: 1, lineCents: 8535),
      ],
      pageImagePaths: const <String>['receipt_1006_page_1.jpg'],
    ),
    Receipt(
      id: 'r-1005',
      merchant: 'Preston Market',
      purchasedAt: DateTime.utc(2026, 8, 10, 11, 5),
      txnRef: 'STALL-18',
      collectionKey: 'groceries',
      status: ReceiptStatus.confirmed,
      totalCents: 4260,
      taxCents: 0,
      items: const <LineItem>[
        LineItem(id: 'l-7', name: 'Fresh produce', qty: 1, lineCents: 4260),
      ],
    ),
    Receipt(
      id: 'r-1004',
      merchant: 'Chemist Warehouse',
      purchasedAt: DateTime.utc(2026, 8, 8, 14, 24),
      txnRef: 'CW-77831',
      collectionKey: 'health',
      status: ReceiptStatus.review,
      totalCents: 2749,
      taxCents: 250,
      items: const <LineItem>[
        LineItem(id: 'l-8', name: 'Pharmacy', qty: 1, lineCents: 2749),
      ],
    ),
    Receipt(
      id: 'r-1003',
      merchant: 'Bunnings Coburg',
      purchasedAt: DateTime.utc(2026, 8, 5, 9, 48),
      txnRef: 'BN-8496',
      collectionKey: 'home',
      status: ReceiptStatus.confirmed,
      totalCents: 12840,
      taxCents: 1167,
      items: const <LineItem>[
        LineItem(id: 'l-9', name: 'Garden and repair', qty: 1, lineCents: 12840),
      ],
      pageImagePaths: const <String>['receipt_1003_page_1.jpg'],
    ),
    Receipt(
      id: 'r-1002',
      merchant: 'Metro Fuel',
      purchasedAt: DateTime.utc(2026, 8, 2, 8, 12),
      txnRef: 'PUMP-06',
      collectionKey: 'travel',
      status: ReceiptStatus.failed,
      totalCents: 4620,
      taxCents: 420,
      items: const <LineItem>[],
      pageImagePaths: const <String>['receipt_1002_page_1.jpg'],
    ),
  ];

  static const shopping = <ShoppingEntry>[
    ShoppingEntry(id: 's-1', name: 'Full cream milk'),
    ShoppingEntry(id: 's-2', name: 'Free range eggs'),
    ShoppingEntry(id: 's-3', name: 'Sourdough loaf', isPickedUp: true),
  ];

  static const monthTrend = <wire.MonthPoint>[
    wire.MonthPoint(month: '2026-03', totalCents: 48620),
    wire.MonthPoint(month: '2026-04', totalCents: 51240),
    wire.MonthPoint(month: '2026-05', totalCents: 49880),
    wire.MonthPoint(month: '2026-06', totalCents: 53640),
    wire.MonthPoint(month: '2026-07', totalCents: 57990),
    wire.MonthPoint(month: '2026-08', totalCents: 63546),
  ];

  static const merchants = <Merchant>[
    Merchant(
      key: 'local',
      name: 'Local Pantry',
      shortName: 'Local',
      minutesAway: 6,
      wins: <String>['short trip', 'reliable staples'],
      edge: 'the short trip and reliable staples',
    ),
    Merchant(
      key: 'market',
      name: 'Market Fresh',
      shortName: 'Market',
      minutesAway: 12,
      wins: <String>['fresh produce', 'single packs'],
      edge: 'fresh produce and single packs',
    ),
    Merchant(
      key: 'warehouse',
      name: 'Warehouse Grocer',
      shortName: 'Warehouse',
      minutesAway: 22,
      wins: <String>['bulk value', 'published prices'],
      edge: 'bulk value and published prices',
    ),
  ];

  static final trackedItems = <TrackedItem>[
    TrackedItem(
      name: 'Full cream milk',
      collection: 'Groceries',
      rhythm: 'Every fortnight',
      timesBought: 18,
      purchasesPerYear: 26,
      pack: const PackSize(1, 'L', '1 L'),
      monthlySeriesCents: const <int>[480, 490, 500, 500, 510, 520],
      quotes: const <PriceQuote>[
        PriceQuote(
          merchantName: 'Local Pantry',
          note: '6 min · your usual shop',
          cents: 520,
          source: PriceSource.you,
          daysSinceSeen: 1,
        ),
        PriceQuote(
          merchantName: 'Market Fresh',
          note: '12 min · single pack',
          cents: 480,
          source: PriceSource.crowd,
          confidence: Confidence.mixed,
          reportCount: 6,
          daysSinceSeen: 2,
          bandCents: 20,
          hasStockSignal: false,
        ),
        PriceQuote(
          merchantName: 'Warehouse Grocer',
          note: '22 min · limited range · double pack',
          cents: 840,
          packMultiple: 2,
          source: PriceSource.published,
          daysSinceSeen: 0,
        ),
        PriceQuote(
          merchantName: 'Pop-up Foods',
          note: '18 min · weekend only',
          cents: 390,
          source: PriceSource.crowd,
          confidence: Confidence.thin,
          reportCount: 2,
          daysSinceSeen: 8,
          hasStockSignal: false,
        ),
        PriceQuote(
          merchantName: 'Glitch Mart',
          note: 'unverified report',
          cents: 200,
          source: PriceSource.crowd,
          confidence: Confidence.high,
          reportCount: 9,
          daysSinceSeen: 1,
          isOutlier: true,
          hasStockSignal: false,
        ),
      ],
      history: <PurchaseRecord>[
        PurchaseRecord(
          date: DateTime.utc(2026, 8, 14),
          merchantName: 'Local Pantry',
          cents: 520,
        ),
        PurchaseRecord(
          date: DateTime.utc(2026, 7, 30),
          merchantName: 'Local Pantry',
          cents: 510,
        ),
        PurchaseRecord(
          date: DateTime.utc(2026, 7, 15),
          merchantName: 'Market Fresh',
          cents: 490,
        ),
      ],
    ),
    TrackedItem(
      name: 'Free range eggs',
      collection: 'Groceries',
      rhythm: 'Every three weeks',
      timesBought: 12,
      purchasesPerYear: 17,
      pack: const PackSize(1, '', '12 pack'),
      monthlySeriesCents: const <int>[820, 820, 850, 850, 870, 890],
      quotes: const <PriceQuote>[
        PriceQuote(
          merchantName: 'Local Pantry',
          note: '6 min · reliable stock',
          cents: 890,
          source: PriceSource.you,
          daysSinceSeen: 1,
        ),
        PriceQuote(
          merchantName: 'Market Fresh',
          note: '12 min · local eggs',
          cents: 830,
          source: PriceSource.crowd,
          confidence: Confidence.high,
          reportCount: 12,
          daysSinceSeen: 3,
          hasStockSignal: false,
        ),
        PriceQuote(
          merchantName: 'Warehouse Grocer',
          note: '22 min · published',
          cents: 790,
          source: PriceSource.published,
        ),
      ],
      history: <PurchaseRecord>[
        PurchaseRecord(
          date: DateTime.utc(2026, 8, 14),
          merchantName: 'Local Pantry',
          cents: 890,
        ),
        PurchaseRecord(
          date: DateTime.utc(2026, 7, 20),
          merchantName: 'Local Pantry',
          cents: 870,
        ),
      ],
    ),
    TrackedItem(
      name: 'Sourdough loaf',
      collection: 'Groceries',
      rhythm: 'Weekly',
      timesBought: 31,
      purchasesPerYear: 48,
      pack: PackSize.each,
      monthlySeriesCents: const <int>[680, 690, 700, 720, 720, 750],
      quotes: const <PriceQuote>[
        PriceQuote(
          merchantName: 'Local Pantry',
          note: '6 min · baked daily',
          cents: 750,
          source: PriceSource.you,
          daysSinceSeen: 1,
        ),
        PriceQuote(
          merchantName: 'Market Fresh',
          note: '12 min · bakery counter',
          cents: 720,
          source: PriceSource.crowd,
          confidence: Confidence.high,
          reportCount: 14,
          daysSinceSeen: 1,
          hasStockSignal: false,
        ),
        PriceQuote(
          merchantName: 'Warehouse Grocer',
          note: '22 min · published',
          cents: 700,
          source: PriceSource.published,
          daysSinceSeen: 0,
        ),
      ],
      history: <PurchaseRecord>[
        PurchaseRecord(
          date: DateTime.utc(2026, 8, 14),
          merchantName: 'Local Pantry',
          cents: 750,
        ),
      ],
    ),
  ];

  /// A household that has loaded, so the surfaces render content rather than
  /// their loading or unavailable state.
  static AppState get appState => AppState(
    receipts: receipts,
    shopping: shopping,
    connection: HubConnection.connected,
    onboardingComplete: true,
    householdName: 'Receipts Hub',
    monthTotalCents: 63546,
    monthTrend: monthTrend,
    collections: collections,
  );

  static ComparisonBasket get comparisonBasket => ComparisonBasket(
    merchants: merchants,
    items: trackedItems,
    usualMerchantKey: 'local',
  );
}

/// Seeds a loaded household without touching the network.
class _SeededAppController extends AppController {
  _SeededAppController(this._seed);

  final AppState _seed;

  @override
  AppState build() => _seed;
}

/// Provider overrides that put a loaded household behind the UI.
List<Override> householdOverrides({AppState? state}) => <Override>[
  appControllerProvider.overrideWith(
    () => _SeededAppController(state ?? HouseholdFixture.appState),
  ),
  comparisonBasketProvider.overrideWithValue(
    HouseholdFixture.comparisonBasket,
  ),
  // Baselines and assertions describe the shipped surface, so debug-only
  // developer affordances stay out of them.
  developerToolsProvider.overrideWithValue(false),
];

/// Overrides for a signed-out app that still hides developer affordances.
List<Override> releaseSurfaceOverrides() => <Override>[
  developerToolsProvider.overrideWithValue(false),
];

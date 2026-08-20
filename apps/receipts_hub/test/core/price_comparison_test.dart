import 'package:flutter_test/flutter_test.dart' hide ComparisonResult;
import 'package:receipts_hub/core/models/models.dart';
import 'package:receipts_hub/core/pricing/price_comparison.dart';

void main() {
  group('PriceComparator evidence invariants', () {
    test('weak prices stay visible but never support a claim', () {
      final result = _compare(_comparisonFixture());

      expect(result.isAvailable, isTrue);
      expect(result.rows, hasLength(5));

      final softRows = result.rows.where((row) => row.isSoft).toList();
      expect(
        softRows.map((row) => row.quote.merchantName),
        unorderedEquals(<String>['Pop-up', 'Glitch quote']),
      );
      expect(softRows.every((row) => row.saveLabel == null), isTrue);
      expect(softRows.every((row) => !row.isBestValue), isTrue);

      expect(result.rangeLow, r'$4.20/L');
      expect(result.rangeHigh, r'$5.20/L');
      expect(result.rangeNote, 'across 3 confirmed prices');
    });

    test('verdict uses paid minus the lowest confirmed unit price', () {
      final result = _compare(_comparisonFixture());

      expect(result.savedHeadline, r'You could have kept $1.00 on this one');
      expect(result.verdictHeadline, r'Warehouse undercuts you by $1.00/L');
      expect(result.verdictAnnualSaving, r'$26.00/yr');
      expect(result.sourceLine, 'From their published price.');

      // The confirmed market spread is $1.00/L. The much larger raw-pack
      // spread and the weak $2.00 quote must not become a savings claim.
      expect(result.savedHeadline, isNot(contains(r'$3.20')));
      expect(result.savedHeadline, isNot(contains(r'$6.40')));
    });

    test('mixed packs use unit ranges and preserve both display bases', () {
      final packResult = _compare(
        _comparisonFixture(),
        basis: CompareBasis.perPack,
      );
      final unitResult = _compare(
        _comparisonFixture(),
        basis: CompareBasis.perUnit,
      );

      expect(packResult.showBasisToggle, isTrue);
      expect(packResult.basisUnitLabel, 'Per L');
      expect(packResult.rangeLow, r'$4.20/L');
      expect(packResult.rangeHigh, r'$5.20/L');

      final marketPack = packResult.rows.singleWhere(
        (row) => row.quote.merchantName == 'Market',
      );
      expect(marketPack.priceLabel, r'$4.60–$5.00');
      expect(marketPack.subLabel, r'$4.60–$5.00/L');

      final marketUnit = unitResult.rows.singleWhere(
        (row) => row.quote.merchantName == 'Market',
      );
      expect(marketUnit.priceLabel, r'$4.60–$5.00/L');
      expect(marketUnit.subLabel, r'$4.60–$5.00 pack');
    });

    test('best-value crown follows the winner across sort bases', () {
      final packResult = _compare(
        _comparisonFixture(),
        basis: CompareBasis.perPack,
      );
      final unitResult = _compare(
        _comparisonFixture(),
        basis: CompareBasis.perUnit,
      );

      final packWinners = packResult.rows
          .where((row) => row.isBestValue)
          .toList();
      final unitWinners = unitResult.rows
          .where((row) => row.isBestValue)
          .toList();

      expect(packWinners, hasLength(1));
      expect(unitWinners, hasLength(1));
      expect(packWinners.single.quote.merchantName, 'Warehouse');
      expect(unitWinners.single.quote.merchantName, 'Warehouse');
      expect(packResult.rows.last.quote.merchantName, 'Warehouse');
      expect(unitResult.rows.indexOf(unitWinners.single), isNot(0));
    });

    test('every comparison row exposes provenance and freshness', () {
      final result = _compare(_comparisonFixture());

      expect(result.rows.every((row) => row.sourceLabel.isNotEmpty), isTrue);
      expect(result.rows.every((row) => row.freshnessLabel.isNotEmpty), isTrue);
      expect(
        result.rows.map((row) => row.sourceLabel),
        unorderedEquals(<String>[
          'Your receipts',
          '6 shoppers',
          'Published',
          '2 shoppers',
          '20 shoppers',
        ]),
      );
    });
  });

  group('PriceComparator eligibility', () {
    test('empty purchase history returns an unavailable result', () {
      final item = _comparisonFixture(history: const <PurchaseRecord>[]);
      final comparator = _comparator(item);

      expect(comparator.eligibility.canCompare, isFalse);
      expect(
        comparator.eligibility.blocker,
        ComparisonBlocker.noPurchaseHistory,
      );

      final result = comparator.build();
      expect(result.isAvailable, isFalse);
      expect(result.rows, isEmpty);
      expect(result.savedHeadline, 'Not enough confirmed prices yet');
    });

    test('newest-first history is required without throwing', () {
      final ordered = _comparisonFixture().history;
      final item = _comparisonFixture(history: ordered.reversed.toList());
      final result = _comparator(item).build();

      expect(result.isAvailable, isFalse);
      expect(
        result.eligibility.blocker,
        ComparisonBlocker.historyNotNewestFirst,
      );
    });

    test('a scope with no prices returns an explicit blocker', () {
      final comparator = PriceComparator(
        item: _comparisonFixture(),
        scope: CompareScope.yourStores,
        basis: CompareBasis.perPack,
        yourMerchantNames: const <String>{'Unknown merchant'},
      );

      final result = comparator.build();
      expect(result.isAvailable, isFalse);
      expect(result.eligibility.blocker, ComparisonBlocker.noPricesInScope);
    });

    test('an all-weak pool cannot produce a verdict', () {
      final base = _comparisonFixture();
      final item = _comparisonFixture(
        quotes: base.quotes.where((quote) => !quote.isConfirmed).toList(),
      );

      final result = _comparator(item).build();
      expect(result.isAvailable, isFalse);
      expect(result.eligibility.blocker, ComparisonBlocker.noConfirmedPrices);
      expect(result.verdictAnnualSaving, isNull);
      expect(result.sourceLine, 'No price claim is shown.');
    });

    test('zero pack multiples are rejected before unit division', () {
      const invalid = PriceQuote(
        merchantName: 'Broken price',
        note: 'invalid fixture',
        cents: 400,
        packMultiple: 0,
        source: PriceSource.published,
      );
      final item = _comparisonFixture(quotes: const <PriceQuote>[invalid]);

      final result = _comparator(item).build();
      expect(result.isAvailable, isFalse);
      expect(result.eligibility.blocker, ComparisonBlocker.invalidQuoteBasis);
    });

    test('inconsistent crowd confidence is rejected explicitly', () {
      const invalid = PriceQuote(
        merchantName: 'Unproven price',
        note: 'missing crowd confidence',
        cents: 400,
        source: PriceSource.crowd,
        reportCount: 4,
      );
      final item = _comparisonFixture(quotes: const <PriceQuote>[invalid]);

      final result = _comparator(item).build();
      expect(result.isAvailable, isFalse);
      expect(
        result.eligibility.blocker,
        ComparisonBlocker.inconsistentEvidence,
      );
    });
  });

  group('Receipt and sharing consent', () {
    test('only a confirmed, fileable receipt may contribute', () {
      expect(_receipt(ReceiptStatus.review).mayContribute, isFalse);
      expect(_receipt(ReceiptStatus.failed).mayContribute, isFalse);
      expect(_receipt(ReceiptStatus.confirmed).mayContribute, isTrue);
      expect(
        _receipt(ReceiptStatus.confirmed, totalCents: 0).mayContribute,
        isFalse,
      );
      expect(
        _receipt(ReceiptStatus.confirmed, merchant: ' ').mayContribute,
        isFalse,
      );
    });

    test('filing gate names only the missing receipt fields', () {
      expect(_receipt(ReceiptStatus.review).missingLabel, isNull);
      expect(
        _receipt(ReceiptStatus.review, totalCents: 0).missingLabel,
        'a total',
      );
      expect(
        _receipt(ReceiptStatus.review, merchant: '').missingLabel,
        'a merchant',
      );
      expect(
        _receipt(
          ReceiptStatus.review,
          merchant: '',
          totalCents: 0,
        ).missingLabel,
        'a merchant and total',
      );
    });

    test('sharing preference never rewrites historical counts', () {
      const counts = ContributionCounts(
        receiptsShared: 12,
        pricesContributed: 94,
        indexPricesUsed: 31,
      );
      const enabled = SharingSnapshot(isEnabled: true, counts: counts);

      final disabled = enabled.withSharing(false);
      expect(disabled.isEnabled, isFalse);
      expect(identical(disabled.counts, enabled.counts), isTrue);
      expect(disabled.counts.receiptsShared, 12);
      expect(disabled.counts.pricesContributed, 94);
      expect(disabled.counts.indexPricesUsed, 31);
    });
  });

  group('BasketComparison safety and basis', () {
    test('totals normalize different pack multiples to the same quantity', () {
      final comparison = _completeBasketComparison();
      final local = comparison.merchants[0];
      final warehouse = comparison.merchants[1];

      expect(comparison.eligibility.canCompare, isTrue);
      expect(comparison.totalFor(local), 500);
      expect(comparison.totalFor(warehouse), 400);
      expect(comparison.annualFor(local), 5000);
      expect(comparison.annualFor(warehouse), 4000);

      final verdict = comparison.switchVerdict();
      expect(verdict.isAvailable, isTrue);
      expect(verdict.headline, r'Warehouse would charge $10.00 less a year');
      expect(verdict.figure, r'$10.00/yr');
    });

    test('weak or missing basket coverage returns no claim', () {
      final complete = _completeBasketComparison();
      final item = complete.basket.single;
      final weakItem = _basketItem(
        quotes: <PriceQuote>[
          item.quotes.first,
          const PriceQuote(
            merchantName: 'Warehouse',
            note: 'two shopper reports',
            cents: 300,
            source: PriceSource.crowd,
            confidence: Confidence.thin,
            reportCount: 2,
          ),
        ],
      );
      final comparison = BasketComparison(
        merchants: complete.merchants,
        basket: <TrackedItem>[weakItem],
        usualMerchantKey: 'local',
      );

      expect(comparison.eligibility.canCompare, isFalse);
      expect(
        comparison.eligibility.blocker,
        BasketBlocker.incompleteConfirmedCoverage,
      );
      expect(comparison.totalFor(complete.merchants.first), isNull);
      expect(comparison.annualFor(complete.merchants.first), isNull);

      final verdict = comparison.switchVerdict();
      expect(verdict.isAvailable, isFalse);
      expect(verdict.figure, isNull);
      expect(verdict.headline, 'Not enough confirmed basket prices yet');
    });
  });
}

ComparisonResult _compare(
  TrackedItem item, {
  CompareBasis basis = CompareBasis.perPack,
}) => _comparator(item, basis: basis).build();

PriceComparator _comparator(
  TrackedItem item, {
  CompareBasis basis = CompareBasis.perPack,
}) => PriceComparator(
  item: item,
  scope: CompareScope.everywhere,
  basis: basis,
  yourMerchantNames: const <String>{'Local Pantry', 'Market'},
);

TrackedItem _comparisonFixture({
  List<PurchaseRecord>? history,
  List<PriceQuote>? quotes,
}) => TrackedItem(
  name: 'Full cream milk',
  collection: 'Groceries',
  rhythm: 'Every fortnight',
  timesBought: 14,
  purchasesPerYear: 26,
  pack: const PackSize(1, 'L', '1 L'),
  monthlySeriesCents: const <int>[500, 500, 510, 520, 520, 520],
  quotes: quotes ?? _comparisonQuotes,
  history:
      history ??
      <PurchaseRecord>[
        PurchaseRecord(
          date: DateTime.utc(2026, 8, 10),
          merchantName: 'Local Pantry',
          cents: 520,
        ),
        PurchaseRecord(
          date: DateTime.utc(2026, 7, 25),
          merchantName: 'Local Pantry',
          cents: 510,
        ),
        PurchaseRecord(
          date: DateTime.utc(2026, 7, 5),
          merchantName: 'Market',
          cents: 500,
        ),
      ],
);

const List<PriceQuote> _comparisonQuotes = <PriceQuote>[
  PriceQuote(
    merchantName: 'Local Pantry',
    note: '4 min · closest',
    cents: 520,
    source: PriceSource.you,
    daysSinceSeen: 5,
  ),
  PriceQuote(
    merchantName: 'Market',
    note: '12 min · strong produce range',
    cents: 480,
    source: PriceSource.crowd,
    confidence: Confidence.mixed,
    reportCount: 6,
    daysSinceSeen: 2,
    bandCents: 20,
    hasStockSignal: false,
  ),
  PriceQuote(
    merchantName: 'Warehouse',
    note: '22 min · double pack',
    cents: 840,
    packMultiple: 2,
    source: PriceSource.published,
    daysSinceSeen: 1,
  ),
  PriceQuote(
    merchantName: 'Pop-up',
    note: '18 min · two reports',
    cents: 390,
    source: PriceSource.crowd,
    confidence: Confidence.thin,
    reportCount: 2,
    daysSinceSeen: 3,
    hasStockSignal: false,
  ),
  PriceQuote(
    merchantName: 'Glitch quote',
    note: 'one report looks wrong',
    cents: 200,
    source: PriceSource.crowd,
    confidence: Confidence.high,
    reportCount: 20,
    daysSinceSeen: 1,
    isOutlier: true,
    hasStockSignal: false,
  ),
];

Receipt _receipt(
  ReceiptStatus status, {
  String merchant = 'Local Pantry',
  int totalCents = 2450,
}) => Receipt(
  id: 'receipt-1',
  merchant: merchant,
  purchasedAt: DateTime.utc(2026, 8, 10),
  txnRef: 'demo-001',
  collectionKey: 'groceries',
  status: status,
  totalCents: totalCents,
  taxCents: 0,
  items: const <LineItem>[],
);

BasketComparison _completeBasketComparison() {
  const merchants = <Merchant>[
    Merchant(
      key: 'local',
      name: 'Local Pantry',
      shortName: 'Local',
      minutesAway: 4,
      wins: <String>['Closest', 'Open late'],
      edge: 'the four-minute trip',
    ),
    Merchant(
      key: 'warehouse',
      name: 'Warehouse',
      shortName: 'Warehouse',
      minutesAway: 22,
      wins: <String>['Bulk packs'],
      edge: 'bulk range',
    ),
  ];
  return BasketComparison(
    merchants: merchants,
    basket: <TrackedItem>[_basketItem()],
    usualMerchantKey: 'local',
  );
}

TrackedItem _basketItem({List<PriceQuote>? quotes}) => TrackedItem(
  name: 'Milk',
  collection: 'Groceries',
  rhythm: 'Every five weeks',
  timesBought: 10,
  purchasesPerYear: 10,
  pack: const PackSize(1, 'L', '1 L'),
  monthlySeriesCents: const <int>[],
  quotes:
      quotes ??
      const <PriceQuote>[
        PriceQuote(
          merchantName: 'Local Pantry',
          note: 'standard pack',
          cents: 500,
          source: PriceSource.you,
        ),
        PriceQuote(
          merchantName: 'Warehouse',
          note: 'double pack',
          cents: 800,
          packMultiple: 2,
          source: PriceSource.published,
        ),
      ],
  history: const <PurchaseRecord>[],
);

// Evidence-safe item and basket price comparisons.

import 'package:receipts_hub/core/models/models.dart';
import '../format/money.dart';

enum CompareScope { yourStores, everywhere }

enum CompareBasis { perPack, perUnit }

enum ComparisonBlocker {
  noPurchaseHistory,
  historyNotNewestFirst,
  invalidPackBasis,
  invalidPurchaseRate,
  noPricesInScope,
  invalidQuoteBasis,
  inconsistentEvidence,
  noConfirmedPrices,
}

class ComparisonEligibility {
  const ComparisonEligibility.eligible() : blocker = null, message = null;

  const ComparisonEligibility.blocked(this.blocker, this.message);

  final ComparisonBlocker? blocker;
  final String? message;

  bool get canCompare => blocker == null;
}

class ComparisonRow {
  const ComparisonRow({
    required this.quote,
    required this.priceLabel,
    required this.subLabel,
    this.saveLabel,
    required this.isBestValue,
    required this.isSoft,
  });

  final PriceQuote quote;
  final String priceLabel;
  final String subLabel;
  final String? saveLabel;
  final bool isBestValue;
  final bool isSoft;

  String get sourceLabel => quote.sourceLabel;
  String get freshnessLabel => quote.freshness;
}

class ComparisonResult {
  const ComparisonResult({
    required this.eligibility,
    required this.rows,
    required this.rangeLow,
    required this.rangeHigh,
    this.rangeNote,
    required this.showBasisToggle,
    required this.basisUnitLabel,
    required this.savedHeadline,
    required this.savedNote,
    required this.sourceLine,
    required this.didOverpay,
    required this.verdictHeadline,
    required this.verdictNote,
    this.verdictAnnualSaving,
  });

  factory ComparisonResult.unavailable(
    ComparisonEligibility eligibility,
    PackSize pack,
  ) => ComparisonResult(
    eligibility: eligibility,
    rows: const <ComparisonRow>[],
    rangeLow: '',
    rangeHigh: '',
    showBasisToggle: false,
    basisUnitLabel: 'Per ${pack.unit.isEmpty ? 'unit' : pack.unit}',
    savedHeadline: 'Not enough confirmed prices yet',
    savedNote: eligibility.message ?? 'No comparison is available.',
    sourceLine: 'No price claim is shown.',
    didOverpay: false,
    verdictHeadline: 'Comparison unavailable',
    verdictNote: eligibility.message ?? 'Add more confirmed prices to compare.',
  );

  final ComparisonEligibility eligibility;
  final List<ComparisonRow> rows;
  final String rangeLow;
  final String rangeHigh;
  final String? rangeNote;
  final bool showBasisToggle;
  final String basisUnitLabel;
  final String savedHeadline;
  final String savedNote;
  final String sourceLine;
  final bool didOverpay;
  final String verdictHeadline;
  final String verdictNote;
  final String? verdictAnnualSaving;

  bool get isAvailable => eligibility.canCompare;
}

/// Money, as the rest of the app renders it.
///
/// This used to build its own string without grouping separators, so a
/// comparison card could show `$1234.56` beside `$1,234.56`.
String money(num cents) => formatCents(cents);

class PriceComparator {
  PriceComparator({
    required this.item,
    required this.scope,
    required this.basis,
    required this.yourMerchantNames,
  });

  final TrackedItem item;
  final CompareScope scope;
  final CompareBasis basis;
  final Set<String> yourMerchantNames;

  List<PriceQuote> get _pool => scope == CompareScope.yourStores
      ? item.quotes
            .where((quote) => yourMerchantNames.contains(quote.merchantName))
            .toList(growable: false)
      : List<PriceQuote>.of(item.quotes, growable: false);

  List<PriceQuote> get _confirmed =>
      _pool.where((quote) => quote.isConfirmed).toList(growable: false);

  bool get _mixedPacks =>
      _pool.any((quote) => quote.packMultiple != 1) || item.pack.amount != 1;

  bool get _byUnit => basis == CompareBasis.perUnit && _mixedPacks;

  ComparisonEligibility get eligibility {
    if (item.history.isEmpty) {
      return const ComparisonEligibility.blocked(
        ComparisonBlocker.noPurchaseHistory,
        'A confirmed purchase is needed before prices can be compared.',
      );
    }
    if (!item.historyIsNewestFirst) {
      return const ComparisonEligibility.blocked(
        ComparisonBlocker.historyNotNewestFirst,
        'Purchase history must be ordered newest first.',
      );
    }
    if (!item.pack.hasValidBasis) {
      return const ComparisonEligibility.blocked(
        ComparisonBlocker.invalidPackBasis,
        'The item pack size cannot be converted to a unit price.',
      );
    }
    if (!item.hasValidPurchaseBasis) {
      return const ComparisonEligibility.blocked(
        ComparisonBlocker.invalidPurchaseRate,
        'Purchase quantity and frequency must be positive values.',
      );
    }

    final pool = _pool;
    if (pool.isEmpty) {
      return const ComparisonEligibility.blocked(
        ComparisonBlocker.noPricesInScope,
        'No prices are available in this comparison scope.',
      );
    }
    if (pool.any((quote) => !quote.hasValidBasis)) {
      return const ComparisonEligibility.blocked(
        ComparisonBlocker.invalidQuoteBasis,
        'A price has an invalid pack size or range.',
      );
    }
    if (pool.any((quote) => !quote.hasConsistentEvidence)) {
      return const ComparisonEligibility.blocked(
        ComparisonBlocker.inconsistentEvidence,
        'A price is missing valid source or confidence evidence.',
      );
    }
    if (_confirmed.isEmpty) {
      return const ComparisonEligibility.blocked(
        ComparisonBlocker.noConfirmedPrices,
        'No confirmed price is strong enough to support a comparison.',
      );
    }
    return const ComparisonEligibility.eligible();
  }

  /// Builds a claim only when [eligibility] is satisfied.
  ///
  /// Ineligible input returns an explicit unavailable result rather than
  /// throwing from an empty list, invalid unit division, or missing history.
  ComparisonResult build() {
    final check = eligibility;
    if (!check.canCompare) {
      return ComparisonResult.unavailable(check, item.pack);
    }

    final pool = _pool;
    final confirmed = _confirmed;
    final pack = item.pack;
    final paidCents = item.history.first.cents;
    final paidUnit = paidCents / pack.amount;

    // The verdict argues from paid versus the lowest confirmed unit price.
    final best = confirmed.reduce(
      (current, quote) =>
          quote.unitCents(pack) < current.unitCents(pack) ? quote : current,
    );
    final dearest = confirmed.reduce(
      (current, quote) =>
          quote.unitCents(pack) > current.unitCents(pack) ? quote : current,
    );
    final bestUnit = best.unitCents(pack);
    final gapUnit = paidUnit - bestUnit;
    final unitsPerYear =
        pack.amount * item.unitsPerPurchase * item.purchasesPerYear;
    final couldSave = gapUnit * pack.amount * item.unitsPerPurchase;
    final annual = gapUnit * unitsPerYear;

    // The range reads only from confirmed prices and uses comparable units.
    final headerLow = confirmed.reduce(
      (current, quote) => quote.cents < current.cents ? quote : current,
    );
    final headerHigh = confirmed.reduce(
      (current, quote) => quote.cents > current.cents ? quote : current,
    );
    final rangeLow = _mixedPacks
        ? '${money(bestUnit)}${pack.suffix}'
        : money(headerLow.cents);
    final rangeHigh = _mixedPacks
        ? '${money(dearest.unitCents(pack))}${pack.suffix}'
        : money(headerHigh.cents);

    final sorted = List<PriceQuote>.of(pool)
      ..sort(
        (left, right) => _byUnit
            ? left.unitCents(pack).compareTo(right.unitCents(pack))
            : left.cents.compareTo(right.cents),
      );

    final rows = sorted
        .map(
          (quote) => _buildRow(
            quote: quote,
            pack: pack,
            paidCents: paidCents,
            paidUnit: paidUnit,
            best: best,
          ),
        )
        .toList(growable: false);

    final overpaid = gapUnit > 0.5;
    final sameEverywhere = dearest.unitCents(pack) - bestUnit < 0.5;

    return ComparisonResult(
      eligibility: const ComparisonEligibility.eligible(),
      rows: rows,
      rangeLow: rangeLow,
      rangeHigh: rangeHigh,
      rangeNote: confirmed.length < pool.length
          ? 'across ${confirmed.length} confirmed prices'
          : null,
      showBasisToggle: _mixedPacks,
      basisUnitLabel: 'Per ${pack.unit.isEmpty ? 'unit' : pack.unit}',
      didOverpay: overpaid,
      savedHeadline: overpaid
          ? 'You could have kept ${money(couldSave)} on this one'
          : 'You paid the lowest price on offer',
      savedNote: _savedNote(
        overpaid: overpaid,
        paidCents: paidCents,
        paidUnit: paidUnit,
        best: best,
        bestUnit: bestUnit,
        gapUnit: gapUnit,
        annual: annual,
      ),
      sourceLine: 'From ${_sourceWord(best)}.',
      verdictHeadline: sameEverywhere
          ? 'Every store charges the same'
          : overpaid
          ? '${best.merchantName} undercuts you by '
                '${money(gapUnit)}${_mixedPacks ? pack.suffix : ''}'
          : 'You already buy it at the cheapest',
      verdictNote: sameEverywhere
          ? 'No price to win here — judge them on the trip instead.'
          : overpaid
          ? 'Over a year of buying this that is the difference below.'
          : '${dearest.merchantName} wants '
                '${money(dearest.unitCents(pack) - bestUnit)}'
                '${_mixedPacks ? pack.suffix : ''} more each time.',
      verdictAnnualSaving: overpaid ? '${money(annual)}/yr' : null,
    );
  }

  ComparisonRow _buildRow({
    required PriceQuote quote,
    required PackSize pack,
    required int paidCents,
    required double paidUnit,
    required PriceQuote best,
  }) {
    final save = _mixedPacks
        ? paidUnit - quote.unitCents(pack)
        : (paidCents - quote.cents).toDouble();
    final band = quote.bandCents;
    final unitSuffix = pack.suffix;
    final lowPack = quote.cents - band;
    final highPack = quote.cents + band;
    final divisor = pack.amount * quote.packMultiple;

    final priceLabel = band > 0
        ? _byUnit
              ? '${money(lowPack / divisor)}–'
                    '${money(highPack / divisor)}$unitSuffix'
              : '${money(lowPack)}–${money(highPack)}'
        : _byUnit
        ? '${money(quote.unitCents(pack))}$unitSuffix'
        : money(quote.cents);

    final subLabel = band > 0
        ? _byUnit
              ? '${money(lowPack)}–${money(highPack)} pack'
              : '${money(lowPack / divisor)}–'
                    '${money(highPack / divisor)}$unitSuffix'
        : _byUnit
        ? '${money(quote.cents)} pack'
        : '${money(quote.unitCents(pack))}$unitSuffix';

    return ComparisonRow(
      quote: quote,
      priceLabel: priceLabel,
      subLabel: subLabel,
      saveLabel: save > 0.5 && quote.isConfirmed
          ? 'save ${money(save)}${_mixedPacks ? unitSuffix : ''}'
          : null,
      // The crown follows the verdict winner, never the current sort position.
      isBestValue: identical(quote, best),
      isSoft: !quote.isConfirmed,
    );
  }

  String _savedNote({
    required bool overpaid,
    required int paidCents,
    required double paidUnit,
    required PriceQuote best,
    required double bestUnit,
    required double gapUnit,
    required double annual,
  }) {
    final pack = item.pack;
    final where = item.history.first.merchantName;
    if (!overpaid) {
      return 'Paid ${money(paidCents)}'
          '${_mixedPacks ? ' for ${pack.label} (${money(paidUnit)}${pack.suffix})' : ''} '
          'at $where. Nothing on offer beats it.';
    }
    if (_mixedPacks) {
      return 'Paid ${money(paidCents)} for ${pack.label} '
          '(${money(paidUnit)}${pack.suffix}) at $where. '
          '${best.merchantName} works out at '
          '${money(bestUnit)}${pack.suffix} — '
          '${money(gapUnit)}${pack.suffix} less, '
          '${money(annual)} a year at your rate of buying.';
    }
    return 'Paid ${money(paidCents)} at $where. '
        '${best.merchantName} listed ${money(best.cents)} — '
        '${money(gapUnit)} less, '
        '${money(annual)} a year at your rate of buying.';
  }

  String _sourceWord(PriceQuote quote) => switch (quote.source) {
    PriceSource.you => 'your own receipts',
    PriceSource.published => 'their published price',
    PriceSource.crowd => '${quote.reportCount} shoppers',
  };
}

enum BasketBlocker {
  notEnoughMerchants,
  noItems,
  usualMerchantMissing,
  invalidItemBasis,
  incompleteConfirmedCoverage,
  ambiguousConfirmedCoverage,
}

class BasketEligibility {
  const BasketEligibility.eligible() : blocker = null, message = null;

  const BasketEligibility.blocked(this.blocker, this.message);

  final BasketBlocker? blocker;
  final String? message;

  bool get canCompare => blocker == null;
}

class BasketVerdict {
  const BasketVerdict({
    required this.eligibility,
    required this.headline,
    required this.note,
    this.figure,
  });

  factory BasketVerdict.unavailable(BasketEligibility eligibility) =>
      BasketVerdict(
        eligibility: eligibility,
        headline: 'Not enough confirmed basket prices yet',
        note: eligibility.message ?? 'No basket comparison is available.',
      );

  final BasketEligibility eligibility;
  final String headline;
  final String note;
  final String? figure;

  bool get isAvailable => eligibility.canCompare;
}

/// Basket-level comparison behind the Rivals screen.
class BasketComparison {
  BasketComparison({
    required this.merchants,
    required this.basket,
    required this.usualMerchantKey,
  });

  final List<Merchant> merchants;
  final List<TrackedItem> basket;
  final String usualMerchantKey;

  BasketEligibility get eligibility {
    if (merchants.length < 2) {
      return const BasketEligibility.blocked(
        BasketBlocker.notEnoughMerchants,
        'At least two merchants are needed for a basket comparison.',
      );
    }
    if (basket.isEmpty) {
      return const BasketEligibility.blocked(
        BasketBlocker.noItems,
        'Add a repeat item before comparing merchant baskets.',
      );
    }
    if (!merchants.any((merchant) => merchant.key == usualMerchantKey)) {
      return const BasketEligibility.blocked(
        BasketBlocker.usualMerchantMissing,
        'Choose a usual merchant before comparing a switch.',
      );
    }

    for (final item in basket) {
      if (!item.pack.hasValidBasis ||
          !item.unitsPerPurchase.isFinite ||
          item.unitsPerPurchase <= 0 ||
          item.purchasesPerYear < 0) {
        return const BasketEligibility.blocked(
          BasketBlocker.invalidItemBasis,
          'A basket item has an invalid quantity or purchase rate.',
        );
      }

      for (final merchant in merchants) {
        final matches = item.quotes
            .where(
              (quote) =>
                  quote.merchantName == merchant.name &&
                  quote.isConfirmed &&
                  quote.hasValidBasis &&
                  quote.hasConsistentEvidence,
            )
            .toList(growable: false);
        if (matches.isEmpty) {
          return BasketEligibility.blocked(
            BasketBlocker.incompleteConfirmedCoverage,
            '${merchant.name} is missing a confirmed price for ${item.name}.',
          );
        }
        if (matches.length > 1) {
          return BasketEligibility.blocked(
            BasketBlocker.ambiguousConfirmedCoverage,
            '${merchant.name} has more than one confirmed price for '
            '${item.name}.',
          );
        }
      }
    }
    return const BasketEligibility.eligible();
  }

  /// Total for the user's standard purchase quantity, normalized by unit.
  int? totalFor(Merchant merchant) {
    if (!eligibility.canCompare) {
      return null;
    }
    return basket.fold<int>(0, (sum, item) {
      final quote = _confirmedQuote(item, merchant);
      return sum + _normalizedPurchaseCents(item, quote!);
    });
  }

  int? annualFor(Merchant merchant) {
    if (!eligibility.canCompare) {
      return null;
    }
    return basket.fold<int>(0, (sum, item) {
      final quote = _confirmedQuote(item, merchant);
      final purchaseCents = _normalizedPurchaseCents(item, quote!);
      return sum + purchaseCents * item.purchasesPerYear;
    });
  }

  BasketVerdict switchVerdict() {
    final check = eligibility;
    if (!check.canCompare) {
      return BasketVerdict.unavailable(check);
    }

    final mine = merchants.firstWhere(
      (merchant) => merchant.key == usualMerchantKey,
    );
    var best = merchants.first;
    var worst = merchants.first;
    for (final merchant in merchants.skip(1)) {
      if (totalFor(merchant)! < totalFor(best)!) {
        best = merchant;
      }
      if (totalFor(merchant)! > totalFor(worst)!) {
        worst = merchant;
      }
    }

    if (best.key == mine.key) {
      return BasketVerdict(
        eligibility: const BasketEligibility.eligible(),
        headline: 'Your usual store is also the cheapest',
        note:
            '${worst.name} would take '
            '${money(annualFor(worst)! - annualFor(mine)!)} more over a year '
            'for the same basket.',
      );
    }

    final yearGap = annualFor(mine)! - annualFor(best)!;
    final extraMinutes = (best.minutesAway - mine.minutesAway).clamp(0, 999);
    final hours = extraMinutes * 2 * 48 / 60;

    return BasketVerdict(
      eligibility: const BasketEligibility.eligible(),
      headline: '${best.name} would charge ${money(yearGap)} less a year',
      note: hours >= 1
          ? 'That is ${hours.toStringAsFixed(0)} more hours in the car — '
                'about ${money(yearGap / hours)} an hour of your time. '
                '${mine.shortName} holds you with ${mine.edge}.'
          : 'Same distance either way, so the gap is yours to take.',
      figure: '${money(yearGap)}/yr',
    );
  }

  PriceQuote? _confirmedQuote(TrackedItem item, Merchant merchant) {
    final matches = item.quotes
        .where(
          (quote) =>
              quote.merchantName == merchant.name &&
              quote.isConfirmed &&
              quote.hasValidBasis &&
              quote.hasConsistentEvidence,
        )
        .toList(growable: false);
    return matches.length == 1 ? matches.single : null;
  }

  int _normalizedPurchaseCents(TrackedItem item, PriceQuote quote) {
    final requestedUnits = item.pack.amount * item.unitsPerPurchase;
    return (quote.unitCents(item.pack) * requestedUnits).round();
  }
}

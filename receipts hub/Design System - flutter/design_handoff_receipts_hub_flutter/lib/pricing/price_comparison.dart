// price_comparison.dart — the comparison engine.
//
// This file is the part of the handoff that MUST be ported faithfully.
// The visual design can be reinterpreted for Flutter idiom; these rules
// cannot, because every one of them exists to stop the app making a claim
// the user could not act on. Three defects were found and fixed in the
// prototype by enforcing exactly these invariants:
//
//   1. The verdict argues from [paid] vs the lowest CONFIRMED unit price.
//      Never the dearest-to-cheapest spread — that was never available.
//   2. The range header reads from the CONFIRMED pool, and switches to
//      unit prices whenever pack sizes differ. Otherwise it compares a
//      half pack to a double pack and calls it a range.
//   3. The "Best value" crown is keyed to the verdict winner, NOT to sort
//      position. Sorting reorders the list; it must not move the crown.

import 'models.dart';

enum CompareScope { yourStores, everywhere }
enum CompareBasis { perPack, perUnit }

class ComparisonRow {
  final PriceQuote quote;
  final String priceLabel;    // '$4.20' or '$4.60–$5.00'
  final String subLabel;      // the other basis, always present when packs differ
  final String? saveLabel;    // 'save $0.20/L' — omitted on unconfirmed rows
  final bool isBestValue;     // the crown
  final bool isSoft;          // dimmed: thin or outlier
  const ComparisonRow({
    required this.quote, required this.priceLabel, required this.subLabel,
    this.saveLabel, required this.isBestValue, required this.isSoft,
  });
}

class ComparisonResult {
  final List<ComparisonRow> rows;
  final String rangeLow;
  final String rangeHigh;
  final String? rangeNote;        // 'across 5 confirmed prices'
  final bool showBasisToggle;     // only when packs or units actually differ
  final String basisUnitLabel;    // 'Per kg'
  final String savedHeadline;
  final String savedNote;
  final String sourceLine;        // 'From 11 shoppers.'
  final bool didOverpay;
  final String verdictHeadline;
  final String verdictNote;
  final String? verdictAnnualSaving;
  const ComparisonResult({
    required this.rows, required this.rangeLow, required this.rangeHigh,
    this.rangeNote, required this.showBasisToggle, required this.basisUnitLabel,
    required this.savedHeadline, required this.savedNote, required this.sourceLine,
    required this.didOverpay, required this.verdictHeadline,
    required this.verdictNote, this.verdictAnnualSaving,
  });
}

String money(num cents) {
  final v = cents / 100;
  return '\$${v.toStringAsFixed(2)}';
}

class PriceComparator {
  final TrackedItem item;
  final CompareScope scope;
  final CompareBasis basis;
  final Set<String> yourMerchantNames;

  PriceComparator({
    required this.item,
    required this.scope,
    required this.basis,
    required this.yourMerchantNames,
  });

  List<PriceQuote> get _pool => scope == CompareScope.yourStores
      ? item.quotes.where((q) => yourMerchantNames.contains(q.merchantName)).toList()
      : item.quotes;

  /// The only rows allowed to make a claim.
  List<PriceQuote> get _confirmed => _pool.where((q) => q.isConfirmed).toList();

  bool get _mixedPacks =>
      _pool.any((q) => q.packMultiple != 1) || item.pack.amount != 1;

  bool get _byUnit => basis == CompareBasis.perUnit && _mixedPacks;

  ComparisonResult build() {
    final pool = _pool;
    final confirmed = _confirmed;
    final pack = item.pack;
    assert(confirmed.isNotEmpty, 'An item must have at least one confirmed price');

    final paidCents = item.history.first.cents;
    final paidUnit = paidCents / pack.amount;

    // Invariant 1 — the verdict's two numbers.
    final best = confirmed.reduce((a, b) => b.unitCents(pack) < a.unitCents(pack) ? b : a);
    final dearest = confirmed.reduce((a, b) => b.unitCents(pack) > a.unitCents(pack) ? b : a);
    final bestUnit = best.unitCents(pack);
    final gapUnit = paidUnit - bestUnit;
    final unitsPerYear = pack.amount * item.unitsPerPurchase * item.purchasesPerYear;
    final couldSave = gapUnit * pack.amount * item.unitsPerPurchase;
    final annual = gapUnit * unitsPerYear;

    // Invariant 2 — the header. Confirmed pool; unit prices when packs differ.
    final headerLow = confirmed.reduce((a, b) => b.cents < a.cents ? b : a);
    final headerHigh = confirmed.reduce((a, b) => b.cents > a.cents ? b : a);
    final rangeLow = _mixedPacks
        ? money(bestUnit) + pack.suffix
        : money(headerLow.cents);
    final rangeHigh = _mixedPacks
        ? money(dearest.unitCents(pack)) + pack.suffix
        : money(headerHigh.cents);

    final sorted = [...pool]..sort((a, b) => _byUnit
        ? a.unitCents(pack).compareTo(b.unitCents(pack))
        : a.cents.compareTo(b.cents));

    final rows = sorted.map((q) {
      final save = _mixedPacks ? (paidUnit - q.unitCents(pack)) : (paidCents - q.cents).toDouble();
      final band = q.bandCents;
      final unitSuffix = pack.suffix;

      final priceLabel = band > 0
          ? (_byUnit
              ? '${money((q.cents - band) / (pack.amount * q.packMultiple))}–${money((q.cents + band) / (pack.amount * q.packMultiple))}$unitSuffix'
              : '${money(q.cents - band)}–${money(q.cents + band)}')
          : (_byUnit ? money(q.unitCents(pack)) + unitSuffix : money(q.cents));

      // Every row keeps the other basis, including disagreeing ones.
      final subLabel = band > 0
          ? (_byUnit
              ? '${money(q.cents - band)}–${money(q.cents + band)} pack'
              : '${money((q.cents - band) / (pack.amount * q.packMultiple))}–${money((q.cents + band) / (pack.amount * q.packMultiple))}$unitSuffix')
          : (_byUnit ? '${money(q.cents)} pack' : money(q.unitCents(pack)) + unitSuffix);

      return ComparisonRow(
        quote: q,
        priceLabel: priceLabel,
        subLabel: subLabel,
        // Unconfirmed rows never advertise a saving.
        saveLabel: (save > 0.5 && q.isConfirmed)
            ? 'save ${money(save)}${_mixedPacks ? unitSuffix : ''}'
            : null,
        // Invariant 3 — identity with the verdict winner, not index 0.
        isBestValue: identical(q, best),
        isSoft: !q.isConfirmed,
      );
    }).toList();

    final overpaid = gapUnit > 0.5;
    final sameEverywhere = (dearest.unitCents(pack) - bestUnit) < 0.5;

    return ComparisonResult(
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
      savedNote: _savedNote(overpaid, paidCents, paidUnit, best, bestUnit, gapUnit, annual),
      sourceLine: 'From ${_sourceWord(best)}.',
      verdictHeadline: sameEverywhere
          ? 'Every store charges the same'
          : (overpaid
              ? '${best.merchantName} undercuts you by ${money(gapUnit)}${_mixedPacks ? pack.suffix : ''}'
              : 'You already buy it at the cheapest'),
      verdictNote: sameEverywhere
          ? 'No price to win here — judge them on the trip instead.'
          : (overpaid
              ? 'Over a year of buying this that is the difference below.'
              : '${dearest.merchantName} wants ${money(dearest.unitCents(pack) - bestUnit)}${_mixedPacks ? pack.suffix : ''} more each time.'),
      verdictAnnualSaving: overpaid ? '${money(annual)}/yr' : null,
    );
  }

  String _savedNote(bool overpaid, int paidCents, double paidUnit,
      PriceQuote best, double bestUnit, double gapUnit, double annual) {
    final p = item.pack;
    final where = '${item.history.first.merchantName}';
    if (!overpaid) {
      return 'Paid ${money(paidCents)}${_mixedPacks ? ' for ${p.label} (${money(paidUnit)}${p.suffix})' : ''} at $where. Nothing on offer beats it.';
    }
    if (_mixedPacks) {
      return 'Paid ${money(paidCents)} for ${p.label} (${money(paidUnit)}${p.suffix}) at $where. '
          '${best.merchantName} works out at ${money(bestUnit)}${p.suffix} — '
          '${money(gapUnit)}${p.suffix} less, ${money(annual)} a year at your rate of buying.';
    }
    return 'Paid ${money(paidCents)} at $where. ${best.merchantName} listed ${money(best.cents)} — '
        '${money(gapUnit)} less, ${money(annual)} a year at your rate of buying.';
  }

  String _sourceWord(PriceQuote q) => switch (q.source) {
    PriceSource.you => 'your own receipts',
    PriceSource.published => 'their published price',
    PriceSource.crowd => '${q.reportCount} shoppers',
  };
}

/// Basket-level comparison behind the Rivals screen.
class BasketComparison {
  final List<Merchant> merchants;
  final List<TrackedItem> basket;
  final String usualMerchantKey;
  BasketComparison({required this.merchants, required this.basket, required this.usualMerchantKey});

  int totalFor(Merchant m) => basket.fold(0, (sum, item) {
    final q = item.quotes.firstWhere((q) => q.merchantName == m.name);
    return sum + q.cents;
  });

  int annualFor(Merchant m) => basket.fold(0, (sum, item) {
    final q = item.quotes.firstWhere((q) => q.merchantName == m.name);
    return sum + q.cents * item.purchasesPerYear;
  });

  /// The switching verdict, priced in the user's own hours.
  /// This is the product's thesis in one method: a price advantage is
  /// only an advantage net of what taking it costs.
  ({String headline, String note, String? figure}) switchVerdict() {
    final mine = merchants.firstWhere((m) => m.key == usualMerchantKey);
    final best = merchants.reduce((a, b) => totalFor(b) < totalFor(a) ? b : a);
    final worst = merchants.reduce((a, b) => totalFor(b) > totalFor(a) ? b : a);

    if (best.key == mine.key) {
      return (
        headline: 'Your usual store is also the cheapest',
        note: '${worst.name} would take ${money(annualFor(worst) - annualFor(mine))} more over a year for the same basket.',
        figure: null,
      );
    }

    final yearGap = annualFor(mine) - annualFor(best);
    final extraMinutes = (best.minutesAway - mine.minutesAway).clamp(0, 999);
    final hours = extraMinutes * 2 * 48 / 60; // two ways, ~48 trips a year

    return (
      headline: '${best.name} would charge ${money(yearGap)} less a year',
      note: hours >= 1
          ? 'That is ${hours.toStringAsFixed(0)} more hours in the car — about '
            '${money(yearGap / hours)} an hour of your time. '
            '${mine.shortName} holds you with ${mine.edge}.'
          : 'Same distance either way, so the gap is yours to take.',
      figure: '${money(yearGap)}/yr',
    );
  }
}

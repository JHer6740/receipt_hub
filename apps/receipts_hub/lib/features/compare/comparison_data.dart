// Where the comparison surfaces get their evidence.
//
// Rivals and Item used to build their argument straight from the design
// fixtures, so a real household saw invented merchants and invented savings.
// The comparison rules in `core/pricing/price_comparison.dart` were never the
// problem — the data source was. This is the seam that replaces it.
//
// The evidence itself needs merchant metadata, pack sizes, provenance,
// freshness and confidence, none of which the service exposes yet. Until those
// endpoints exist this reports no coverage, and the screens say so plainly
// rather than arguing from figures nobody was ever offered.

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/models/models.dart';

/// The merchants and repeat purchases a comparison may argue from.
class ComparisonBasket {
  const ComparisonBasket({
    required this.merchants,
    required this.items,
    this.usualMerchantKey,
  });

  static const none = ComparisonBasket(
    merchants: <Merchant>[],
    items: <TrackedItem>[],
  );

  final List<Merchant> merchants;
  final List<TrackedItem> items;

  /// The merchant this household normally uses, when it is known.
  final String? usualMerchantKey;

  /// A comparison needs at least two merchants and one repeat purchase before
  /// any claim about a cheaper option can be supported.
  bool get hasCoverage => merchants.length >= 2 && items.isNotEmpty;

  TrackedItem? itemNamed(String name) {
    final wanted = name.trim().toLowerCase();
    for (final item in items) {
      if (item.name.toLowerCase() == wanted) return item;
    }
    return null;
  }
}

final comparisonBasketProvider = Provider<ComparisonBasket>(
  (ref) => ComparisonBasket.none,
);

/// Short month labels for a series that ends with the current month.
///
/// The series carries values but no labels, so they are derived from today
/// rather than copied from a fixture whose months had drifted out of date.
List<String> trailingMonthLabels(int count, {DateTime? now}) {
  const names = <String>[
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', //
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ];
  if (count <= 0) return const <String>[];
  final end = now ?? DateTime.now();
  return <String>[
    for (var back = count - 1; back >= 0; back -= 1)
      names[DateTime(end.year, end.month - back).month - 1],
  ];
}

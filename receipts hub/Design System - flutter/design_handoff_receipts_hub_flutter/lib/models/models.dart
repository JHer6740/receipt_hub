// models.dart — the data the UI reads.
// Money is stored in CENTS as int. Never use double for currency.

enum ReceiptStatus { review, confirmed, failed }

enum PriceSource {
  /// The user's own receipts. Always trusted.
  you,
  /// Anonymous aggregated reports from other users' confirmed receipts.
  crowd,
  /// A chain's own published price. Always trusted, partial coverage.
  published,
}

enum Confidence {
  /// >= 9 reports in close agreement. Single figure.
  high,
  /// 4-8 reports that disagree. MUST render as a range.
  mixed,
  /// <= 3 reports. Shown dimmed; never argued from.
  thin,
  /// Not applicable (own receipts / published).
  notApplicable,
}

class LineItem {
  final String id;
  final String name;
  final num qty;
  final int lineCents;
  const LineItem({required this.id, required this.name, required this.qty, required this.lineCents});
}

class Receipt {
  final String id;
  final String merchant;
  final DateTime purchasedAt;
  final String txnRef;
  final String collectionKey;
  final ReceiptStatus status;
  final int totalCents;
  final int taxCents;
  final List<LineItem> items;
  final List<String> pageImagePaths;

  const Receipt({
    required this.id,
    required this.merchant,
    required this.purchasedAt,
    required this.txnRef,
    required this.collectionKey,
    required this.status,
    required this.totalCents,
    required this.taxCents,
    required this.items,
    this.pageImagePaths = const [],
  });

  /// Save gate: a receipt cannot be filed without both of these.
  bool get isFileable => merchant.trim().isNotEmpty && totalCents > 0;

  /// What the save button says when blocked. Name only what is missing.
  String? get missingLabel {
    final hasMerchant = merchant.trim().isNotEmpty;
    final hasTotal = totalCents > 0;
    if (hasMerchant && hasTotal) return null;
    if (hasMerchant) return 'a total';
    if (hasTotal) return 'a merchant';
    return 'a merchant and total';
  }

  /// Only confirmed receipts may contribute to the shared index.
  bool get mayContribute => status == ReceiptStatus.confirmed;
}

class SpendCollection {
  final String key;
  final String name;
  final int monthCents;
  final int receiptCount;
  final double deltaPct;
  const SpendCollection({
    required this.key, required this.name, required this.monthCents,
    required this.receiptCount, required this.deltaPct,
  });
}

/// The pack an item is sold in. Drives all unit-price maths.
class PackSize {
  final double amount;   // 0.25
  final String unit;     // 'kg'
  final String label;    // '250 g'
  const PackSize(this.amount, this.unit, this.label);
  static const each = PackSize(1, '', 'each');
  String get suffix => unit.isEmpty ? '' : '/$unit';
}

class Merchant {
  final String key;
  final String name;
  final String shortName;
  final int minutesAway;
  /// What this merchant wins on beyond price. Never empty — the app
  /// refuses to reduce a merchant to its price alone.
  final List<String> wins;
  final String edge; // prose fragment for the verdict copy
  const Merchant({
    required this.key, required this.name, required this.shortName,
    required this.minutesAway, required this.wins, required this.edge,
  });
}

/// One merchant's price for one item, with its provenance.
class PriceQuote {
  final String merchantName;
  final String note;          // trade-off line: '22 min · limited range · double pack'
  final int cents;            // pack price (midpoint if [bandCents] > 0)
  final double packMultiple;  // 1 = standard, 2 = double pack, 0.5 = half pack
  final PriceSource source;
  final Confidence confidence;
  final int reportCount;      // crowd only
  final int daysSinceSeen;
  final int bandCents;        // > 0 when reports disagree -> render as a range
  final bool isOutlier;
  final bool inStock;
  final bool hasStockSignal;  // crowd cannot vouch for stock

  const PriceQuote({
    required this.merchantName,
    required this.note,
    required this.cents,
    this.packMultiple = 1,
    required this.source,
    this.confidence = Confidence.notApplicable,
    this.reportCount = 0,
    this.daysSinceSeen = 0,
    this.bandCents = 0,
    this.isOutlier = false,
    this.inStock = true,
    this.hasStockSignal = true,
  });

  /// THE RULE: weak data is displayed but never argued from.
  bool get isConfirmed =>
      source != PriceSource.crowd ||
      (confidence != Confidence.thin && !isOutlier);

  /// Cents per base unit (per kg, per L, per egg...).
  double unitCents(PackSize pack) => cents / (pack.amount * packMultiple);

  String get sourceLabel => switch (source) {
    PriceSource.you => 'Your receipts',
    PriceSource.published => 'Published',
    PriceSource.crowd => '$reportCount shoppers',
  };

  String get freshness => daysSinceSeen == 0
      ? 'seen today'
      : daysSinceSeen == 1 ? 'seen yesterday' : 'seen $daysSinceSeen days ago';

  String? get softNote {
    if (isConfirmed) return null;
    return isOutlier ? 'One report looks off — not counted' : 'Too few reports to rely on';
  }
}

class TrackedItem {
  final String name;
  final String collection;
  final String rhythm;        // 'Every fortnight'
  final int timesBought;
  final int purchasesPerYear;
  final PackSize pack;
  /// Units consumed per purchase (a 47 L fuel fill, 1 grocery pack).
  final double unitsPerPurchase;
  final List<int> monthlySeriesCents;
  final List<PriceQuote> quotes;
  final List<PurchaseRecord> history;

  const TrackedItem({
    required this.name,
    required this.collection,
    required this.rhythm,
    required this.timesBought,
    required this.purchasesPerYear,
    required this.pack,
    this.unitsPerPurchase = 1,
    required this.monthlySeriesCents,
    required this.quotes,
    required this.history,
  });
}

class PurchaseRecord {
  final DateTime date;
  final String merchantName;
  final int cents;
  const PurchaseRecord({required this.date, required this.merchantName, required this.cents});
}

/// The unit of the shared index. Note what is absent: any author.
class PriceReport {
  final String itemName;
  final String merchantName;
  final int cents;
  final PackSize pack;
  final DateTime purchasedAt;
  final String collectionKey;
  final String suburb;
  const PriceReport({
    required this.itemName, required this.merchantName, required this.cents,
    required this.pack, required this.purchasedAt, required this.collectionKey,
    required this.suburb,
  });
}

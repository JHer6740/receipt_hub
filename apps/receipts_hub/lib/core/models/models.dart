// Domain models consumed by the Receipts Hub Flutter interface.
//
// Money is stored in integer cents. Doubles are used only for quantities and
// derived unit-price comparisons.

enum ReceiptStatus { review, confirmed, failed }

enum PriceSource {
  /// The household's own confirmed receipts.
  you,

  /// Anonymous aggregate reports from confirmed receipts.
  crowd,

  /// A merchant's own published price.
  published,
}

enum Confidence {
  /// Nine or more reports in close agreement. Render a single figure.
  high,

  /// Four to eight disagreeing reports. Render a range.
  mixed,

  /// Three or fewer reports. Display softly and never argue from it.
  thin,

  /// Own-receipt and published prices do not use crowd confidence.
  notApplicable,
}

class LineItem {
  const LineItem({
    required this.id,
    required this.name,
    required this.qty,
    required this.lineCents,
  });

  final String id;
  final String name;
  final num qty;
  final int lineCents;
}

class Receipt {
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
    this.pageImagePaths = const <String>[],
  });

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

  /// A receipt cannot be filed without both a merchant and a positive total.
  bool get isFileable => merchant.trim().isNotEmpty && totalCents > 0;

  /// What the save action should name while the filing gate is blocked.
  String? get missingLabel {
    final hasMerchant = merchant.trim().isNotEmpty;
    final hasTotal = totalCents > 0;
    if (hasMerchant && hasTotal) {
      return null;
    }
    if (hasMerchant) {
      return 'a total';
    }
    if (hasTotal) {
      return 'a merchant';
    }
    return 'a merchant and total';
  }

  /// Confirmation is the consent gate; invalid receipts are never shared.
  bool get mayContribute => status == ReceiptStatus.confirmed && isFileable;
}

class SpendCollection {
  const SpendCollection({
    required this.key,
    required this.name,
    required this.monthCents,
    required this.receiptCount,
    required this.deltaPct,
  });

  final String key;
  final String name;
  final int monthCents;
  final int receiptCount;
  final double deltaPct;
}

/// The base pack an item is sold in. It drives all unit-price arithmetic.
class PackSize {
  const PackSize(this.amount, this.unit, this.label);

  static const each = PackSize(1, '', 'each');

  final double amount;
  final String unit;
  final String label;

  bool get hasValidBasis => amount.isFinite && amount > 0;

  String get suffix => unit.isEmpty ? '' : '/$unit';
}

class Merchant {
  const Merchant({
    required this.key,
    required this.name,
    required this.shortName,
    required this.minutesAway,
    required this.wins,
    required this.edge,
  });

  final String key;
  final String name;
  final String shortName;
  final int minutesAway;

  /// Non-price reasons the merchant may still be the useful choice.
  final List<String> wins;
  final String edge;
}

/// One merchant price with its source, freshness, and evidence quality.
class PriceQuote {
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

  final String merchantName;
  final String note;

  /// Pack price, or the midpoint when [bandCents] is positive.
  final int cents;
  final double packMultiple;
  final PriceSource source;
  final Confidence confidence;
  final int reportCount;
  final int daysSinceSeen;
  final int bandCents;
  final bool isOutlier;
  final bool inStock;
  final bool hasStockSignal;

  /// Weak data remains visible but is excluded from every comparison claim.
  bool get isConfirmed =>
      source != PriceSource.crowd ||
      (confidence != Confidence.thin && !isOutlier);

  /// Whether pack and range arithmetic can be performed safely.
  bool get hasValidBasis =>
      cents > 0 &&
      packMultiple.isFinite &&
      packMultiple > 0 &&
      bandCents >= 0 &&
      bandCents < cents;

  /// Whether source-specific confidence fields match the handoff contract.
  bool get hasConsistentEvidence {
    if (merchantName.trim().isEmpty || daysSinceSeen < 0) {
      return false;
    }

    if (source != PriceSource.crowd) {
      return confidence == Confidence.notApplicable &&
          reportCount == 0 &&
          bandCents == 0 &&
          !isOutlier;
    }

    if (reportCount <= 0 || confidence == Confidence.notApplicable) {
      return false;
    }

    return switch (confidence) {
      Confidence.high => reportCount >= 9 && bandCents == 0,
      Confidence.mixed => reportCount >= 4 && reportCount <= 8 && bandCents > 0,
      Confidence.thin => reportCount <= 3,
      Confidence.notApplicable => false,
    };
  }

  /// Cents per base unit (per kg, per litre, per item, and so on).
  double unitCents(PackSize pack) => cents / (pack.amount * packMultiple);

  String get sourceLabel => switch (source) {
    PriceSource.you => 'Your receipts',
    PriceSource.published => 'Published',
    PriceSource.crowd => '$reportCount shoppers',
  };

  String get freshness => switch (daysSinceSeen) {
    0 => 'seen today',
    1 => 'seen yesterday',
    _ => 'seen $daysSinceSeen days ago',
  };

  String? get softNote {
    if (isConfirmed) {
      return null;
    }
    return isOutlier
        ? 'One report looks off — not counted'
        : 'Too few reports to rely on';
  }
}

class TrackedItem {
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

  final String name;
  final String collection;
  final String rhythm;
  final int timesBought;
  final int purchasesPerYear;
  final PackSize pack;
  final double unitsPerPurchase;
  final List<int> monthlySeriesCents;
  final List<PriceQuote> quotes;
  final List<PurchaseRecord> history;

  bool get historyIsNewestFirst {
    for (var index = 1; index < history.length; index += 1) {
      if (history[index - 1].date.isBefore(history[index].date)) {
        return false;
      }
    }
    return true;
  }

  bool get hasValidPurchaseBasis =>
      pack.hasValidBasis &&
      unitsPerPurchase.isFinite &&
      unitsPerPurchase > 0 &&
      purchasesPerYear >= 0 &&
      history.every((record) => record.cents > 0);
}

class PurchaseRecord {
  const PurchaseRecord({
    required this.date,
    required this.merchantName,
    required this.cents,
  });

  final DateTime date;
  final String merchantName;
  final int cents;
}

/// Historical contribution totals are independent of the current preference.
class ContributionCounts {
  const ContributionCounts({
    required this.receiptsShared,
    required this.pricesContributed,
    required this.indexPricesUsed,
  });

  final int receiptsShared;
  final int pricesContributed;
  final int indexPricesUsed;
}

class SharingSnapshot {
  const SharingSnapshot({required this.isEnabled, required this.counts});

  final bool isEnabled;
  final ContributionCounts counts;

  /// Changes consent for future receipts without rewriting historical totals.
  SharingSnapshot withSharing(bool value) =>
      SharingSnapshot(isEnabled: value, counts: counts);
}

/// The anonymous unit contributed to the shared price index.
class PriceReport {
  const PriceReport({
    required this.itemName,
    required this.merchantName,
    required this.cents,
    required this.pack,
    required this.purchasedAt,
    required this.collectionKey,
    required this.suburb,
  });

  final String itemName;
  final String merchantName;
  final int cents;
  final PackSize pack;
  final DateTime purchasedAt;
  final String collectionKey;
  final String suburb;
}

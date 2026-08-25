// Wire models mirroring the host's /api/v1 payloads.
//
// These stay deliberately close to the JSON so parsing is obvious and a
// contract change is a compile error rather than a silent null. Translation
// into the interface's domain models happens in the repository layer.

import '../models/models.dart';

int _cents(dynamic value) => (value as num?)?.toInt() ?? 0;

int? _centsOrNull(dynamic value) => (value as num?)?.toInt();

DateTime? _dateOrNull(dynamic value) {
  if (value == null) return null;
  return DateTime.tryParse(value as String);
}

class SessionEnvelope {
  const SessionEnvelope({
    required this.token,
    required this.expiresAt,
    required this.householdName,
  });

  final String token;
  final DateTime expiresAt;
  final String householdName;

  factory SessionEnvelope.fromJson(Map<String, dynamic> json) =>
      SessionEnvelope(
        token: json['session_token'] as String,
        expiresAt:
            _dateOrNull(json['expires_at']) ??
            DateTime.now().add(const Duration(days: 30)),
        householdName:
            (json['household'] as Map<String, dynamic>?)?['name'] as String? ??
            'Household',
      );
}

class CollectionSummary {
  const CollectionSummary({
    required this.id,
    required this.name,
    required this.icon,
    required this.monthCents,
    this.deltaPercent,
  });

  final String id;
  final String name;
  final String icon;
  final int monthCents;
  final double? deltaPercent;

  factory CollectionSummary.fromJson(Map<String, dynamic> json) =>
      CollectionSummary(
        id: json['id'] as String? ?? '',
        name: json['name'] as String? ?? 'Uncategorised',
        icon: json['icon'] as String? ?? '🛒',
        monthCents: _cents(json['month_total']),
        deltaPercent: (json['month_delta_percent'] as num?)?.toDouble(),
      );
}

class MonthPoint {
  const MonthPoint({required this.month, required this.totalCents});

  final String month;
  final int totalCents;

  factory MonthPoint.fromJson(Map<String, dynamic> json) => MonthPoint(
    month: json['month'] as String? ?? '',
    totalCents: _cents(json['total']),
  );
}

class BootstrapSnapshot {
  const BootstrapSnapshot({
    required this.householdName,
    required this.monthTotalCents,
    required this.monthTrend,
    required this.collections,
    required this.receiptCount,
    required this.activeListCount,
  });

  final String householdName;
  final int monthTotalCents;
  final List<MonthPoint> monthTrend;
  final List<CollectionSummary> collections;
  final int receiptCount;
  final int activeListCount;

  factory BootstrapSnapshot.fromJson(Map<String, dynamic> json) {
    final totals = json['totals'] as Map<String, dynamic>? ?? const {};
    final counts = json['counts'] as Map<String, dynamic>? ?? const {};
    return BootstrapSnapshot(
      householdName:
          (json['household'] as Map<String, dynamic>?)?['name'] as String? ??
          'Household',
      monthTotalCents: _cents(totals['month_total']),
      monthTrend: <MonthPoint>[
        for (final row in (totals['month_trend'] as List<dynamic>? ?? const []))
          MonthPoint.fromJson(row as Map<String, dynamic>),
      ],
      collections: <CollectionSummary>[
        for (final row in (json['collections'] as List<dynamic>? ?? const []))
          CollectionSummary.fromJson(row as Map<String, dynamic>),
      ],
      receiptCount: (counts['receipts'] as num?)?.toInt() ?? 0,
      activeListCount: (counts['active_list_items'] as num?)?.toInt() ?? 0,
    );
  }
}

class ReceiptSummary {
  const ReceiptSummary({
    required this.id,
    required this.merchant,
    required this.purchasedAt,
    required this.totalCents,
    required this.status,
    required this.imageCount,
    required this.itemCount,
    required this.attentionRequired,
    required this.dated,
    required this.collectionId,
    required this.createdAt,
  });

  final String id;
  final String merchant;

  /// Null while the receipt is filed but still undated.
  final DateTime? purchasedAt;
  final int totalCents;
  final String status;
  final int imageCount;
  final int itemCount;
  final bool attentionRequired;
  final bool dated;
  final String? collectionId;
  final DateTime? createdAt;

  factory ReceiptSummary.fromJson(Map<String, dynamic> json) => ReceiptSummary(
    id: json['id'] as String,
    merchant: json['merchant'] as String? ?? 'Unknown shop',
    purchasedAt: _dateOrNull(json['date']),
    totalCents: _cents(json['total']),
    status: json['status'] as String? ?? 'needs_review',
    imageCount: (json['image_count'] as num?)?.toInt() ?? 0,
    itemCount: (json['item_count'] as num?)?.toInt() ?? 0,
    attentionRequired: json['attention_required'] as bool? ?? false,
    dated: json['dated'] as bool? ?? (json['date'] != null),
    collectionId: json['collection_id'] as String?,
    createdAt: _dateOrNull(json['created_at']),
  );

  ReceiptStatus get receiptStatus => switch (status) {
    'complete' || 'duplicate' => ReceiptStatus.confirmed,
    'failed' => ReceiptStatus.failed,
    _ => ReceiptStatus.review,
  };
}

class ApiLineItem {
  const ApiLineItem({
    required this.id,
    required this.product,
    required this.quantity,
    required this.unit,
    required this.totalCents,
    required this.category,
    required this.needsReview,
    this.unitPriceCents,
  });

  final String id;
  final String product;
  final num quantity;
  final String unit;
  final int totalCents;
  final String category;

  /// True when OCR was unsure of this line, so the interface can mark it.
  final bool needsReview;
  final int? unitPriceCents;

  factory ApiLineItem.fromJson(Map<String, dynamic> json) => ApiLineItem(
    id: json['id'] as String? ?? '',
    product: json['product'] as String? ?? '',
    quantity: num.tryParse('${json['quantity']}') ?? 1,
    unit: json['unit'] as String? ?? 'each',
    totalCents: _cents(json['total_price']),
    category: json['category'] as String? ?? 'unmapped',
    needsReview: json['needs_review'] as bool? ?? false,
    unitPriceCents: _centsOrNull(json['unit_price']),
  );

  LineItem toDomain() => LineItem(
    id: id,
    name: product,
    qty: quantity,
    lineCents: totalCents,
    unit: unit,
    needsReview: needsReview,
    category: category,
  );
}

class ReceiptBalance {
  const ReceiptBalance({
    required this.lineItemsSumCents,
    required this.statedTotalCents,
    required this.differenceCents,
    required this.reconciled,
  });

  final int lineItemsSumCents;
  final int statedTotalCents;
  final int differenceCents;
  final bool reconciled;

  factory ReceiptBalance.fromJson(Map<String, dynamic> json) => ReceiptBalance(
    lineItemsSumCents: _cents(json['line_items_sum']),
    statedTotalCents: _cents(json['stated_total']),
    differenceCents: _cents(json['difference']),
    reconciled: json['reconciled'] as bool? ?? false,
  );
}

class ReceiptDetail {
  const ReceiptDetail({
    required this.summary,
    required this.lineItems,
    required this.balance,
    required this.warnings,
    required this.imageUrls,
    required this.taxCents,
    required this.duplicateOfId,
    this.transactionNumber,
  });

  final ReceiptSummary summary;
  final List<ApiLineItem> lineItems;
  final ReceiptBalance balance;

  /// What a person still needs to check, as decided by the host.
  final List<String> warnings;
  final List<String> imageUrls;
  final int? taxCents;
  final String? duplicateOfId;

  /// The receipt's own transaction reference, which the review screen edits.
  final String? transactionNumber;

  factory ReceiptDetail.fromJson(Map<String, dynamic> json) => ReceiptDetail(
    summary: ReceiptSummary.fromJson(json),
    lineItems: <ApiLineItem>[
      for (final row in (json['line_items'] as List<dynamic>? ?? const []))
        ApiLineItem.fromJson(row as Map<String, dynamic>),
    ],
    balance: ReceiptBalance.fromJson(
      json['balance'] as Map<String, dynamic>? ?? const {},
    ),
    warnings: <String>[
      for (final row in (json['warnings'] as List<dynamic>? ?? const []))
        row as String,
    ],
    imageUrls: <String>[
      for (final row in (json['image_urls'] as List<dynamic>? ?? const []))
        row as String,
    ],
    taxCents: _centsOrNull(json['tax']),
    duplicateOfId: json['duplicate_of_id'] as String?,
    transactionNumber: json['transaction_number'] as String?,
  );

  bool get isDuplicate => duplicateOfId != null;
}

class ReceiptPage {
  const ReceiptPage({
    required this.items,
    required this.total,
    required this.hasMore,
  });

  final List<ReceiptSummary> items;
  final int total;
  final bool hasMore;

  factory ReceiptPage.fromJson(Map<String, dynamic> json) {
    final pagination = json['pagination'] as Map<String, dynamic>? ?? const {};
    return ReceiptPage(
      items: <ReceiptSummary>[
        for (final row in (json['items'] as List<dynamic>? ?? const []))
          ReceiptSummary.fromJson(row as Map<String, dynamic>),
      ],
      total: (pagination['total'] as num?)?.toInt() ?? 0,
      hasMore: pagination['has_more'] as bool? ?? false,
    );
  }
}

/// One corrected line a reviewer is sending back to the host.
class LineItemDraft {
  const LineItemDraft({
    required this.description,
    required this.quantity,
    required this.unit,
    required this.lineTotalCents,
    this.category = '',
  });

  final String description;
  final num quantity;
  final String unit;
  final int lineTotalCents;
  final String category;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'description': description,
    'quantity': '$quantity',
    'unit': unit,
    'line_total': (lineTotalCents / 100).toStringAsFixed(2),
    if (category.isNotEmpty) 'category': category,
  };
}

class UploadTicket {
  const UploadTicket({
    required this.batchId,
    required this.status,
    required this.totalFiles,
  });

  final String batchId;
  final String status;
  final int totalFiles;

  factory UploadTicket.fromJson(Map<String, dynamic> json) => UploadTicket(
    batchId: json['batch_id'] as String,
    status: json['status'] as String? ?? 'queued',
    totalFiles: (json['total_files'] as num?)?.toInt() ?? 0,
  );
}

enum UploadOutcome { inProgress, complete, failed }

class ProcessingStage {
  const ProcessingStage({
    required this.name,
    required this.status,
    required this.progress,
  });

  final String name;
  final String status;
  final int progress;

  bool get isComplete => status == 'complete';
  bool get isActive => status == 'in_progress';
  bool get isFailed => status == 'failed';

  factory ProcessingStage.fromJson(Map<String, dynamic> json) =>
      ProcessingStage(
        name: json['name'] as String? ?? '',
        status: json['status'] as String? ?? 'pending',
        progress: (json['progress'] as num?)?.toInt() ?? 0,
      );
}

class UploadProgress {
  const UploadProgress({
    required this.batchId,
    required this.receiptId,
    required this.outcome,
    required this.detailStatus,
    required this.progress,
    required this.heading,
    required this.message,
    required this.stages,
    required this.canRetry,
  });

  final String batchId;

  /// Available as soon as the host has created a draft receipt.
  final String? receiptId;
  final UploadOutcome outcome;
  final String detailStatus;
  final int progress;
  final String heading;
  final String message;
  final List<ProcessingStage> stages;
  final bool canRetry;

  bool get isSettled => outcome != UploadOutcome.inProgress;

  /// A finished receipt that still needs a person to check it.
  bool get needsReview => detailStatus == 'needs_review';
  bool get isDuplicate => detailStatus == 'duplicate';

  factory UploadProgress.fromJson(Map<String, dynamic> json) => UploadProgress(
    batchId: json['batch_id'] as String,
    receiptId: json['receipt_id'] as String?,
    outcome: switch (json['status'] as String? ?? 'in_progress') {
      'complete' => UploadOutcome.complete,
      'failed' => UploadOutcome.failed,
      _ => UploadOutcome.inProgress,
    },
    detailStatus: json['detail_status'] as String? ?? 'queued',
    progress: (json['progress'] as num?)?.toInt() ?? 0,
    heading: json['heading'] as String? ?? 'Reading your receipt.',
    message: json['message'] as String? ?? '',
    stages: <ProcessingStage>[
      for (final row in (json['stages'] as List<dynamic>? ?? const []))
        ProcessingStage.fromJson(row as Map<String, dynamic>),
    ],
    canRetry: json['can_retry'] as bool? ?? false,
  );
}

class ShoppingItem {
  const ShoppingItem({
    required this.id,
    required this.description,
    required this.quantityLabel,
    required this.unit,
    required this.status,
    required this.version,
    this.note,
  });

  final String id;
  final String description;
  final String quantityLabel;
  final String unit;
  final String status;

  /// The copy this device last saw, sent back on edits to detect a stale write.
  final int version;
  final String? note;

  bool get isPickedUp => status == 'completed';

  factory ShoppingItem.fromJson(Map<String, dynamic> json) => ShoppingItem(
    id: json['id'] as String,
    description: json['description'] as String? ?? '',
    quantityLabel: json['quantity_label'] as String? ?? '1',
    unit: json['unit'] as String? ?? 'each',
    status: json['status'] as String? ?? 'active',
    version: (json['version'] as num?)?.toInt() ?? 1,
    note: json['note'] as String?,
  );
}

class ShoppingSuggestion {
  const ShoppingSuggestion({
    required this.key,
    required this.description,
    required this.dueLabel,
    required this.estimatedCents,
    required this.confidence,
  });

  final String key;
  final String description;
  final String dueLabel;
  final int estimatedCents;
  final String confidence;

  factory ShoppingSuggestion.fromJson(Map<String, dynamic> json) =>
      ShoppingSuggestion(
        key: json['key'] as String? ?? '',
        description: json['description'] as String? ?? '',
        dueLabel: json['due_label'] as String? ?? '',
        estimatedCents: _cents(json['estimated_cost']),
        confidence: json['confidence'] as String? ?? 'low',
      );
}

class ShoppingSnapshot {
  const ShoppingSnapshot({
    required this.items,
    required this.completed,
    required this.suggestions,
  });

  final List<ShoppingItem> items;
  final List<ShoppingItem> completed;
  final List<ShoppingSuggestion> suggestions;

  factory ShoppingSnapshot.fromJson(Map<String, dynamic> json) =>
      ShoppingSnapshot(
        items: <ShoppingItem>[
          for (final row in (json['items'] as List<dynamic>? ?? const []))
            ShoppingItem.fromJson(row as Map<String, dynamic>),
        ],
        completed: <ShoppingItem>[
          for (final row in (json['completed'] as List<dynamic>? ?? const []))
            ShoppingItem.fromJson(row as Map<String, dynamic>),
        ],
        suggestions: <ShoppingSuggestion>[
          for (final row in (json['suggestions'] as List<dynamic>? ?? const []))
            ShoppingSuggestion.fromJson(row as Map<String, dynamic>),
        ],
      );
}

class CategoryTotal {
  const CategoryTotal({
    required this.category,
    required this.spendCents,
    required this.itemCount,
  });

  final String category;
  final int spendCents;
  final int itemCount;

  factory CategoryTotal.fromJson(Map<String, dynamic> json) => CategoryTotal(
    category: json['category'] as String? ?? 'Uncategorised',
    spendCents: _cents(json['spend']),
    itemCount: (json['item_count'] as num?)?.toInt() ?? 0,
  );
}

class ProductHistoryEntry {
  const ProductHistoryEntry({
    required this.description,
    required this.purchaseCount,
    required this.totalSpendCents,
    required this.averagePriceCents,
    required this.lastPurchased,
  });

  final String description;
  final int purchaseCount;
  final int totalSpendCents;
  final int averagePriceCents;
  final DateTime? lastPurchased;

  factory ProductHistoryEntry.fromJson(Map<String, dynamic> json) =>
      ProductHistoryEntry(
        description: json['description'] as String? ?? '',
        purchaseCount: (json['purchase_count'] as num?)?.toInt() ?? 0,
        totalSpendCents: _cents(json['total_spend']),
        averagePriceCents: _cents(json['average_price']),
        lastPurchased: _dateOrNull(json['last_purchased']),
      );
}

class InsightsSnapshot {
  const InsightsSnapshot({
    required this.monthTotalCents,
    required this.previousMonthTotalCents,
    required this.monthChangePercent,
    required this.forecast30dCents,
    required this.receiptCount,
    required this.monthTrend,
    required this.collections,
    required this.categories,
    required this.productHistory,
  });

  final int monthTotalCents;
  final int previousMonthTotalCents;
  final double? monthChangePercent;
  final int forecast30dCents;
  final int receiptCount;
  final List<MonthPoint> monthTrend;
  final List<CollectionSummary> collections;
  final List<CategoryTotal> categories;
  final List<ProductHistoryEntry> productHistory;

  factory InsightsSnapshot.fromJson(Map<String, dynamic> json) =>
      InsightsSnapshot(
        monthTotalCents: _cents(json['month_total']),
        previousMonthTotalCents: _cents(json['previous_month_total']),
        monthChangePercent: (json['month_change_percent'] as num?)?.toDouble(),
        forecast30dCents: _cents(json['forecast_30d']),
        receiptCount: (json['receipt_count'] as num?)?.toInt() ?? 0,
        monthTrend: <MonthPoint>[
          for (final row in (json['month_trend'] as List<dynamic>? ?? const []))
            MonthPoint.fromJson(row as Map<String, dynamic>),
        ],
        collections: <CollectionSummary>[
          for (final row in (json['collections'] as List<dynamic>? ?? const []))
            CollectionSummary.fromJson(row as Map<String, dynamic>),
        ],
        categories: <CategoryTotal>[
          for (final row in (json['categories'] as List<dynamic>? ?? const []))
            CategoryTotal.fromJson(row as Map<String, dynamic>),
        ],
        productHistory: <ProductHistoryEntry>[
          for (final row
              in (json['product_history'] as List<dynamic>? ?? const []))
            ProductHistoryEntry.fromJson(row as Map<String, dynamic>),
        ],
      );
}

class HostSettings {
  const HostSettings({
    required this.householdName,
    required this.receiptCount,
    required this.maxPhotoFiles,
    required this.sharingAvailable,
    required this.backupEnabled,
  });

  final String householdName;
  final int receiptCount;
  final int maxPhotoFiles;

  /// The shared price index needs a hosted backend, so this LAN build reports
  /// it as unavailable rather than implying a capability it does not have.
  final bool sharingAvailable;
  final bool backupEnabled;

  factory HostSettings.fromJson(Map<String, dynamic> json) => HostSettings(
    householdName: json['household_name'] as String? ?? 'Household',
    receiptCount: (json['receipt_count'] as num?)?.toInt() ?? 0,
    maxPhotoFiles: (json['max_photo_files'] as num?)?.toInt() ?? 5,
    sharingAvailable: json['sharing_available'] as bool? ?? false,
    backupEnabled: json['backup_enabled'] as bool? ?? false,
  );
}

/// One household this account can see, and where the account stands with it.
///
/// A membership and a pending request are deliberately the same shape so the
/// UI can list both without pretending a request is access.
class HouseholdSummary {
  const HouseholdSummary({
    required this.id,
    required this.name,
    required this.role,
    required this.status,
    this.memberCount = 0,
  });

  final String id;
  final String name;

  /// `owner`, `admin`, `member` or `viewer`.
  final String role;

  /// `active`, `pending` or `declined`.
  final String status;
  final int memberCount;

  bool get isActive => status == 'active';
  bool get isPending => status == 'pending';
  bool get canApproveOthers => role == 'owner' || role == 'admin';

  factory HouseholdSummary.fromJson(Map<String, dynamic> json) =>
      HouseholdSummary(
        id: json['id']?.toString() ?? '',
        name: json['name'] as String? ?? 'Household',
        role: json['role'] as String? ?? 'member',
        status: json['status'] as String? ?? 'active',
        memberCount: (json['member_count'] as num?)?.toInt() ?? 0,
      );
}

/// One person in a household, or one person asking to be.
class HouseholdMember {
  const HouseholdMember({
    required this.id,
    required this.name,
    required this.email,
    required this.role,
    required this.status,
  });

  final String id;
  final String name;
  final String email;

  /// `owner`, `admin`, `member` or `viewer`.
  final String role;

  /// `active` or `pending`.
  final String status;

  bool get isPending => status == 'pending';

  factory HouseholdMember.fromJson(Map<String, dynamic> json) =>
      HouseholdMember(
        id: json['id']?.toString() ?? '',
        name: json['name'] as String? ?? json['email'] as String? ?? 'Someone',
        email: json['email'] as String? ?? '',
        role: json['role'] as String? ?? 'member',
        status: json['status'] as String? ?? 'active',
      );
}

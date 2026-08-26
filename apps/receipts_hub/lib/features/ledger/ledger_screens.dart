import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/design/app_components.dart';
import '../../core/design/app_theme.dart';
import '../../core/models/models.dart';
import '../../core/state/app_state.dart';
import '../../core/widgets/ledger_scaffold.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final householdName = ref.watch(
      appControllerProvider.select((value) => value.householdName),
    );
    // No Account action: Account is a destination in the navigation bar, so an
    // app-bar shortcut to it would be a second way to the same place — and one
    // only reachable from this screen.
    return LedgerScaffold(
      scaffoldKey: const Key('home-screen'),
      title: Text(householdName, overflow: TextOverflow.ellipsis),
      body: (context) => const _HomeBody(),
    );
  }
}

/// How the collections sheet is ordered.
///
/// The second option is what the Insights screen used to be. Insights rendered
/// the same month total, the same delta and the same six-month chart as Home,
/// and its one distinct contribution was listing collections by how much they
/// had moved. That is an ordering, not a screen — so it became one here, and
/// the navigation slot it occupied went to Account, which until now was
/// reachable only from an icon on this screen.
enum _CollectionOrder {
  spend('By spend'),
  change('By change');

  const _CollectionOrder(this.label);

  final String label;
}

class _HomeBody extends ConsumerStatefulWidget {
  const _HomeBody();

  @override
  ConsumerState<_HomeBody> createState() => _HomeBodyState();
}

class _HomeBodyState extends ConsumerState<_HomeBody> {
  _CollectionOrder _order = _CollectionOrder.spend;

  List<SpendCollection> _ordered(List<SpendCollection> source) {
    final ordered = source.toList();
    switch (_order) {
      case _CollectionOrder.spend:
        ordered.sort((a, b) => b.monthCents.compareTo(a.monthCents));
      case _CollectionOrder.change:
        ordered.sort((a, b) => b.deltaPct.abs().compareTo(a.deltaPct.abs()));
    }
    return ordered;
  }

  @override
  Widget build(BuildContext context) {
    final attentionCount = ref.watch(
      appControllerProvider.select((value) => value.attentionCount),
    );
    final figures = ref.watch(householdFiguresProvider);
    final colors = context.appColors;

    if (figures.isEmptyMonth) {
      return ListView(
        children: <Widget>[
          AppStatePanel(
            key: const Key('home-empty'),
            icon: Icons.receipt_long_outlined,
            title: 'Nothing filed yet',
            message: 'Scan your first receipt and this month takes shape.',
            actionLabel: 'Scan a receipt',
            onAction: () => context.push('/capture'),
          ),
        ],
      );
    }

    return ListView(
      padding: EdgeInsets.zero,
      children: <Widget>[
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.gutter),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              const SizedBox(height: 8),
              SectionLabel(_monthName(DateTime.now().month)),
              const SizedBox(height: 8),
              MoneyText(
                key: const Key('home-month-total'),
                cents: figures.monthTotalCents,
                style: AppText.displayXL,
                semanticsPrefix: 'Spent this month',
              ),
              const SizedBox(height: 5),
              Wrap(
                spacing: 8,
                runSpacing: 4,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: <Widget>[
                  Text(
                    '${_plural(figures.receiptCount, 'receipt')} this month',
                    style: AppText.bodyS.copyWith(color: colors.textSecondary),
                  ),
                  if (figures.monthDeltaPercent != null) ...<Widget>[
                    Text(
                      '·',
                      style: AppText.bodyS.copyWith(
                        color: colors.textSecondary,
                      ),
                    ),
                    _DeltaLabel(value: figures.monthDeltaPercent),
                  ],
                ],
              ),
              if (attentionCount > 0) ...<Widget>[
                const SizedBox(height: 24),
                LedgerCard(
                  key: const Key('home-attention'),
                  color: colors.warnBg,
                  borderColor: Colors.transparent,
                  semanticLabel:
                      '${_plural(attentionCount, 'receipt')} need attention',
                  onTap: () {
                    ref
                        .read(appControllerProvider.notifier)
                        .setAttentionOnly(true);
                    context.go('/receipts');
                  },
                  child: Row(
                    children: <Widget>[
                      Icon(Icons.error_outline_rounded, color: colors.warnFg),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          '${_plural(attentionCount, 'receipt')} need attention',
                          style: AppText.bodyS.copyWith(
                            color: colors.warnFg,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                      Icon(Icons.chevron_right_rounded, color: colors.warnFg),
                    ],
                  ),
                ),
              ],
              // Six months of history only renders when the service supplied
              // six months. A chart derived from one month's total would be a
              // drawing, not a trend.
              if (figures.monthSeries.isNotEmpty) ...<Widget>[
                const SizedBox(height: 26),
                MiniBarChart(
                  key: const Key('home-six-month-chart'),
                  values: figures.monthSeries,
                  labels: figures.monthLabels,
                  height: 96,
                ),
              ],
              const SizedBox(height: 28),
            ],
          ),
        ),
        RaisedLedgerSheet(
          key: const Key('home-collections-sheet'),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              const SectionLabel('Collections'),
              if (figures.collections.length > 1) ...<Widget>[
                const SizedBox(height: 10),
                Wrap(
                  spacing: 8,
                  children: <Widget>[
                    for (final order in _CollectionOrder.values)
                      ChoiceChip(
                        key: ValueKey<String>('home-order-${order.name}'),
                        selected: _order == order,
                        onSelected: (_) => setState(() => _order = order),
                        label: Text(order.label),
                      ),
                  ],
                ),
              ],
              const SizedBox(height: 6),
              for (final entry in _ordered(figures.collections).indexed)
                _CollectionRow(
                  key: ValueKey('home-collection-${entry.$2.key}'),
                  collection: entry.$2,
                  showDivider: entry.$1 < figures.collections.length - 1,
                  onTap: () => context.push(
                    _collectionLocation(entry.$2.key, from: 'home'),
                  ),
                ),
              if (figures.collections.isEmpty)
                AppStatePanel(
                  key: const Key('home-empty-collections'),
                  icon: Icons.folder_outlined,
                  title: 'No collections yet',
                  message:
                      'Collections appear once a filed receipt has categorised '
                      'line items.',
                  actionLabel: 'Scan a receipt',
                  onAction: () => context.push('/capture'),
                ),
            ],
          ),
        ),
      ],
    );
  }
}

class CollectionScreen extends ConsumerWidget {
  const CollectionScreen({
    required this.collectionKey,
    this.origin = '/home',
    super.key,
  });

  final String collectionKey;
  final String origin;

  void _back(BuildContext context) {
    if (context.canPop()) {
      context.pop();
      return;
    }
    context.go(_normaliseOrigin(origin));
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return LedgerScaffold(
      leading: BackButton(onPressed: () => _back(context)),
      title: Text(_titleFor(ref)),
      body: (context) => _CollectionBody(collectionKey: collectionKey),
    );
  }

  String _titleFor(WidgetRef ref) {
    final collections = ref.watch(
      householdFiguresProvider.select((value) => value.collections),
    );
    return _collectionForKey(collectionKey, collections)?.name ?? 'Collection';
  }
}

class _CollectionBody extends ConsumerWidget {
  const _CollectionBody({required this.collectionKey});

  final String collectionKey;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final figures = ref.watch(householdFiguresProvider);
    final collection = _collectionForKey(collectionKey, figures.collections);
    if (collection == null) {
      return ListView(
        children: <Widget>[
          AppStatePanel(
            icon: Icons.folder_off_outlined,
            title: 'Collection not found',
            message: 'This collection is no longer in the ledger.',
            actionLabel: 'Back to home',
            onAction: () => context.go('/home'),
          ),
        ],
      );
    }

    final receipts = ref.watch(
      appControllerProvider.select(
        (value) => value.receipts
            .where((receipt) => receipt.collectionKey == collectionKey)
            .toList(),
      ),
    )..sort((a, b) => b.purchasedAt.compareTo(a.purchasedAt));

    final average = collection.receiptCount == 0
        ? 0
        : collection.monthCents / collection.receiptCount;
    // Share of spend is measured against this household's own collections,
    // not a fixed reference total.
    final allCollectionsTotal = figures.collections.fold<int>(
      0,
      (total, item) => total + item.monthCents,
    );
    final share = allCollectionsTotal == 0
        ? 0
        : (collection.monthCents / allCollectionsTotal * 100).round();

    return ListView(
      key: Key('collection-screen-${collection.key}'),
      padding: EdgeInsets.zero,
      children: <Widget>[
        Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.gutter,
            8,
            AppSpacing.gutter,
            24,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              SectionLabel('${_monthName(DateTime.now().month)} total'),
              const SizedBox(height: 8),
              MoneyText(
                key: const Key('collection-month-total'),
                cents: collection.monthCents,
                style: AppText.displayL,
                semanticsPrefix: '${collection.name} total',
              ),
              const SizedBox(height: 5),
              _DeltaLabel(
                value: collection.deltaPct,
                suffix: 'from last month',
              ),
            ],
          ),
        ),
        RaisedLedgerSheet(
          key: const Key('collection-ledger-sheet'),
          padding: const EdgeInsets.fromLTRB(24, 6, 24, 32),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 14),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Expanded(
                      child: KeyValueStat(
                        label: 'receipts',
                        value: '${collection.receiptCount}',
                      ),
                    ),
                    Expanded(
                      child: KeyValueStat(
                        label: 'average',
                        value: formatCents(average),
                      ),
                    ),
                    Expanded(
                      child: KeyValueStat(label: 'of spend', value: '$share%'),
                    ),
                  ],
                ),
              ),
              Divider(height: 1, color: context.appColors.divider),
              if (receipts.isEmpty)
                AppStatePanel(
                  key: const Key('empty-collection-state'),
                  icon: Icons.receipt_long_outlined,
                  title: 'Nothing filed here yet',
                  message:
                      'Scan the first receipt and it will appear in this '
                      'collection.',
                  actionLabel: 'Scan a receipt',
                  onAction: () => context.push('/capture'),
                )
              else ...<Widget>[
                const SizedBox(height: 22),
                SectionLabel(_plural(receipts.length, 'receipt')),
                const SizedBox(height: 6),
                for (var index = 0; index < receipts.length; index += 1)
                  _ReceiptRow(
                    key: ValueKey('collection-receipt-${receipts[index].id}'),
                    receipt: receipts[index],
                    showDivider: index < receipts.length - 1,
                    onTap: () => context.push(
                      '/receipts/${Uri.encodeComponent(receipts[index].id)}',
                    ),
                  ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

class _CollectionRow extends StatelessWidget {
  const _CollectionRow({
    required this.collection,
    required this.onTap,
    required this.showDivider,
    super.key,
  });

  final SpendCollection collection;
  final VoidCallback onTap;
  final bool showDivider;

  @override
  Widget build(BuildContext context) {
    return LedgerRow(
      onTap: onTap,
      showDivider: showDivider,
      child: Row(
        children: <Widget>[
          Expanded(child: Text(collection.name, style: AppText.body)),
          const SizedBox(width: 12),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            mainAxisAlignment: MainAxisAlignment.center,
            children: <Widget>[
              MoneyText(
                cents: collection.monthCents,
                style: AppText.body.copyWith(fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 2),
              _DeltaLabel(value: collection.deltaPct, compact: true),
            ],
          ),
          const SizedBox(width: 4),
          Icon(
            Icons.chevron_right_rounded,
            color: context.appColors.textSecondary,
          ),
        ],
      ),
    );
  }
}

class _ReceiptRow extends StatelessWidget {
  const _ReceiptRow({
    required this.receipt,
    required this.onTap,
    required this.showDivider,
    super.key,
  });

  final Receipt receipt;
  final VoidCallback onTap;
  final bool showDivider;

  @override
  Widget build(BuildContext context) {
    return LedgerRow(
      onTap: onTap,
      showDivider: showDivider,
      child: Row(
        children: <Widget>[
          MerchantMark(name: receipt.merchant, size: 40),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  receipt.merchant,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: AppText.body,
                ),
                const SizedBox(height: 4),
                Row(
                  children: <Widget>[
                    Text(
                      _shortDate(receipt.purchasedAt),
                      style: AppText.caption.copyWith(
                        color: context.appColors.textSecondary,
                      ),
                    ),
                    if (receipt.status != ReceiptStatus.confirmed) ...<Widget>[
                      const SizedBox(width: 8),
                      StatusPill(_hubStatus(receipt.status)),
                    ],
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(width: 10),
          MoneyText(cents: receipt.totalCents, style: AppText.body),
          const SizedBox(width: 2),
          Icon(
            Icons.chevron_right_rounded,
            color: context.appColors.textSecondary,
          ),
        ],
      ),
    );
  }
}

/// Change against last month.
///
/// Renders nothing when [value] is null. "steady" is a claim, and it used to
/// appear whenever the service had sent no comparison at all.
class _DeltaLabel extends StatelessWidget {
  const _DeltaLabel({required this.value, this.suffix, this.compact = false});

  final double? value;
  final String? suffix;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final value = this.value;
    if (value == null) return const SizedBox.shrink();
    final isFlat = value.abs() < .5;
    final isDown = value < 0;
    final direction = isFlat
        ? 'steady'
        : '${isDown ? '−' : '+'}${value.abs().toStringAsFixed(0)}%';
    final detail = suffix == null || compact ? direction : '$direction $suffix';
    final color = isFlat
        ? context.appColors.textSecondary
        : isDown
        ? context.appColors.good
        : context.appColors.warn;

    return Text(
      detail,
      style: AppText.numeric(
        AppText.caption.copyWith(color: color, fontWeight: FontWeight.w600),
      ),
    );
  }
}

SpendCollection? _collectionForKey(String key, List<SpendCollection> source) {
  for (final collection in source) {
    if (collection.key == key) return collection;
  }
  return null;
}

String _collectionLocation(String key, {required String from}) =>
    '/collections/${Uri.encodeComponent(key)}?from=${Uri.encodeQueryComponent(from)}';

String _normaliseOrigin(String origin) {
  final value = origin.trim();
  if (value.isEmpty) return '/home';
  return value.startsWith('/') ? value : '/$value';
}

String _plural(int count, String noun) =>
    '$count $noun${count == 1 ? '' : 's'}';

String _monthName(int month) => const <String>[
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
][month.clamp(1, 12).toInt() - 1];

String _shortDate(DateTime value) =>
    '${value.day} ${_monthName(value.month).substring(0, 3)} ${value.year}';

HubStatus _hubStatus(ReceiptStatus status) => switch (status) {
  ReceiptStatus.review => HubStatus.review,
  ReceiptStatus.confirmed => HubStatus.confirmed,
  ReceiptStatus.failed => HubStatus.failed,
};

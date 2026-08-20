import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/design/app_components.dart';
import '../../core/design/app_theme.dart';
import '../../core/models/models.dart';
import '../../core/pricing/price_comparison.dart';
import '../../core/state/app_state.dart';
import 'comparison_data.dart';

class RivalsScreen extends ConsumerWidget {
  const RivalsScreen({this.origin = '/insights', super.key});

  final String origin;

  void _back(BuildContext context) {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go(origin);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final evidence = ref.watch(comparisonBasketProvider);
    final basket = BasketComparison(
      merchants: evidence.merchants,
      basket: evidence.items,
      // Empty means "no usual shop known", so nothing is labelled as theirs.
      usualMerchantKey: evidence.usualMerchantKey ?? '',
    );
    if (!evidence.hasCoverage || !basket.eligibility.canCompare) {
      return Scaffold(
        appBar: AppBar(
          leading: IconButton(
            tooltip: 'Back',
            onPressed: () => _back(context),
            icon: const Icon(Icons.arrow_back_rounded),
          ),
          title: const Text('Rivals'),
        ),
        body: AppStatePanel(
          key: const Key('rivals-no-coverage'),
          icon: Icons.incomplete_circle_outlined,
          title: 'Not enough prices yet',
          message:
              basket.eligibility.message ??
              'Comparing shops needs the same items bought at more than one '
                  'merchant. File a few more receipts and this fills in.',
          actionLabel: 'Scan a receipt',
          onAction: () => context.push('/capture'),
        ),
      );
    }
    final merchantTotals = <Merchant, int>{
      for (final merchant in evidence.merchants)
        merchant: basket.totalFor(merchant)!,
    };
    final ordered = merchantTotals.entries.toList()
      ..sort((a, b) => a.value.compareTo(b.value));
    final cheapest = ordered.first;
    final dearest = ordered.last;
    final spread = dearest.value - cheapest.value;
    final verdict = basket.switchVerdict();
    final maxTotal = merchantTotals.values.reduce(math.max);
    final colors = context.appColors;

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          tooltip: 'Back',
          onPressed: () => _back(context),
          icon: const Icon(Icons.arrow_back_rounded),
        ),
        title: const Text('Rivals'),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.gutter,
          4,
          AppSpacing.gutter,
          36,
        ),
        children: <Widget>[
          const SectionLabel('Spread on your basket'),
          const SizedBox(height: 8),
          Text(formatCents(spread), style: AppText.numeric(AppText.displayXL)),
          const SizedBox(height: 4),
          Text(
            '${cheapest.key.name} is lowest; ${dearest.key.name} is highest for the same ${evidence.items.length} repeat buys.',
            style: AppText.body.copyWith(color: colors.textSecondary),
          ),
          const SizedBox(height: 28),
          const SectionLabel('Same basket, three tills'),
          const SizedBox(height: 8),
          LedgerCard(
            child: Column(
              children: ordered.map((entry) {
                final merchant = entry.key;
                final delta = entry.value - cheapest.value;
                final usual = merchant.key == 'local';
                return Padding(
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  child: Row(
                    children: <Widget>[
                      MerchantMark(
                        name: merchant.name,
                        filled: entry.key == cheapest.key,
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            Row(
                              children: <Widget>[
                                Flexible(
                                  child: Text(
                                    merchant.name,
                                    style: AppText.body.copyWith(
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                ),
                                if (usual) ...<Widget>[
                                  const SizedBox(width: 6),
                                  const StatusPill(HubStatus.confirmed),
                                ],
                              ],
                            ),
                            const SizedBox(height: 7),
                            ClipRRect(
                              borderRadius: BorderRadius.circular(8),
                              child: LinearProgressIndicator(
                                minHeight: 7,
                                value: entry.value / maxTotal,
                                backgroundColor: colors.divider,
                                color: entry.key == cheapest.key
                                    ? colors.good
                                    : colors.primary.withValues(alpha: .5),
                              ),
                            ),
                            const SizedBox(height: 7),
                            Wrap(
                              spacing: 6,
                              runSpacing: 4,
                              children: <Widget>[
                                if (usual)
                                  Text(
                                    'Your usual',
                                    style: AppText.captionS.copyWith(
                                      color: colors.primary,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                ...merchant.wins
                                    .take(2)
                                    .map(
                                      (win) => Text(
                                        '· $win',
                                        style: AppText.captionS.copyWith(
                                          color: colors.textSecondary,
                                        ),
                                      ),
                                    ),
                              ],
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 12),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: <Widget>[
                          MoneyText(
                            cents: entry.value,
                            style: AppText.bodyL.copyWith(
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          Text(
                            delta == 0 ? 'cheapest' : '+${formatCents(delta)}',
                            style: AppText.numeric(
                              AppText.captionS.copyWith(
                                color: delta == 0
                                    ? colors.good
                                    : colors.textSecondary,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                );
              }).toList(),
            ),
          ),
          const SizedBox(height: 20),
          LedgerCard(
            color: colors.warnBg,
            borderColor: Colors.transparent,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Icon(Icons.route_outlined, color: colors.warnFg),
                const SizedBox(height: 10),
                Text(
                  verdict.headline,
                  style: AppText.displayS.copyWith(color: colors.warnFg),
                ),
                const SizedBox(height: 8),
                Text(
                  verdict.note,
                  style: AppText.bodyS.copyWith(color: colors.warnFg),
                ),
                if (verdict.figure != null) ...<Widget>[
                  const SizedBox(height: 14),
                  Text(
                    verdict.figure!,
                    style: AppText.numeric(
                      AppText.displayM.copyWith(color: colors.warnFg),
                    ),
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(height: 28),
          const SectionLabel('Where they compete hardest'),
          const SizedBox(height: 8),
          ...evidence.items.map((item) {
            final confirmed = item.quotes
                .where((quote) => quote.isConfirmed)
                .toList();
            final low = confirmed
                .map((quote) => quote.unitCents(item.pack))
                .reduce(math.min);
            final high = confirmed
                .map((quote) => quote.unitCents(item.pack))
                .reduce(math.max);
            final annual =
                (high - low) * item.pack.amount * item.purchasesPerYear;
            return Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: LedgerCard(
                onTap: () => context.push(
                  '/items/${Uri.encodeComponent(item.name)}?from=rivals',
                ),
                child: Row(
                  children: <Widget>[
                    MerchantMark(name: item.name, size: 42),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Text(
                            item.name,
                            style: AppText.body.copyWith(
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          Text(
                            '${item.rhythm} · ${item.quotes.length} places',
                            style: AppText.captionS.copyWith(
                              color: colors.textSecondary,
                            ),
                          ),
                        ],
                      ),
                    ),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: <Widget>[
                        Text(
                          '${formatCents(annual)}/yr',
                          style: AppText.numeric(
                            AppText.body.copyWith(fontWeight: FontWeight.w700),
                          ),
                        ),
                        Text(
                          'at stake',
                          style: AppText.captionS.copyWith(
                            color: colors.textSecondary,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(width: 2),
                    const Icon(Icons.chevron_right_rounded),
                  ],
                ),
              ),
            );
          }),
          const SizedBox(height: 20),
          const SectionLabel('Everything else you track'),
          const SizedBox(height: 8),
          LedgerCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                const Text(
                  'Three settled items have comparable coverage across all three merchants.',
                ),
                const SizedBox(height: 8),
                Text(
                  'Cherry-picking each best price saves ${formatCents(spread * 18)} a year before travel. This view leaves uncovered items out of the claim.',
                  style: AppText.bodyS.copyWith(color: colors.textSecondary),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class ItemComparisonScreen extends ConsumerStatefulWidget {
  const ItemComparisonScreen({
    required this.itemName,
    this.origin = '/insights',
    super.key,
  });

  final String itemName;
  final String origin;

  @override
  ConsumerState<ItemComparisonScreen> createState() =>
      _ItemComparisonScreenState();
}

class _ItemComparisonScreenState extends ConsumerState<ItemComparisonScreen> {
  CompareScope _scope = CompareScope.yourStores;
  CompareBasis _basis = CompareBasis.perUnit;

  void _back() {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go(widget.origin);
    }
  }

  @override
  Widget build(BuildContext context) {
    final evidence = ref.watch(comparisonBasketProvider);
    final item = evidence.itemNamed(widget.itemName);
    if (item == null) {
      return Scaffold(
        appBar: AppBar(
          leading: BackButton(onPressed: _back),
          title: Text(widget.itemName),
        ),
        body: AppStatePanel(
          key: const Key('item-no-history'),
          icon: Icons.search_off_rounded,
          title: 'No price history yet',
          message:
              'Once this item appears on receipts from more than one merchant, '
              'its price history and the cheaper options show up here.',
          actionLabel: 'Scan a receipt',
          onAction: () => context.push('/capture'),
        ),
      );
    }

    final yourStores = evidence.merchants
        .map((merchant) => merchant.name)
        .toSet();
    final comparator = PriceComparator(
      item: item,
      scope: _scope,
      basis: _basis,
      yourMerchantNames: yourStores,
    );
    final result = comparator.build();
    final colors = context.appColors;
    final confirmedCount = item.quotes
        .where((quote) => quote.isConfirmed)
        .length;
    final ownCount = item.quotes
        .where((quote) => yourStores.contains(quote.merchantName))
        .length;

    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: _back),
        title: const Text('Item'),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.gutter,
          4,
          AppSpacing.gutter,
          36,
        ),
        children: <Widget>[
          Text(item.name, style: AppText.displayM),
          const SizedBox(height: 4),
          Text(
            '${item.rhythm} · bought ${item.timesBought} times',
            style: AppText.bodyS.copyWith(color: colors.textSecondary),
          ),
          const SizedBox(height: 18),
          MoneyText(
            cents: item.history.first.cents,
            style: AppText.displayL,
            semanticsPrefix: 'Last paid',
          ),
          const SizedBox(height: 4),
          Text(
            'last paid · ${item.history.first.merchantName}',
            style: AppText.caption.copyWith(color: colors.textSecondary),
          ),
          const SizedBox(height: 16),
          MiniBarChart(
            values: item.monthlySeriesCents,
            labels: trailingMonthLabels(item.monthlySeriesCents.length),
            height: 104,
          ),
          const SizedBox(height: 20),
          LedgerCard(
            color: result.didOverpay
                ? colors.warnBg
                : colors.good.withValues(alpha: .09),
            borderColor: Colors.transparent,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Icon(
                  result.didOverpay
                      ? Icons.savings_outlined
                      : Icons.check_circle_outline_rounded,
                  color: result.didOverpay ? colors.warnFg : colors.good,
                ),
                const SizedBox(height: 10),
                Text(
                  result.savedHeadline,
                  style: AppText.displayS.copyWith(
                    color: result.didOverpay ? colors.warnFg : colors.good,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  result.savedNote,
                  style: AppText.bodyS.copyWith(
                    color: result.didOverpay
                        ? colors.warnFg
                        : colors.textPrimary,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  result.sourceLine,
                  style: AppText.caption.copyWith(
                    color: result.didOverpay
                        ? colors.warnFg
                        : colors.textSecondary,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 22),
          LedgerCard(
            padding: EdgeInsets.zero,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                Padding(
                  padding: const EdgeInsets.all(16),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      MerchantMark(name: item.name, size: 52),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            Text(
                              '${result.rangeLow}–${result.rangeHigh}',
                              style: AppText.numeric(AppText.displayS),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              result.rangeNote ??
                                  '$confirmedCount confirmed comparable prices',
                              style: AppText.captionS.copyWith(
                                color: colors.textSecondary,
                              ),
                            ),
                            Text(
                              item.name,
                              style: AppText.body.copyWith(
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                if (item.quotes.length > ownCount)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
                    child: SegmentedButton<CompareScope>(
                      showSelectedIcon: false,
                      segments: <ButtonSegment<CompareScope>>[
                        ButtonSegment(
                          value: CompareScope.yourStores,
                          label: Text('Where you shop $ownCount'),
                        ),
                        ButtonSegment(
                          value: CompareScope.everywhere,
                          label: Text('Everywhere ${item.quotes.length}'),
                        ),
                      ],
                      selected: <CompareScope>{_scope},
                      onSelectionChanged: (values) =>
                          setState(() => _scope = values.first),
                    ),
                  ),
                if (result.showBasisToggle)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 14),
                    child: Wrap(
                      spacing: 8,
                      children: <Widget>[
                        ChoiceChip(
                          label: const Text('Per pack'),
                          selected: _basis == CompareBasis.perPack,
                          onSelected: (_) =>
                              setState(() => _basis = CompareBasis.perPack),
                        ),
                        ChoiceChip(
                          label: Text(result.basisUnitLabel),
                          selected: _basis == CompareBasis.perUnit,
                          onSelected: (_) =>
                              setState(() => _basis = CompareBasis.perUnit),
                        ),
                      ],
                    ),
                  ),
                const Divider(),
                ...result.rows.map((row) => _ComparisonPriceRow(row: row)),
              ],
            ),
          ),
          const SizedBox(height: 20),
          LedgerCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                const SectionLabel('Value verdict'),
                const SizedBox(height: 10),
                Text(result.verdictHeadline, style: AppText.displayS),
                const SizedBox(height: 8),
                Text(
                  result.verdictNote,
                  style: AppText.bodyS.copyWith(color: colors.textSecondary),
                ),
                if (result.verdictAnnualSaving != null) ...<Widget>[
                  const SizedBox(height: 12),
                  Text(
                    result.verdictAnnualSaving!,
                    style: AppText.numeric(
                      AppText.displayM.copyWith(color: colors.good),
                    ),
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(height: 26),
          const SectionLabel('Last bought'),
          const SizedBox(height: 8),
          LedgerCard(
            padding: EdgeInsets.zero,
            child: Column(
              children: item.history
                  .map(
                    (purchase) => ListTile(
                      minTileHeight: AppSpacing.rowMinHeight,
                      leading: MerchantMark(
                        name: purchase.merchantName,
                        size: 36,
                      ),
                      title: Text(purchase.merchantName),
                      subtitle: Text(
                        '${purchase.date.day}/${purchase.date.month}/${purchase.date.year} · Your receipt',
                      ),
                      trailing: MoneyText(
                        cents: purchase.cents,
                        style: AppText.body.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  )
                  .toList(),
            ),
          ),
          const SizedBox(height: 20),
          FilledButton.icon(
            onPressed: () {
              ref
                  .read(appControllerProvider.notifier)
                  .addShoppingItem(item.name);
              showOutcomeToast(context, '${item.name} added to your list');
            },
            icon: const Icon(Icons.playlist_add_rounded),
            label: const Text('Add to list'),
          ),
        ],
      ),
    );
  }
}

class _ComparisonPriceRow extends StatelessWidget {
  const _ComparisonPriceRow({required this.row});

  final ComparisonRow row;

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;
    final quote = row.quote;
    return Opacity(
      opacity: row.isSoft ? .58 : 1,
      child: Container(
        color: row.isBestValue
            ? colors.good.withValues(alpha: .07)
            : Colors.transparent,
        padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            MerchantMark(
              name: quote.merchantName,
              size: 42,
              filled: row.isBestValue,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Row(
                    children: <Widget>[
                      Flexible(
                        child: Text(
                          quote.merchantName,
                          style: AppText.body.copyWith(
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                      if (row.isBestValue) ...<Widget>[
                        const SizedBox(width: 6),
                        Icon(
                          Icons.workspace_premium_rounded,
                          size: 18,
                          color: colors.good,
                        ),
                      ],
                    ],
                  ),
                  if (row.isBestValue)
                    Text(
                      'Best value',
                      style: AppText.captionS.copyWith(
                        color: colors.good,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  Text(
                    quote.note,
                    style: AppText.captionS.copyWith(
                      color: colors.textSecondary,
                    ),
                  ),
                  const SizedBox(height: 6),
                  EvidenceChip(
                    source: quote.sourceLabel,
                    freshness: quote.freshness,
                    soft: row.isSoft,
                  ),
                  if (quote.softNote != null) ...<Widget>[
                    const SizedBox(height: 5),
                    Text(
                      quote.softNote!,
                      style: AppText.captionS.copyWith(
                        color: colors.warn,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                  if (quote.hasStockSignal && !quote.inStock) ...<Widget>[
                    const SizedBox(height: 5),
                    Text(
                      'Reported out of stock',
                      style: AppText.captionS.copyWith(color: colors.error),
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(width: 10),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: <Widget>[
                Text(
                  row.priceLabel,
                  style: AppText.numeric(
                    AppText.bodyL.copyWith(fontWeight: FontWeight.w700),
                  ),
                ),
                Text(
                  row.subLabel,
                  style: AppText.numeric(
                    AppText.captionS.copyWith(color: colors.textSecondary),
                  ),
                ),
                if (row.saveLabel != null) ...<Widget>[
                  const SizedBox(height: 5),
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 4,
                    ),
                    decoration: BoxDecoration(
                      color: colors.good.withValues(alpha: .1),
                      borderRadius: BorderRadius.circular(AppRadii.chip),
                    ),
                    child: Text(
                      row.saveLabel!,
                      style: AppText.captionS.copyWith(
                        color: colors.good,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }
}

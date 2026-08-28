import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../format/money.dart';
import 'app_theme.dart';

// Re-exported so the many screens that already import this file for
// `formatCents` keep working, while there is only one implementation.
export '../format/money.dart' show formatCents;

class LedgerCard extends StatelessWidget {
  const LedgerCard({
    required this.child,
    this.padding = const EdgeInsets.all(AppSpacing.cardPad),
    this.onTap,
    this.color,
    this.borderColor,
    this.semanticLabel,
    super.key,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final VoidCallback? onTap;
  final Color? color;
  final Color? borderColor;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;
    return Semantics(
      container: true,
      button: onTap != null,
      label: semanticLabel,
      child: Material(
        color: color ?? colors.surface,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadii.card),
          side: BorderSide(color: borderColor ?? colors.divider),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: Padding(padding: padding, child: child),
        ),
      ),
    );
  }
}

class RaisedLedgerSheet extends StatelessWidget {
  const RaisedLedgerSheet({
    required this.child,
    this.padding = const EdgeInsets.fromLTRB(24, 24, 24, 32),
    super.key,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: const BorderRadius.vertical(
          top: Radius.circular(AppRadii.sheet),
        ),
        border: Border(top: BorderSide(color: colors.divider)),
      ),
      child: Padding(padding: padding, child: child),
    );
  }
}

/// One row in a ledger list.
///
/// Three screens hand-rolled this: the same
/// `Material > InkWell > Container(min height, padding, one-pixel bottom
/// divider)` skeleton, with three different magic minimum heights — 76, 72 and
/// 64 — while `AppSpacing.rowMinHeight` sat in the design system unused. A
/// minimum only decides the height of a row whose content is shorter than it
/// is, so those numbers differed without changing what anyone saw. What they
/// did do was make it easy for the next row to land under the tap target, and
/// easy to forget the divider.
///
/// The contents stay the caller's: these rows show genuinely different things.
/// It is the frame around them that was copied.
class LedgerRow extends StatelessWidget {
  const LedgerRow({
    required this.child,
    this.onTap,
    this.showDivider = true,
    this.semanticLabel,
    super.key,
  });

  final Widget child;

  /// Omit for a row that is not tappable; the ink and button semantics go with
  /// it, rather than being advertised to a screen reader and doing nothing.
  final VoidCallback? onTap;

  final bool showDivider;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    final row = Container(
      constraints: const BoxConstraints(minHeight: AppSpacing.rowMinHeight),
      padding: const EdgeInsets.symmetric(vertical: 12),
      decoration: BoxDecoration(
        border: showDivider
            ? Border(bottom: BorderSide(color: context.appColors.divider))
            : null,
      ),
      child: child,
    );

    final onTap = this.onTap;
    if (onTap == null) return row;

    final tappable = Material(
      color: Colors.transparent,
      child: InkWell(onTap: onTap, child: row),
    );
    final label = semanticLabel;
    return label == null
        ? tappable
        : Semantics(button: true, label: label, child: tappable);
  }
}

class SectionLabel extends StatelessWidget {
  const SectionLabel(this.label, {this.trailing, super.key});

  final String label;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final labelWidget = Text(
      label.toUpperCase(),
      style: AppText.sectionLabel.copyWith(
        color: context.appColors.textSecondary,
      ),
    );
    if (trailing == null) return labelWidget;
    return Row(
      children: <Widget>[
        Expanded(child: labelWidget),
        trailing!,
      ],
    );
  }
}

class MoneyText extends StatelessWidget {
  const MoneyText({
    required this.cents,
    this.style,
    this.semanticsPrefix,
    super.key,
  });

  final num cents;
  final TextStyle? style;
  final String? semanticsPrefix;

  @override
  Widget build(BuildContext context) {
    final label = formatCents(cents);
    return Semantics(
      label: semanticsPrefix == null ? label : '$semanticsPrefix $label',
      child: ExcludeSemantics(
        child: Text(label, style: AppText.numeric(style ?? AppText.bodyL)),
      ),
    );
  }
}

class DeltaText extends StatelessWidget {
  const DeltaText(this.value, {this.compact = false, super.key});

  final double value;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;
    final isDown = value < 0;
    final label =
        '${isDown
            ? '↓'
            : value > 0
            ? '↑'
            : '—'} ${value.abs().toStringAsFixed(0)}%${compact ? '' : ' from last month'}';
    return Text(
      label,
      style: AppText.numeric(
        AppText.caption.copyWith(
          color: isDown
              ? colors.good
              : value > 0
              ? colors.warn
              : colors.textSecondary,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

class MerchantMark extends StatelessWidget {
  const MerchantMark({
    required this.name,
    this.size = 38,
    this.filled = false,
    super.key,
  });

  final String name;
  final double size;
  final bool filled;

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;
    final words = name.trim().split(RegExp(r'\s+'));
    final initials = words
        .take(2)
        .map((word) => word.isEmpty ? '' : word[0].toUpperCase())
        .join();
    return Semantics(
      label: name,
      child: Container(
        width: size,
        height: size,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: filled ? colors.primary : colors.actionSelected,
          borderRadius: BorderRadius.circular(
            size > 45 ? AppRadii.markLarge : AppRadii.mark,
          ),
          border: Border.all(color: filled ? colors.primary : colors.divider),
        ),
        child: Text(
          initials,
          style: AppText.caption.copyWith(
            color: filled ? colors.onPrimary : colors.primary,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
    );
  }
}

/// The same mark, for a product rather than a shop.
///
/// `.interface-design/system.md` names `MerchantMark` and `ItemMark` together
/// and gives them one treatment, so this is deliberately not a second
/// implementation. It exists because three item surfaces were calling
/// `MerchantMark(name: item.name)`, which reads as a claim that a product is a
/// shop, and because a product mark is where the two will diverge first if
/// they ever do.
class ItemMark extends StatelessWidget {
  const ItemMark({required this.name, this.size = 38, super.key});

  final String name;
  final double size;

  @override
  Widget build(BuildContext context) => MerchantMark(name: name, size: size);
}

class ReceiptAppMark extends StatelessWidget {
  const ReceiptAppMark({this.size = 64, super.key});

  final double size;

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;
    return Semantics(
      label: 'Receipts Hub',
      image: true,
      child: CustomPaint(
        size: Size.square(size),
        painter: _ReceiptMarkPainter(
          primary: colors.primary,
          paper: colors.surface,
          line: colors.divider,
        ),
      ),
    );
  }
}

class _ReceiptMarkPainter extends CustomPainter {
  const _ReceiptMarkPainter({
    required this.primary,
    required this.paper,
    required this.line,
  });

  final Color primary;
  final Color paper;
  final Color line;

  @override
  void paint(Canvas canvas, Size size) {
    final body = RRect.fromRectAndRadius(
      Rect.fromLTWH(
        size.width * .17,
        size.height * .08,
        size.width * .66,
        size.height * .80,
      ),
      Radius.circular(size.width * .13),
    );
    canvas.drawRRect(body, Paint()..color = primary);
    final inner = RRect.fromRectAndRadius(
      Rect.fromLTWH(
        size.width * .28,
        size.height * .19,
        size.width * .44,
        size.height * .53,
      ),
      Radius.circular(size.width * .05),
    );
    canvas.drawRRect(inner, Paint()..color = paper);
    final stroke = Paint()
      ..color = line
      ..strokeWidth = math.max(1, size.width * .025)
      ..strokeCap = StrokeCap.round;
    for (final y in <double>[.32, .43, .54]) {
      canvas.drawLine(
        Offset(size.width * .36, size.height * y),
        Offset(size.width * .64, size.height * y),
        stroke,
      );
    }
    final teeth = Path()..moveTo(size.width * .29, size.height * .72);
    for (var index = 0; index < 5; index++) {
      final x = size.width * (.29 + index * .11);
      teeth.lineTo(x + size.width * .055, size.height * .80);
      teeth.lineTo(x + size.width * .11, size.height * .72);
    }
    canvas.drawPath(
      teeth,
      Paint()
        ..color = paper
        ..style = PaintingStyle.fill,
    );
  }

  @override
  bool shouldRepaint(covariant _ReceiptMarkPainter oldDelegate) =>
      primary != oldDelegate.primary ||
      paper != oldDelegate.paper ||
      line != oldDelegate.line;
}

class EvidenceChip extends StatelessWidget {
  const EvidenceChip({
    required this.source,
    this.freshness,
    this.soft = false,
    super.key,
  });

  final String source;
  final String? freshness;
  final bool soft;

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;
    return Wrap(
      spacing: 8,
      runSpacing: 4,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: <Widget>[
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
          decoration: BoxDecoration(
            color: soft ? colors.actionHover : colors.actionSelected,
            borderRadius: BorderRadius.circular(AppRadii.chip),
          ),
          child: Text(
            source,
            style: AppText.captionS.copyWith(
              color: colors.textSecondary,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        if (freshness != null)
          Text(
            freshness!,
            style: AppText.captionS.copyWith(color: colors.textSecondary),
          ),
      ],
    );
  }
}

enum HubStatus { review, duplicate, failed, confirmed, queued }

class StatusPill extends StatelessWidget {
  const StatusPill(this.status, {super.key});

  final HubStatus status;

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;
    final (label, icon, foreground, background) = switch (status) {
      HubStatus.review => (
        'Review',
        Icons.error_outline_rounded,
        colors.warn,
        colors.warnBg,
      ),
      HubStatus.duplicate => (
        'Possible duplicate',
        Icons.content_copy_rounded,
        colors.warn,
        colors.warnBg,
      ),
      HubStatus.failed => (
        'Read failed',
        Icons.sync_problem_rounded,
        colors.error,
        colors.error.withValues(alpha: .09),
      ),
      HubStatus.confirmed => (
        'Filed',
        Icons.check_rounded,
        colors.good,
        colors.good.withValues(alpha: .09),
      ),
      HubStatus.queued => (
        'Queued',
        Icons.schedule_rounded,
        colors.textSecondary,
        colors.actionSelected,
      ),
    };
    return Semantics(
      label: label,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
        decoration: BoxDecoration(
          color: background,
          borderRadius: BorderRadius.circular(AppRadii.chip),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(icon, size: 14, color: foreground),
            const SizedBox(width: 5),
            Text(
              label,
              style: AppText.captionS.copyWith(
                color: foreground,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class MiniBarChart extends StatelessWidget {
  const MiniBarChart({
    required this.values,
    this.labels = const <String>[],
    this.height = 96,
    super.key,
  });

  final List<num> values;
  final List<String> labels;
  final double height;

  @override
  Widget build(BuildContext context) {
    final description = values.isEmpty
        ? 'No spend history'
        : 'Six month spend trend: ${values.map((value) => formatCents(value)).join(', ')}';
    return Semantics(
      label: description,
      image: true,
      child: SizedBox(
        height: height,
        width: double.infinity,
        child: CustomPaint(
          painter: _MiniBarChartPainter(
            values: values,
            labels: labels,
            colors: context.appColors,
          ),
        ),
      ),
    );
  }
}

class _MiniBarChartPainter extends CustomPainter {
  const _MiniBarChartPainter({
    required this.values,
    required this.labels,
    required this.colors,
  });

  final List<num> values;
  final List<String> labels;
  final AppColors colors;

  @override
  void paint(Canvas canvas, Size size) {
    if (values.isEmpty) return;
    final maxValue = values.fold<double>(
      0,
      (current, value) => math.max(current, value.toDouble()),
    );
    final gap = 8.0;
    final labelHeight = labels.isEmpty ? 0.0 : 18.0;
    final available = size.height - labelHeight;
    final width = (size.width - gap * (values.length - 1)) / values.length;
    final textPainter = TextPainter(
      textDirection: TextDirection.ltr,
      textAlign: TextAlign.center,
    );
    for (var index = 0; index < values.length; index++) {
      final ratio = maxValue <= 0 ? 0.0 : values[index] / maxValue;
      final barHeight = math.max(5.0, available * ratio);
      final rect = RRect.fromRectAndRadius(
        Rect.fromLTWH(
          index * (width + gap),
          available - barHeight,
          width,
          barHeight,
        ),
        const Radius.circular(8),
      );
      canvas.drawRRect(
        rect,
        Paint()
          ..color = index == values.length - 1
              ? colors.primary
              : colors.primary.withValues(alpha: .22),
      );
      if (index < labels.length) {
        textPainter.text = TextSpan(
          text: labels[index],
          style: AppText.captionS.copyWith(color: colors.textSecondary),
        );
        textPainter.layout(maxWidth: width);
        textPainter.paint(
          canvas,
          Offset(
            index * (width + gap) + (width - textPainter.width) / 2,
            available + 3,
          ),
        );
      }
    }
  }

  @override
  bool shouldRepaint(covariant _MiniBarChartPainter oldDelegate) =>
      oldDelegate.values != values ||
      oldDelegate.labels != labels ||
      oldDelegate.colors != colors;
}

/// A flat placeholder the size of content that has not arrived.
///
/// No shimmer: the interface system communicates depth through surface shifts
/// rather than motion, and a state a person has to watch move to understand is
/// worse than one they can simply read.
class SkeletonBlock extends StatelessWidget {
  const SkeletonBlock({this.width, this.height = 16, super.key});

  final double? width;
  final double height;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        color: context.appColors.actionSelected,
        borderRadius: BorderRadius.circular(height < 20 ? 6 : AppRadii.field),
      ),
    );
  }
}

class AppStatePanel extends StatelessWidget {
  const AppStatePanel({
    required this.icon,
    required this.title,
    required this.message,
    this.actionLabel,
    this.onAction,
    super.key,
  });

  final IconData icon;
  final String title;
  final String message;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;
    return Semantics(
      container: true,
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.gutter,
          vertical: 40,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Container(
              width: 56,
              height: 56,
              decoration: BoxDecoration(
                color: colors.actionSelected,
                shape: BoxShape.circle,
              ),
              child: Icon(icon, color: colors.primary),
            ),
            const SizedBox(height: 16),
            Text(title, style: AppText.displayS, textAlign: TextAlign.center),
            const SizedBox(height: 8),
            Text(
              message,
              style: AppText.bodyS.copyWith(color: colors.textSecondary),
              textAlign: TextAlign.center,
            ),
            if (actionLabel != null && onAction != null) ...<Widget>[
              const SizedBox(height: 20),
              FilledButton(onPressed: onAction, child: Text(actionLabel!)),
            ],
          ],
        ),
      ),
    );
  }
}

class KeyValueStat extends StatelessWidget {
  const KeyValueStat({
    required this.label,
    required this.value,
    this.numeric = true,
    super.key,
  });

  final String label;
  final String value;
  final bool numeric;

  @override
  Widget build(BuildContext context) {
    final style = AppText.bodyL.copyWith(fontWeight: FontWeight.w600);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(value, style: numeric ? AppText.numeric(style) : style),
        const SizedBox(height: 2),
        Text(
          label,
          style: AppText.captionS.copyWith(
            color: context.appColors.textSecondary,
          ),
        ),
      ],
    );
  }
}

void showOutcomeToast(
  BuildContext context,
  String message, {
  bool hasNavigation = true,
}) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(
      SnackBar(
        content: Text(message),
        margin: EdgeInsets.fromLTRB(16, 0, 16, hasNavigation ? 84 : 24),
      ),
    );
}

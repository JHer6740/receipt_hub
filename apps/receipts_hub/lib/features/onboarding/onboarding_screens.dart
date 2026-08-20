import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/design/app_components.dart';
import '../../core/design/app_theme.dart';
import '../developer/host_connection_screen.dart' show developerToolsProvider;

/// First run.
///
/// The price-sharing consent panel that used to sit here described an
/// anonymous shared index that will not exist at launch, and asked for consent
/// to it before the person had an account. Consent belongs with the feature.
class WelcomeScreen extends ConsumerWidget {
  const WelcomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final colors = context.appColors;
    final showDeveloperTools = ref.watch(developerToolsProvider);
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: <Widget>[
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(
                  AppSpacing.gutter,
                  24,
                  AppSpacing.gutter,
                  16,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    const Align(
                      alignment: Alignment.centerLeft,
                      child: ReceiptAppMark(size: 56),
                    ),
                    const SizedBox(height: 24),
                    Text(
                      'Your receipts,\nworth something to you',
                      style: AppText.displayL,
                    ),
                    const SizedBox(height: 16),
                    Text(
                      'File the paper trail, see where the household money '
                      'goes, and find out when another shop is quietly '
                      'charging less for the things you buy on repeat.',
                      style: AppText.bodyL.copyWith(
                        color: colors.textSecondary,
                      ),
                    ),
                    const SizedBox(height: 24),
                    _ValueRow(
                      icon: Icons.document_scanner_outlined,
                      title: 'Photograph the receipt',
                      detail: 'Every line item is read and filed for you.',
                    ),
                    _ValueRow(
                      icon: Icons.insights_outlined,
                      title: 'See where the money goes',
                      detail: 'Monthly totals and trends by collection.',
                    ),
                    _ValueRow(
                      icon: Icons.compare_arrows_rounded,
                      title: 'Compare what you buy again',
                      detail:
                          'Built from your own receipts, so every price has '
                          'a source.',
                    ),
                  ],
                ),
              ),
            ),
            DecoratedBox(
              decoration: BoxDecoration(
                color: colors.surface,
                border: Border(top: BorderSide(color: colors.divider)),
              ),
              child: Padding(
                padding: const EdgeInsets.fromLTRB(
                  AppSpacing.gutter,
                  12,
                  AppSpacing.gutter,
                  14,
                ),
                // Two actions, two destinations. They both used to open the
                // same host-address-and-PIN screen, so "I already have an
                // account" led somewhere that had no concept of an account.
                //
                // "Join a household" used to sit here as a third action, which
                // let someone reach the ledger before authenticating. Joining
                // a household belongs after sign-in.
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    FilledButton(
                      onPressed: () => context.push('/create-account'),
                      child: const Text('Get started'),
                    ),
                    const SizedBox(height: 8),
                    TextButton(
                      onPressed: () => context.push('/sign-in'),
                      child: const Text('I already have an account'),
                    ),
                    // Debug builds only, and absent from release entirely.
                    if (showDeveloperTools)
                      TextButton(
                        onPressed: () => context.push('/developer/connection'),
                        child: Text(
                          'Developer: connect to a host',
                          style: AppText.captionS.copyWith(
                            color: colors.textSecondary,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ValueRow extends StatelessWidget {
  const _ValueRow({
    required this.icon,
    required this.title,
    required this.detail,
  });

  final IconData icon;
  final String title;
  final String detail;

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;
    return Padding(
      padding: const EdgeInsets.only(bottom: 18),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: colors.actionSelected,
              borderRadius: BorderRadius.circular(AppRadii.mark),
            ),
            child: Icon(icon, size: 20, color: colors.primary),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  title,
                  style: AppText.body.copyWith(fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 3),
                Text(
                  detail,
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

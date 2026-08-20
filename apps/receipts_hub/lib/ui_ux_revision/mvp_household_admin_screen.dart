import 'package:flutter/material.dart';

import '../core/design/app_components.dart';
import '../core/design/app_theme.dart';

class MvpHouseholdAdminScreen extends StatefulWidget {
  const MvpHouseholdAdminScreen({super.key});

  @override
  State<MvpHouseholdAdminScreen> createState() => _MvpHouseholdAdminScreenState();
}

class _MvpHouseholdAdminScreenState extends State<MvpHouseholdAdminScreen> {
  final List<String> _requests = ['Alex Morgan'];

  void _resolve(String name, bool approved) {
    setState(() => _requests.remove(name));
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          approved
              ? 'Access approved for $name.'
              : 'Join request from $name declined.',
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;
    return Scaffold(
      appBar: AppBar(title: const Text('Household members')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(AppSpacing.gutter, 16, AppSpacing.gutter, 32),
        children: [
          LedgerCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('The Morgan household', style: AppText.screenTitle),
                const SizedBox(height: 6),
                Text('Household ID · H7K4-92QF', style: AppText.caption.copyWith(color: colors.textSecondary)),
                const SizedBox(height: 12),
                Text('Share this ID with people you trust. They still need your approval before they can view household receipts.', style: AppText.bodyS.copyWith(color: colors.textSecondary)),
              ],
            ),
          ),
          const SizedBox(height: 24),
                Text('Pending access requests', style: AppText.screenTitle),
          const SizedBox(height: 10),
          if (_requests.isEmpty)
            LedgerCard(
              child: Text('No pending requests.', style: AppText.body.copyWith(color: colors.textSecondary)),
            )
          else
            ..._requests.map(
              (name) => Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: LedgerCard(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(name, style: AppText.body.copyWith(fontWeight: FontWeight.w600)),
                      const SizedBox(height: 4),
                      Text('Requests access to this household', style: AppText.caption.copyWith(color: colors.textSecondary)),
                      const SizedBox(height: 12),
                      Row(
                        children: [
                          Expanded(child: OutlinedButton(onPressed: () => _resolve(name, false), child: const Text('Decline'))),
                          const SizedBox(width: 10),
                          Expanded(child: FilledButton(onPressed: () => _resolve(name, true), child: const Text('Approve'))),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

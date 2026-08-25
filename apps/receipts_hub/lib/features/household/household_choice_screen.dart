// The step between having an account and having a ledger.
//
// An account is personal; receipts belong to a household. So after signing in
// a person either starts a household or asks to join one that already exists
// and adds their receipts to it. Joining is a request, not access: nothing of
// that household is visible until an owner or admin approves it.
//
// This screen used to not exist. "Join a household" sat on Welcome instead,
// before authentication, with a "Not now" that walked straight into the ledger
// with no session at all.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/design/app_components.dart';
import '../../core/design/app_theme.dart';
import '../../core/network/api_models.dart' as wire;
import '../../core/state/app_state.dart';

class HouseholdChoiceScreen extends ConsumerStatefulWidget {
  const HouseholdChoiceScreen({super.key});

  @override
  ConsumerState<HouseholdChoiceScreen> createState() =>
      _HouseholdChoiceScreenState();
}

class _HouseholdChoiceScreenState extends ConsumerState<HouseholdChoiceScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) ref.read(appControllerProvider.notifier).loadHouseholds();
    });
  }

  Future<void> _enter(wire.HouseholdSummary household) async {
    final failure = await ref
        .read(appControllerProvider.notifier)
        .enterHousehold(household);
    if (!mounted) return;
    if (failure != null) {
      showOutcomeToast(context, failure, hasNavigation: false);
      return;
    }
    context.go('/home');
  }

  Future<void> _createHousehold() async {
    final name = await showDialog<String>(
      context: context,
      builder: (dialogContext) => const _NameHouseholdDialog(),
    );
    final trimmed = name?.trim() ?? '';
    if (trimmed.isEmpty || !mounted) return;
    final failure = await ref
        .read(appControllerProvider.notifier)
        .createHousehold(trimmed);
    if (!mounted) return;
    if (failure != null) {
      showOutcomeToast(context, failure, hasNavigation: false);
      return;
    }
    context.go('/home');
  }

  @override
  Widget build(BuildContext context) {
    final app = ref.watch(appControllerProvider);
    final colors = context.appColors;
    final active = app.activeHouseholds;
    final pending = app.pendingHouseholds;
    final controller = ref.read(appControllerProvider.notifier);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Your households'),
        actions: <Widget>[
          IconButton(
            tooltip: 'Sign out',
            onPressed: () async {
              await controller.signOut();
              if (context.mounted) context.go('/welcome');
            },
            icon: const Icon(Icons.logout_rounded),
          ),
        ],
      ),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: () async => controller.loadHouseholds(),
          child: ListView(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.gutter,
              16,
              AppSpacing.gutter,
              32,
            ),
            children: <Widget>[
              Text('Where do these receipts go?', style: AppText.displayM),
              const SizedBox(height: 10),
              Text(
                'Receipts belong to a household. Start your own, or join one '
                'that already exists and add yours to it.',
                style: AppText.body.copyWith(color: colors.textSecondary),
              ),
              const SizedBox(height: 28),

              if (!app.householdsLoaded && app.isLoading) ...<Widget>[
                const SkeletonBlock(height: 72),
                const SizedBox(height: 12),
                const SkeletonBlock(height: 72),
              ] else ...<Widget>[
                if (active.isNotEmpty) ...<Widget>[
                  const SectionLabel('Your households'),
                  const SizedBox(height: 8),
                  for (final household in active)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: LedgerCard(
                        key: ValueKey<String>('household-${household.id}'),
                        onTap: () => _enter(household),
                        semanticLabel:
                            '${household.name}. ${_roleLine(household)}',
                        child: Row(
                          children: <Widget>[
                            MerchantMark(name: household.name, size: 40),
                            const SizedBox(width: 14),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: <Widget>[
                                  Text(
                                    household.name,
                                    style: AppText.body.copyWith(
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                  const SizedBox(height: 3),
                                  Text(
                                    _roleLine(household),
                                    style: AppText.caption.copyWith(
                                      color: colors.textSecondary,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            Icon(
                              Icons.chevron_right_rounded,
                              color: colors.textSecondary,
                            ),
                          ],
                        ),
                      ),
                    ),
                  const SizedBox(height: 16),
                ],

                // A request is visibly not access. It sits here until an owner
                // or admin decides, and none of that household's receipts
                // appear in the meantime.
                if (pending.isNotEmpty) ...<Widget>[
                  const SectionLabel('Waiting for approval'),
                  const SizedBox(height: 8),
                  for (final household in pending)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: LedgerCard(
                        key: ValueKey<String>('pending-${household.id}'),
                        color: colors.warnBg,
                        borderColor: Colors.transparent,
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            Icon(Icons.schedule_outlined, color: colors.warnFg),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: <Widget>[
                                  Text(
                                    household.name,
                                    style: AppText.body.copyWith(
                                      color: colors.warnFg,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                  const SizedBox(height: 3),
                                  Text(
                                    'An owner or admin still needs to approve '
                                    'you.',
                                    style: AppText.caption.copyWith(
                                      color: colors.warnFg,
                                    ),
                                  ),
                                  const SizedBox(height: 6),
                                  TextButton(
                                    onPressed: () => controller
                                        .cancelJoinRequest(household.id),
                                    style: TextButton.styleFrom(
                                      foregroundColor: colors.warnFg,
                                      padding: EdgeInsets.zero,
                                      minimumSize: const Size(44, 44),
                                    ),
                                    child: const Text('Withdraw request'),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  const SizedBox(height: 16),
                ],

                if (active.isEmpty && pending.isEmpty && app.householdsLoaded)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Text(
                      'You are not in a household yet.',
                      style: AppText.bodyS.copyWith(
                        color: colors.textSecondary,
                      ),
                    ),
                  ),

                if (app.failureMessage != null && !app.householdsLoaded)
                  AppStatePanel(
                    key: const Key('households-unavailable'),
                    icon: Icons.cloud_off_outlined,
                    title: 'Could not load your households',
                    message: app.failureMessage!,
                    actionLabel: 'Try again',
                    onAction: controller.loadHouseholds,
                  ),
              ],

              const SizedBox(height: 12),
              FilledButton.icon(
                key: const Key('create-household'),
                onPressed: app.isLoading ? null : _createHousehold,
                icon: const Icon(Icons.add_home_outlined),
                label: const Text('Create a household'),
              ),
              const SizedBox(height: 8),
              OutlinedButton.icon(
                key: const Key('join-household'),
                onPressed: app.isLoading
                    ? null
                    : () => context.push('/household/join'),
                icon: const Icon(Icons.group_add_outlined),
                label: const Text('Join a household'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  String _roleLine(wire.HouseholdSummary household) {
    final role = switch (household.role) {
      'owner' => 'You own this household',
      'admin' => 'You help manage this household',
      'viewer' => 'You can view this household',
      _ => 'You are a member',
    };
    if (household.memberCount <= 1) return role;
    return '$role · ${household.memberCount} people';
  }
}

class _NameHouseholdDialog extends StatefulWidget {
  const _NameHouseholdDialog();

  @override
  State<_NameHouseholdDialog> createState() => _NameHouseholdDialogState();
}

class _NameHouseholdDialogState extends State<_NameHouseholdDialog> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Name your household'),
      content: TextField(
        controller: _controller,
        autofocus: true,
        textCapitalization: TextCapitalization.words,
        onSubmitted: (value) => Navigator.of(context).pop(value),
        decoration: const InputDecoration(
          labelText: 'Household name',
          hintText: 'The Morgan household',
        ),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () => Navigator.of(context).pop(_controller.text),
          child: const Text('Create'),
        ),
      ],
    );
  }
}

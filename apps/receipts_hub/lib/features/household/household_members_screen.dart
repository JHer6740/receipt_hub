// Who is in this household, and who is asking to be.
//
// This screen existed but was reachable from nowhere and rendered a hardcoded
// `['Alex Morgan']`, so the join requests the app sends could never be
// approved by anyone. Approve, decline and remove now go to the service.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/data/receipts_repository.dart';
import '../../core/design/app_components.dart';
import '../../core/design/app_theme.dart';
import '../../core/network/api_models.dart' as wire;
import '../../core/network/mobile_api.dart';
import '../../core/state/app_state.dart';
import '../../core/widgets/household_gate.dart';

/// The people in one household, fetched from the service.
final householdMembersProvider = FutureProvider.autoDispose
    .family<List<wire.HouseholdMember>, String>((ref, householdId) async {
      final api = ref.watch(mobileApiProvider);
      if (!api.hasSession) return const <wire.HouseholdMember>[];
      return api.householdMembers(householdId);
    });

class HouseholdMembersScreen extends ConsumerWidget {
  const HouseholdMembersScreen({this.householdId, super.key});

  /// Which household. Falls back to the active one.
  final String? householdId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final app = ref.watch(appControllerProvider);
    final active = app.activeHouseholds;
    final id = householdId ?? (active.isEmpty ? null : active.first.id);

    return Scaffold(
      appBar: AppBar(
        title: const Text('People'),
        leading: IconButton(
          tooltip: 'Back',
          onPressed: () =>
              context.canPop() ? context.pop() : context.go('/account'),
          icon: const Icon(Icons.arrow_back_rounded),
        ),
      ),
      body: id == null
          ? AppStatePanel(
              key: const Key('members-no-household'),
              icon: Icons.home_work_outlined,
              title: 'No household yet',
              message:
                  'Create or join a household and the people in it appear '
                  'here.',
              actionLabel: 'Your households',
              onAction: () => context.go('/household'),
            )
          : _MembersBody(householdId: id),
    );
  }
}

class _MembersBody extends ConsumerWidget {
  const _MembersBody({required this.householdId});

  final String householdId;

  Future<void> _resolve(
    BuildContext context,
    WidgetRef ref, {
    required wire.HouseholdMember member,
    required bool approve,
  }) async {
    final api = ref.read(mobileApiProvider);
    try {
      await api.resolveJoinRequest(
        householdId: householdId,
        requestId: member.id,
        approve: approve,
      );
      ref.invalidate(householdMembersProvider(householdId));
      if (!context.mounted) return;
      showOutcomeToast(
        context,
        approve
            ? '${member.name} can now see this household'
            : 'Request from ${member.name} declined',
        hasNavigation: false,
      );
    } on ApiFailure catch (failure) {
      if (!context.mounted) return;
      showOutcomeToast(context, failure.message, hasNavigation: false);
    }
  }

  Future<void> _remove(
    BuildContext context,
    WidgetRef ref,
    wire.HouseholdMember member,
  ) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text('Remove ${member.name}?'),
        content: const Text(
          'They lose access to this household. Receipts they already filed '
          'stay in the ledger.',
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            style: FilledButton.styleFrom(
              backgroundColor: context.appColors.error,
              foregroundColor: context.appColors.onPrimary,
            ),
            child: const Text('Remove'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await ref
          .read(mobileApiProvider)
          .removeHouseholdMember(householdId: householdId, memberId: member.id);
      ref.invalidate(householdMembersProvider(householdId));
      if (!context.mounted) return;
      showOutcomeToast(context, '${member.name} removed', hasNavigation: false);
    } on ApiFailure catch (failure) {
      if (!context.mounted) return;
      showOutcomeToast(context, failure.message, hasNavigation: false);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final members = ref.watch(householdMembersProvider(householdId));
    final colors = context.appColors;

    return members.when(
      loading: () => const LedgerSkeleton(rows: 3),
      error: (error, stack) => AppStatePanel(
        key: const Key('members-error'),
        icon: Icons.cloud_off_outlined,
        title: 'Could not load the people here',
        message: error is ApiFailure
            ? error.message
            : 'Something went wrong. Try again.',
        actionLabel: 'Try again',
        onAction: () => ref.invalidate(householdMembersProvider(householdId)),
      ),
      data: (all) {
        final pending = all.where((member) => member.isPending).toList();
        final active = all.where((member) => !member.isPending).toList();

        return RefreshIndicator(
          onRefresh: () async =>
              ref.invalidate(householdMembersProvider(householdId)),
          child: ListView(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.gutter,
              16,
              AppSpacing.gutter,
              32,
            ),
            children: <Widget>[
              // Requests first: someone is waiting on a decision.
              if (pending.isNotEmpty) ...<Widget>[
                SectionLabel('Waiting on you · ${pending.length}'),
                const SizedBox(height: 8),
                for (final member in pending)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: LedgerCard(
                      key: ValueKey<String>('request-${member.id}'),
                      color: colors.warnBg,
                      borderColor: Colors.transparent,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Text(
                            member.name,
                            style: AppText.body.copyWith(
                              color: colors.warnFg,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          const SizedBox(height: 3),
                          // The requester and the role they would get, so the
                          // decision is made with the facts in view.
                          Text(
                            '${member.email} · would join as '
                            '${_roleLabel(member.role)}',
                            style: AppText.caption.copyWith(
                              color: colors.warnFg,
                            ),
                          ),
                          const SizedBox(height: 12),
                          Row(
                            children: <Widget>[
                              Expanded(
                                child: OutlinedButton(
                                  onPressed: () => _resolve(
                                    context,
                                    ref,
                                    member: member,
                                    approve: false,
                                  ),
                                  child: const Text('Decline'),
                                ),
                              ),
                              const SizedBox(width: 10),
                              Expanded(
                                child: FilledButton(
                                  onPressed: () => _resolve(
                                    context,
                                    ref,
                                    member: member,
                                    approve: true,
                                  ),
                                  child: const Text('Approve'),
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ),
                const SizedBox(height: 20),
              ],

              SectionLabel('In this household · ${active.length}'),
              const SizedBox(height: 8),
              if (active.isEmpty)
                Text(
                  'Nobody else yet.',
                  style: AppText.bodyS.copyWith(color: colors.textSecondary),
                )
              else
                LedgerCard(
                  padding: EdgeInsets.zero,
                  child: Column(
                    children: <Widget>[
                      for (var index = 0; index < active.length; index += 1)
                        Column(
                          children: <Widget>[
                            if (index > 0) const Divider(height: 1),
                            ListTile(
                              minTileHeight: AppSpacing.rowMinHeight,
                              leading: MerchantMark(
                                name: active[index].name,
                                size: 40,
                              ),
                              title: Text(active[index].name),
                              subtitle: Text(_roleLabel(active[index].role)),
                              trailing: active[index].role == 'owner'
                                  // An owner cannot be removed here; that
                                  // would leave a household with nobody able
                                  // to administer it.
                                  ? null
                                  : IconButton(
                                      tooltip: 'Remove ${active[index].name}',
                                      onPressed: () =>
                                          _remove(context, ref, active[index]),
                                      icon: const Icon(
                                        Icons.person_remove_outlined,
                                      ),
                                    ),
                            ),
                          ],
                        ),
                    ],
                  ),
                ),
            ],
          ),
        );
      },
    );
  }
}

String _roleLabel(String role) => switch (role) {
  'owner' => 'Owner',
  'admin' => 'Admin',
  'viewer' => 'Can view',
  _ => 'Member',
};

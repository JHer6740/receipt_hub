// One place that decides what a household surface shows when it has no data.
//
// Every screen that reads household figures needs the same four states:
// loading, empty, error and ready. Leaving that to each screen is why an
// unreachable service used to render sample money on Home while Insights
// rendered a section heading over nothing. A surface either has service data
// or it renders the reason it does not.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../design/app_components.dart';
import '../design/app_theme.dart';
import '../state/app_state.dart';

/// What a surface should render, decided from the connection state alone.
///
/// [signedOut] and [sessionExpired] are separate because they are different
/// facts: one person has never signed in, the other was signed in a moment
/// ago. Telling a new user their "session has ended" is nonsense.
enum HouseholdGateState {
  loading,
  ready,
  unavailable,
  signedOut,
  sessionExpired,
  pending,
}

HouseholdGateState _gateFor(AppState app) => switch (app.connection) {
  HubConnection.connecting => HouseholdGateState.loading,
  HubConnection.connected => HouseholdGateState.ready,
  HubConnection.unavailable => HouseholdGateState.unavailable,
  HubConnection.authFailed => HouseholdGateState.sessionExpired,
  HubConnection.pendingHousehold => HouseholdGateState.pending,
  HubConnection.signedOut => HouseholdGateState.signedOut,
};

/// Wraps a household surface so it cannot render figures it does not have.
///
/// [ready] is only called once the service has confirmed this household, so
/// anything inside it can treat its data as fact.
class HouseholdGate extends ConsumerWidget {
  const HouseholdGate({
    required this.ready,
    this.loading,
    this.onSignIn,
    super.key,
  });

  final WidgetBuilder ready;

  /// A skeleton shaped like the real content. Falls back to a generic one.
  final WidgetBuilder? loading;

  /// Where sign-in lives. Supplied by the caller so this widget stays
  /// independent of the router.
  final VoidCallback? onSignIn;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final app = ref.watch(appControllerProvider);
    final controller = ref.read(appControllerProvider.notifier);

    switch (_gateFor(app)) {
      case HouseholdGateState.ready:
        return ready(context);

      case HouseholdGateState.loading:
        return loading?.call(context) ?? const LedgerSkeleton();

      case HouseholdGateState.unavailable:
        return AppStatePanel(
          key: const Key('gate-unavailable'),
          icon: Icons.cloud_off_outlined,
          title: 'Receipts Hub is not responding',
          // The service's own words when it gave any, so the person is told
          // what happened rather than shown a generic apology.
          message:
              app.failureMessage ??
              'Your receipts are safe. Check your connection and try again.',
          actionLabel: 'Try again',
          onAction: controller.refresh,
        );

      case HouseholdGateState.signedOut:
        return AppStatePanel(
          key: const Key('gate-sign-in'),
          icon: Icons.lock_outline_rounded,
          title: 'Sign in to continue',
          message: 'Sign in to see your household.',
          actionLabel: onSignIn == null ? null : 'Sign in',
          onAction: onSignIn,
        );

      case HouseholdGateState.sessionExpired:
        return AppStatePanel(
          key: const Key('gate-sign-in'),
          icon: Icons.lock_outline_rounded,
          title: 'Your session has ended',
          message: app.failureMessage ?? 'Sign in to see your household again.',
          actionLabel: onSignIn == null ? null : 'Sign in',
          onAction: onSignIn,
        );

      case HouseholdGateState.pending:
        return AppStatePanel(
          key: const Key('gate-pending'),
          icon: Icons.schedule_outlined,
          title: 'Waiting for approval',
          message:
              'You will see this household as soon as an owner or admin '
              'approves your request.',
        );
    }
  }
}

/// A neutral loading shape for a ledger surface.
///
/// Deliberately not a centred spinner: keeping the page's rhythm means the
/// content does not jump when it arrives.
class LedgerSkeleton extends StatelessWidget {
  const LedgerSkeleton({this.rows = 4, super.key});

  final int rows;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'Loading your household',
      liveRegion: true,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.gutter,
          24,
          AppSpacing.gutter,
          24,
        ),
        children: <Widget>[
          const SkeletonBlock(width: 120, height: 14),
          const SizedBox(height: 16),
          const SkeletonBlock(width: 190, height: 38),
          const SizedBox(height: 12),
          const SkeletonBlock(width: 140, height: 14),
          const SizedBox(height: 32),
          const SkeletonBlock(height: 96),
          const SizedBox(height: 32),
          for (var index = 0; index < rows; index += 1)
            const Padding(
              padding: EdgeInsets.only(bottom: 14),
              child: SkeletonBlock(height: 56),
            ),
        ],
      ),
    );
  }
}

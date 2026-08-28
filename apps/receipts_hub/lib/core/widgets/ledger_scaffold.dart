// A household-scoped page.
//
// Four screens repeated this frame by hand — an app bar, `HouseholdGate`, and
// pull-to-refresh — including the destination a signed-out person is sent to.
// That last part is why it is a component rather than a convention: a screen
// that forgot the gate would render a household's figures to whoever opened
// the route, and a screen that spelled the sign-in destination differently
// would strand them somewhere else.
//
// `.interface-design/system.md` names this `LedgerScaffold`. It lives here
// rather than in the design system because it knows about the session and the
// router, and `app_components.dart` deliberately knows about neither.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../state/app_state.dart';
import 'household_gate.dart';

class LedgerScaffold extends ConsumerWidget {
  const LedgerScaffold({
    required this.body,
    this.title,
    this.leading,
    this.actions,
    this.refreshable = true,
    this.scaffoldKey,
    super.key,
  });

  /// Built only once a household has resolved, so a gated screen does not
  /// assemble a subtree nobody will see.
  final WidgetBuilder body;

  final Widget? title;
  final Widget? leading;
  final List<Widget>? actions;

  /// Whether to wrap [body] in pull-to-refresh. A screen that owns its own
  /// paging and refresh — the receipt list — passes false.
  final bool refreshable;

  /// Key for the underlying `Scaffold`, where a screen is identified by it in
  /// tests.
  final Key? scaffoldKey;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      key: scaffoldKey,
      appBar: AppBar(
        title: title,
        leading: leading,
        automaticallyImplyLeading: leading != null,
        actions: actions,
      ),
      body: HouseholdGate(
        onSignIn: () => context.go('/welcome'),
        ready: (context) {
          final child = body(context);
          if (!refreshable) return child;
          return RefreshIndicator(
            onRefresh: ref.read(appControllerProvider.notifier).refresh,
            child: child,
          );
        },
      ),
    );
  }
}

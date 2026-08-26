import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/account/account_screen.dart';
import '../../features/auth/auth_screens.dart';
import '../../features/capture/capture_screens.dart';
import '../../features/developer/host_connection_screen.dart';
import '../../features/household/household_choice_screen.dart';
import '../../features/household/household_join_screen.dart';
import '../../features/household/household_members_screen.dart';
import '../../features/compare/comparison_screens.dart';
import '../../features/ledger/ledger_screens.dart';
import '../../features/onboarding/onboarding_screens.dart';
import '../../features/onboarding/splash_screen.dart';
import '../../features/receipts/receipt_screens.dart';
import '../../features/shopping/shopping_list_screen.dart';
import '../state/app_state.dart';
import '../widgets/app_shell.dart';

String _origin(GoRouterState state, String fallback) {
  return switch (state.uri.queryParameters['from']) {
    'home' => '/home',
    'receipts' || 'receipt' => '/receipts',
    'insights' => '/insights',
    'rivals' => '/rivals',
    'list' => '/list',
    'account' => '/account',
    _ => fallback,
  };
}

/// Locations anyone may open, signed in or not.
const _publicRoutes = <String>{
  '/splash',
  '/welcome',
  '/create-account',
  '/sign-in',
  '/developer/connection',
};

/// Locations that need an account but not yet a household.
const _accountRoutes = <String>{'/household', '/household/join'};

/// Build the router.
///
/// [readState] lets the router see the session. When it is null the guard is
/// disabled, which is what widget tests want: they deep-link straight to the
/// surface under test and assert its own empty and error states.
GoRouter createAppRouter({
  String initialLocation = '/welcome',
  AppState Function()? readState,
  Listenable? refreshListenable,
}) {
  return GoRouter(
    initialLocation: initialLocation,
    // Without this the guard below runs once and never again, so the splash
    // screen never leaves: `restoreSession()` resolves, the state changes, and
    // nothing tells the router to look again.
    refreshListenable: refreshListenable,
    redirect: readState == null
        ? null
        : (context, state) {
            final app = readState();
            final location = state.uri.path;
            final signedIn =
                app.connection != HubConnection.signedOut &&
                app.connection != HubConnection.authFailed;

            // The splash exists only while a stored session is resolving, so
            // it has to know where to send people once it has. Treating it as
            // an ordinary public route left the app sitting on it forever.
            if (location == '/splash') {
              if (app.connection == HubConnection.connecting) return null;
              if (app.connected) return '/home';
              return signedIn ? '/household' : '/welcome';
            }

            if (_publicRoutes.contains(location)) {
              // Nothing to do here but leave once there is a session.
              if (location == '/welcome' && app.connected) return '/home';
              return null;
            }

            // Still resolving a stored session: hold rather than bounce
            // someone who is in fact signed in out to the front door.
            if (app.connection == HubConnection.connecting) return '/splash';

            if (!signedIn) return '/welcome';

            // An account without a household has nowhere to file a receipt,
            // so every household-scoped location resolves to the chooser.
            if (!app.connected && !_accountRoutes.contains(location)) {
              return '/household';
            }
            return null;
          },
    errorBuilder: (context, state) => Scaffold(
      appBar: AppBar(title: const Text('Page not found')),
      body: Center(
        child: FilledButton.icon(
          onPressed: () => context.go('/home'),
          icon: const Icon(Icons.home_outlined),
          label: const Text('Return home'),
        ),
      ),
    ),
    routes: <RouteBase>[
      // Shown while a stored session is being restored, so a returning user
      // never sees the first-run screen flash past.
      GoRoute(
        path: '/splash',
        name: 'splash',
        builder: (context, state) => const SplashScreen(),
      ),
      GoRoute(
        path: '/welcome',
        name: 'welcome',
        builder: (context, state) => const WelcomeScreen(),
      ),
      // The product front door: an account on the configured service. Nobody
      // is asked for a host address or a PIN.
      GoRoute(
        path: '/create-account',
        name: 'create-account',
        builder: (context, state) =>
            const AuthScreen(mode: AuthMode.createAccount),
      ),
      GoRoute(
        path: '/sign-in',
        name: 'sign-in',
        builder: (context, state) => const AuthScreen(mode: AuthMode.signIn),
      ),
      // Development and support only; gated on a debug build.
      GoRoute(
        path: '/developer/connection',
        name: 'developer-connection',
        builder: (context, state) => const HostConnectionScreen(),
      ),
      // Where an account picks the ledger its receipts go into. Reached after
      // authentication, never before it.
      GoRoute(
        path: '/household',
        name: 'household-choice',
        builder: (context, state) => const HouseholdChoiceScreen(),
      ),
      GoRoute(
        path: '/household/join',
        name: 'household-join',
        builder: (context, state) => const HouseholdJoinScreen(),
      ),
      GoRoute(
        path: '/household/members',
        name: 'household-members',
        builder: (context, state) => HouseholdMembersScreen(
          householdId: state.uri.queryParameters['id'],
        ),
      ),
      GoRoute(
        path: '/capture',
        name: 'capture',
        builder: (context, state) => const CaptureScreen(),
      ),
      GoRoute(
        path: '/processing',
        name: 'processing',
        builder: (context, state) => const ProcessingScreen(),
      ),
      GoRoute(
        path: '/receipts/:id/edit',
        name: 'receipt-edit',
        builder: (context, state) => ReceiptEditScreen(
          id: state.pathParameters['id']!,
          manual: state.uri.queryParameters['manual'] == 'true',
        ),
      ),
      // Photo zoom is addressed by receipt and page, so a shared or restored
      // link opens the right photograph. It used to take a bare filename.
      GoRoute(
        path: '/receipts/:id/photo',
        name: 'receipt-photo',
        builder: (context, state) => PhotoZoomScreen(
          receiptId: state.pathParameters['id']!,
          initialPage:
              int.tryParse(state.uri.queryParameters['page'] ?? '') ?? 1,
        ),
      ),
      ShellRoute(
        builder: (context, state, child) => Consumer(
          builder: (context, ref, _) => AppShell(
            location: state.uri.path,
            offline: ref.watch(
              appControllerProvider.select((value) => value.offline),
            ),
            child: child,
          ),
        ),
        routes: <RouteBase>[
          GoRoute(
            path: '/home',
            name: 'home',
            builder: (context, state) => const HomeScreen(),
          ),
          GoRoute(
            path: '/receipts',
            name: 'receipts',
            builder: (context, state) => const ReceiptListScreen(),
          ),
          GoRoute(
            path: '/receipts/:id',
            name: 'receipt-view',
            builder: (context, state) =>
                ReceiptViewScreen(id: state.pathParameters['id']!),
          ),
          GoRoute(
            path: '/collections/:key',
            name: 'collection',
            builder: (context, state) => CollectionScreen(
              collectionKey: state.pathParameters['key']!,
              origin: _origin(state, '/home'),
            ),
          ),
          GoRoute(
            path: '/insights',
            name: 'insights',
            builder: (context, state) => const InsightsScreen(),
          ),
          GoRoute(
            path: '/rivals',
            name: 'rivals',
            builder: (context, state) =>
                RivalsScreen(origin: _origin(state, '/insights')),
          ),
          GoRoute(
            path: '/items/:name',
            name: 'item',
            builder: (context, state) => ItemComparisonScreen(
              itemName: Uri.decodeComponent(state.pathParameters['name']!),
              origin: _origin(state, '/insights'),
            ),
          ),
          GoRoute(
            path: '/list',
            name: 'list',
            builder: (context, state) => const ShoppingListScreen(),
          ),
          GoRoute(
            path: '/account',
            name: 'account',
            builder: (context, state) => const AccountScreen(),
          ),
        ],
      ),
    ],
  );
}

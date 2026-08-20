import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/account/account_screen.dart';
import '../../features/capture/capture_screens.dart';
import '../../features/compare/comparison_screens.dart';
import '../../features/ledger/ledger_screens.dart';
import '../../features/onboarding/onboarding_screens.dart';
import '../../features/receipts/receipt_screens.dart';
import '../../features/shopping/shopping_list_screen.dart';
import '../state/app_state.dart';
import '../widgets/app_shell.dart';
import '../../ui_ux_revision/mvp_access_screens.dart';
import '../../ui_ux_revision/mvp_household_admin_screen.dart';

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

GoRouter createAppRouter({String initialLocation = '/welcome'}) {
  return GoRouter(
    initialLocation: initialLocation,
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
      GoRoute(
        path: '/welcome',
        name: 'welcome',
        builder: (context, state) => const WelcomeScreen(),
      ),
      GoRoute(
        path: '/connect',
        name: 'connect',
        builder: (context, state) => const ConnectionScreen(),
      ),
      GoRoute(
        path: '/household/join',
        name: 'household-join',
        builder: (context, state) => const MvpAccessScreen(),
      ),
      GoRoute(
        path: '/household/members',
        name: 'household-members',
        builder: (context, state) => const MvpHouseholdAdminScreen(),
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
          GoRoute(
            path: '/household/members',
            name: 'household-members-shell',
            builder: (context, state) => const MvpHouseholdAdminScreen(),
          ),
        ],
      ),
    ],
  );
}

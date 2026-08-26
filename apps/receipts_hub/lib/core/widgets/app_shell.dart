import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../design/app_theme.dart';

/// The five-destination shell.
///
/// The offline banner sits directly above the navigation bar rather than at the
/// top of the body. At the top it rendered under the status bar, and because
/// every child screen nests its own `Scaffold` and `AppBar`, the inset was
/// applied twice whenever the banner was visible.
class AppShell extends StatelessWidget {
  const AppShell({
    required this.location,
    required this.child,
    this.offline = false,
    super.key,
  });

  final String location;
  final Widget child;
  final bool offline;

  static const _destinations = <_ShellDestination>[
    _ShellDestination(
      path: '/home',
      label: 'Home',
      icon: Icons.home_outlined,
      selectedIcon: Icons.home_rounded,
      // Collections and the comparison surfaces are reached from Home, so
      // they keep this tab lit rather than reporting nothing as selected.
      prefixes: <String>['/home', '/collections', '/rivals', '/items'],
    ),
    _ShellDestination(
      path: '/receipts',
      label: 'Receipts',
      icon: Icons.receipt_long_outlined,
      selectedIcon: Icons.receipt_long_rounded,
      // Receipt detail and review live under this destination.
      prefixes: <String>['/receipts'],
    ),
    _ShellDestination(
      path: '/capture',
      label: 'Scan',
      icon: Icons.document_scanner_outlined,
      selectedIcon: Icons.document_scanner_rounded,
      pushes: true,
    ),
    _ShellDestination(
      path: '/list',
      label: 'List',
      icon: Icons.checklist_rounded,
      selectedIcon: Icons.playlist_add_check_rounded,
    ),
    // Account was reachable only from an icon on Home, so from Receipts, Scan
    // or List there was no way to it at all — and everything a person needs to
    // act on their own data lives there: export, deletion, the household's
    // people, privacy. Insights vacated this slot by being folded into Home.
    _ShellDestination(
      path: '/account',
      label: 'Account',
      icon: Icons.account_circle_outlined,
      selectedIcon: Icons.account_circle_rounded,
    ),
  ];

  /// Which destination owns the current location.
  ///
  /// Returns null when nothing does, rather than falling through to Home:
  /// highlighting Home while a person is somewhere else was simply wrong.
  int? get _selectedIndex {
    for (var index = 0; index < _destinations.length; index += 1) {
      if (_destinations[index].matches(location)) return index;
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;
    final selected = _selectedIndex;

    return Scaffold(
      body: child,
      bottomNavigationBar: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          if (offline)
            Semantics(
              liveRegion: true,
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 6,
                ),
                color: colors.warnBg,
                child: Text(
                  'Offline · changes will sync when you reconnect',
                  textAlign: TextAlign.center,
                  style: AppText.captionS.copyWith(
                    color: colors.warnFg,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ),
          DecoratedBox(
            decoration: BoxDecoration(
              border: Border(top: BorderSide(color: colors.divider)),
            ),
            child: NavigationBar(
              // NavigationBar needs a valid index, so a non-destination route
              // parks on Home visually while nothing is reported as selected
              // to assistive technology.
              selectedIndex: selected ?? 0,
              onDestinationSelected: (index) {
                final destination = _destinations[index];
                if (destination.pushes) {
                  context.push(destination.path);
                } else {
                  context.go(destination.path);
                }
              },
              destinations: <NavigationDestination>[
                for (var index = 0; index < _destinations.length; index += 1)
                  NavigationDestination(
                    icon: Icon(_destinations[index].icon),
                    selectedIcon: Icon(_destinations[index].selectedIcon),
                    label: _destinations[index].label,
                    tooltip: _destinations[index].label,
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ShellDestination {
  const _ShellDestination({
    required this.path,
    required this.label,
    required this.icon,
    required this.selectedIcon,
    this.prefixes,
    this.pushes = false,
  });

  final String path;
  final String label;
  final IconData icon;
  final IconData selectedIcon;

  /// Extra location prefixes this destination owns.
  final List<String>? prefixes;

  /// Whether selecting it pushes a full-screen route instead of switching tab.
  final bool pushes;

  bool matches(String location) {
    for (final prefix in prefixes ?? <String>[path]) {
      if (location == prefix || location.startsWith('$prefix/')) return true;
    }
    return location == path;
  }
}

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../design/app_theme.dart';

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

  int get _selectedIndex {
    if (location.startsWith('/receipts')) {
      return 1;
    }
    if (location.startsWith('/insights') ||
        location.startsWith('/rivals') ||
        location.startsWith('/items')) {
      return 3;
    }
    if (location.startsWith('/list')) {
      return 4;
    }
    return 0;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: <Widget>[
          if (offline)
            Semantics(
              liveRegion: true,
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 5,
                ),
                color: context.appColors.warnBg,
                child: Text(
                  'Offline · queued',
                  textAlign: TextAlign.center,
                  style: AppText.captionS.copyWith(
                    color: context.appColors.warnFg,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ),
          Expanded(child: child),
        ],
      ),
      bottomNavigationBar: DecoratedBox(
        decoration: BoxDecoration(
          border: Border(top: BorderSide(color: context.appColors.divider)),
        ),
        child: NavigationBar(
          selectedIndex: _selectedIndex,
          onDestinationSelected: (index) {
            switch (index) {
              case 0:
                context.go('/home');
              case 1:
                context.go('/receipts');
              case 2:
                context.push('/capture');
              case 3:
                context.go('/insights');
              case 4:
                context.go('/list');
            }
          },
          destinations: <NavigationDestination>[
            const NavigationDestination(
              icon: Icon(Icons.home_outlined),
              selectedIcon: Icon(Icons.home_rounded),
              label: 'Home',
            ),
            const NavigationDestination(
              icon: Icon(Icons.receipt_long_outlined),
              selectedIcon: Icon(Icons.receipt_long_rounded),
              label: 'Receipts',
            ),
            NavigationDestination(
              icon: Semantics(
                label: 'Scan a receipt',
                child: Icon(Icons.document_scanner_outlined),
              ),
              selectedIcon: Icon(Icons.document_scanner_rounded),
              label: 'Scan',
            ),
            const NavigationDestination(
              icon: Icon(Icons.insights_outlined),
              selectedIcon: Icon(Icons.insights_rounded),
              label: 'Insights',
            ),
            const NavigationDestination(
              icon: Icon(Icons.checklist_rounded),
              selectedIcon: Icon(Icons.playlist_add_check_rounded),
              label: 'List',
            ),
          ],
        ),
      ),
    );
  }
}

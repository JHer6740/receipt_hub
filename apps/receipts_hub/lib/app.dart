import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'core/data/connectivity_watcher.dart';
import 'core/design/app_theme.dart';
import 'core/routing/app_router.dart';
import 'core/state/app_state.dart';

class ReceiptsHubApp extends ConsumerStatefulWidget {
  const ReceiptsHubApp({this.router, this.restoreSession = false, super.key});

  final GoRouter? router;

  /// Whether to reconnect to the saved host on launch.
  ///
  /// Off by default so widget and golden tests render the design preview
  /// without reaching for platform secure storage or a network.
  final bool restoreSession;

  @override
  ConsumerState<ReceiptsHubApp> createState() => _ReceiptsHubAppState();
}

class _ReceiptsHubAppState extends ConsumerState<ReceiptsHubApp> {
  late final GoRouter _router =
      widget.router ??
      createAppRouter(
        initialLocation: widget.restoreSession ? '/splash' : '/welcome',
        readState: () => ref.read(appControllerProvider),
      );

  @override
  void initState() {
    super.initState();
    if (!widget.restoreSession) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      // Watch the network for real, not just when a request fails.
      ref.read(connectivityWatcherProvider);
      // A device that has signed in before goes straight to its household.
      ref.read(appControllerProvider.notifier).restoreSession();
    });
  }

  @override
  void dispose() {
    if (widget.router == null) _router.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final preference = ref.watch(themeControllerProvider);
    final light = AppColors.resolve(preference.colorway, Brightness.light);
    final dark = AppColors.resolve(preference.colorway, Brightness.dark);
    return MaterialApp.router(
      title: 'Receipts Hub',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(light, Brightness.light),
      darkTheme: buildTheme(dark, Brightness.dark),
      themeMode: preference.mode,
      routerConfig: _router,
      builder: (context, child) {
        // "Larger text" was a switch that changed nothing. It now scales on
        // top of the platform setting rather than replacing it, so someone
        // already using large system text is not scaled back down.
        final platform = MediaQuery.textScalerOf(context);
        return MediaQuery(
          data: MediaQuery.of(context).copyWith(
            textScaler: preference.largerText
                ? platform.clamp(minScaleFactor: 1.15)
                : platform,
          ),
          child: child ?? const SizedBox.shrink(),
        );
      },
    );
  }
}

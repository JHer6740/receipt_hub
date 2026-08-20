// Developer and support only: point the app at a host by hand.
//
// This was once the product's second screen, asking a customer for an IP
// address and a shared PIN and telling them their receipts stayed on their own
// computer. None of that is true of a hosted product, so it moved here.
//
// It stays because the app has to be drivable against a local backend during
// development. It is reachable only from a debug build (see `WelcomeScreen`),
// and `AppConfig.allowHostOverride` can switch it off entirely.

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/config/app_config.dart';
import '../../core/design/app_components.dart';
import '../../core/design/app_theme.dart';
import '../../core/state/app_state.dart';

/// Whether the hand-entered host path is available in this build at all.
bool get hostOverrideAvailable => kDebugMode && AppConfig.allowHostOverride;

/// Whether the UI should offer developer tools.
///
/// A provider rather than a bare getter so golden baselines can render the
/// release surface instead of whatever the debug build happens to expose.
final developerToolsProvider = Provider<bool>(
  (ref) => hostOverrideAvailable,
);

class HostConnectionScreen extends ConsumerStatefulWidget {
  const HostConnectionScreen({super.key});

  @override
  ConsumerState<HostConnectionScreen> createState() =>
      _HostConnectionScreenState();
}

class _HostConnectionScreenState extends ConsumerState<HostConnectionScreen> {
  late final TextEditingController _serverController;
  final TextEditingController _pinController = TextEditingController();
  String? _error;
  bool _obscure = true;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _serverController = TextEditingController(
      text: ref.read(appControllerProvider).serverUrl,
    );
  }

  @override
  void dispose() {
    _serverController.dispose();
    _pinController.dispose();
    super.dispose();
  }

  Future<void> _continue() async {
    if (_busy) return;
    final value = _serverController.text.trim();
    final uri = Uri.tryParse(value);
    if (uri == null || !uri.hasScheme || uri.host.isEmpty) {
      setState(
        () =>
            _error = 'Enter a full address, such as http://192.168.1.20:8000.',
      );
      return;
    }
    if (_pinController.text.trim().length < 4) {
      setState(() => _error = 'Enter the household PIN.');
      return;
    }

    setState(() {
      _busy = true;
      _error = null;
    });
    final controller = ref.read(appControllerProvider.notifier);

    // Check the host is awake first so an unreachable address is reported as a
    // network problem rather than looking like a wrong PIN.
    final reachable = await controller.checkHost(value);
    if (!mounted) return;
    if (!reachable) {
      setState(() {
        _busy = false;
        _error = 'Nothing answered at that address.';
      });
      return;
    }

    final failure = await controller.signIn(
      serverUrl: value,
      pin: _pinController.text.trim(),
    );
    if (!mounted) return;
    setState(() {
      _busy = false;
      _error = failure;
    });
    if (failure == null) context.go('/home');
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;
    if (!hostOverrideAvailable) {
      return Scaffold(
        appBar: AppBar(title: const Text('Not available')),
        body: AppStatePanel(
          icon: Icons.block_outlined,
          title: 'Not available in this build',
          message: 'Connecting to a host by hand is a development tool.',
          actionLabel: 'Back',
          onAction: () => context.go('/welcome'),
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('Developer: connect to a host'),
        backgroundColor: colors.warnBg,
        foregroundColor: colors.warnFg,
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.gutter,
            16,
            AppSpacing.gutter,
            28,
          ),
          children: <Widget>[
            LedgerCard(
              color: colors.warnBg,
              borderColor: Colors.transparent,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Icon(Icons.construction_rounded, color: colors.warnFg),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      'Development tool. Signs in to a local backend with a '
                      'household PIN. Not part of the product.',
                      style: AppText.caption.copyWith(color: colors.warnFg),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 20),
            Text(
              'Configured service: ${AppConfig.apiBaseUrl}',
              style: AppText.captionS.copyWith(color: colors.textSecondary),
            ),
            const SizedBox(height: 20),
            TextField(
              key: const Key('server-url-field'),
              controller: _serverController,
              keyboardType: TextInputType.url,
              textInputAction: TextInputAction.next,
              autocorrect: false,
              decoration: const InputDecoration(
                labelText: 'Host address',
                hintText: 'http://10.0.2.2:8000',
                prefixIcon: Icon(Icons.lan_outlined),
              ),
            ),
            const SizedBox(height: 14),
            TextField(
              key: const Key('pin-field'),
              controller: _pinController,
              obscureText: _obscure,
              keyboardType: TextInputType.number,
              textInputAction: TextInputAction.done,
              onSubmitted: (_) => _continue(),
              decoration: InputDecoration(
                labelText: 'Household PIN',
                prefixIcon: const Icon(Icons.lock_outline_rounded),
                suffixIcon: IconButton(
                  tooltip: _obscure ? 'Show PIN' : 'Hide PIN',
                  onPressed: () => setState(() => _obscure = !_obscure),
                  icon: Icon(
                    _obscure
                        ? Icons.visibility_outlined
                        : Icons.visibility_off_outlined,
                  ),
                ),
              ),
            ),
            if (_error != null) ...<Widget>[
              const SizedBox(height: 12),
              Text(_error!, style: AppText.bodyS.copyWith(color: colors.error)),
            ],
            const SizedBox(height: 22),
            FilledButton(
              onPressed: _busy ? null : _continue,
              child: _busy
                  ? const SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('Connect'),
            ),
          ],
        ),
      ),
    );
  }
}

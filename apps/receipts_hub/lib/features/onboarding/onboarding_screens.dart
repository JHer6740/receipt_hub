import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/design/app_components.dart';
import '../../core/design/app_theme.dart';
import '../../core/state/app_state.dart';

/// First run.
///
/// The price-sharing consent panel that used to sit here described an
/// anonymous shared index that will not exist at launch, and asked for consent
/// to it before the person had an account. Consent belongs with the feature.
class WelcomeScreen extends ConsumerWidget {
  const WelcomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final colors = context.appColors;
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: <Widget>[
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(
                  AppSpacing.gutter,
                  24,
                  AppSpacing.gutter,
                  16,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    const Align(
                      alignment: Alignment.centerLeft,
                      child: ReceiptAppMark(size: 56),
                    ),
                    const SizedBox(height: 24),
                    Text(
                      'Your receipts,\nworth something to you',
                      style: AppText.displayL,
                    ),
                    const SizedBox(height: 16),
                    Text(
                      'File the paper trail, see where the household money '
                      'goes, and find out when another shop is quietly '
                      'charging less for the things you buy on repeat.',
                      style: AppText.bodyL.copyWith(
                        color: colors.textSecondary,
                      ),
                    ),
                    const SizedBox(height: 24),
                    _ValueRow(
                      icon: Icons.document_scanner_outlined,
                      title: 'Photograph the receipt',
                      detail: 'Every line item is read and filed for you.',
                    ),
                    _ValueRow(
                      icon: Icons.insights_outlined,
                      title: 'See where the money goes',
                      detail: 'Monthly totals and trends by collection.',
                    ),
                    _ValueRow(
                      icon: Icons.compare_arrows_rounded,
                      title: 'Compare what you buy again',
                      detail:
                          'Built from your own receipts, so every price has '
                          'a source.',
                    ),
                  ],
                ),
              ),
            ),
            DecoratedBox(
              decoration: BoxDecoration(
                color: colors.surface,
                border: Border(top: BorderSide(color: colors.divider)),
              ),
              child: Padding(
                padding: const EdgeInsets.fromLTRB(
                  AppSpacing.gutter,
                  12,
                  AppSpacing.gutter,
                  14,
                ),
                // "Join a household" used to sit here as a third action, which
                // let someone reach the ledger before authenticating. Joining
                // a household belongs after sign-in.
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    FilledButton(
                      onPressed: () => context.push('/connect'),
                      child: const Text('Get started'),
                    ),
                    const SizedBox(height: 8),
                    TextButton(
                      onPressed: () => context.push('/connect'),
                      child: const Text('I already have an account'),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ValueRow extends StatelessWidget {
  const _ValueRow({
    required this.icon,
    required this.title,
    required this.detail,
  });

  final IconData icon;
  final String title;
  final String detail;

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;
    return Padding(
      padding: const EdgeInsets.only(bottom: 18),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: colors.actionSelected,
              borderRadius: BorderRadius.circular(AppRadii.mark),
            ),
            child: Icon(icon, size: 20, color: colors.primary),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  title,
                  style: AppText.body.copyWith(fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 3),
                Text(
                  detail,
                  style: AppText.bodyS.copyWith(color: colors.textSecondary),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class ConnectionScreen extends ConsumerStatefulWidget {
  const ConnectionScreen({super.key});

  @override
  ConsumerState<ConnectionScreen> createState() => _ConnectionScreenState();
}

class _ConnectionScreenState extends ConsumerState<ConnectionScreen> {
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
        _error =
            'No Receipts Hub answered at that address. Check the host computer '
            'is awake and on the same network.';
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
    if (failure == null) {
      context.go('/home');
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;
    return Scaffold(
      appBar: AppBar(title: const Text('Connect to your hub')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.gutter,
            12,
            AppSpacing.gutter,
            28,
          ),
          children: <Widget>[
            const ReceiptAppMark(size: 52),
            const SizedBox(height: 24),
            Text('Your receipts stay on your host', style: AppText.displayM),
            const SizedBox(height: 10),
            Text(
              'Enter the address shown by Receipts Hub on your home computer. Your phone and host need to be on the same trusted network.',
              style: AppText.body.copyWith(color: colors.textSecondary),
            ),
            const SizedBox(height: 24),
            TextField(
              key: const Key('server-url-field'),
              controller: _serverController,
              keyboardType: TextInputType.url,
              textInputAction: TextInputAction.next,
              autocorrect: false,
              decoration: const InputDecoration(
                labelText: 'Hub address',
                hintText: 'http://192.168.1.20:8000',
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
                  : const Text('Connect securely'),
            ),
            const SizedBox(height: 16),
            LedgerCard(
              color: colors.warnBg,
              borderColor: Colors.transparent,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Icon(Icons.info_outline_rounded, color: colors.warnFg),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      'Your PIN is exchanged for a session held in this phone\'s '
                      'secure storage. Receipts stay on your host; nothing is '
                      'sent outside your network.',
                      style: AppText.caption.copyWith(color: colors.warnFg),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

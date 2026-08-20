import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../core/design/app_components.dart';
import '../core/design/app_theme.dart';

class MvpAccessScreen extends StatefulWidget {
  const MvpAccessScreen({super.key});

  @override
  State<MvpAccessScreen> createState() => _MvpAccessScreenState();
}

class _MvpAccessScreenState extends State<MvpAccessScreen> {
  final _householdController = TextEditingController();
  bool _requestSent = false;
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _householdController.dispose();
    super.dispose();
  }

  Future<void> _requestToJoin() async {
    final id = _householdController.text.trim();
    if (id.isEmpty) {
      setState(() => _error = 'Enter the household ID or join code.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    await Future<void>.delayed(const Duration(milliseconds: 450));
    if (!mounted) return;
    setState(() {
      _busy = false;
      _requestSent = true;
    });
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;
    return Scaffold(
      appBar: AppBar(title: const Text('Join a household')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(AppSpacing.gutter, 16, AppSpacing.gutter, 32),
          children: [
            const ReceiptAppMark(size: 52),
            const SizedBox(height: 24),
            Text('Use your household ID', style: AppText.displayM),
            const SizedBox(height: 10),
            Text(
              'Ask the owner or an admin for the household ID. Entering it sends a request; it does not give access until they approve you.',
              style: AppText.body.copyWith(color: colors.textSecondary),
            ),
            const SizedBox(height: 24),
            if (_requestSent)
              LedgerCard(
                color: colors.actionSelected,
                borderColor: colors.primary,
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(Icons.schedule_outlined, color: colors.primary),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        'Request sent. You can use this app when an owner or admin approves your access.',
                        style: AppText.body.copyWith(color: colors.textPrimary),
                      ),
                    ),
                  ],
                ),
              )
            else ...[
              TextField(
                controller: _householdController,
                textInputAction: TextInputAction.done,
                autocorrect: false,
                decoration: const InputDecoration(
                  labelText: 'Household ID or join code',
                  hintText: 'For example: H7K4-92QF',
                  prefixIcon: Icon(Icons.home_work_outlined),
                ),
                onSubmitted: (_) => _requestToJoin(),
              ),
              if (_error != null) ...[
                const SizedBox(height: 10),
                Text(_error!, style: AppText.bodyS.copyWith(color: colors.error)),
              ],
              const SizedBox(height: 20),
              FilledButton(
                onPressed: _busy ? null : _requestToJoin,
                child: _busy
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Request to join'),
              ),
            ],
            const SizedBox(height: 16),
            TextButton(
              onPressed: () => context.go('/home'),
              child: Text(_requestSent ? 'Return to account' : 'Not now'),
            ),
          ],
        ),
      ),
    );
  }
}

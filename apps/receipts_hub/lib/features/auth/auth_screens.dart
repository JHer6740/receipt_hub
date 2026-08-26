// The product's front door: an account, on the service this build ships with.
//
// Nothing here asks for a host address, a network, or a PIN. Those belong to
// the LAN prototype and now live behind a debug-only developer screen.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/data/error_reporter.dart';
import '../../core/design/app_components.dart';
import '../../core/design/app_theme.dart';
import '../../core/state/app_state.dart';

enum AuthMode { signIn, createAccount }

class AuthScreen extends ConsumerStatefulWidget {
  const AuthScreen({required this.mode, super.key});

  final AuthMode mode;

  @override
  ConsumerState<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends ConsumerState<AuthScreen> {
  final _formKey = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _name = TextEditingController();
  bool _obscure = true;
  bool _busy = false;
  String? _error;

  bool get _isCreating => widget.mode == AuthMode.createAccount;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _name.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_busy) return;
    setState(() => _error = null);
    if (!(_formKey.currentState?.validate() ?? false)) return;

    setState(() => _busy = true);
    final controller = ref.read(appControllerProvider.notifier);
    final email = _email.text.trim();
    // Guarded, not just awaited: a throw here would leave the button spinning
    // with no message and no way forward.
    String? failure;
    try {
      failure = _isCreating
          ? await controller.createAccount(
              email: email,
              password: _password.text,
              displayName: _name.text,
            )
          : await controller.logIn(email: email, password: _password.text);
    } on Object catch (error, stack) {
      errorReporter.report(ReportedError(error: error, stack: stack));
      failure = 'Something went wrong. Please try again.';
    }
    if (!mounted) return;
    setState(() {
      _busy = false;
      _error = failure;
    });
    // An account is not a ledger. Receipts need a household, so a new or
    // returning account picks one before anything else.
    if (failure == null) context.go('/household');
  }

  Future<void> _resetPassword() async {
    final email = _email.text.trim();
    if (!_looksLikeEmail(email)) {
      setState(() => _error = 'Enter your email address first.');
      return;
    }
    setState(() => _busy = true);
    final failure = await ref
        .read(appControllerProvider.notifier)
        .requestPasswordReset(email);
    if (!mounted) return;
    setState(() {
      _busy = false;
      _error = failure;
    });
    if (failure == null) {
      showOutcomeToast(
        context,
        'If that address has an account, a reset link is on its way',
        hasNavigation: false,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;
    return Scaffold(
      appBar: AppBar(
        title: Text(_isCreating ? 'Create your account' : 'Sign in'),
      ),
      body: SafeArea(
        child: Form(
          key: _formKey,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.gutter,
              16,
              AppSpacing.gutter,
              32,
            ),
            children: <Widget>[
              Text(
                _isCreating ? 'Your receipts, in one place' : 'Welcome back',
                style: AppText.displayM,
              ),
              const SizedBox(height: 10),
              Text(
                _isCreating
                    ? 'You will be able to invite the rest of your household '
                          'once your account is set up.'
                    : 'Sign in to see your household ledger.',
                style: AppText.body.copyWith(color: colors.textSecondary),
              ),
              const SizedBox(height: 28),
              if (_isCreating) ...<Widget>[
                TextFormField(
                  key: const Key('name-field'),
                  controller: _name,
                  textCapitalization: TextCapitalization.words,
                  textInputAction: TextInputAction.next,
                  autofillHints: const <String>[AutofillHints.name],
                  decoration: const InputDecoration(
                    labelText: 'Your name',
                    helperText: 'Shown to others in your household',
                  ),
                ),
                const SizedBox(height: 16),
              ],
              TextFormField(
                key: const Key('email-field'),
                controller: _email,
                keyboardType: TextInputType.emailAddress,
                textInputAction: TextInputAction.next,
                autocorrect: false,
                autofillHints: const <String>[AutofillHints.email],
                decoration: const InputDecoration(labelText: 'Email'),
                validator: (value) => _looksLikeEmail(value?.trim() ?? '')
                    ? null
                    : 'Enter a valid email address.',
              ),
              const SizedBox(height: 16),
              TextFormField(
                key: const Key('password-field'),
                controller: _password,
                obscureText: _obscure,
                textInputAction: TextInputAction.done,
                autofillHints: <String>[
                  _isCreating
                      ? AutofillHints.newPassword
                      : AutofillHints.password,
                ],
                onFieldSubmitted: (_) => _submit(),
                decoration: InputDecoration(
                  labelText: 'Password',
                  helperText: _isCreating ? 'At least 10 characters' : null,
                  suffixIcon: IconButton(
                    tooltip: _obscure ? 'Show password' : 'Hide password',
                    onPressed: () => setState(() => _obscure = !_obscure),
                    icon: Icon(
                      _obscure
                          ? Icons.visibility_outlined
                          : Icons.visibility_off_outlined,
                    ),
                  ),
                ),
                validator: (value) {
                  final password = value ?? '';
                  if (password.isEmpty) return 'Enter your password.';
                  if (_isCreating && password.length < 10) {
                    return 'Use at least 10 characters.';
                  }
                  return null;
                },
              ),
              if (_error != null) ...<Widget>[
                const SizedBox(height: 16),
                // The service's own words, so the next step is knowable.
                LedgerCard(
                  key: const Key('auth-error'),
                  color: colors.warnBg,
                  borderColor: Colors.transparent,
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Icon(Icons.error_outline_rounded, color: colors.warnFg),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          _error!,
                          style: AppText.bodyS.copyWith(color: colors.warnFg),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
              const SizedBox(height: 24),
              FilledButton(
                key: const Key('auth-submit'),
                onPressed: _busy ? null : _submit,
                child: _busy
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : Text(_isCreating ? 'Create account' : 'Sign in'),
              ),
              const SizedBox(height: 8),
              if (_isCreating)
                TextButton(
                  onPressed: _busy ? null : () => context.go('/sign-in'),
                  child: const Text('I already have an account'),
                )
              else ...<Widget>[
                TextButton(
                  onPressed: _busy ? null : _resetPassword,
                  child: const Text('I forgot my password'),
                ),
                TextButton(
                  onPressed: _busy ? null : () => context.go('/create-account'),
                  child: const Text('Create an account'),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

bool _looksLikeEmail(String value) {
  // Deliberately loose. The service is the authority on whether an address is
  // real; this only catches obvious typos before a round trip.
  final at = value.indexOf('@');
  if (at <= 0 || at != value.lastIndexOf('@')) return false;
  final domain = value.substring(at + 1);
  return domain.contains('.') &&
      !domain.startsWith('.') &&
      !domain.endsWith('.') &&
      !value.contains(' ');
}

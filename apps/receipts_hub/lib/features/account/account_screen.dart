import 'package:flutter/material.dart';
import '../../core/network/mobile_api.dart';
import '../../core/data/receipts_repository.dart';
import '../../core/config/app_config.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:share_plus/share_plus.dart';
import 'package:path_provider/path_provider.dart';
import 'dart:io';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/design/app_components.dart';
import '../../core/design/app_theme.dart';
import '../../core/state/app_state.dart';

/// Account holds what a person can actually change or act on.
///
/// It used to also carry three invented contribution counts, a sharing switch
/// for a price index that does not exist yet, two privacy lists describing
/// that index, and three chevron rows that only raised a toast. All of it
/// promised behaviour the product does not have.
class AccountScreen extends ConsumerWidget {
  const AccountScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final app = ref.watch(appControllerProvider);
    final theme = ref.watch(themeControllerProvider);
    final colors = context.appColors;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Account'),
        leading: IconButton(
          tooltip: 'Back',
          onPressed: () =>
              context.canPop() ? context.pop() : context.go('/home'),
          icon: const Icon(Icons.arrow_back_rounded),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.gutter,
          8,
          AppSpacing.gutter,
          36,
        ),
        children: <Widget>[
          LedgerCard(
            key: const Key('account-connection'),
            color: app.connected ? null : colors.warnBg,
            borderColor: app.connected ? null : Colors.transparent,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Icon(
                      app.connected
                          ? Icons.home_work_outlined
                          : Icons.cloud_off_outlined,
                      color: app.connected ? colors.primary : colors.warnFg,
                      size: 28,
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        app.connected
                            ? app.householdName
                            : _titleFor(app.connection),
                        style: AppText.displayS.copyWith(
                          color: app.connected ? null : colors.warnFg,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  app.connected
                      ? 'Your household'
                      : app.failureMessage ?? _messageFor(app.connection),
                  style: AppText.bodyS.copyWith(
                    color: app.connected ? colors.textSecondary : colors.warnFg,
                  ),
                ),
                const SizedBox(height: 12),
                if (app.connected)
                  OutlinedButton.icon(
                    key: const Key('account-sign-out'),
                    onPressed: () => _confirmSignOut(context, ref),
                    icon: const Icon(Icons.logout_rounded),
                    label: const Text('Sign out'),
                  )
                else
                  FilledButton.icon(
                    key: const Key('account-connect'),
                    onPressed: () => context.go('/welcome'),
                    icon: const Icon(Icons.login_rounded),
                    label: const Text('Sign in'),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          // The way in to approving join requests. Account used to carry a
          // "Members" row that only raised a toast, so requests could not be
          // approved by anyone at all.
          const SectionLabel('Household'),
          const SizedBox(height: 8),
          LedgerCard(
            padding: EdgeInsets.zero,
            child: Column(
              children: <Widget>[
                ListTile(
                  key: const Key('account-people'),
                  minTileHeight: AppSpacing.rowMinHeight,
                  leading: const Icon(Icons.group_outlined),
                  title: const Text('People'),
                  subtitle: Text(
                    app.pendingHouseholds.isNotEmpty
                        ? 'You have a request waiting'
                        : 'Who can see this household',
                  ),
                  trailing: const Icon(Icons.chevron_right_rounded),
                  onTap: () => context.push('/household/members'),
                ),
                const Divider(height: 1),
                ListTile(
                  key: const Key('account-households'),
                  minTileHeight: AppSpacing.rowMinHeight,
                  leading: const Icon(Icons.swap_horiz_rounded),
                  title: const Text('Switch household'),
                  subtitle: Text(
                    '${app.activeHouseholds.length} '
                    '${app.activeHouseholds.length == 1 ? 'household' : 'households'}',
                  ),
                  trailing: const Icon(Icons.chevron_right_rounded),
                  onTap: () => context.push('/household'),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          const SectionLabel('Appearance'),
          const SizedBox(height: 8),
          LedgerCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  'Colourway',
                  style: AppText.body.copyWith(fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 10),
                SegmentedButton<AppColorway>(
                  showSelectedIcon: false,
                  segments: const <ButtonSegment<AppColorway>>[
                    ButtonSegment(value: AppColorway.sage, label: Text('Sage')),
                    ButtonSegment(value: AppColorway.clay, label: Text('Clay')),
                    ButtonSegment(
                      value: AppColorway.olive,
                      label: Text('Olive'),
                    ),
                  ],
                  selected: <AppColorway>{theme.colorway},
                  onSelectionChanged: (values) => ref
                      .read(themeControllerProvider.notifier)
                      .setColorway(values.first),
                ),
                const SizedBox(height: 8),
                SwitchListTile.adaptive(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Dark appearance'),
                  value: theme.mode == ThemeMode.dark,
                  onChanged: (value) => ref
                      .read(themeControllerProvider.notifier)
                      .setMode(value ? ThemeMode.dark : ThemeMode.light),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          const SectionLabel('Your data'),
          const SizedBox(height: 8),
          LedgerCard(
            padding: EdgeInsets.zero,
            child: Column(
              children: <Widget>[
                ListTile(
                  key: const Key('account-export'),
                  minTileHeight: AppSpacing.rowMinHeight,
                  leading: const Icon(Icons.download_outlined),
                  title: const Text('Export this household'),
                  subtitle: const Text(
                    'Every receipt and line item, as a spreadsheet.',
                  ),
                  trailing: const Icon(Icons.chevron_right_rounded),
                  onTap: app.connected
                      ? () => _exportHousehold(context, ref)
                      : null,
                ),
                const Divider(height: 1),
                ListTile(
                  key: const Key('account-delete'),
                  minTileHeight: AppSpacing.rowMinHeight,
                  leading: Icon(
                    Icons.person_remove_outlined,
                    color: colors.error,
                  ),
                  title: Text(
                    'Delete my account',
                    style: TextStyle(color: colors.error),
                  ),
                  subtitle: const Text(
                    'Removes your account. Household receipts stay.',
                  ),
                  onTap: () => _confirmDeleteAccount(context, ref),
                ),
              ],
            ),
          ),
          // Only rendered once these are real URLs. A dead privacy link is
          // worse than none, and both are required to list the app anyway.
          if (AppConfig.privacyPolicyUrl.isNotEmpty ||
              AppConfig.termsUrl.isNotEmpty ||
              AppConfig.privacyChoicesUrl.isNotEmpty ||
              AppConfig.cookiesUrl.isNotEmpty ||
              AppConfig.supportEmail.isNotEmpty) ...<Widget>[
            const SizedBox(height: 24),
            const SectionLabel('About'),
            const SizedBox(height: 8),
            LedgerCard(
              padding: EdgeInsets.zero,
              child: Column(
                children: <Widget>[
                  if (AppConfig.privacyPolicyUrl.isNotEmpty)
                    ListTile(
                      minTileHeight: AppSpacing.rowMinHeight,
                      leading: const Icon(Icons.lock_outline_rounded),
                      title: const Text('Privacy policy'),
                      trailing: const Icon(Icons.open_in_new_rounded, size: 18),
                      onTap: () => _open(context, AppConfig.privacyPolicyUrl),
                    ),
                  if (AppConfig.termsUrl.isNotEmpty)
                    ListTile(
                      minTileHeight: AppSpacing.rowMinHeight,
                      leading: const Icon(Icons.description_outlined),
                      title: const Text('Terms of use'),
                      trailing: const Icon(Icons.open_in_new_rounded, size: 18),
                      onTap: () => _open(context, AppConfig.termsUrl),
                    ),
                  if (AppConfig.privacyChoicesUrl.isNotEmpty)
                    ListTile(
                      minTileHeight: AppSpacing.rowMinHeight,
                      leading: const Icon(Icons.tune_rounded),
                      title: const Text('Your privacy choices'),
                      subtitle: const Text(
                        'Access, export, correct or delete your information',
                      ),
                      trailing: const Icon(Icons.open_in_new_rounded, size: 18),
                      onTap: () => _open(context, AppConfig.privacyChoicesUrl),
                    ),
                  if (AppConfig.cookiesUrl.isNotEmpty)
                    ListTile(
                      minTileHeight: AppSpacing.rowMinHeight,
                      leading: const Icon(Icons.cookie_outlined),
                      title: const Text('Cookies and tracking'),
                      trailing: const Icon(Icons.open_in_new_rounded, size: 18),
                      onTap: () => _open(context, AppConfig.cookiesUrl),
                    ),
                  if (AppConfig.supportEmail.isNotEmpty)
                    ListTile(
                      minTileHeight: AppSpacing.rowMinHeight,
                      leading: const Icon(Icons.mail_outline_rounded),
                      title: const Text('Contact support'),
                      trailing: const Icon(Icons.open_in_new_rounded, size: 18),
                      onTap: () =>
                          _open(context, 'mailto:${AppConfig.supportEmail}'),
                    ),
                ],
              ),
            ),
          ],
          const SizedBox(height: 24),
          const SectionLabel('Receipts and reading'),
          const SizedBox(height: 8),
          LedgerCard(
            padding: EdgeInsets.zero,
            child: Column(
              children: <Widget>[
                SwitchListTile.adaptive(
                  secondary: const Icon(Icons.photo_outlined),
                  title: const Text('Keep receipt photos'),
                  subtitle: const Text(
                    'Keeps the photograph with each filed receipt so you can '
                    'check it later.',
                  ),
                  value: app.keepPhotos,
                  onChanged: ref
                      .read(appControllerProvider.notifier)
                      .setKeepPhotos,
                ),
                const Divider(height: 1),
                SwitchListTile.adaptive(
                  secondary: const Icon(Icons.text_fields_rounded),
                  title: const Text('Larger text'),
                  subtitle: const Text(
                    'Increases text size throughout the app.',
                  ),
                  value: theme.largerText,
                  onChanged: ref
                      .read(themeControllerProvider.notifier)
                      .setLargerText,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _titleFor(HubConnection connection) => switch (connection) {
    HubConnection.unavailable => 'Receipts Hub is not responding',
    HubConnection.authFailed => 'Your session has ended',
    HubConnection.pendingHousehold => 'Waiting for approval',
    HubConnection.connecting => 'Connecting',
    _ => 'Not signed in',
  };

  String _messageFor(HubConnection connection) => switch (connection) {
    HubConnection.unavailable =>
      'Your receipts are safe. Check your connection and try again.',
    HubConnection.authFailed => 'Sign in to see your household again.',
    HubConnection.pendingHousehold =>
      'An owner or admin still needs to approve your request.',
    HubConnection.connecting => 'One moment.',
    _ => 'Sign in to see your household.',
  };

  Future<void> _open(BuildContext context, String url) async {
    final uri = Uri.tryParse(url);
    if (uri == null) return;
    final opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!opened && context.mounted) {
      showOutcomeToast(
        context,
        'Could not open that link',
        hasNavigation: false,
      );
    }
  }

  Future<void> _exportHousehold(BuildContext context, WidgetRef ref) async {
    final app = ref.read(appControllerProvider);
    final household = app.activeHouseholds.isEmpty
        ? null
        : app.activeHouseholds.first;
    if (household == null) {
      showOutcomeToast(
        context,
        'Choose a household first',
        hasNavigation: false,
      );
      return;
    }
    try {
      final bytes = await ref
          .read(mobileApiProvider)
          .exportHousehold(household.id);
      final directory = await getTemporaryDirectory();
      final file = File('${directory.path}/receipts-hub-${household.id}.csv');
      await file.writeAsBytes(bytes, flush: true);
      if (!context.mounted) return;
      // Hand it to the OS share sheet: an in-app viewer would be a worse way
      // to get a spreadsheet somewhere useful.
      await SharePlus.instance.share(
        ShareParams(
          files: <XFile>[XFile(file.path, mimeType: 'text/csv')],
          subject: '${household.name} receipts',
        ),
      );
    } on ApiFailure catch (failure) {
      if (!context.mounted) return;
      showOutcomeToast(context, failure.message, hasNavigation: false);
    } on Object {
      if (!context.mounted) return;
      showOutcomeToast(
        context,
        'Your data could not be saved to this device.',
        hasNavigation: false,
      );
    }
  }

  Future<void> _confirmDeleteAccount(
    BuildContext context,
    WidgetRef ref,
  ) async {
    final colors = context.appColors;
    // Two steps, because this cannot be undone. The first explains what
    // survives; the second requires typing, so it cannot be tapped through.
    final understood = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Delete your account?'),
        content: const Text(
          'Your account and its access to every household are removed. '
          'Receipts already filed stay with the household — they belong to it, '
          'not to you. This cannot be undone.',
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Keep my account'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            style: FilledButton.styleFrom(
              backgroundColor: colors.error,
              foregroundColor: colors.onPrimary,
            ),
            child: const Text('Continue'),
          ),
        ],
      ),
    );
    if (understood != true || !context.mounted) return;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => const _ConfirmDeleteDialog(),
    );
    if (confirmed != true || !context.mounted) return;

    final failure = await ref
        .read(appControllerProvider.notifier)
        .deleteAccount();
    if (!context.mounted) return;
    if (failure != null) {
      showOutcomeToast(context, failure, hasNavigation: false);
      return;
    }
    context.go('/welcome');
  }

  Future<void> _confirmSignOut(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Sign out?'),
        content: const Text(
          'Your receipts stay in your household. You will need to sign in '
          'again on this phone.',
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Sign out'),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;
    await ref.read(appControllerProvider.notifier).signOut();
    if (!context.mounted) return;
    context.go('/welcome');
  }
}

/// Requires the word DELETE, so an irreversible action cannot be tapped
/// through by accident.
class _ConfirmDeleteDialog extends StatefulWidget {
  const _ConfirmDeleteDialog();

  @override
  State<_ConfirmDeleteDialog> createState() => _ConfirmDeleteDialogState();
}

class _ConfirmDeleteDialogState extends State<_ConfirmDeleteDialog> {
  final _controller = TextEditingController();
  static const _word = 'DELETE';

  @override
  void initState() {
    super.initState();
    _controller.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;
    final matches = _controller.text.trim().toUpperCase() == _word;
    return AlertDialog(
      title: const Text('Type DELETE to confirm'),
      content: TextField(
        key: const Key('confirm-delete-field'),
        controller: _controller,
        autofocus: true,
        textCapitalization: TextCapitalization.characters,
        decoration: const InputDecoration(labelText: 'DELETE'),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(context).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: matches ? () => Navigator.of(context).pop(true) : null,
          style: FilledButton.styleFrom(
            backgroundColor: colors.error,
            foregroundColor: colors.onPrimary,
          ),
          child: const Text('Delete my account'),
        ),
      ],
    );
  }
}

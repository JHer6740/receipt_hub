import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/design/app_components.dart';
import '../../core/design/app_theme.dart';
import '../../core/state/app_state.dart';
import '../../core/widgets/household_gate.dart';

class ShoppingListScreen extends ConsumerStatefulWidget {
  const ShoppingListScreen({super.key});

  @override
  ConsumerState<ShoppingListScreen> createState() => _ShoppingListScreenState();
}

class _ShoppingListScreenState extends ConsumerState<ShoppingListScreen> {
  final TextEditingController _controller = TextEditingController();
  final FocusNode _focusNode = FocusNode();

  @override
  void dispose() {
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  /// Add an item.
  ///
  /// The row appears immediately and the controller reverts it if the write is
  /// rejected, so there is no success toast to contradict: the list itself is
  /// the confirmation.
  void _add() {
    final value = _controller.text.trim();
    if (value.isEmpty) return;
    _controller.clear();
    _focusNode.requestFocus();
    ref.read(appControllerProvider.notifier).addShoppingItem(value);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('List')),
      body: HouseholdGate(
        onSignIn: () => context.go('/welcome'),
        ready: (context) => RefreshIndicator(
          onRefresh: ref.read(appControllerProvider.notifier).refresh,
          child: _body(context),
        ),
      ),
    );
  }

  Widget _body(BuildContext context) {
    final entries = ref.watch(
      appControllerProvider.select((value) => value.shopping),
    );
    final suggestions = ref.watch(
      appControllerProvider.select((value) => value.suggestions),
    );
    final failure = ref.watch(
      appControllerProvider.select((value) => value.failureMessage),
    );
    final toBuy = entries.where((item) => !item.isPickedUp).toList();
    final picked = entries.where((item) => item.isPickedUp).toList();

    return ListView(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.gutter,
        12,
        AppSpacing.gutter,
        36,
      ),
      children: <Widget>[
        // What another device did, in the service's words. A stale edit
        // returns 409 and the list reloads; saying nothing made that look
        // like the app had simply discarded the change.
        if (failure != null) ...<Widget>[
          LedgerCard(
            key: const Key('shopping-conflict'),
            color: context.appColors.warnBg,
            borderColor: Colors.transparent,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Icon(
                  Icons.sync_problem_outlined,
                  color: context.appColors.warnFg,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    failure,
                    style: AppText.bodyS.copyWith(
                      color: context.appColors.warnFg,
                    ),
                  ),
                ),
                IconButton(
                  tooltip: 'Dismiss',
                  onPressed: ref
                      .read(appControllerProvider.notifier)
                      .clearFailure,
                  icon: Icon(
                    Icons.close_rounded,
                    size: 18,
                    color: context.appColors.warnFg,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
        ],
        Row(
          children: <Widget>[
            Expanded(
              child: TextField(
                key: const Key('add-item-field'),
                controller: _controller,
                focusNode: _focusNode,
                textInputAction: TextInputAction.done,
                textCapitalization: TextCapitalization.sentences,
                onSubmitted: (_) => _add(),
                decoration: const InputDecoration(
                  hintText: 'Add an item',
                  prefixIcon: Icon(Icons.add_rounded),
                ),
              ),
            ),
            const SizedBox(width: 10),
            IconButton.filled(
              tooltip: 'Add item',
              onPressed: _add,
              icon: const Icon(Icons.arrow_upward_rounded),
            ),
          ],
        ),
        const SizedBox(height: 26),
        SectionLabel('To buy · ${toBuy.length}'),
        const SizedBox(height: 8),
        if (toBuy.isEmpty)
          AppStatePanel(
            icon: Icons.done_all_rounded,
            title: 'The list is clear',
            message: 'Add the next thing you need above.',
          )
        else
          LedgerCard(
            padding: EdgeInsets.zero,
            child: Column(
              children: toBuy.map((item) => _ShoppingRow(item: item)).toList(),
            ),
          ),
        // The service predicts what is probably due. This was parsed into
        // state and never rendered, so the feature was invisible.
        if (suggestions.isNotEmpty) ...<Widget>[
          const SizedBox(height: 26),
          SectionLabel('Probably due · ${suggestions.length}'),
          const SizedBox(height: 8),
          for (final suggestion in suggestions)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: LedgerCard(
                key: ValueKey<String>('suggestion-${suggestion.key}'),
                child: Row(
                  children: <Widget>[
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Text(suggestion.description, style: AppText.body),
                          const SizedBox(height: 3),
                          Text(
                            suggestion.dueLabel,
                            style: AppText.caption.copyWith(
                              color: context.appColors.textSecondary,
                            ),
                          ),
                        ],
                      ),
                    ),
                    IconButton(
                      tooltip: 'Not needed',
                      onPressed: () => ref
                          .read(appControllerProvider.notifier)
                          .dismissSuggestion(suggestion.key),
                      icon: const Icon(Icons.close_rounded),
                    ),
                    IconButton.filledTonal(
                      tooltip: 'Add to list',
                      onPressed: () => ref
                          .read(appControllerProvider.notifier)
                          .acceptSuggestion(suggestion.key),
                      icon: const Icon(Icons.add_rounded),
                    ),
                  ],
                ),
              ),
            ),
        ],
        if (picked.isNotEmpty) ...<Widget>[
          const SizedBox(height: 26),
          SectionLabel('Picked up · ${picked.length}'),
          const SizedBox(height: 8),
          LedgerCard(
            padding: EdgeInsets.zero,
            child: Column(
              children: picked.map((item) => _ShoppingRow(item: item)).toList(),
            ),
          ),
        ],
      ],
    );
  }
}

class _ShoppingRow extends ConsumerWidget {
  const _ShoppingRow({required this.item});
  final ShoppingEntry item;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final controller = ref.read(appControllerProvider.notifier);
    return Dismissible(
      key: ValueKey(item.id),
      direction: DismissDirection.endToStart,
      background: Container(
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 20),
        color: context.appColors.error.withValues(alpha: .1),
        child: Icon(
          Icons.delete_outline_rounded,
          color: context.appColors.error,
        ),
      ),
      onDismissed: (_) {
        controller.deleteShoppingItem(item.id);
        // A swipe is easy to do by accident, so the removal is undoable rather
        // than confirmed up front.
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(
            SnackBar(
              content: Text('${item.name} removed'),
              margin: const EdgeInsets.fromLTRB(16, 0, 16, 84),
              action: SnackBarAction(
                label: 'Undo',
                onPressed: () => controller.addShoppingItem(item.name),
              ),
            ),
          );
      },
      child: CheckboxListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 8),
        controlAffinity: ListTileControlAffinity.leading,
        value: item.isPickedUp,
        title: Text(
          item.name,
          style: AppText.body.copyWith(
            color: item.isPickedUp
                ? context.appColors.textSecondary
                : context.appColors.textPrimary,
            decoration: item.isPickedUp ? TextDecoration.lineThrough : null,
          ),
        ),
        onChanged: (_) => controller.toggleShoppingItem(item.id),
      ),
    );
  }
}

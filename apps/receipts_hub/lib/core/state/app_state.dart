import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/preferences_store.dart';
import '../data/receipts_repository.dart';
import '../design/app_theme.dart';
import '../models/models.dart';
import '../network/api_models.dart' as wire;
import '../network/mobile_api.dart';

@immutable
class ThemePreference {
  const ThemePreference({
    this.colorway = AppColorway.sage,
    this.mode = ThemeMode.light,
    this.largerText = false,
  });

  final AppColorway colorway;
  final ThemeMode mode;

  /// Bumps the app's own text scale, on top of whatever the OS asks for.
  final bool largerText;

  ThemePreference copyWith({
    AppColorway? colorway,
    ThemeMode? mode,
    bool? largerText,
  }) => ThemePreference(
    colorway: colorway ?? this.colorway,
    mode: mode ?? this.mode,
    largerText: largerText ?? this.largerText,
  );
}

/// Appearance choices, remembered across launches.
class ThemeController extends Notifier<ThemePreference> {
  @override
  ThemePreference build() {
    // Load in the background: the first frame uses the defaults rather than
    // blocking on disk, then settles once the stored values arrive.
    Future<void>(() async {
      final stored = await ref.read(preferencesStoreProvider).load();
      state = ThemePreference(
        colorway: stored.colorway,
        mode: stored.darkMode ? ThemeMode.dark : ThemeMode.light,
        largerText: stored.largerText,
      );
    });
    return const ThemePreference();
  }

  void setColorway(AppColorway value) {
    state = state.copyWith(colorway: value);
    _persist();
  }

  void setMode(ThemeMode value) {
    state = state.copyWith(mode: value);
    _persist();
  }

  void setLargerText(bool value) {
    state = state.copyWith(largerText: value);
    _persist();
  }

  void _persist() {
    final keepPhotos = ref.read(appControllerProvider).keepPhotos;
    ref
        .read(preferencesStoreProvider)
        .save(
          StoredPreferences(
            colorway: state.colorway,
            darkMode: state.mode == ThemeMode.dark,
            keepPhotos: keepPhotos,
            largerText: state.largerText,
          ),
        );
  }
}

final themeControllerProvider =
    NotifierProvider<ThemeController, ThemePreference>(ThemeController.new);

/// Why a surface can or cannot show household figures.
///
/// Every state here is distinct on purpose: a person needs to know whether the
/// service is down, their session expired, or they are simply waiting on a
/// household owner. Collapsing these into one "not ready" state is what made
/// an unreachable service read as if the numbers on screen were real.
enum HubConnection {
  /// This device has no session yet.
  signedOut,

  /// A sign-in or session restore is in flight.
  connecting,

  /// The service answered and this device has an approved household.
  connected,

  /// The service could not be reached.
  unavailable,

  /// The service answered but rejected this device's session.
  authFailed,

  /// Authenticated, but no household membership has been approved yet.
  pendingHousehold,
}

@immutable
class ShoppingEntry {
  const ShoppingEntry({
    required this.id,
    required this.name,
    this.isPickedUp = false,
    this.quantityLabel = '1',
    this.version = 1,
  });

  final String id;
  final String name;
  final bool isPickedUp;
  final String quantityLabel;

  /// The copy this device last read, sent back on edits so the host can reject
  /// a write made against a stale view of the shared list.
  final int version;

  ShoppingEntry copyWith({
    String? name,
    bool? isPickedUp,
    String? quantityLabel,
    int? version,
  }) => ShoppingEntry(
    id: id,
    name: name ?? this.name,
    isPickedUp: isPickedUp ?? this.isPickedUp,
    quantityLabel: quantityLabel ?? this.quantityLabel,
    version: version ?? this.version,
  );

  factory ShoppingEntry.fromWire(wire.ShoppingItem item) => ShoppingEntry(
    id: item.id,
    name: item.description,
    isPickedUp: item.isPickedUp,
    quantityLabel: item.quantityLabel,
    version: item.version,
  );
}

@immutable
class AppState {
  const AppState({
    required this.receipts,
    required this.shopping,
    this.onboardingComplete = false,
    this.connection = HubConnection.signedOut,
    this.offline = false,
    this.sharingEnabled = true,
    this.keepPhotos = true,
    this.largerText = false,
    this.serverUrl = 'http://10.0.2.2:8000',
    this.searchQuery = '',
    this.attentionOnly = false,
    this.capturePagePaths = const <String>[],
    this.maxCapturePages = 5,
    this.cameraDenied = false,
    this.isLoading = false,
    this.failureMessage,
    this.householdName = 'Receipts Hub',
    this.households = const <wire.HouseholdSummary>[],
    this.householdsLoaded = false,
    this.monthTotalCents = 0,
    this.collections = const <SpendCollection>[],
    this.monthTrend = const <wire.MonthPoint>[],
    this.suggestions = const <wire.ShoppingSuggestion>[],
    this.insights,
  });

  final List<Receipt> receipts;
  final List<ShoppingEntry> shopping;
  final bool onboardingComplete;
  final HubConnection connection;
  final bool offline;
  final bool sharingEnabled;
  final bool keepPhotos;
  final bool largerText;
  final String serverUrl;
  final String searchQuery;
  final bool attentionOnly;
  final List<String> capturePagePaths;

  /// How many photos one receipt may carry. The service owns this limit
  /// (`HostSettings.maxPhotoFiles`); this default only covers the first launch
  /// before settings have been read.
  final int maxCapturePages;

  final bool cameraDenied;

  /// A host request is in flight.
  final bool isLoading;

  /// The last host failure, in words a person can act on.
  final String? failureMessage;
  final String householdName;

  /// Households this account can see, including pending requests.
  final List<wire.HouseholdSummary> households;

  /// Whether the household list has been fetched at least once. Distinguishes
  /// "none yet" from "not asked", so the chooser never shows an empty list as
  /// though it were an answer.
  final bool householdsLoaded;

  final int monthTotalCents;
  final List<SpendCollection> collections;
  final List<wire.MonthPoint> monthTrend;
  final List<wire.ShoppingSuggestion> suggestions;
  final wire.InsightsSnapshot? insights;

  bool get connected => connection == HubConnection.connected;

  /// Households this account is actually a member of.
  List<wire.HouseholdSummary> get activeHouseholds =>
      households.where((household) => household.isActive).toList();

  /// Requests still waiting on an owner or admin.
  List<wire.HouseholdSummary> get pendingHouseholds =>
      households.where((household) => household.isPending).toList();

  /// True while a request is establishing or restoring the session.
  bool get isConnecting => connection == HubConnection.connecting;

  /// Whether this device may render household figures at all.
  ///
  /// Nothing on a money surface renders unless the service confirmed this
  /// household, so a screen can never present a placeholder as a fact.
  bool get hasHouseholdData => connection == HubConnection.connected;

  int get capturePages => capturePagePaths.length;

  AppState copyWith({
    List<Receipt>? receipts,
    List<ShoppingEntry>? shopping,
    bool? onboardingComplete,
    HubConnection? connection,
    bool? offline,
    bool? sharingEnabled,
    bool? keepPhotos,
    bool? largerText,
    String? serverUrl,
    String? searchQuery,
    bool? attentionOnly,
    List<String>? capturePagePaths,
    int? maxCapturePages,
    bool? cameraDenied,
    bool? isLoading,
    String? failureMessage,
    bool clearFailure = false,
    String? householdName,
    List<wire.HouseholdSummary>? households,
    bool? householdsLoaded,
    int? monthTotalCents,
    List<SpendCollection>? collections,
    List<wire.MonthPoint>? monthTrend,
    List<wire.ShoppingSuggestion>? suggestions,
    wire.InsightsSnapshot? insights,
  }) {
    return AppState(
      receipts: receipts ?? this.receipts,
      shopping: shopping ?? this.shopping,
      onboardingComplete: onboardingComplete ?? this.onboardingComplete,
      connection: connection ?? this.connection,
      offline: offline ?? this.offline,
      sharingEnabled: sharingEnabled ?? this.sharingEnabled,
      keepPhotos: keepPhotos ?? this.keepPhotos,
      largerText: largerText ?? this.largerText,
      serverUrl: serverUrl ?? this.serverUrl,
      searchQuery: searchQuery ?? this.searchQuery,
      attentionOnly: attentionOnly ?? this.attentionOnly,
      capturePagePaths: capturePagePaths ?? this.capturePagePaths,
      maxCapturePages: maxCapturePages ?? this.maxCapturePages,
      cameraDenied: cameraDenied ?? this.cameraDenied,
      isLoading: isLoading ?? this.isLoading,
      failureMessage: clearFailure
          ? null
          : (failureMessage ?? this.failureMessage),
      householdName: householdName ?? this.householdName,
      households: households ?? this.households,
      householdsLoaded: householdsLoaded ?? this.householdsLoaded,
      monthTotalCents: monthTotalCents ?? this.monthTotalCents,
      collections: collections ?? this.collections,
      monthTrend: monthTrend ?? this.monthTrend,
      suggestions: suggestions ?? this.suggestions,
      insights: insights ?? this.insights,
    );
  }

  int get attentionCount => receipts
      .where((receipt) => receipt.status != ReceiptStatus.confirmed)
      .length;

  List<Receipt> get visibleReceipts {
    final query = searchQuery.trim().toLowerCase();
    return receipts.where((receipt) {
      final matchesQuery =
          query.isEmpty || receipt.merchant.toLowerCase().contains(query);
      final matchesAttention =
          !attentionOnly || receipt.status != ReceiptStatus.confirmed;
      return matchesQuery && matchesAttention;
    }).toList();
  }
}

class AppController extends Notifier<AppState> {
  /// A device that has not loaded a household holds nothing.
  ///
  /// Seeding this with sample receipts is what let invented money reach Home,
  /// Insights and the ledger. An empty ledger is the honest starting point;
  /// screens render their empty state until the service answers.
  @override
  AppState build() =>
      const AppState(receipts: <Receipt>[], shopping: <ShoppingEntry>[]);

  ReceiptsRepository get _repository => ref.read(receiptsRepositoryProvider);
  MobileApi get api => ref.read(mobileApiProvider);

  // ---------------------------------------------------------------------------
  // Connection
  // ---------------------------------------------------------------------------

  /// Restore a saved session on launch and load the household.
  ///
  /// A device that has connected before should not have to re-enter the PIN
  /// every time the app opens, so a stored token is reused until the host
  /// rejects it.
  Future<void> restoreSession() async {
    state = state.copyWith(connection: HubConnection.connecting);
    final restored = await api.restoreSession();
    if (!restored) {
      state = state.copyWith(connection: HubConnection.signedOut);
      return;
    }
    state = state.copyWith(
      serverUrl: api.baseUrl ?? state.serverUrl,
      onboardingComplete: true,
    );
    // refresh() resolves the connection state: a restored token that the
    // service rejects must land on authFailed, not on a screen of zeroes.
    await refresh();
  }

  /// Create an account and load whatever household it can see.
  ///
  /// Returns null on success, or a message describing what went wrong.
  Future<String?> createAccount({
    required String email,
    required String password,
    String? displayName,
  }) => _withSession(
    () => api.register(
      email: email,
      password: password,
      displayName: displayName,
    ),
  );

  /// Sign in with an email and password.
  Future<String?> logIn({required String email, required String password}) =>
      _withSession(() => api.logIn(email: email, password: password));

  Future<String?> requestPasswordReset(String email) async {
    state = state.copyWith(isLoading: true, clearFailure: true);
    try {
      await api.requestPasswordReset(email);
      state = state.copyWith(isLoading: false);
      return null;
    } on ApiFailure catch (failure) {
      state = state.copyWith(isLoading: false, failureMessage: failure.message);
      return failure.message;
    }
  }

  /// Run one authentication attempt and settle the connection state from it.
  Future<String?> _withSession(
    Future<wire.SessionEnvelope> Function() authenticate,
  ) async {
    state = state.copyWith(
      connection: HubConnection.connecting,
      isLoading: true,
      clearFailure: true,
    );
    try {
      final session = await authenticate();
      state = state.copyWith(
        serverUrl: api.baseUrl ?? state.serverUrl,
        householdName: session.householdName,
        onboardingComplete: true,
        connection: HubConnection.connected,
      );
      await refresh();
      return null;
    } on ApiFailure catch (failure) {
      state = state.copyWith(
        connection: _connectionFor(failure),
        isLoading: false,
        failureMessage: failure.message,
      );
      return failure.message;
    }
  }

  /// Sign in to a hand-entered host with a household PIN.
  ///
  /// Development and support only; the product path is [createAccount] and
  /// [logIn].
  Future<String?> signIn({
    required String serverUrl,
    required String pin,
  }) async {
    state = state.copyWith(
      connection: HubConnection.connecting,
      isLoading: true,
      clearFailure: true,
    );
    try {
      final session = await api.signIn(serverUrl: serverUrl, pin: pin);
      state = state.copyWith(
        serverUrl: MobileApi.normalizeBaseUrl(serverUrl),
        householdName: session.householdName,
        onboardingComplete: true,
        connection: HubConnection.connected,
      );
      await refresh();
      return null;
    } on ApiFailure catch (failure) {
      state = state.copyWith(
        connection: _connectionFor(failure),
        isLoading: false,
        failureMessage: failure.message,
      );
      return failure.message;
    }
  }

  /// Signing out clears the household from this device entirely.
  Future<void> signOut() async {
    await api.signOut();
    state = build().copyWith(
      onboardingComplete: true,
      serverUrl: state.serverUrl,
      connection: HubConnection.signedOut,
    );
  }

  /// Which connection state a failure puts the app into.
  ///
  /// Kept in one place so every caller reports the same distinction between a
  /// service that is down and a session that was rejected.
  static HubConnection _connectionFor(ApiFailure failure) {
    if (failure.isUnreachable) return HubConnection.unavailable;
    if (failure.needsSignIn) return HubConnection.authFailed;
    return HubConnection.unavailable;
  }

  /// Confirm the host is awake at this address without signing in.
  Future<bool> checkHost(String serverUrl) => api.checkHealth(serverUrl);

  /// Reload every household surface from the host.
  Future<void> refresh() async {
    if (!api.hasSession) {
      state = state.copyWith(connection: HubConnection.signedOut);
      return;
    }
    state = state.copyWith(isLoading: true, clearFailure: true);
    try {
      final snapshot = await _repository.loadHousehold();
      state = state.copyWith(
        receipts: snapshot.receipts,
        shopping: snapshot.shopping.map(ShoppingEntry.fromWire).toList(),
        collections: snapshot.collections,
        monthTotalCents: snapshot.monthTotalCents,
        monthTrend: snapshot.monthTrend,
        suggestions: snapshot.suggestions,
        insights: snapshot.insights,
        householdName: snapshot.householdName,
        connection: HubConnection.connected,
        isLoading: false,
        offline: false,
      );
    } on ApiFailure catch (failure) {
      state = state.copyWith(
        isLoading: false,
        offline: failure.isUnreachable,
        connection: _connectionFor(failure),
        failureMessage: failure.message,
      );
    }
  }

  void clearFailure() => state = state.copyWith(clearFailure: true);

  // ---------------------------------------------------------------------------
  // Households
  // ---------------------------------------------------------------------------

  /// Load the households this account can see.
  Future<String?> loadHouseholds() async {
    if (!api.hasSession) {
      state = state.copyWith(connection: HubConnection.signedOut);
      return 'Sign in to see your households.';
    }
    state = state.copyWith(isLoading: true, clearFailure: true);
    try {
      final households = await api.households();
      state = state.copyWith(
        households: households,
        householdsLoaded: true,
        isLoading: false,
      );
      return null;
    } on ApiFailure catch (failure) {
      state = state.copyWith(
        isLoading: false,
        connection: _connectionFor(failure),
        failureMessage: failure.message,
      );
      return failure.message;
    }
  }

  /// Start a new household and enter it.
  Future<String?> createHousehold(String name) async {
    final trimmed = name.trim();
    if (trimmed.isEmpty) return 'Give your household a name.';
    state = state.copyWith(isLoading: true, clearFailure: true);
    try {
      final household = await api.createHousehold(trimmed);
      state = state.copyWith(
        households: <wire.HouseholdSummary>[...state.households, household],
        householdsLoaded: true,
        householdName: household.name,
        connection: HubConnection.connected,
        isLoading: false,
      );
      await refresh();
      return null;
    } on ApiFailure catch (failure) {
      state = state.copyWith(isLoading: false, failureMessage: failure.message);
      return failure.message;
    }
  }

  /// Ask to join a household. This is a request, not access.
  Future<String?> requestToJoinHousehold(String joinCode) async {
    final trimmed = joinCode.trim();
    if (trimmed.isEmpty) return 'Enter the household ID or join code.';
    state = state.copyWith(isLoading: true, clearFailure: true);
    try {
      final requested = await api.requestToJoinHousehold(trimmed);
      state = state.copyWith(
        households: <wire.HouseholdSummary>[...state.households, requested],
        householdsLoaded: true,
        isLoading: false,
      );
      return null;
    } on ApiFailure catch (failure) {
      state = state.copyWith(isLoading: false, failureMessage: failure.message);
      return failure.message;
    }
  }

  /// Withdraw a pending request.
  Future<String?> cancelJoinRequest(String householdId) async {
    state = state.copyWith(isLoading: true, clearFailure: true);
    try {
      await api.cancelJoinRequest(householdId);
      state = state.copyWith(
        households: state.households
            .where((household) => household.id != householdId)
            .toList(),
        isLoading: false,
      );
      return null;
    } on ApiFailure catch (failure) {
      state = state.copyWith(isLoading: false, failureMessage: failure.message);
      return failure.message;
    }
  }

  /// Enter a household.
  ///
  /// Selecting it on the service first, because household reads are authorised
  /// by a token that names the household. Data reloads before the household is
  /// presented as current, so no figure from the previous one lingers.
  Future<String?> enterHousehold(wire.HouseholdSummary household) async {
    state = state.copyWith(
      connection: HubConnection.connecting,
      isLoading: true,
      clearFailure: true,
    );
    try {
      final session = await api.selectHousehold(household.id);
      state = state.copyWith(
        householdName: session.householdName.isEmpty
            ? household.name
            : session.householdName,
        connection: HubConnection.connected,
      );
    } on ApiFailure catch (failure) {
      state = state.copyWith(
        isLoading: false,
        connection: _connectionFor(failure),
        failureMessage: failure.message,
      );
      return failure.message;
    }
    await refresh();
    return state.failureMessage;
  }

  // ---------------------------------------------------------------------------
  // Local preferences and capture
  // ---------------------------------------------------------------------------

  void completeOnboarding() => state = state.copyWith(onboardingComplete: true);

  void setOffline(bool value) => state = state.copyWith(offline: value);
  void setSharing(bool value) => state = state.copyWith(sharingEnabled: value);
  void setKeepPhotos(bool value) {
    state = state.copyWith(keepPhotos: value);
    final theme = ref.read(themeControllerProvider);
    ref
        .read(preferencesStoreProvider)
        .save(
          StoredPreferences(
            colorway: theme.colorway,
            darkMode: theme.mode == ThemeMode.dark,
            keepPhotos: value,
            largerText: theme.largerText,
          ),
        );
  }

  void setSearch(String value) => state = state.copyWith(searchQuery: value);
  void setAttentionOnly(bool value) =>
      state = state.copyWith(attentionOnly: value);
  void setCameraDenied(bool value) =>
      state = state.copyWith(cameraDenied: value);

  /// Add one captured page. Returns false when there is nothing to add.
  ///
  /// This used to invent a `demo://` path when the camera had not produced a
  /// file, which queued a page that could never upload. A capture either has a
  /// real file behind it or the screen reports that the photo failed.
  bool addCapturePage(String path) {
    if (path.trim().isEmpty) return false;
    if (state.capturePagePaths.length >= state.maxCapturePages) return false;
    state = state.copyWith(
      capturePagePaths: <String>[...state.capturePagePaths, path],
    );
    return true;
  }

  void addCapturePages(Iterable<String> paths) {
    final remaining = state.maxCapturePages - state.capturePagePaths.length;
    if (remaining <= 0) return;
    state = state.copyWith(
      capturePagePaths: <String>[
        ...state.capturePagePaths,
        ...paths.where((path) => path.trim().isNotEmpty).take(remaining),
      ],
    );
  }

  /// Drop one page from the capture tray, keeping the rest in order.
  void removeCapturePage(int index) {
    if (index < 0 || index >= state.capturePagePaths.length) return;
    state = state.copyWith(
      capturePagePaths: <String>[...state.capturePagePaths]..removeAt(index),
    );
  }

  /// Reorder the capture tray. Page order is the receipt's page order.
  void moveCapturePage(int from, int to) {
    final pages = <String>[...state.capturePagePaths];
    if (from < 0 || from >= pages.length || to < 0 || to >= pages.length) {
      return;
    }
    pages.insert(to, pages.removeAt(from));
    state = state.copyWith(capturePagePaths: pages);
  }

  void clearCapture() =>
      state = state.copyWith(capturePagePaths: const <String>[]);

  // ---------------------------------------------------------------------------
  // Shopping list
  // ---------------------------------------------------------------------------

  /// Add to the shared list.
  ///
  /// The item appears immediately and is reconciled with the host's copy when
  /// the write lands, so a slow LAN never makes the list feel unresponsive.
  Future<void> addShoppingItem(String value) async {
    final name = value.trim();
    if (name.isEmpty) return;
    final placeholderId = 's-${DateTime.now().microsecondsSinceEpoch}';
    state = state.copyWith(
      shopping: <ShoppingEntry>[
        ...state.shopping,
        ShoppingEntry(id: placeholderId, name: name),
      ],
    );
    if (!api.hasSession) return;
    try {
      final created = await api.addShoppingItem(product: name);
      state = state.copyWith(
        shopping: state.shopping
            .map(
              (item) => item.id == placeholderId
                  ? ShoppingEntry.fromWire(created)
                  : item,
            )
            .toList(),
      );
    } on ApiFailure catch (failure) {
      state = state.copyWith(
        shopping: state.shopping
            .where((item) => item.id != placeholderId)
            .toList(),
        failureMessage: failure.message,
      );
    }
  }

  Future<void> toggleShoppingItem(String id) async {
    final existing = state.shopping.where((item) => item.id == id).firstOrNull;
    state = state.copyWith(
      shopping: state.shopping
          .map(
            (item) => item.id == id
                ? item.copyWith(isPickedUp: !item.isPickedUp)
                : item,
          )
          .toList(),
    );
    if (!api.hasSession || existing == null) return;
    try {
      final updated = await api.toggleShoppingItem(
        id,
        pickedUp: !existing.isPickedUp,
        version: existing.version,
      );
      state = state.copyWith(
        shopping: state.shopping
            .map(
              (item) => item.id == id ? ShoppingEntry.fromWire(updated) : item,
            )
            .toList(),
      );
    } on ApiFailure catch (failure) {
      // Another device won. Take the host's word for it rather than keeping a
      // local guess the rest of the household cannot see.
      state = state.copyWith(failureMessage: failure.message);
      await refresh();
    }
  }

  Future<void> deleteShoppingItem(String id) async {
    final removed = state.shopping.where((item) => item.id == id).toList();
    state = state.copyWith(
      shopping: state.shopping.where((item) => item.id != id).toList(),
    );
    if (!api.hasSession || removed.isEmpty) return;
    try {
      await api.deleteShoppingItem(id, version: removed.first.version);
    } on ApiFailure catch (failure) {
      state = state.copyWith(failureMessage: failure.message);
      await refresh();
    }
  }

  /// Promote a host suggestion onto the shared list.
  Future<void> acceptSuggestion(String key) async {
    if (!api.hasSession) return;
    try {
      await api.acceptSuggestion(key);
      await refresh();
    } on ApiFailure catch (failure) {
      state = state.copyWith(failureMessage: failure.message);
    }
  }

  Future<void> dismissSuggestion(String key) async {
    if (!api.hasSession) return;
    try {
      await api.dismissSuggestion(key);
      await refresh();
    } on ApiFailure catch (failure) {
      state = state.copyWith(failureMessage: failure.message);
    }
  }

  // ---------------------------------------------------------------------------
  // Receipts
  // ---------------------------------------------------------------------------

  /// Delete a receipt for the whole household.
  ///
  /// Returns null on success, or a message. This used to only filter the local
  /// list, so "Receipt deleted" was false and the row returned on the next
  /// refresh.
  Future<String?> deleteReceipt(String id) async {
    if (!api.hasSession) {
      const message = 'Sign in to delete this receipt.';
      state = state.copyWith(failureMessage: message);
      return message;
    }
    final previous = state.receipts;
    state = state.copyWith(
      receipts: previous.where((receipt) => receipt.id != id).toList(),
      isLoading: true,
      clearFailure: true,
    );
    try {
      await api.deleteReceipt(id);
      await refresh();
      return null;
    } on ApiFailure catch (failure) {
      // Put it back: the household still has this receipt.
      state = state.copyWith(
        receipts: previous,
        isLoading: false,
        failureMessage: failure.message,
      );
      return failure.message;
    }
  }

  void markReceiptConfirmed(String id) {
    state = state.copyWith(
      receipts: state.receipts.map((receipt) {
        if (receipt.id != id) return receipt;
        return Receipt(
          id: receipt.id,
          merchant: receipt.merchant,
          purchasedAt: receipt.purchasedAt,
          txnRef: receipt.txnRef,
          collectionKey: receipt.collectionKey,
          status: ReceiptStatus.confirmed,
          totalCents: receipt.totalCents,
          taxCents: receipt.taxCents,
          items: receipt.items,
          pageImagePaths: receipt.pageImagePaths,
        );
      }).toList(),
    );
  }

  void replaceReceipt(Receipt replacement) {
    final exists = state.receipts.any(
      (receipt) => receipt.id == replacement.id,
    );
    state = state.copyWith(
      receipts: exists
          ? state.receipts
                .map(
                  (receipt) =>
                      receipt.id == replacement.id ? replacement : receipt,
                )
                .toList()
          : <Receipt>[replacement, ...state.receipts],
    );
  }

  /// File a corrected receipt in the household ledger.
  ///
  /// The service owns duplicate detection, the filing gate and the analytics
  /// refresh, so nothing is applied locally first: the ledger only changes
  /// once the write lands and `refresh()` brings back the service's version.
  /// Marking a receipt confirmed before then reported a success that may never
  /// have happened, and left a "confirmed" row the service had rejected.
  Future<String?> fileReceipt(Receipt corrected) async {
    if (!api.hasSession) {
      const message = 'Sign in to file this receipt.';
      state = state.copyWith(
        connection: HubConnection.signedOut,
        failureMessage: message,
      );
      return message;
    }
    state = state.copyWith(isLoading: true, clearFailure: true);
    try {
      await api.confirmReceipt(
        id: corrected.id,
        merchant: corrected.merchant,
        totalCents: corrected.totalCents,
        purchasedAt: corrected.purchasedAt,
        taxCents: corrected.taxCents,
        lineItems: corrected.items
            .map(
              (item) => wire.LineItemDraft(
                description: item.name,
                quantity: item.qty,
                // The line's own unit. This was hardcoded to `each`, so filing
                // a correction rewrote every weighed or measured line.
                unit: item.unit,
                lineTotalCents: item.lineCents,
              ),
            )
            .toList(),
      );
      await refresh();
      return null;
    } on ApiFailure catch (failure) {
      state = state.copyWith(isLoading: false, failureMessage: failure.message);
      return failure.message;
    }
  }
}

final appControllerProvider = NotifierProvider<AppController, AppState>(
  AppController.new,
);

/// The month-level figures Home, Insights and Collections render.
///
/// One provider decides what these are, so no screen has to know whether this
/// device is connected. Every figure here comes from the service or does not
/// exist: there is no illustrative fallback to mistake for household money.
class HouseholdFigures {
  const HouseholdFigures({
    required this.monthTotalCents,
    required this.receiptCount,
    required this.monthSeries,
    required this.monthLabels,
    required this.collections,
    required this.monthDeltaPercent,
    required this.hasData,
  });

  /// Nothing to show: no session, no approved household, or a failed load.
  static const unavailable = HouseholdFigures(
    monthTotalCents: 0,
    receiptCount: 0,
    monthSeries: <int>[],
    monthLabels: <String>[],
    collections: <SpendCollection>[],
    monthDeltaPercent: null,
    hasData: false,
  );

  final int monthTotalCents;
  final int receiptCount;
  final List<int> monthSeries;
  final List<String> monthLabels;
  final List<SpendCollection> collections;

  /// Change against last month, or null when there is no previous month to
  /// compare with. Null is not zero: rendering "steady" for an unmeasured
  /// month claims a comparison that was never made.
  final double? monthDeltaPercent;

  /// Whether the service supplied these figures. False means render a state,
  /// not a number — a zero total is indistinguishable from a real empty month.
  final bool hasData;

  /// True when the household is loaded but has filed nothing this month.
  bool get isEmptyMonth => hasData && receiptCount == 0 && collections.isEmpty;
}

/// Turn the host's `YYYY-MM` trend keys into the chart's short month labels.
String _monthLabel(String isoMonth) {
  const names = <String>[
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', //
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ];
  final month = int.tryParse(
    isoMonth.length >= 7 ? isoMonth.substring(5, 7) : '',
  );
  return month != null && month >= 1 && month <= 12
      ? names[month - 1]
      : isoMonth;
}

final householdFiguresProvider = Provider<HouseholdFigures>((ref) {
  final state = ref.watch(appControllerProvider);

  if (!state.hasHouseholdData) return HouseholdFigures.unavailable;

  final trend = state.monthTrend;
  return HouseholdFigures(
    monthTotalCents: state.monthTotalCents,
    receiptCount: state.insights?.receiptCount ?? state.receipts.length,
    monthSeries: <int>[for (final point in trend) point.totalCents],
    monthLabels: <String>[for (final point in trend) _monthLabel(point.month)],
    collections: state.collections,
    monthDeltaPercent: state.insights?.monthChangePercent,
    hasData: true,
  );
});

final receiptByIdProvider = Provider.family<Receipt?, String>((ref, id) {
  final receipts = ref.watch(
    appControllerProvider.select((value) => value.receipts),
  );
  for (final receipt in receipts) {
    if (receipt.id == id) return receipt;
  }
  return null;
});

/// Full detail for one receipt, fetched from the service on demand.
///
/// The ledger list carries only summaries, so the review and view surfaces
/// load line items, tax, warnings, duplicate state and image URLs separately.
final receiptDetailProvider =
    FutureProvider.family<wire.ReceiptDetail?, String>((ref, id) async {
      final api = ref.watch(mobileApiProvider);
      if (!api.hasSession) return null;
      return ref.watch(receiptsRepositoryProvider).loadReceiptDetail(id);
    });

/// One receipt with everything the service knows about it.
///
/// Screens watch this rather than the list summary. A summary has no line
/// items, tax or reference, so reading it on a detail screen rendered every
/// live receipt as "No line items were read."
final receiptWithDetailProvider = FutureProvider.family<Receipt?, String>((
  ref,
  id,
) async {
  final summary = ref.watch(receiptByIdProvider(id));
  final api = ref.watch(mobileApiProvider);
  if (!api.hasSession) return summary;
  try {
    return await ref.watch(receiptsRepositoryProvider).loadFullReceipt(id);
  } on ApiFailure {
    // The summary is still true as far as it goes; the screen reports that
    // detail could not be loaded rather than pretending the receipt is empty.
    if (summary != null) return summary;
    rethrow;
  }
});

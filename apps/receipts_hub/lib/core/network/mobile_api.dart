import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../config/app_config.dart';
import 'api_models.dart';

/// Why a request failed, in terms the interface can respond to.
enum ApiFailureKind {
  /// The host could not be reached: asleep, off the network, or wrong address.
  unreachable,

  /// The session is missing, expired, or was revoked by a PIN change.
  unauthorized,

  /// Too many failed PIN attempts.
  rateLimited,

  /// The PIN did not match.
  badPin,

  /// The record is gone.
  notFound,

  /// Another household device changed this record first.
  conflict,

  /// The request was understood but a field was not acceptable.
  validation,

  /// The host failed to handle an otherwise valid request.
  server,
}

class ApiFailure implements Exception {
  const ApiFailure({
    required this.kind,
    required this.code,
    required this.message,
    this.field,
    this.retryAfterSeconds,
  });

  final ApiFailureKind kind;
  final String code;
  final String message;

  /// Which input the host rejected, when it named one.
  final String? field;

  /// How long to wait before retrying a throttled PIN attempt.
  final int? retryAfterSeconds;

  bool get isUnreachable => kind == ApiFailureKind.unreachable;
  bool get needsSignIn => kind == ApiFailureKind.unauthorized;

  @override
  String toString() => 'ApiFailure($code: $message)';
}

/// A typed client for the host's `/api/v1` JSON layer.
///
/// The client owns the two pieces of state a household device keeps between
/// launches: the host address and the bearer token, both held in platform
/// secure storage. Every call unwraps the host's response envelope so callers
/// only ever see payloads or an [ApiFailure].
class MobileApi {
  MobileApi({Dio? dio, FlutterSecureStorage? secureStorage})
    : _dio =
          dio ??
          Dio(
            BaseOptions(
              connectTimeout: const Duration(seconds: 8),
              receiveTimeout: const Duration(seconds: 20),
              sendTimeout: const Duration(seconds: 60),
              // The envelope carries the real outcome, so let non-2xx
              // responses through and map them to a typed failure below.
              validateStatus: (status) => status != null && status < 500,
            ),
          ),
      _secureStorage = secureStorage ?? const FlutterSecureStorage();

  static const _serverKey = 'receipts_hub.server_url';
  static const _tokenKey = 'receipts_hub.session_token';

  final Dio _dio;
  final FlutterSecureStorage _secureStorage;

  String? _baseUrl;
  String? _token;

  /// Restore the saved session, if this device has one.
  ///
  /// The address falls back to this build's configured service, so a stored
  /// session keeps working even though nothing asks the person for a host.
  Future<bool> restoreSession() async {
    _baseUrl =
        await _secureStorage.read(key: _serverKey) ?? AppConfig.apiBaseUrl;
    _token = await _secureStorage.read(key: _tokenKey);
    return _token != null;
  }

  Future<String?> savedServerUrl() async =>
      _baseUrl ??= await _secureStorage.read(key: _serverKey);

  String? get baseUrl => _baseUrl;
  bool get hasSession => _token != null;

  static String normalizeBaseUrl(String value) =>
      value.trim().replaceFirst(RegExp(r'/+$'), '');

  /// Confirm a host is awake and speaking this API before asking for a PIN.
  ///
  /// Used by first connection and by recovery when the host has gone to sleep
  /// or its LAN address has changed.
  Future<bool> checkHealth(String serverUrl) async {
    final base = normalizeBaseUrl(serverUrl);
    try {
      final response = await _dio.get<Map<String, dynamic>>(
        '$base/api/v1/health',
        options: Options(receiveTimeout: const Duration(seconds: 5)),
      );
      return response.statusCode == 200 && response.data?['status'] == 'ok';
    } on DioException {
      return false;
    }
  }

  /// Create an account on the configured service.
  ///
  /// Returns the session the service issues, so a new account lands straight in
  /// the app rather than being sent back to sign in.
  Future<SessionEnvelope> register({
    required String email,
    required String password,
    String? displayName,
  }) => _authenticate('/api/v1/auth/register', <String, dynamic>{
    'email': email,
    'password': password,
    if (displayName != null && displayName.trim().isNotEmpty)
      'display_name': displayName.trim(),
  });

  /// Sign in to the configured service with an email and password.
  Future<SessionEnvelope> logIn({
    required String email,
    required String password,
  }) => _authenticate('/api/v1/auth/login', <String, dynamic>{
    'email': email,
    'password': password,
  });

  /// Ask the service to send a password reset email.
  Future<void> requestPasswordReset(String email) async {
    _baseUrl ??= AppConfig.apiBaseUrl;
    await _post('/api/v1/auth/reset-password', <String, dynamic>{
      'email': email,
    });
  }

  /// Shared account-auth path: post credentials, keep the session it returns.
  Future<SessionEnvelope> _authenticate(
    String path,
    Map<String, dynamic> body,
  ) async {
    // A hosted build knows its own address; nobody is asked for one.
    final base = _baseUrl ??= AppConfig.apiBaseUrl;
    final data = await _send<Map<String, dynamic>>(
      () => _dio.post<Map<String, dynamic>>('$base$path', data: body),
    );
    final session = SessionEnvelope.fromJson(data);
    _token = session.token;
    await _secureStorage.write(key: _serverKey, value: base);
    await _secureStorage.write(key: _tokenKey, value: session.token);
    return session;
  }

  /// Exchange a household PIN for a bearer token against a hand-entered host.
  ///
  /// Development and support only. The product path is [register] / [logIn];
  /// this exists so the app can be driven against a local backend.
  Future<SessionEnvelope> signIn({
    required String serverUrl,
    required String pin,
  }) async {
    final base = normalizeBaseUrl(serverUrl);
    final data = await _send<Map<String, dynamic>>(
      () => _dio.post<Map<String, dynamic>>(
        '$base/api/v1/auth/pin',
        data: <String, dynamic>{'pin': pin},
      ),
    );
    final session = SessionEnvelope.fromJson(data);
    _baseUrl = base;
    _token = session.token;
    await _secureStorage.write(key: _serverKey, value: base);
    await _secureStorage.write(key: _tokenKey, value: session.token);
    return session;
  }

  /// Forget this device's session. The host address is kept so reconnecting
  /// only asks for the PIN again.
  Future<void> signOut() async {
    if (_token != null && _baseUrl != null) {
      try {
        await _dio.delete<Map<String, dynamic>>(
          '$_baseUrl/api/v1/auth',
          options: _authOptions(),
        );
      } on DioException {
        // Signing out locally must succeed even when the host is unreachable.
      }
    }
    _token = null;
    await _secureStorage.delete(key: _tokenKey);
  }

  Options _authOptions({Map<String, String>? extra}) => Options(
    headers: <String, String>{
      if (_token != null) 'Authorization': 'Bearer $_token',
      ...?extra,
    },
  );

  /// Headers an image widget needs to fetch a private receipt photo.
  Map<String, String> get imageHeaders => <String, String>{
    if (_token != null) 'Authorization': 'Bearer $_token',
  };

  /// The absolute URL of one stored receipt page.
  String receiptImageUrl(String receiptId, {int page = 1}) =>
      '$_baseUrl/api/v1/receipts/$receiptId/image?page=$page';

  // -------------------------------------------------------------------------
  // Reads
  // -------------------------------------------------------------------------

  // ---------------------------------------------------------------------------
  // Households
  // ---------------------------------------------------------------------------

  /// Every household this account belongs to, plus any pending requests.
  Future<List<HouseholdSummary>> households() async {
    final data = await _get('/api/v1/households');
    return <HouseholdSummary>[
      for (final row in (data['items'] as List<dynamic>? ?? const []))
        if (row is Map<String, dynamic>) HouseholdSummary.fromJson(row),
    ];
  }

  /// Start a new household. The creator owns it.
  Future<HouseholdSummary> createHousehold(String name) async {
    final data = await _post('/api/v1/households', <String, dynamic>{
      'name': name,
    });
    return HouseholdSummary.fromJson(data);
  }

  /// Ask to join an existing household by its ID or join code.
  ///
  /// This creates a request, not a membership: the household's owner or an
  /// admin has to approve it before any of its receipts are visible.
  Future<HouseholdSummary> requestToJoinHousehold(String joinCode) async {
    final data = await _post(
      '/api/v1/households/${Uri.encodeComponent(joinCode)}/join-requests',
      const <String, dynamic>{},
    );
    return HouseholdSummary.fromJson(data);
  }

  /// Withdraw a request this account made.
  Future<void> cancelJoinRequest(String householdId) async {
    _requireHost();
    await _send<Map<String, dynamic>>(
      () => _dio.delete<Map<String, dynamic>>(
        '$_baseUrl/api/v1/households/${Uri.encodeComponent(householdId)}'
        '/join-requests/me',
        options: _authOptions(),
      ),
    );
  }

  Future<BootstrapSnapshot> bootstrap() async {
    final data = await _get('/api/v1/bootstrap');
    return BootstrapSnapshot.fromJson(data);
  }

  Future<ReceiptPage> listReceipts({
    int limit = 50,
    int offset = 0,
    bool attentionOnly = false,
    String? merchant,
  }) async {
    final trimmed = merchant?.trim() ?? '';
    final data = await _get(
      '/api/v1/receipts',
      query: <String, dynamic>{
        'limit': limit,
        'offset': offset,
        if (attentionOnly) 'attention_only': true,
        if (trimmed.isNotEmpty) 'merchant': trimmed,
      },
    );
    return ReceiptPage.fromJson(data);
  }

  Future<ReceiptDetail> receipt(String id) async =>
      ReceiptDetail.fromJson(await _get('/api/v1/receipts/$id'));

  Future<InsightsSnapshot> insights() async =>
      InsightsSnapshot.fromJson(await _get('/api/v1/insights'));

  Future<ShoppingSnapshot> shopping() async =>
      ShoppingSnapshot.fromJson(await _get('/api/v1/shopping'));

  Future<HostSettings> settings() async =>
      HostSettings.fromJson(await _get('/api/v1/settings'));

  // -------------------------------------------------------------------------
  // Writes
  // -------------------------------------------------------------------------

  /// Apply corrections and file a receipt in the household ledger.
  Future<ReceiptSummary> confirmReceipt({
    required String id,
    required String merchant,
    required int totalCents,
    DateTime? purchasedAt,
    int? taxCents,
    List<LineItemDraft>? lineItems,
  }) async {
    final data = await _patch('/api/v1/receipts/$id', <String, dynamic>{
      'merchant': merchant,
      'total': totalCents,
      // Send the date only when there is one: the host files a receipt on
      // merchant and total alone, and holds an undated one out of dated
      // analytics until a date arrives.
      if (purchasedAt != null)
        'date':
            '${purchasedAt.year.toString().padLeft(4, '0')}-'
            '${purchasedAt.month.toString().padLeft(2, '0')}-'
            '${purchasedAt.day.toString().padLeft(2, '0')}',
      'tax': ?taxCents,
      if (lineItems != null)
        'line_items': lineItems.map((item) => item.toJson()).toList(),
    });
    return ReceiptSummary.fromJson(data);
  }

  /// Upload one to five ordered receipt photos as a single logical receipt.
  Future<UploadTicket> uploadPhotos(
    List<String> paths, {
    void Function(int sent, int total)? onProgress,
  }) async {
    if (paths.isEmpty) {
      throw const ApiFailure(
        kind: ApiFailureKind.validation,
        code: 'NO_FILES',
        message: 'Add at least one photo of the receipt.',
      );
    }
    _requireHost();
    final form = FormData();
    for (var index = 0; index < paths.length; index += 1) {
      final path = paths[index];
      form.files.add(
        MapEntry(
          'files',
          await MultipartFile.fromFile(
            path,
            filename: 'page-${index + 1}${_extensionOf(path)}',
          ),
        ),
      );
    }
    final data = await _send<Map<String, dynamic>>(
      () => _dio.post<Map<String, dynamic>>(
        '$_baseUrl/api/v1/uploads',
        data: form,
        options: _authOptions(),
        onSendProgress: onProgress,
      ),
    );
    return UploadTicket.fromJson(data);
  }

  /// Delete a receipt for the whole household.
  Future<void> deleteReceipt(String id) async {
    _requireHost();
    await _send<Map<String, dynamic>>(
      () => _dio.delete<Map<String, dynamic>>(
        '$_baseUrl/api/v1/receipts/$id',
        options: _authOptions(),
      ),
    );
  }

  Future<UploadProgress> uploadStatus(String batchId) async =>
      UploadProgress.fromJson(await _get('/api/v1/uploads/$batchId'));

  /// Re-read a failed batch using the photos already on the host.
  Future<void> retryUpload(String batchId) async {
    await _post('/api/v1/uploads/$batchId/retry', const <String, dynamic>{});
  }

  Future<ShoppingItem> addShoppingItem({
    required String product,
    String quantity = '1',
    String unit = 'each',
    String? note,
  }) async {
    final data = await _post('/api/v1/shopping', <String, dynamic>{
      'product': product,
      'quantity': quantity,
      'unit': unit,
      if (note != null && note.isNotEmpty) 'note': note,
    });
    return ShoppingItem.fromJson(data);
  }

  /// Tick or untick an item. [version] is the copy the device last saw, so a
  /// stale write is reported as a conflict instead of silently winning.
  Future<ShoppingItem> toggleShoppingItem(
    String id, {
    required bool pickedUp,
    int? version,
  }) async {
    // The status being moved *to*. This was hardcoded to `completed`, so
    // un-ticking an item sent "completed" again and the tick came straight
    // back from the service.
    final data = await _patch('/api/v1/shopping/$id', <String, dynamic>{
      'status': pickedUp ? 'completed' : 'active',
      'version': ?version,
    });
    return ShoppingItem.fromJson(data);
  }

  Future<ShoppingItem> editShoppingItem(
    String id, {
    String? product,
    String? quantity,
    String? unit,
    String? note,
    int? version,
  }) async {
    final data = await _patch('/api/v1/shopping/$id', <String, dynamic>{
      'product': ?product,
      'quantity': ?quantity,
      'unit': ?unit,
      'note': ?note,
      'version': ?version,
    });
    return ShoppingItem.fromJson(data);
  }

  Future<void> deleteShoppingItem(String id, {int? version}) async {
    _requireHost();
    await _send<Map<String, dynamic>>(
      () => _dio.delete<Map<String, dynamic>>(
        '$_baseUrl/api/v1/shopping/$id',
        queryParameters: <String, dynamic>{'version': ?version},
        options: _authOptions(),
      ),
    );
  }

  Future<ShoppingItem> acceptSuggestion(String key) async {
    final data = await _post(
      '/api/v1/shopping/suggestions/$key/accept',
      const <String, dynamic>{},
    );
    return ShoppingItem.fromJson(data);
  }

  Future<void> dismissSuggestion(String key) async {
    await _post(
      '/api/v1/shopping/suggestions/$key/dismiss',
      const <String, dynamic>{},
    );
  }

  // -------------------------------------------------------------------------
  // Transport
  // -------------------------------------------------------------------------

  Future<Map<String, dynamic>> _get(
    String path, {
    Map<String, dynamic>? query,
  }) {
    _requireHost();
    return _send<Map<String, dynamic>>(
      () => _dio.get<Map<String, dynamic>>(
        '$_baseUrl$path',
        queryParameters: query,
        options: _authOptions(),
      ),
    );
  }

  Future<Map<String, dynamic>> _post(String path, Map<String, dynamic> body) {
    _requireHost();
    return _send<Map<String, dynamic>>(
      () => _dio.post<Map<String, dynamic>>(
        '$_baseUrl$path',
        data: body,
        options: _authOptions(),
      ),
    );
  }

  Future<Map<String, dynamic>> _patch(String path, Map<String, dynamic> body) {
    _requireHost();
    return _send<Map<String, dynamic>>(
      () => _dio.patch<Map<String, dynamic>>(
        '$_baseUrl$path',
        data: body,
        options: _authOptions(),
      ),
    );
  }

  /// Fail fast when a call needs a host this device has not connected to yet.
  void _requireHost() {
    if (_baseUrl != null) return;
    throw const ApiFailure(
      kind: ApiFailureKind.unauthorized,
      code: 'NO_HOST',
      message: 'Connect to your Receipts Hub first.',
    );
  }

  /// Run a request and return its envelope payload, or throw an [ApiFailure].
  Future<Map<String, dynamic>> _send<T>(
    Future<Response<Map<String, dynamic>>> Function() request,
  ) async {
    late final Response<Map<String, dynamic>> response;
    try {
      response = await request();
    } on DioException catch (error) {
      throw _mapTransportError(error);
    }

    final body = response.data ?? const <String, dynamic>{};
    final status = response.statusCode ?? 0;
    if (status >= 200 && status < 300 && body['success'] != false) {
      final data = body['data'];
      return data is Map<String, dynamic> ? data : <String, dynamic>{};
    }
    throw _mapEnvelopeError(status, body);
  }

  ApiFailure _mapTransportError(DioException error) {
    final response = error.response;
    if (response != null) {
      final body = response.data;
      return _mapEnvelopeError(
        response.statusCode ?? 0,
        body is Map<String, dynamic> ? body : const <String, dynamic>{},
      );
    }
    if (error.type == DioExceptionType.badCertificate) {
      return const ApiFailure(
        kind: ApiFailureKind.unreachable,
        code: 'BAD_CERTIFICATE',
        message: 'That host presented a certificate this app cannot verify.',
      );
    }
    final isTimeout =
        error.type == DioExceptionType.connectionTimeout ||
        error.type == DioExceptionType.receiveTimeout ||
        error.type == DioExceptionType.sendTimeout;
    return ApiFailure(
      kind: ApiFailureKind.unreachable,
      code: isTimeout ? 'TIMEOUT' : 'UNREACHABLE',
      message: error.error is SocketException || !isTimeout
          ? 'Could not reach your Receipts Hub. Check the address and that the '
                'host computer is awake and on the same network.'
          : 'Your Receipts Hub did not answer in time. It may be busy or '
                'asleep.',
    );
  }

  ApiFailure _mapEnvelopeError(int status, Map<String, dynamic> body) {
    final error = body['error'];
    final code = error is Map<String, dynamic>
        ? (error['code'] as String? ?? 'REQUEST_FAILED')
        : 'REQUEST_FAILED';
    final message = error is Map<String, dynamic>
        ? (error['message'] as String? ?? 'That request could not be completed.')
        : 'That request could not be completed.';
    final details = error is Map<String, dynamic>
        ? error['details'] as Map<String, dynamic>?
        : null;

    final kind = switch (status) {
      401 => code == 'INVALID_PIN'
          ? ApiFailureKind.badPin
          : ApiFailureKind.unauthorized,
      403 => ApiFailureKind.unauthorized,
      404 => ApiFailureKind.notFound,
      409 => ApiFailureKind.conflict,
      429 => ApiFailureKind.rateLimited,
      >= 500 => ApiFailureKind.server,
      _ => ApiFailureKind.validation,
    };
    return ApiFailure(
      kind: kind,
      code: code,
      message: message,
      field: details?['field'] as String?,
      retryAfterSeconds: (details?['retry_after_seconds'] as num?)?.toInt(),
    );
  }

  static String _extensionOf(String path) {
    final dot = path.lastIndexOf('.');
    if (dot <= 0 || dot == path.length - 1) return '.jpg';
    return path.substring(dot).toLowerCase();
  }
}

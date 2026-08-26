// Contract tests for the client half of the /api/v1 conversation.
//
// These pin the behaviours a household actually feels: a wrong PIN reads
// differently from an unreachable host, a throttled attempt says how long to
// wait, and a shared-list edit that lost a race is reported as a conflict
// rather than silently discarded.

import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:receipts_hub/core/config/app_config.dart';
import 'package:receipts_hub/core/network/mobile_api.dart';

/// A transport that answers from a canned routing table instead of a network.
class _FakeAdapter implements HttpClientAdapter {
  _FakeAdapter(this.handler);

  final ResponseBody Function(RequestOptions options) handler;
  final List<RequestOptions> requests = <RequestOptions>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    return handler(options);
  }

  @override
  void close({bool force = false}) {}
}

ResponseBody _json(Map<String, dynamic> body, {int status = 200}) =>
    ResponseBody.fromString(
      jsonEncode(body),
      status,
      headers: <String, List<String>>{
        Headers.contentTypeHeader: <String>[Headers.jsonContentType],
      },
    );

ResponseBody _ok(Map<String, dynamic> data) => _json(<String, dynamic>{
  'success': true,
  'data': data,
  'error': null,
  'timestamp': '2026-08-16T00:00:00Z',
  'trace_id': 'test1234',
});

ResponseBody _fail(
  int status,
  String code,
  String message, {
  Map<String, dynamic>? details,
}) => _json(<String, dynamic>{
  'success': false,
  'data': null,
  'error': <String, dynamic>{
    'code': code,
    'message': message,
    'details': details,
    'timestamp': '2026-08-16T00:00:00Z',
    'trace_id': 'test1234',
  },
  'timestamp': '2026-08-16T00:00:00Z',
  'trace_id': 'test1234',
}, status: status);

({MobileApi api, _FakeAdapter adapter}) buildApi(
  ResponseBody Function(RequestOptions options) handler, {
  bool? allowHostOverride,
}) {
  final adapter = _FakeAdapter(handler);
  final dio = Dio(
    BaseOptions(validateStatus: (status) => status != null && status < 500),
  )..httpClientAdapter = adapter;
  return (
    api: MobileApi(dio: dio, allowHostOverride: allowHostOverride),
    adapter: adapter,
  );
}

Future<MobileApi> signedInApi(
  ResponseBody Function(RequestOptions options) handler,
) async {
  final built = buildApi((options) {
    if (options.path.endsWith('/auth/pin')) {
      return _ok(<String, dynamic>{
        'session_token': 'signed.token.value',
        'token_type': 'Bearer',
        'expires_in': 2592000,
        'expires_at': '2026-09-15T00:00:00Z',
        'household': <String, dynamic>{'name': 'The Test Kitchen'},
      });
    }
    return handler(options);
  });
  await built.api.signIn(serverUrl: 'http://10.0.0.5:8000', pin: '4826');
  return built.api;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => FlutterSecureStorage.setMockInitialValues(<String, String>{}));

  group('sign in', () {
    test('stores the session and reports the household name', () async {
      final built = buildApi(
        (_) => _ok(<String, dynamic>{
          'session_token': 'signed.token.value',
          'token_type': 'Bearer',
          'expires_in': 2592000,
          'expires_at': '2026-09-15T00:00:00Z',
          'household': <String, dynamic>{'name': 'The Test Kitchen'},
        }),
      );

      final session = await built.api.signIn(
        serverUrl: 'http://10.0.0.5:8000/',
        pin: '4826',
      );

      expect(session.householdName, 'The Test Kitchen');
      expect(built.api.hasSession, isTrue);
      // A trailing slash must not produce a doubled path segment.
      expect(built.api.baseUrl, 'http://10.0.0.5:8000');
      expect(
        built.adapter.requests.single.uri.toString(),
        'http://10.0.0.5:8000/api/v1/auth/pin',
      );
    });

    test('a wrong PIN is distinguishable from an unreachable host', () async {
      final built = buildApi(
        (_) => _fail(401, 'INVALID_PIN', 'That PIN did not match.'),
      );

      await expectLater(
        built.api.signIn(serverUrl: 'http://10.0.0.5:8000', pin: '0000'),
        throwsA(
          isA<ApiFailure>()
              .having((f) => f.kind, 'kind', ApiFailureKind.badPin)
              .having((f) => f.message, 'message', 'That PIN did not match.'),
        ),
      );
      expect(built.api.hasSession, isFalse);
    });

    test('a throttled attempt carries how long to wait', () async {
      final built = buildApi(
        (_) => _fail(
          429,
          'RATE_LIMITED',
          'Too many failed attempts. Try again in 900 seconds.',
          details: <String, dynamic>{'retry_after_seconds': 900},
        ),
      );

      await expectLater(
        built.api.signIn(serverUrl: 'http://10.0.0.5:8000', pin: '0000'),
        throwsA(
          isA<ApiFailure>()
              .having((f) => f.kind, 'kind', ApiFailureKind.rateLimited)
              .having((f) => f.retryAfterSeconds, 'retryAfter', 900),
        ),
      );
    });

    test('a sleeping host reads as unreachable, not as a bad PIN', () async {
      final adapter = _FakeAdapter((_) => throw StateError('no route'));
      final dio = Dio()..httpClientAdapter = adapter;
      final api = MobileApi(dio: dio);

      await expectLater(
        api.signIn(serverUrl: 'http://10.0.0.5:8000', pin: '4826'),
        throwsA(
          isA<ApiFailure>()
              .having((f) => f.kind, 'kind', ApiFailureKind.unreachable)
              .having((f) => f.isUnreachable, 'isUnreachable', isTrue),
        ),
      );
    });
  });

  group('authenticated reads', () {
    test('every request carries the bearer token', () async {
      final built = buildApi((options) {
        if (options.path.endsWith('/auth/pin')) {
          return _ok(<String, dynamic>{
            'session_token': 'signed.token.value',
            'expires_in': 2592000,
            'expires_at': '2026-09-15T00:00:00Z',
            'household': <String, dynamic>{'name': 'Home'},
          });
        }
        return _ok(<String, dynamic>{
          'household': <String, dynamic>{'name': 'Home'},
          'totals': <String, dynamic>{
            'month_total': 12345,
            'month_trend': <dynamic>[
              <String, dynamic>{'month': '2026-08', 'total': 12345},
            ],
          },
          'collections': <dynamic>[],
          'counts': <String, dynamic>{'receipts': 3, 'active_list_items': 2},
        });
      });
      await built.api.signIn(serverUrl: 'http://10.0.0.5:8000', pin: '4826');

      final snapshot = await built.api.bootstrap();

      expect(snapshot.monthTotalCents, 12345);
      expect(snapshot.receiptCount, 3);
      expect(snapshot.monthTrend.single.month, '2026-08');
      expect(
        built.adapter.requests.last.headers['Authorization'],
        'Bearer signed.token.value',
      );
    });

    test('an expired session is reported as needing sign-in', () async {
      final api = await signedInApi(
        (_) => _fail(401, 'INVALID_TOKEN', 'This session has expired.'),
      );

      await expectLater(
        api.bootstrap(),
        throwsA(
          isA<ApiFailure>()
              .having((f) => f.kind, 'kind', ApiFailureKind.unauthorized)
              .having((f) => f.needsSignIn, 'needsSignIn', isTrue),
        ),
      );
    });

    test('receipts map undated entries without inventing a date', () async {
      final api = await signedInApi(
        (_) => _ok(<String, dynamic>{
          'items': <dynamic>[
            <String, dynamic>{
              'id': 'r-1',
              'merchant': 'Aldi',
              'date': null,
              'total': 1200,
              'status': 'complete',
              'image_count': 1,
              'item_count': 2,
              'attention_required': false,
              'dated': false,
              'created_at': '2026-08-14T02:00:00Z',
            },
          ],
          'pagination': <String, dynamic>{
            'total': 1,
            'limit': 50,
            'offset': 0,
            'has_more': false,
          },
        }),
      );

      final page = await api.listReceipts();

      expect(page.total, 1);
      expect(page.items.single.purchasedAt, isNull);
      expect(page.items.single.dated, isFalse);
    });
  });

  group('writes', () {
    test('filing omits the date when a receipt has none', () async {
      late RequestOptions captured;
      final api = await signedInApi((options) {
        captured = options;
        return _ok(<String, dynamic>{
          'id': 'r-1',
          'merchant': 'Aldi',
          'date': null,
          'total': 1200,
          'status': 'complete',
          'dated': false,
        });
      });

      await api.confirmReceipt(id: 'r-1', merchant: 'Aldi', totalCents: 1200);

      final body = captured.data as Map<String, dynamic>;
      expect(body.containsKey('date'), isFalse);
      expect(body['merchant'], 'Aldi');
      expect(body['total'], 1200);
    });

    test('filing sends an ISO date when one is known', () async {
      late RequestOptions captured;
      final api = await signedInApi((options) {
        captured = options;
        return _ok(<String, dynamic>{
          'id': 'r-1',
          'merchant': 'Coles',
          'date': '2026-08-03',
          'total': 650,
          'status': 'complete',
          'dated': true,
        });
      });

      await api.confirmReceipt(
        id: 'r-1',
        merchant: 'Coles',
        totalCents: 650,
        purchasedAt: DateTime(2026, 8, 3),
      );

      expect((captured.data as Map<String, dynamic>)['date'], '2026-08-03');
    });

    test('a stale list edit surfaces as a conflict', () async {
      final api = await signedInApi(
        (_) => _fail(
          409,
          'VERSION_CONFLICT',
          'Another household device changed this item. Reload the list.',
        ),
      );

      await expectLater(
        api.toggleShoppingItem('s-1', pickedUp: true, version: 1),
        throwsA(
          isA<ApiFailure>().having(
            (f) => f.kind,
            'kind',
            ApiFailureKind.conflict,
          ),
        ),
      );
    });

    test('a rejected field is named so the form can point at it', () async {
      final api = await signedInApi(
        (_) => _fail(
          422,
          'INVALID_REQUEST',
          'Store name is required.',
          details: <String, dynamic>{'field': 'merchant_name'},
        ),
      );

      await expectLater(
        api.confirmReceipt(id: 'r-1', merchant: '  ', totalCents: 500),
        throwsA(
          isA<ApiFailure>()
              .having((f) => f.kind, 'kind', ApiFailureKind.validation)
              .having((f) => f.field, 'field', 'merchant_name'),
        ),
      );
    });
  });

  group('host health', () {
    test('reports a healthy host', () async {
      final built = buildApi(
        (_) =>
            _json(<String, dynamic>{'status': 'ok', 'service': 'grocery-home'}),
      );

      expect(await built.api.checkHealth('http://10.0.0.5:8000'), isTrue);
    });

    test('reports an unreachable host without throwing', () async {
      final adapter = _FakeAdapter((_) => throw StateError('no route'));
      final dio = Dio()..httpClientAdapter = adapter;

      expect(
        await MobileApi(dio: dio).checkHealth('http://10.0.0.5:8000'),
        isFalse,
      );
    });
  });

  // The account routes and the developer PIN route return different session
  // shapes, and the client has to read both. It read only the PIN shape, so
  // every real signup died on a null cast *after* the service had created the
  // account: the button spun forever and nothing said why.
  group('account sessions', () {
    ResponseBody accountSession() => _ok(<String, dynamic>{
      'token': 'account.token.value',
      'expires_at': '2026-09-25T09:05:09.085348+00:00',
      'household_name': 'Joe',
      'user': <String, dynamic>{
        'id': 'c22b7193dbf34fe490b0a3255246a285',
        'email': 'joe@example.com',
        'display_name': 'Joe',
        'email_verified': false,
      },
    });

    test('register reads the payload the account routes send', () async {
      final built = buildApi((_) => accountSession());

      final session = await built.api.register(
        email: 'joe@example.com',
        password: 'a-long-enough-password',
        displayName: 'Joe',
      );

      expect(session.token, 'account.token.value');
      expect(session.householdName, 'Joe');
      expect(built.api.hasSession, isTrue);
      expect(
        built.adapter.requests.single.uri.toString(),
        '${AppConfig.apiBaseUrl}/api/v1/auth/register',
      );
    });

    test('signing in reads it too', () async {
      final built = buildApi((_) => accountSession());

      final session = await built.api.logIn(
        email: 'joe@example.com',
        password: 'a-long-enough-password',
      );

      expect(session.token, 'account.token.value');
      expect(session.householdName, 'Joe');
    });

    test('the configured service is not written to storage', () async {
      final built = buildApi((_) => accountSession());

      await built.api.logIn(
        email: 'joe@example.com',
        password: 'a-long-enough-password',
      );

      // Only a hand-entered developer host is stored, so a stored address
      // always means somebody chose it.
      expect(
        await const FlutterSecureStorage().read(key: 'receipts_hub.server_url'),
        isNull,
      );
    });

    test(
      'a session it cannot read fails, rather than throwing a cast',
      () async {
        final built = buildApi(
          (_) => _ok(<String, dynamic>{
            'expires_at': '2026-09-25T09:05:09.085348+00:00',
            'household_name': 'Joe',
          }),
        );

        await expectLater(
          built.api.register(
            email: 'joe@example.com',
            password: 'a-long-enough-password',
          ),
          throwsA(
            isA<ApiFailure>()
                .having((f) => f.code, 'code', 'MALFORMED_SESSION')
                .having((f) => f.kind, 'kind', ApiFailureKind.server),
          ),
        );
        expect(built.api.hasSession, isFalse);
      },
    );
  });

  group('the address this build talks to', () {
    test(
      'a stored host is ignored, and cleared, when none may be entered',
      () async {
        FlutterSecureStorage.setMockInitialValues(<String, String>{
          'receipts_hub.server_url': 'http://10.0.2.2:8000',
        });
        final built = buildApi(
          (_) => _ok(<String, dynamic>{}),
          allowHostOverride: false,
        );

        await built.api.restoreSession();

        // A release build has no screen for entering an address, so honouring a
        // stale one leaves signup posting at a host that stopped answering.
        expect(built.api.baseUrl, AppConfig.apiBaseUrl);
        expect(
          await const FlutterSecureStorage().read(
            key: 'receipts_hub.server_url',
          ),
          isNull,
        );
      },
    );

    test('a development build keeps the host it was pointed at', () async {
      FlutterSecureStorage.setMockInitialValues(<String, String>{
        'receipts_hub.server_url': 'http://192.168.1.20:8000',
      });
      final built = buildApi(
        (_) => _ok(<String, dynamic>{}),
        allowHostOverride: true,
      );

      await built.api.restoreSession();

      expect(built.api.baseUrl, 'http://192.168.1.20:8000');
    });

    test(
      'with nothing stored it uses the service this build ships with',
      () async {
        final built = buildApi((_) => _ok(<String, dynamic>{}));

        await built.api.restoreSession();

        expect(built.api.baseUrl, AppConfig.apiBaseUrl);
      },
    );
  });
}

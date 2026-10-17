import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ai_vhrs_mobile/core/network/dio_client.dart';
import 'package:ai_vhrs_mobile/core/network/network_exceptions.dart';
import 'package:ai_vhrs_mobile/core/storage/secure_storage_service.dart';
import 'package:ai_vhrs_mobile/features/auth/data/auth_repository.dart';
import 'package:ai_vhrs_mobile/features/auth/domain/models/auth_state.dart';
import 'package:ai_vhrs_mobile/features/auth/presentation/auth_notifier.dart';

/// Answers requests from a route table, like the real backend would.
class FakeApi implements HttpClientAdapter {
  final Map<String, ({int status, Object? body})> Function(RequestOptions o) handler;
  final calls = <String>[];
  FakeApi(this.handler);

  @override
  Future<ResponseBody> fetch(RequestOptions o, Stream<Uint8List>? body, Future<void>? cancel) async {
    final key = '${o.method} ${o.path}';
    calls.add(key);
    final r = handler(o)[key] ?? (status: 404, body: _err('NOT_FOUND', 'no route $key'));
    return ResponseBody.fromString(
      r.body == null ? '' : jsonEncode(r.body),
      r.status,
      headers: {
        Headers.contentTypeHeader: ['application/json'],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

Map<String, Object?> _err(String code, String message) => {
      'error': {'code': code, 'message': message, 'details': null},
    };

const _account = {
  'id': 4,
  'email': 'tech@netviet.vn',
  'full_name': 'Technical Staff',
  'phone': null,
  'phone_verified': false,
  'role': 'TECHNICAL_STAFF',
  'status': 'ACTIVE',
  'addresses': [],
  'created_at': '2026-10-11T06:50:59.464298Z',
  'last_login_at': null,
};

Map<String, Object?> _tokens(String access, [Map<String, Object?> account = _account]) =>
    {'access_token': access, 'refresh_token': 'refresh-$access', 'token_type': 'bearer', 'account': account};

({ProviderContainer c, FakeApi api, SecureStorageService storage}) _setup(
  Map<String, ({int status, Object? body})> Function(RequestOptions o) routes,
) {
  final storage = SecureStorageService();
  final api = FakeApi(routes);
  final c = ProviderContainer(overrides: [secureStorageProvider.overrideWithValue(storage)]);
  c.read(dioClientProvider).dio.httpClientAdapter = api;
  return (c: c, api: api, storage: storage);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('login reads tokens and the account, sends a bearer token afterwards', () async {
    String? auth;
    final s = _setup((o) {
      auth = o.headers['Authorization'] as String?;
      return {
        'POST /auth/login': (status: 200, body: _tokens('a1')),
        'GET /me': (status: 200, body: _account),
      };
    });
    await s.c.read(authNotifierProvider.notifier).login(email: 'tech@netviet.vn', password: 'ChangeMe@123');
    final st = s.c.read(authNotifierProvider);
    expect(st, isA<AuthAuthenticated>());
    st as AuthAuthenticated;
    expect(st.userId, '4');
    expect(st.fullName, 'Technical Staff');
    expect(st.role, 'TECHNICAL_STAFF');
    expect(await s.storage.getAccessToken(), 'a1');

    await s.c.read(authRepositoryProvider).getProfile();
    expect(auth, 'Bearer a1');
  });

  test('wrong password shows a message and stays signed out (no demo fallback)', () async {
    final s = _setup((_) => {
          'POST /auth/login': (status: 401, body: _err('INVALID_CREDENTIALS', 'Email hoặc mật khẩu không đúng.')),
        });
    await s.c.read(authNotifierProvider.notifier).login(email: 'x@example.com', password: 'nope12345');
    final st = s.c.read(authNotifierProvider);
    expect(st, isA<AuthError>());
    expect((st as AuthError).message, 'dk.err.credentials');
    expect(await s.storage.hasToken(), isFalse);
    // The login 401 must not trigger a token refresh.
    expect(s.api.calls, ['POST /auth/login']);
  });

  test('customer accounts are refused by the technician desk and their session is revoked', () async {
    final s = _setup((_) => {
          'POST /auth/login': (status: 200, body: _tokens('t1', {..._account, 'role': 'CUSTOMER'})),
          'POST /auth/logout': (status: 204, body: null),
        });
    await s.c.read(authNotifierProvider.notifier).login(email: 'customer@example.com', password: 'ChangeMe@123');
    expect((s.c.read(authNotifierProvider) as AuthError).message, 'dk.err.role');
    expect(s.api.calls, contains('POST /auth/logout'));
    expect(await s.storage.hasToken(), isFalse);
  });

  test('an expired access token is refreshed once and the request retried', () async {
    final s = _setup((o) {
      final bearer = o.headers['Authorization'];
      return {
        'GET /me': bearer == 'Bearer new'
            ? (status: 200, body: _account)
            : (status: 401, body: _err('TOKEN_EXPIRED', 'expired')),
        'POST /auth/refresh': (status: 200, body: _tokens('new')),
      };
    });
    await s.storage.saveTokens(accessToken: 'old', refreshToken: 'r-old');
    final user = await s.c.read(authRepositoryProvider).getProfile();
    expect(user.email, 'tech@netviet.vn');
    expect(await s.storage.getAccessToken(), 'new');
    expect(s.api.calls, ['GET /me', 'POST /auth/refresh', 'GET /me']);
  });

  test('a rejected refresh token signs the user out', () async {
    final s = _setup((_) => {
          'POST /auth/login': (status: 200, body: _tokens('a3')),
          'GET /me': (status: 401, body: _err('NOT_AUTHENTICATED', '...')),
          'POST /auth/refresh': (status: 401, body: _err('TOKEN_INVALID', '...')),
        });
    final n = s.c.read(authNotifierProvider.notifier);
    await n.login(email: 'tech@netviet.vn', password: 'ChangeMe@123');
    expect(s.c.read(authNotifierProvider), isA<AuthAuthenticated>());
    await expectLater(s.c.read(authRepositoryProvider).getProfile(), throwsA(isA<UnauthorizedException>()));
    expect((s.c.read(authNotifierProvider) as AuthError).message, 'dk.err.expired');
    expect(await s.storage.hasToken(), isFalse);
  });

  test('logout revokes the session on the server', () async {
    final s = _setup((_) => {
          'POST /auth/login': (status: 200, body: _tokens('a4')),
          'POST /auth/logout': (status: 204, body: null),
        });
    final n = s.c.read(authNotifierProvider.notifier);
    await n.login(email: 'tech@netviet.vn', password: 'ChangeMe@123');
    await n.logout();
    expect(s.api.calls.last, 'POST /auth/logout');
    expect(s.c.read(authNotifierProvider), isA<AuthUnauthenticated>());
    expect(await s.storage.hasToken(), isFalse);
  });

  test('rate limits and temporary locks have their own messages', () async {
    final s = _setup((_) => {
          'POST /auth/login': (status: 423, body: _err('ACCOUNT_TEMP_LOCKED', '...')),
        });
    await s.c.read(authNotifierProvider.notifier).login(email: 'a@b.co', password: 'x');
    expect((s.c.read(authNotifierProvider) as AuthError).message, 'dk.err.locked');
  });
}

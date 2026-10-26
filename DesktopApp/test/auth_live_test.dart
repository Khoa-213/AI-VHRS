import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ai_vhrs_mobile/core/network/dio_client.dart';
import 'package:ai_vhrs_mobile/core/storage/secure_storage_service.dart';
import 'package:ai_vhrs_mobile/features/auth/data/auth_repository.dart';

/// Hits the deployed API with the seeded technical-staff account. Skipped unless asked:
///
///   flutter test test/auth_live_test.dart --dart-define=LIVE_API=true
///
/// No test binding here on purpose: the widget test binding blocks real HTTP.
void main() {
  test('seeded technician signs in, reads /me, signs out', () async {
    final client = DioClient(storage: SecureStorageService());
    final repo = AuthRepositoryImpl(client: client);
    final session = await repo.login(email: 'tech@netviet.vn', password: 'ChangeMe@123');
    expect(session.user.role, 'TECHNICAL_STAFF');
    final bearer = Options(headers: {'Authorization': 'Bearer ${session.accessToken}'});
    final me = await client.dio.get<Map<String, dynamic>>('/me', options: bearer);
    expect(me.data!['email'], 'tech@netviet.vn');
    await client.dio.post<void>('/auth/logout', options: bearer);
  }, skip: !const bool.fromEnvironment('LIVE_API'), timeout: const Timeout(Duration(minutes: 2)));
}

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ai_vhrs_mobile/core/network/dio_client.dart';
import 'package:ai_vhrs_mobile/core/storage/secure_storage_service.dart';
import 'package:ai_vhrs_mobile/features/auth/data/auth_repository.dart';
import 'package:ai_vhrs_mobile/features/tech/data/robot_api.dart';
import 'package:ai_vhrs_mobile/features/tech/data/tech_api.dart';

/// Parses real answers from the deployed API with the seeded technical-staff account. Read calls
/// only: `package` is left out because it records the download. Skipped unless asked:
///
///   flutter test test/tech_live_test.dart --dart-define=LIVE_API=true
///
/// No test binding here on purpose: the widget test binding blocks real HTTP.
void main() {
  test('seeded technician reads jobs, photos, robots and alerts', () async {
    final client = DioClient(storage: SecureStorageService());
    final session = await AuthRepositoryImpl(client: client)
        .login(email: 'tech@netviet.vn', password: 'ChangeMe@123');
    client.dio.interceptors.clear();
    client.dio.options.headers['Authorization'] = 'Bearer ${session.accessToken}';
    final tech = TechApi(client: client, storage: Dio());
    final robot = RobotApi(client: client);

    final jobs = await tech.allJobs();
    expect(jobs, isNotEmpty);
    for (final j in jobs) {
      final d = await tech.getJob(j.id);
      expect(d.job.id, j.id);
      await tech.allEvents(j.id);
      await tech.photos(j.id);
      await robot.jobCommands(j.id);
    }

    final status = await robot.robotStatus();
    expect(status, isNotEmpty);
    for (final s in status) {
      final live = await robot.getLive(s.robotId, 0);
      expect(live.robotId, s.robotId);
      // ignore: avoid_print
      print('${jobs.length} jobs; ${s.robotCode} ${s.state.name} online=${live.online} alerts='
          '${[for (final a in s.alerts) '${a.code}/L${a.level}/estop=${a.estopAdvised}/ack=${a.acknowledgedAt != null}']}');
    }
    await client.dio.post<void>('/auth/logout');
  }, skip: !const bool.fromEnvironment('LIVE_API'), timeout: const Timeout(Duration(minutes: 5)));
}

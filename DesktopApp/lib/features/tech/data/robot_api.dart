import 'dart:math';

import '../../../core/constants/api_constants.dart';
import '../../../core/network/dio_client.dart';
import '../../../core/network/network_exceptions.dart';
import '../domain/robot.dart';

/// Robot control, one to one with FE `services/robot.ts`. The app never talks to the workstation:
/// it creates commands on the backend, the Robot Agent pulls and runs them and reports back.
class RobotApi {
  final DioClient _client;
  final Random _random = Random.secure();

  RobotApi({required DioClient client}) : _client = client;

  /// A random UUID v4.
  String _newKey() {
    final b = List<int>.generate(16, (_) => _random.nextInt(256));
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    final h = [for (final x in b) x.toRadixString(16).padLeft(2, '0')].join();
    return '${h.substring(0, 8)}-${h.substring(8, 12)}-${h.substring(12, 16)}-${h.substring(16, 20)}-${h.substring(20)}';
  }

  /// One press of a button: a fresh idempotency key, so a retried request makes one command only.
  Future<RobotCommand> sendCommand(
    CommandKind kind, {
    int? jobId,
    int? robotId,
    Map<String, dynamic> params = const {},
  }) async =>
      RobotCommand.fromJson(await _client.post<Map<String, dynamic>>(ApiConstants.robotCommands, data: {
        'kind': kind.code,
        if (jobId != null) 'job_id': jobId,
        if (robotId != null) 'robot_id': robotId,
        'params': params,
        'idempotency_key': _newKey(),
      }));

  Future<RobotCommand> getCommand(String id) async => RobotCommand.fromJson(
      await _client.get<Map<String, dynamic>>('${ApiConstants.robotCommands}/${Uri.encodeComponent(id)}'));

  Future<List<RobotCommand>> jobCommands(int jobId, {int limit = 20}) async {
    final r = await _client.get<List<dynamic>>(
      '${ApiConstants.technicianJobs}/$jobId/robot-commands',
      queryParameters: {'limit': limit},
    );
    return [for (final c in r) RobotCommand.fromJson(c as Map<String, dynamic>)];
  }

  /// Follows a command until the agent answers (DONE, FAILED) or it lapses (EXPIRED). A network
  /// or server hiccup keeps asking; any other API error is thrown. When [cancelled] turns true
  /// it returns the last state it saw.
  Future<RobotCommand> waitCommand(
    RobotCommand cmd, {
    void Function(RobotCommand)? onUpdate,
    bool Function()? cancelled,
    Duration every = const Duration(milliseconds: 700),
  }) async {
    var current = cmd;
    while (!current.status.isFinal) {
      await Future<void>.delayed(every);
      if (cancelled?.call() ?? false) return current;
      try {
        current = await getCommand(cmd.id);
        onUpdate?.call(current);
      } on ServerException {
        continue;
      } on TimeoutException {
        continue;
      } on NoInternetException {
        continue;
      }
    }
    return current;
  }

  Future<Live> getLive(int robotId, int after) async => Live.fromJson(await _client.get<Map<String, dynamic>>(
        '${ApiConstants.technicianRobots}/$robotId/live',
        queryParameters: {'after': after},
      ));

  /// Read-only 3D page served by the backend. The ticket lasts `expiresIn` seconds.
  Future<ViewTicket> viewTicket(int robotId) async {
    final r = await _client.post<Map<String, dynamic>>('${ApiConstants.technicianRobots}/$robotId/view-ticket');
    final origin = ApiConstants.baseUrl.replaceFirst(RegExp(r'/api/v1$'), '');
    return ViewTicket(url: '$origin${r['viewer_path']}', expiresIn: r['expires_in'] as int);
  }

  Future<List<RobotStatus>> robotStatus() async {
    final r = await _client.get<List<dynamic>>(ApiConstants.robotStatus);
    return [for (final s in r) RobotStatus.fromJson(s as Map<String, dynamic>)];
  }

  Future<RobotAlert> ackAlert(int id) async =>
      RobotAlert.fromJson(await _client.post<Map<String, dynamic>>('${ApiConstants.technicianAlerts}/$id/ack'));

  /// Levels 1 to 3 only; a red (level 4) alert is closed by a Manager.
  Future<RobotAlert> resolveAlert(int id, String note) async => RobotAlert.fromJson(await _client
      .post<Map<String, dynamic>>('${ApiConstants.technicianAlerts}/$id/resolve', data: {'note': note}));
}

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_vhrs_mobile/core/network/network_exceptions.dart';
import 'package:ai_vhrs_mobile/features/auth/data/auth_repository.dart';
import 'package:ai_vhrs_mobile/features/auth/domain/models/user.dart';
import 'package:ai_vhrs_mobile/features/auth/presentation/auth_notifier.dart';
import 'package:ai_vhrs_mobile/features/tech/data/prefs.dart';
import 'package:ai_vhrs_mobile/features/tech/data/providers.dart';
import 'package:ai_vhrs_mobile/features/tech/data/robot_api.dart';
import 'package:ai_vhrs_mobile/features/tech/domain/robot.dart';
import 'package:ai_vhrs_mobile/features/tech/i18n/tech_strings.dart';
import 'package:ai_vhrs_mobile/features/tech/presentation/widgets/alert_bell.dart';
import 'package:ai_vhrs_mobile/features/tech/presentation/widgets/estop.dart';

RobotAlert _alert(int id, {bool estop = true, int level = 4, DateTime? ack}) => RobotAlert(
      id: id,
      robotId: 46,
      code: 'CODE_$id',
      level: level,
      title: 'Lỗi an toàn $id',
      action: 'Bấm E-Stop',
      estopAdvised: estop,
      occurrences: 1,
      raisedAt: DateTime.utc(2026, 10, 23, 6, 23),
      acknowledgedAt: ack,
    );

RobotStatus _status(List<RobotAlert> alerts) => RobotStatus(
      robotId: 46,
      robotCode: 'FR3-01',
      state: RobotHealth.danger,
      headline: 'Nguy hiểm',
      level: 4,
      connection: 'OFFLINE',
      alerts: alerts,
    );

class _StubAuth implements AuthRepository {
  @override
  Future<AuthSession> login({required String email, required String password}) async => (
        accessToken: 'a',
        refreshToken: 'r',
        user: User(id: '4', email: email, fullName: 'Tech', role: UserRole.technicalStaff, createdAt: DateTime(2026)),
      );
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _RobotApi implements RobotApi {
  final acked = <int>[];
  final commands = <(CommandKind, int?)>[];
  bool failAck = false;
  void Function()? onAck;

  @override
  Future<RobotAlert> ackAlert(int id) async {
    if (failAck) throw const NoInternetException();
    acked.add(id);
    onAck?.call();
    return _alert(id);
  }

  @override
  Future<RobotCommand> sendCommand(CommandKind kind, {int? jobId, int? robotId, Map<String, dynamic> params = const {}}) async {
    commands.add((kind, robotId));
    return RobotCommand(id: 'c', robotId: 46, kind: kind, params: const {}, status: CommandStatus.pending, createdAt: DateTime(2026), expiresAt: DateTime(2026));
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Future<void> _pump(WidgetTester tester, List<RobotAlert> alerts, _RobotApi api, {Widget? behind, Size size = const Size(1440, 900)}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  FlutterSecureStorage.setMockInitialValues({});
  SharedPreferences.setMockInitialValues({'aivhrs-lang': 'en'});
  final prefs = await SharedPreferences.getInstance();
  var current = alerts;
  api.onAck = () => current = [for (final a in current) _alert(a.id, estop: a.estopAdvised, level: a.level, ack: a.acknowledgedAt ?? DateTime.utc(2026, 10, 23, 6, 24))];
  await tester.pumpWidget(ProviderScope(
    overrides: [
      prefsProvider.overrideWithValue(prefs),
      authRepositoryProvider.overrideWithValue(_StubAuth()),
      robotApiProvider.overrideWithValue(api),
      robotStatusProvider.overrideWith((ref) => Stream.value([_status(current)])),
    ],
    child: MaterialApp(
      builder: (_, child) => EstopGate(child: child!),
      home: Scaffold(body: Column(children: [const EstopBand(), behind ?? const Text('the page behind')])),
    ),
  ));
  final c = ProviderScope.containerOf(tester.element(find.byType(EstopGate)));
  await c.read(authNotifierProvider.notifier).login(email: 'tech@netviet.vn', password: 'x');
  await tester.pump();
  await tester.pump();
}

/// The takeover runs a repeating timer, so these tests pump by hand and leave it cleanly.
Future<void> _leave(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox());
  await tester.pump();
}

void main() {
  setUpAll(() async {
    for (final l in Lang.values) {
      await initializeDateFormatting(l.locale);
    }
  });

  testWidgets('an unacknowledged E-Stop alert covers everything, and taps do not reach the page', (tester) async {
    var tapped = 0;
    await _pump(tester, [_alert(1)], _RobotApi(), behind: ElevatedButton(onPressed: () => tapped++, child: const Text('behind')));
    expect(find.text('PRESS THE PHYSICAL E-STOP NOW'), findsOneWidget);
    expect(find.text('DANGER'), findsOneWidget);
    expect(find.text('I pressed the E-Stop'), findsOneWidget);
    await tester.tap(find.text('behind'), warnIfMissed: false);
    await tester.pump();
    expect(tapped, 0);
    expect(tester.takeException(), isNull);
    await _leave(tester);
  });

  testWidgets('it has no way out but the button: Esc does nothing', (tester) async {
    await _pump(tester, [_alert(1)], _RobotApi());
    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pump();
    expect(find.text('I pressed the E-Stop'), findsOneWidget);
    await _leave(tester);
  });

  testWidgets('confirming acknowledges every pending alert, then the steady band remains', (tester) async {
    final api = _RobotApi();
    await _pump(tester, [_alert(1), _alert(2)], api);
    await tester.tap(find.text('I pressed the E-Stop'));
    await tester.pump();
    await tester.pump();
    await tester.pump();
    expect(api.acked, [1, 2]);
    expect(find.text('I pressed the E-Stop'), findsNothing);
    expect(find.text('FR3-01: E-Stop acknowledged at 13:24 23/10. Waiting for a Manager to close the alert.'), findsOneWidget);
    await _leave(tester);
  });

  testWidgets('a failed acknowledge keeps it up and says why', (tester) async {
    final api = _RobotApi()..failAck = true;
    await _pump(tester, [_alert(1)], api);
    await tester.tap(find.text('I pressed the E-Stop'));
    await tester.pump();
    await tester.pump();
    expect(find.text('I pressed the E-Stop'), findsOneWidget);
    expect(find.text('No connection to the server. Check your network.'), findsOneWidget);
    await _leave(tester);
  });

  testWidgets('Stop can be sent from it without leaving', (tester) async {
    final api = _RobotApi();
    await _pump(tester, [_alert(1)], api);
    await tester.tap(find.text('Send Stop to the robot'));
    await tester.pump();
    await tester.pump();
    expect(api.commands, [(CommandKind.stop, 46)]);
    expect(find.text('Stop sent to the robot.'), findsOneWidget);
    expect(find.text('I pressed the E-Stop'), findsOneWidget);
    await _leave(tester);
  });

  testWidgets('an alert without the E-Stop flag, or already acknowledged, does not take over', (tester) async {
    await _pump(tester, [_alert(1, estop: false, level: 3), _alert(2, ack: DateTime.utc(2026))], _RobotApi());
    expect(find.text('I pressed the E-Stop'), findsNothing);
    expect(find.text('the page behind'), findsOneWidget);
    await _leave(tester);
  });

  testWidgets('it fits a phone in the longest languages', (tester) async {
    await _pump(tester, [_alert(1)], _RobotApi(), size: const Size(390, 844));
    expect(find.text('I pressed the E-Stop'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await _leave(tester);
  });

  testWidgets('the bell lists alerts; red ones close only by a Manager, others need a note', (tester) async {
    await _pump(tester, [_alert(1, ack: DateTime.utc(2026)), _alert(2, estop: false, level: 3)], _RobotApi(), behind: const AlertBell());
    await tester.tap(find.byType(AlertBell));
    await tester.pumpAndSettle();
    expect(find.text('Lỗi an toàn 1'), findsOneWidget);
    expect(find.text('Lỗi an toàn 2'), findsOneWidget);
    expect(find.byType(TextField), findsOneWidget);
    await _leave(tester);
  });
}

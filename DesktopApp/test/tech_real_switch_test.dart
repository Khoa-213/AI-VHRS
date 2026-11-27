import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'package:ai_vhrs_mobile/features/tech/data/agent_process.dart';
import 'package:ai_vhrs_mobile/features/tech/i18n/tech_strings.dart';
import 'package:ai_vhrs_mobile/features/tech/presentation/widgets/real_switch.dart';

/// The agent's local API without a network: records the calls and answers like the agent.
class _FakeApi extends AgentLocalApi {
  final calls = <String>[];
  Map<String, dynamic>? real;
  AgentApiError? refuse;
  _FakeApi() : super(base: 'http://127.0.0.1:1/', code: 'x');

  @override
  Future<Map<String, dynamic>?> realState() async {
    calls.add('state');
    return real;
  }

  @override
  Future<Map<String, dynamic>> realEnable(int jobId, {int minutes = 30}) async {
    calls.add('enable $jobId $minutes');
    if (refuse != null) throw refuse!;
    real = {'job_id': jobId, 'expires_at': DateTime.now().millisecondsSinceEpoch / 1000 + 1800};
    return {'real_enabled': real, 'robot_check': {'ok': true, 'controller': {'controller': 'V3.8.25'}}};
  }

  @override
  Future<void> realDisable() async {
    calls.add('disable');
    real = null;
  }
}

void main() {
  late Directory dir;
  setUpAll(() => initializeDateFormatting('en'));
  setUp(() {
    dir = Directory.systemTemp.createTempSync('real-switch');
    File('${dir.path}/agent.json').writeAsStringSync(jsonEncode({'robot_id': 46, 'modes': ['mock', 'sim', 'real']}));
  });
  tearDown(() => dir.deleteSync(recursive: true));

  Future<void> pump(WidgetTester tester, {required AgentLocalApi? api, int? robotId = 46}) async {
    await tester.pumpWidget(ProviderScope(
      overrides: [
        tProvider.overrideWithValue(const T(Lang.en)),
        agentControllerProvider.overrideWith((ref) => AgentController(dir: dir.path)),
        agentLocalApiProvider.overrideWithValue(api),
      ],
      child: MaterialApp(
        home: Scaffold(body: RealSwitch(jobId: 276, robotId: robotId, fallback: const Text('copy the command'))),
      ),
    ));
    await tester.pumpAndSettle();
  }

  testWidgets('no agent here, or the job runs on another robot: the command to run at that workstation', (tester) async {
    await pump(tester, api: null);
    expect(find.text('copy the command'), findsOneWidget);
    await pump(tester, api: _FakeApi(), robotId: 7);
    expect(find.text('copy the command'), findsOneWidget);
  });

  testWidgets('on this robot\'s workstation: a button, a confirmation, then REAL on until a time, and off again', (tester) async {
    final api = _FakeApi();
    await pump(tester, api: api);
    expect(find.text('copy the command'), findsNothing);
    await tester.tap(find.text('Turn REAL on (30 min)'));
    await tester.pumpAndSettle();
    expect(find.text('Turn REAL on for job #276?'), findsOneWidget);
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(api.calls, isNot(contains('enable 276 30')), reason: 'nothing without the confirmation');

    await tester.tap(find.text('Turn REAL on (30 min)'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Turn REAL on (30 min)'));
    await tester.pumpAndSettle();
    expect(api.calls, contains('enable 276 30'));
    expect(find.textContaining('REAL on until'), findsOneWidget);
    expect(find.textContaining('controller V3.8.25'), findsOneWidget);

    await tester.tap(find.text('Turn REAL off'));
    await tester.pumpAndSettle();
    expect(api.calls.last, 'disable');
    expect(find.text('REAL is off.'), findsOneWidget);
  });

  testWidgets('a robot that does not answer keeps REAL off and says why', (tester) async {
    final api = _FakeApi()..refuse = const AgentApiError(502, 'ROBOT_UNREACHABLE', 'SDK_TIMEOUT');
    await pump(tester, api: api);
    await tester.tap(find.text('Turn REAL on (30 min)'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Turn REAL on (30 min)'));
    await tester.pumpAndSettle();
    expect(find.textContaining('The real robot does not answer'), findsOneWidget);
    expect(find.textContaining('REAL on until'), findsNothing);
  });
}

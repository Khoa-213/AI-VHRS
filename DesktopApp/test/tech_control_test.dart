import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_vhrs_mobile/features/tech/data/prefs.dart';
import 'package:ai_vhrs_mobile/features/tech/data/providers.dart';
import 'package:ai_vhrs_mobile/features/tech/data/robot_api.dart';
import 'package:ai_vhrs_mobile/features/tech/data/tech_api.dart';
import 'package:ai_vhrs_mobile/features/tech/domain/job.dart';
import 'package:ai_vhrs_mobile/features/tech/domain/robot.dart';
import 'package:ai_vhrs_mobile/features/tech/i18n/tech_strings.dart';
import 'package:ai_vhrs_mobile/features/tech/presentation/screens/job_photos_screen.dart';
import 'package:ai_vhrs_mobile/features/tech/presentation/screens/robot_control_screen.dart';
import 'package:ai_vhrs_mobile/features/tech/presentation/widgets/robot_view_3d.dart';
import 'package:ai_vhrs_mobile/features/tech/presentation/widgets/tech_ui.dart';

TechJobDetail _detail(JobStatus status, {bool sim = true}) => TechJobDetail(
      job: TechJob(
        id: 276,
        orderId: 9,
        orderCode: 'VHRS-SEED02',
        robotId: 46,
        robotCode: 'FR3-01',
        technicianId: 4,
        technicianName: 'Tech',
        status: status,
        isRewrite: false,
        slotStart: DateTime.utc(2026, 10, 23),
        slotEnd: DateTime.utc(2026, 10, 23, 1),
        durationMin: 25,
        downloadedAt: DateTime.utc(2026, 10, 23),
        simulationPassed: sim ? true : null,
        packageHash: 'abc',
      ),
      orderType: 'OT3_TEMPLATE',
      quantity: 1,
      canStart: true,
      incidents: const [],
      calibration: Calibration(id: 1, isValid: true, createdAt: DateTime.utc(2026)),
    );

RobotCommand _command(CommandKind kind, CommandStatus status, {Map<String, dynamic>? result}) => RobotCommand(
      id: 'c-${kind.code}',
      robotId: 46,
      jobId: 276,
      kind: kind,
      params: const {},
      status: status,
      result: result,
      createdAt: DateTime.utc(2026, 10, 23),
      expiresAt: DateTime.utc(2026, 10, 23, 1),
    );

class _Robot implements RobotApi {
  final sent = <(CommandKind, Map<String, dynamic>)>[];

  @override
  Future<RobotCommand> sendCommand(CommandKind kind, {int? jobId, int? robotId, Map<String, dynamic> params = const {}}) async {
    sent.add((kind, params));
    return _command(kind, CommandStatus.done);
  }

  @override
  Future<RobotCommand> waitCommand(RobotCommand cmd, {void Function(RobotCommand)? onUpdate, bool Function()? cancelled, Duration every = Duration.zero}) async => cmd;

  @override
  Future<ViewTicket> viewTicket(int robotId) async => const ViewTicket(url: 'https://x/viewer', expiresIn: 3600);

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

LiveView _live({bool online = true, bool busy = false, List<String> modes = const ['REAL']}) => LiveView(
      Live(robotId: 46, robotCode: 'FR3-01', online: online, status: AgentStatus(busy: busy, enabledModes: modes), lastSeq: 1, frames: const []),
      null,
    );

Future<_Robot> _pumpControl(
  WidgetTester tester, {
  JobStatus status = JobStatus.preparing,
  LiveView? live,
  List<RobotCommand> commands = const [],
  Size size = const Size(1440, 1400),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  FlutterSecureStorage.setMockInitialValues({});
  SharedPreferences.setMockInitialValues({'aivhrs-lang': 'en'});
  final prefs = await SharedPreferences.getInstance();
  final robot = _Robot();
  final router = GoRouter(routes: [GoRoute(path: '/', builder: (_, _) => const Scaffold(body: RobotControlScreen(jobId: 276)))]);
  addTearDown(router.dispose);
  await tester.pumpWidget(ProviderScope(
    overrides: [
      prefsProvider.overrideWithValue(prefs),
      robotApiProvider.overrideWithValue(robot),
      techJobProvider.overrideWith((ref, id) => Stream.value(_detail(status))),
      techJobsProvider.overrideWith((ref) => Stream.value(const [])),
      robotStatusProvider.overrideWith((ref) => Stream.value(const [])),
      robotLiveProvider.overrideWith((ref, id) => Stream.value(live ?? _live())),
      jobCommandsProvider.overrideWith((ref, id) async => commands),
      jobEventsProvider.overrideWith((ref, id) async => const []),
      jobPhotosProvider.overrideWith((ref, id) => Stream.value(const [])),
      robotWebViewProvider.overrideWithValue((url) => Text('3D $url')),
    ],
    child: MaterialApp.router(routerConfig: router),
  ));
  await tester.pumpAndSettle();
  return robot;
}

void main() {
  setUpAll(() async {
    for (final l in Lang.values) {
      await initializeDateFormatting(l.locale);
    }
  });

  group('robot control', () {
    testWidgets('shows the 3D page from the backend, on desktop and phone', (tester) async {
      await _pumpControl(tester);
      expect(find.text('3D https://x/viewer'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await _pumpControl(tester, size: const Size(390, 844));
      expect(find.text('3D https://x/viewer'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('an offline agent locks every command', (tester) async {
      final robot = await _pumpControl(tester, live: _live(online: false));
      await tester.tap(find.text('Load job'), warnIfMissed: false);
      await tester.pumpAndSettle();
      expect(robot.sent, isEmpty);
    });

    testWidgets('LOAD goes to the backend for this job when the agent is online', (tester) async {
      final robot = await _pumpControl(tester);
      await tester.tap(find.text(const T(Lang.en)('rb.do.LOAD')));
      await tester.pumpAndSettle();
      expect(robot.sent.single.$1, CommandKind.load);
    });

    testWidgets('Run needs a loaded job and the operator typing the code; it is not filled in', (tester) async {
      const t = T(Lang.en);
      final robot = await _pumpControl(
        tester,
        status: JobStatus.writing,
        commands: [_command(CommandKind.load, CommandStatus.done, result: {'authorization_token': 'AUTHORIZE-276-X'})],
      );
      await tester.tap(find.text(t('rb.kind.RUN')), warnIfMissed: false);
      await tester.pumpAndSettle();
      expect(robot.sent, isEmpty);
      final field = tester.widget<TextFormField>(find.byType(TextFormField).first);
      expect(field.controller!.text, '');

      await tester.enterText(find.byType(TextFormField).first, 'AUTHORIZE-276-X');
      await tester.pumpAndSettle();
      await tester.tap(find.text(t('rb.kind.RUN')));
      await tester.pumpAndSettle();
      // Asks first: nothing moves until the operator confirms.
      expect(robot.sent, isEmpty);
      await tester.tap(find.text('Confirm'));
      await tester.pumpAndSettle();
      expect(robot.sent.single.$1, CommandKind.run);
      expect(robot.sent.single.$2, {'mode': 'REAL', 'authorization': 'AUTHORIZE-276-X'});
    });

    testWidgets('Stop works while the robot runs, and asks first', (tester) async {
      const t = T(Lang.en);
      final robot = await _pumpControl(tester, status: JobStatus.writing, live: _live(busy: true));
      await tester.tap(find.text(t('rb.do.STOP')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Confirm'));
      await tester.pumpAndSettle();
      expect(robot.sent.single.$1, CommandKind.stop);
    });

    test('a command error reads in words', () {
      const t = T(Lang.en);
      expect(commandError(_command(CommandKind.load, CommandStatus.expired), t), t('rb.err.expired'));
      expect(commandError(_command(CommandKind.load, CommandStatus.failed), t), t('rb.err.failed'));
    });
  });

  group('photos', () {
    Future<Uint8List> png(int w, int h) async {
      final recorder = ui.PictureRecorder();
      Canvas(recorder).drawRect(Rect.fromLTWH(0, 0, w.toDouble(), h.toDouble()), Paint());
      final image = await recorder.endRecording().toImage(w, h);
      final data = await image.toByteData(format: ui.ImageByteFormat.png);
      return data!.buffer.asUint8List();
    }

    testWidgets('a photo must be a real JPG or PNG with a long side of 1280 px', (tester) async {
      await tester.runAsync(() async {
        await expectLater(validateProductPhoto(Uint8List.fromList([1, 2, 3, 4, 5])), throwsA(isA<TechFlowError>().having((e) => e.key, 'key', 'td.flow.invalidPhoto')));
        await expectLater(validateProductPhoto(await png(640, 480)), throwsA(isA<TechFlowError>().having((e) => e.key, 'key', 'td.flow.photoTooSmall')));
        expect(await validateProductPhoto(await png(1280, 10)), 'image/png');
      });
    });

    testWidgets('the page lays out on desktop and phone for a written job', (tester) async {
      for (final size in const [Size(1440, 1000), Size(390, 844)]) {
        tester.view.physicalSize = size;
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.reset);
        SharedPreferences.setMockInitialValues({'aivhrs-lang': 'vi'});
        final prefs = await SharedPreferences.getInstance();
        await tester.pumpWidget(ProviderScope(
          key: ValueKey(size),
          overrides: [
            prefsProvider.overrideWithValue(prefs),
            techJobProvider.overrideWith((ref, id) => Stream.value(_detail(JobStatus.written))),
            robotStatusProvider.overrideWith((ref) => Stream.value(const [])),
            jobPhotosProvider.overrideWith((ref, id) => Stream.value([
                  ProductPhoto(id: 1, kind: PhotoKind.overall, qcResult: QcResult.pass, urlExpiresIn: 0, createdAt: DateTime.utc(2026)),
                ])),
          ],
          child: const MaterialApp(home: Scaffold(body: JobPhotosScreen(jobId: 276))),
        ));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull, reason: '$size');
        expect(find.byType(TechCard), findsWidgets);
      }
    });
  });
}

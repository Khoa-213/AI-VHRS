import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_vhrs_mobile/core/network/network_exceptions.dart';
import 'package:ai_vhrs_mobile/features/tech/data/prefs.dart';
import 'package:ai_vhrs_mobile/features/tech/data/providers.dart';
import 'package:ai_vhrs_mobile/features/tech/domain/notification.dart';
import 'package:ai_vhrs_mobile/features/tech/data/tech_api.dart';
import 'package:ai_vhrs_mobile/features/tech/domain/calibration.dart';
import 'package:ai_vhrs_mobile/features/tech/domain/job.dart';
import 'package:ai_vhrs_mobile/features/tech/domain/robot.dart';
import 'package:ai_vhrs_mobile/features/tech/i18n/tech_strings.dart';
import 'package:ai_vhrs_mobile/features/tech/presentation/screens/job_detail_screen.dart';
import 'package:ai_vhrs_mobile/features/tech/presentation/screens/jobs_screen.dart';
import 'package:ai_vhrs_mobile/features/tech/presentation/screens/tech_dashboard_screen.dart';
import 'package:ai_vhrs_mobile/features/tech/presentation/widgets/job_setup.dart';
import 'package:ai_vhrs_mobile/features/tech/presentation/widgets/job_widgets.dart';
import 'package:ai_vhrs_mobile/features/tech/presentation/widgets/tech_shell.dart';
import 'package:ai_vhrs_mobile/features/tech/presentation/widgets/tech_ui.dart';

TechJob _job(int id, JobStatus status, {int minutes = 25, bool rewrite = false, int? robot = 46}) => TechJob(
      id: id,
      orderId: id + 1000,
      orderCode: 'VHRS-$id',
      robotId: robot,
      robotCode: robot == null ? '' : 'FR3-01',
      technicianId: 4,
      technicianName: 'Technical Staff',
      status: status,
      isRewrite: rewrite,
      slotStart: DateTime.utc(2026, 10, 23, 7, 50),
      slotEnd: DateTime.utc(2026, 10, 23, 8, 15),
      durationMin: minutes,
    );

final _jobs = [
  _job(276, JobStatus.preparing),
  _job(275, JobStatus.scheduled, minutes: 30),
  _job(277, JobStatus.scheduled, minutes: 40, rewrite: true),
  _job(280, JobStatus.written),
  _job(279, JobStatus.done),
  _job(281, JobStatus.failed),
  _job(282, JobStatus.scheduled, robot: null),
];

TechJobDetail _detail(int id, {Calibration? calibration}) => TechJobDetail(
      calibration: calibration,
      job: _jobs.firstWhere((j) => j.id == id),
      orderType: 'OT3_TEMPLATE',
      quantity: 2,
      canStart: false,
      incidents: const [],
      paper: 'A5',
      pen: 'Ballpoint',
      ink: 'Black',
    );

const _danger = RobotStatus(
  robotId: 46,
  robotCode: 'FR3-01',
  state: RobotHealth.danger,
  headline: 'Máy trạm mất kết nối',
  level: 4,
  connection: 'OFFLINE',
  alerts: [],
);

const _writer = RobotStatus(
  robotId: 47,
  robotCode: 'FR3-02',
  state: RobotHealth.writing,
  headline: 'Đang viết',
  level: 1,
  connection: 'ONLINE',
  alerts: [],
  active: true,
  enabledModes: ['SIM', 'REAL'],
);

const _broken = RobotStatus(
  robotId: 48,
  robotCode: 'FR3-03',
  state: RobotHealth.offline,
  headline: '',
  level: 1,
  connection: 'UNKNOWN',
  alerts: [],
  robotStatus: 'MAINTENANCE',
);

/// The job calls the pages make; the rest are not used here.
class _Api implements TechApi {
  final chosen = <(int, int)>[];
  final calibrations = <Map<String, dynamic>>[];
  final issues = <(int, int, bool, int)>[];

  @override
  Future<JobStock> issueStock(int id, {required int paper, bool newPen = false, required int seenIssued}) async {
    issues.add((id, paper, newPen, seenIssued));
    return const JobStock(issued: true, canIssue: true);
  }

  @override
  Future<TechJob> chooseRobot(int id, int robotId) async {
    chosen.add((id, robotId));
    return _jobs.firstWhere((j) => j.id == id);
  }

  @override
  Future<void> calibrate(int id, Map<String, dynamic> body) async => calibrations.add(body);

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Future<GoRouter> _pump(
  WidgetTester tester,
  Size size,
  String start, {
  Stream<List<TechJob>>? jobs,
  List<RobotStatus> status = const [_danger],
  List<RobotStatus>? mine,
  Stream<TechJobDetail> Function(int id)? detail,
  String lang = 'en',
  TechApi? api,
  JobReference? reference,
  JobStock? stock,
}) async {
  final my = mine ?? status;
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  FlutterSecureStorage.setMockInitialValues({});
  SharedPreferences.setMockInitialValues({'aivhrs-lang': lang});
  final prefs = await SharedPreferences.getInstance();
  final router = GoRouter(
    initialLocation: start,
    routes: [
      ShellRoute(
        builder: (_, s, child) => TechShell(location: s.uri.toString(), child: child),
        routes: [
          GoRoute(path: '/tech', builder: (_, _) => const TechDashboardScreen()),
          GoRoute(
            path: '/tech/jobs',
            builder: (_, s) => JobsScreen(
              filter: JobFilter.parse(s.uri.queryParameters['filter']),
              robotId: int.tryParse(s.uri.queryParameters['robot'] ?? ''),
            ),
          ),
          GoRoute(
            path: '/tech/jobs/:id',
            builder: (_, s) => JobDetailScreen(
              jobId: int.parse(s.pathParameters['id']!),
              backTo: s.uri.queryParameters['filter'] == null ? '/tech/jobs' : '/tech/jobs?filter=${s.uri.queryParameters['filter']}',
            ),
          ),
          GoRoute(path: '/tech/qc', builder: (_, _) => const JobsScreen(filter: JobFilter.qc)),
          GoRoute(path: '/tech/qc/:id', builder: (_, _) => const Text('photos page')),
        ],
      ),
    ],
  );
  addTearDown(router.dispose);
  await tester.pumpWidget(ProviderScope(
    overrides: [
      prefsProvider.overrideWithValue(prefs),
      // The header's notification bell: no call to the real backend from a test.
      notificationsProvider.overrideWith((ref) => Stream.value(const NotificationPage(items: [], unreadCount: 0))),
      techJobsProvider.overrideWith((ref) => jobs ?? Stream.value(_jobs)),
      robotStatusProvider.overrideWith((ref) => Stream.value(status)),
      myRobotsProvider.overrideWith((ref) => Stream.value(MyRobots(
            total: my.length,
            online: my.where((r) => r.online).length,
            active: my.where((r) => r.active).length,
            robots: my,
          ))),
      jobCommandsProvider.overrideWith((ref, id) async => const []),
      if (api != null) techApiProvider.overrideWithValue(api),
      techJobProvider.overrideWith((ref, id) => detail?.call(id) ?? Stream.value(_detail(id))),
      jobEventsProvider.overrideWith((ref, id) async => const []),
      // An older server has no /reference: the column falls back to the names of the job detail.
      jobReferenceProvider.overrideWith(
          (ref, id) => reference == null ? Stream<JobReference>.error(const NotFoundException('x', 'NOT_FOUND')) : Stream.value(reference)),
      // An older server has no stock sheet either (0033): Prepare is then left to the server.
      jobStockProvider.overrideWith(
          (ref, id) => stock == null ? Stream<JobStock>.error(const NotFoundException('x', 'NOT_FOUND')) : Stream.value(stock)),
    ],
    child: MaterialApp.router(routerConfig: router),
  ));
  await tester.pumpAndSettle();
  return router;
}

void main() {
  setUpAll(() async {
    for (final l in Lang.values) {
      await initializeDateFormatting(l.locale);
    }
  });

  group('dashboard', () {
    testWidgets('counts, groups and the queue come from the jobs', (tester) async {
      await _pump(tester, const Size(1440, 1400), '/tech');
      expect(find.text('Needs QC'), findsOneWidget);
      expect(find.text('Scheduled and preparing'), findsOneWidget);
      expect(find.text('Photo and QC'), findsOneWidget);
      expect(find.text('Needs attention'), findsOneWidget);
      expect(find.text('7 assigned'), findsOneWidget);
      // 25 + 30 + 40 + 25 minutes wait to start; the groups with no jobs are not shown.
      expect(find.text('120 min'), findsOneWidget);
      expect(find.text('Writing and paused'), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('history starts folded and opens on a tap', (tester) async {
      await _pump(tester, const Size(1440, 1400), '/tech');
      expect(find.text('VHRS-279'), findsNothing);
      await tester.tap(find.text('History'));
      await tester.pumpAndSettle();
      expect(find.text('VHRS-279'), findsOneWidget);
    });

    testWidgets('the robot shows the state and the backend sentence', (tester) async {
      await _pump(tester, const Size(1440, 1400), '/tech');
      expect(find.text('Danger'), findsOneWidget);
      expect(find.text('Máy trạm mất kết nối'), findsOneWidget);
    });

    testWidgets('a tile and a row open the right place', (tester) async {
      final router = await _pump(tester, const Size(1440, 1400), '/tech');
      await tester.tap(find.text('VHRS-276').first);
      await tester.pumpAndSettle();
      expect(router.routerDelegate.currentConfiguration.uri.path, '/tech/jobs/276');
      router.go('/tech');
      await tester.pumpAndSettle();
      await tester.tap(find.text('Needs QC'));
      await tester.pumpAndSettle();
      expect(router.routerDelegate.currentConfiguration.uri.path, '/tech/qc');
    });

    testWidgets('a failed load says so instead of showing an empty queue', (tester) async {
      await _pump(tester, const Size(1440, 1000), '/tech', jobs: Stream.error(const NoInternetException()), status: const []);
      expect(find.text('No connection to the server. Check your network.'), findsOneWidget);
      expect(find.text('Nothing assigned yet'), findsNothing);
      expect(find.text('Refresh'), findsNWidgets(2));
    });

    testWidgets('no jobs reads as nothing assigned', (tester) async {
      await _pump(tester, const Size(1440, 1000), '/tech', jobs: Stream.value(const []), status: const []);
      expect(find.text('Nothing assigned yet'), findsOneWidget);
    });

    for (final lang in Lang.values) {
      testWidgets('a phone stacks it without overflow in ${lang.name}', (tester) async {
        await _pump(tester, const Size(390, 844), '/tech', lang: lang.name);
        expect(tester.takeException(), isNull);
        expect(find.byType(NavigationBar), findsOneWidget);
      });
    }
  });

  group('job list', () {
    testWidgets('the filters split the jobs, and the QC tab carries a count', (tester) async {
      final router = await _pump(tester, const Size(1440, 1000), '/tech/jobs');
      expect(find.text('VHRS-276'), findsOneWidget);
      expect(find.text('VHRS-280'), findsNothing);
      expect(find.text('In progress · 4'), findsOneWidget);
      expect(find.text('History · 2'), findsOneWidget);

      await tester.tap(find.text('History · 2'));
      await tester.pumpAndSettle();
      expect(router.routerDelegate.currentConfiguration.uri.toString(), '/tech/jobs?filter=history');
      expect(find.text('VHRS-279'), findsOneWidget);
      expect(find.text('VHRS-281'), findsOneWidget);
      expect(find.text('VHRS-276'), findsNothing);

      await tester.tap(find.text('Needs QC · 1'));
      await tester.pumpAndSettle();
      expect(router.routerDelegate.currentConfiguration.uri.path, '/tech/qc');
      expect(find.text('VHRS-280'), findsOneWidget);
      expect(find.text('1'), findsOneWidget); // the rail's QC badge
    });

    testWidgets('search finds by order code and job number', (tester) async {
      await _pump(tester, const Size(1440, 1000), '/tech/jobs');
      await tester.enterText(find.byType(TextFormField), 'vhrs-275');
      await tester.pumpAndSettle();
      expect(find.text('VHRS-275'), findsOneWidget);
      expect(find.text('VHRS-276'), findsNothing);
      await tester.enterText(find.byType(TextFormField), '277');
      await tester.pumpAndSettle();
      expect(find.text('VHRS-277'), findsOneWidget);
      await tester.enterText(find.byType(TextFormField), 'nope');
      await tester.pumpAndSettle();
      expect(find.text('No job matches this search.'), findsOneWidget);
    });

    for (final size in const [Size(1440, 1000), Size(390, 844)]) {
      testWidgets('at ${size.width}: list and job are separate pages, and back keeps the filter', (tester) async {
        final router = await _pump(tester, size, '/tech/jobs?filter=history');
        expect(find.text('Final sketch'), findsNothing);
        await tester.tap(find.text('VHRS-279'));
        await tester.pumpAndSettle();
        expect(router.routerDelegate.currentConfiguration.uri.toString(), '/tech/jobs/279?filter=history');
        expect(find.text('Job for VHRS-279'), findsOneWidget);
        expect(find.text('Final sketch'), findsOneWidget, reason: 'the reference column stays beside the steps');
        expect(find.text('Find a job'), findsNothing);
        expect(tester.takeException(), isNull);
        await tester.tap(find.text('Back to jobs'));
        await tester.pumpAndSettle();
        expect(router.routerDelegate.currentConfiguration.uri.toString(), '/tech/jobs?filter=history');
        expect(find.text('Find a job'), findsOneWidget);
      });
    }

    testWidgets('a job that is not mine reads as not found', (tester) async {
      await _pump(tester, const Size(1440, 1000), '/tech/jobs/999',
          detail: (_) => Stream.error(const NotFoundException('x', 'JOB_NOT_FOUND')));
      expect(find.text('This job does not exist or is not assigned to you.'), findsOneWidget);
    });

    testWidgets('a written job in the QC list opens its photos page', (tester) async {
      final router = await _pump(tester, const Size(1440, 1000), '/tech/qc');
      await tester.tap(find.text('VHRS-280'));
      await tester.pumpAndSettle();
      // A written job opens its photos page, which lives under /tech/qc.
      expect(router.routerDelegate.currentConfiguration.uri.toString(), '/tech/qc/280');
    });
  });

  group('job page: steps, step work and the reference column (2026-11-27)', () {
    const ref = JobReference(
      pages: 2,
      pagesAssumed: false,
      sketchVersion: 3,
      paper: RefMaterial(name: 'Art A5', spec: 'A5 · 120 gsm · ART', need: 4, stock: 1),
      pen: RefMaterial(name: 'Gel 0.5', spec: 'GEL · 0.5 mm', need: 1, stock: 12),
      ink: RefMaterial(name: 'Black', spec: '#000000', hex: '#000000', need: 1, stock: 30),
      approachNote: 'Write the signature lower right.',
    );

    const taken = JobStock(issued: true, canIssue: true, pages: 2, lines: [
      StockLine(kind: 'PAPER', itemId: 1, name: 'Art A5', unit: 'tờ', need: 4, issued: 4, stock: 1),
      StockLine(kind: 'PEN', itemId: 2, name: 'Gel 0.5', unit: 'cây', need: 0, issued: 0, stock: 12),
      StockLine(kind: 'INK', itemId: 3, name: 'Black', unit: 'cây', need: 0, issued: 0, stock: 30),
    ]);

    testWidgets('the current step opens, its materials light up, and what was taken shows', (tester) async {
      await _pump(tester, const Size(1440, 2000), '/tech/jobs/276', reference: ref, stock: taken);
      expect(find.text('Step 4 of 12'), findsOneWidget, reason: 'a preparing job without calibration is on Calibrate');
      expect(find.text('Final sketch'), findsOneWidget);
      expect(find.text('Approved · v3'), findsOneWidget);
      expect(find.text('2 page(s) per copy'), findsOneWidget);
      expect(find.text('Need 4 · in stock 1 · Not enough in stock'), findsOneWidget);
      expect(find.text('Paper · Used in this step'), findsOneWidget);
      expect(find.text('Pen · Used in this step'), findsOneWidget);
      expect(find.text('Ink'), findsWidgets);
      expect(find.text('Write the signature lower right.'), findsOneWidget);
      expect(find.text('Paper taken'), findsOneWidget);
      expect(find.text('Taken 4/4'), findsOneWidget);
      expect(find.text('On pen change'), findsNWidgets(2), reason: 'pens and ink are taken only when the pen is replaced (Q1)');

      await tester.tap(find.text('Choose the robot').first);
      await tester.pumpAndSettle();
      expect(find.text('Step 2 of 12'), findsOneWidget);
      expect(find.text('This step is done.'), findsOneWidget);
      expect(find.text('Paper · Used in this step'), findsNothing);
      await tester.tap(find.byTooltip('Next step'));
      await tester.pumpAndSettle();
      expect(find.text('Step 3 of 12'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('without /reference the column keeps the names and says what is missing', (tester) async {
      await _pump(tester, const Size(1440, 2000), '/tech/jobs/276');
      expect(find.text('Ballpoint'), findsOneWidget);
      expect(find.text('Quantities and the preview are not available from the server yet.'), findsOneWidget);
      expect(find.text('No preview image. Download the job package to see the writing path.'), findsOneWidget);
    });

    testWidgets('Prepare: take the paper (plus spare) before preparing, never twice from one screen', (tester) async {
      final api = _Api();
      const waiting = JobStock(issued: false, canIssue: true, pages: 2, lines: [
        StockLine(kind: 'PAPER', itemId: 1, name: 'Art A5', unit: 'tờ', need: 4, issued: 0, stock: 50),
        StockLine(kind: 'PEN', itemId: 2, name: 'Gel 0.5', unit: 'cây', need: 0, issued: 0, stock: 0),
      ]);
      await _pump(tester, const Size(1440, 2400), '/tech/jobs/282', api: api, stock: waiting, mine: const [_danger, _writer]);
      await tester.tap(find.text('Choose the robot').first);
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Next step'));
      await tester.pumpAndSettle();
      expect(find.text('Take materials from stock'), findsOneWidget);
      expect(find.text('Need 4 sheets · taken 0 · in stock 50'), findsOneWidget);
      expect(find.text('Take the paper in the card above first.'), findsOneWidget);
      expect(find.text('Paper not taken'), findsOneWidget);
      await tester.tap(find.byTooltip('One more'));
      await tester.pumpAndSettle();
      // a new pen with no pen in stock cannot be taken
      await tester.tap(find.byType(Checkbox).first);
      await tester.pumpAndSettle();
      expect(tester.widget<TechButton>(find.widgetWithText(TechButton, 'Take 5 sheets and a new pen')).onPressed, isNull);
      await tester.tap(find.byType(Checkbox).first);
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(TechButton, 'Take 5 sheets'));
      await tester.pumpAndSettle();
      expect(api.issues, [(282, 5, false, 0)], reason: 'need + 1 spare, with the issued count the screen showed');
      expect(tester.takeException(), isNull);
    });

    testWidgets('short stock blocks the issue and says to ask the manager', (tester) async {
      const short = JobStock(issued: false, canIssue: true, lines: [
        StockLine(kind: 'PAPER', itemId: 1, name: 'Art A5', unit: 'tờ', need: 4, issued: 0, stock: 3),
      ]);
      await _pump(tester, const Size(1440, 2400), '/tech/jobs/282', stock: short, mine: const [_danger, _writer]);
      await tester.tap(find.text('Choose the robot').first);
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Next step'));
      await tester.pumpAndSettle();
      expect(find.text('Only 3 sheets left in stock. Ask the Manager to receive more.'), findsOneWidget);
      expect(tester.widget<TechButton>(find.widgetWithText(TechButton, 'Take 4 sheets')).onPressed, isNull);
    });

    for (final w in [1000.0, 390.0]) {
      testWidgets('the three parts fit a $w window', (tester) async {
        await _pump(tester, Size(w, 4000), '/tech/jobs/276', reference: ref);
        expect(find.text('Final sketch'), findsOneWidget);
        expect(tester.takeException(), isNull);
      });
    }
  });

  group('my robots and the robot choice (migration 0032)', () {
    testWidgets('the dashboard lists the robots given to me with the connected and working counts', (tester) async {
      final router = await _pump(tester, const Size(1440, 1400), '/tech', mine: const [_danger, _writer, _broken]);
      expect(find.text('My robots'), findsOneWidget);
      expect(find.text('Connected 1 / 3 · Working 1'), findsOneWidget);
      expect(find.text('Connected'), findsOneWidget);
      expect(find.text('Disconnected'), findsOneWidget);
      expect(find.text('Never connected'), findsOneWidget);
      expect(find.text('Working'), findsOneWidget);
      expect(find.text('Under maintenance'), findsOneWidget);
      expect(find.text('Real robot'), findsOneWidget);

      await tester.tap(find.text('FR3-01'));
      await tester.pumpAndSettle();
      expect(router.routerDelegate.currentConfiguration.uri.toString(), '/tech/jobs?robot=46');
      expect(find.text('Showing the jobs of FR3-01.'), findsOneWidget);
      expect(find.text('VHRS-276'), findsOneWidget);
      expect(find.text('VHRS-282'), findsNothing, reason: 'a job without a robot is not on FR3-01');
      await tester.tap(find.text('Show all'));
      await tester.pumpAndSettle();
      expect(find.text('VHRS-282'), findsOneWidget);
      expect(find.textContaining('No robot chosen'), findsOneWidget);
    });

    testWidgets('no robot given yet says to ask the manager', (tester) async {
      await _pump(tester, const Size(1440, 1400), '/tech', mine: const []);
      expect(find.text('No robot is assigned to you yet. Ask the manager to assign one.'), findsOneWidget);
    });

    testWidgets('a scheduled job without a robot: pick one of mine, not one in maintenance', (tester) async {
      final api = _Api();
      await _pump(tester, const Size(1440, 2400), '/tech/jobs/282', mine: const [_danger, _writer, _broken], api: api);
      expect(find.text('No robot chosen'), findsWidgets);
      expect(find.text('Download the job package first.'), findsOneWidget, reason: 'the step list says why Prepare waits');
      // The rail opens the current step (the package); the robot choice is the work of step 2.
      expect(find.widgetWithText(TechButton, 'Choose this robot'), findsNothing);
      await tester.tap(find.text('Choose the robot').first);
      await tester.pumpAndSettle();
      final choose = find.widgetWithText(TechButton, 'Choose this robot');
      expect(tester.widget<TechButton>(choose).onPressed, isNull);

      await tester.tap(find.text('FR3-03'));
      await tester.pumpAndSettle();
      expect(tester.widget<TechButton>(choose).onPressed, isNull, reason: 'a robot in maintenance cannot be chosen');

      await tester.tap(find.text('FR3-01').last);
      await tester.pumpAndSettle();
      expect(find.textContaining('FR3-01 is not connected now'), findsOneWidget);
      await tester.ensureVisible(choose);
      await tester.tap(choose);
      await tester.pumpAndSettle();
      expect(api.chosen, [(282, 46)]);
    });

    testWidgets('a preparing job takes a calibration typed by hand once P0 to P2 span the paper', (tester) async {
      final api = _Api();
      await _pump(tester, const Size(1440, 3000), '/tech/jobs/276', api: api);
      await tester.tap(find.text('Enter by hand'));
      await tester.pumpAndSettle();
      for (final k in ['Frame mounted', 'Paper clamped', 'Pen installed', 'Force zeroed (pen lifted)']) {
        await tester.tap(find.text(k));
      }
      final fields = find.descendant(of: find.byType(CalibrationCard), matching: find.byType(TextFormField));
      expect(fields, findsNWidgets(10));
      final values = ['0.1', '0', '0', '0', '100', '0', '0', '0', '100', '0'];
      for (var i = 0; i < 10; i++) {
        await tester.enterText(fields.at(i), values[i]);
      }
      await tester.pumpAndSettle();
      final send = find.widgetWithText(TechButton, 'Send calibration');
      await tester.ensureVisible(send);
      await tester.tap(send);
      await tester.pumpAndSettle();
      expect(api.calibrations, hasLength(1));
      expect(api.calibrations.single['probe_points'], [
        {'x': 0.0, 'y': 0.0, 'z': 0.0},
        {'x': 100.0, 'y': 0.0, 'z': 0.0},
        {'x': 0.0, 'y': 100.0, 'z': 0.0},
      ]);
      expect((api.calibrations.single['checklist'] as Map).values.every((v) => v == true), isTrue);
    });

    for (final lang in Lang.values) {
      testWidgets('the robot strip and the job steps fit a phone in ${lang.name}', (tester) async {
        await _pump(tester, const Size(390, 844), '/tech', lang: lang.name, mine: const [_danger, _writer, _broken]);
        expect(tester.takeException(), isNull);
        await _pump(tester, const Size(390, 844), '/tech/jobs/282', lang: lang.name, mine: const [_danger, _writer, _broken]);
        expect(tester.takeException(), isNull);
      });
    }
  });

  test('a job without a robot reads, waits for one before Prepare, and is labelled', () {
    final j = TechJob.fromJson({
      'id': 5, 'order_id': 9, 'order_code': 'VHRS-5', 'robot_id': null, 'robot_code': '', 'technician_id': 4, 'status': 'SCHEDULED',
      'is_rewrite': false, 'slot_start': '2026-11-26T01:00:00Z', 'slot_end': '2026-11-26T02:00:00Z', 'estimated_duration_min': 60,
      'package_hash': 'a', 'downloaded_at': '2026-11-26T00:00:00Z',
    });
    expect(j.robotId, isNull);
    expect(jobRobotLabel(const T(Lang.en), j), 'No robot chosen');
    final d = TechJobDetail(job: j, orderType: 'OT3_TEMPLATE', quantity: 1, canStart: false, incidents: const []);
    expect(d.permissions('a').chooseRobot, isTrue);
    expect(d.permissions('a').prepare, isFalse);
    final withRobot = TechJobDetail(
      job: TechJob.fromJson({...{
        'id': 5, 'order_id': 9, 'technician_id': 4, 'status': 'SCHEDULED', 'is_rewrite': false, 'slot_start': '2026-11-26T01:00:00Z',
        'slot_end': '2026-11-26T02:00:00Z', 'estimated_duration_min': 60, 'package_hash': 'a', 'downloaded_at': '2026-11-26T00:00:00Z',
      }, 'robot_id': 46}),
      orderType: 'OT3_TEMPLATE', quantity: 1, canStart: false, incidents: const [],
    );
    expect(withRobot.permissions('a').prepare, isTrue);
    expect(withRobot.permissions('a').calibrate, isFalse);
  });

  test('the step list ticks what is done and says why the next steps wait', () {
    final cal = Calibration(id: 1, isValid: true, createdAt: DateTime.utc(2026, 11, 26, 1));
    RobotCommand cmd(CommandKind k, DateTime at) =>
        RobotCommand(id: '$k', robotId: 46, jobId: 276, kind: k, params: const {}, status: CommandStatus.done, createdAt: at, expiresAt: at);
    final none = jobSteps(_detail(282), verified: false);
    expect(none.map((s) => s.key), ['package', 'robot', 'prepare', 'calibrate', 'load', 'real', 'preflight', 'simulate', 'dryRun', 'write', 'finish', 'photos']);
    expect(none.firstWhere((s) => s.key == 'robot').done, isFalse);
    expect(none.firstWhere((s) => s.key == 'prepare').why, 'tw.why.download');

    final preparing = jobSteps(_detail(276, calibration: cal), verified: true, commands: [
      cmd(CommandKind.load, DateTime.utc(2026, 11, 26, 0)), // before the calibration: asked again
      cmd(CommandKind.preflight, DateTime.utc(2026, 11, 26, 2)),
    ]);
    bool done(String k) => preparing.firstWhere((s) => s.key == k).done;
    expect([done('package'), done('robot'), done('prepare'), done('calibrate'), done('load')], [true, true, true, true, false]);
    expect(preparing.firstWhere((s) => s.key == 'real').manual, isTrue);
    expect(preparing.firstWhere((s) => s.key == 'dryRun').why, 'tw.why.simulate');
    expect(preparing.firstWhere((s) => s.key == 'finish').why, 'tw.why.finish');
    expect(realEnableCommand(276), 'real-enable --config agent.json --job 276 --minutes 30');
  });

  test('calibration.json is read like robot_console.py: notes dropped, unmeasured values refused with their paths', () {
    final body = readCalibrationFile('﻿{"_help":"x","checklist":{"frame_mounted":true,"_n":"y"},"force_zero_offset":0.2,'
        '"probe_points":[{"x":1,"y":2,"z":3}],"frame_transform":{"_note":"z","motion":{"a":1}}}');
    expect(body.containsKey('_help'), isFalse);
    expect(body['checklist'], {'frame_mounted': true});
    expect(body['frame_transform'], {'motion': {'a': 1}});
    expect(
      () => readCalibrationFile('{"checklist":{},"force_zero_offset":0,"probe_points":[{"x":"<P0 x>","y":null,"z":1}]}'),
      throwsA(isA<CalibrationFileError>().having((e) => e.paths, 'paths', ['probe_points[0].x', 'probe_points[0].y'])),
    );
    expect(() => readCalibrationFile('not json'), throwsA(isA<CalibrationFileError>().having((e) => e.key, 'key', 'td.cal.notJson')));
    expect(() => readCalibrationFile('{"checklist":{}}'), throwsA(isA<CalibrationFileError>().having((e) => e.key, 'key', 'td.cal.shape')));
    expect(probePlaneValid([(x: 0, y: 0, z: 0), (x: 100, y: 0, z: 0), (x: 0, y: 100, z: 0)]), isTrue);
    expect(probePlaneValid([(x: 0, y: 0, z: 0), (x: 50, y: 0, z: 0), (x: 100, y: 0, z: 0)]), isFalse);
  });

  test('times read on the workshop clock, and API errors translate', () {
    const t = T(Lang.en);
    expect(jobStamp(t, DateTime.utc(2026, 10, 23, 7, 50)), '14:50 23/10');
    expect(techErrorText(t, const ConflictException('x', 'JOB_NOT_ACTIVE')), 'This job is no longer active.');
    expect(techErrorText(t, const ConflictException('Lỗi lạ', 'SOME_NEW_CODE')), 'Lỗi lạ');
    expect(techErrorText(t, const ServerException('x', 500)), 'The server had a problem. Try again later.');
  });

  test('a PAUSED job calibrated again is stale until a new simulation is recorded', () {
    JobEvent e(int id, String type) => JobEvent(id: id, eventType: type, occurredAt: DateTime.utc(2026, 11, 26, 0, id));
    // Latest first, as TechApi.allEvents returns them.
    expect(simulationStale([e(3, 'CALIBRATED'), e(2, 'PAUSE'), e(1, 'SIMULATED')]), isTrue);
    expect(simulationStale([e(4, 'SIMULATED'), e(3, 'CALIBRATED'), e(1, 'SIMULATED')]), isFalse);
    expect(simulationStale([e(2, 'PROGRESS')]), isFalse);
  });

  test('the simulation can be recorded while PAUSED, as the backend allows after a recalibration', () {
    TechJobDetail paused(JobStatus s) => TechJobDetail(
          job: TechJob(
            id: 1, orderId: 2, orderCode: 'V', robotId: 46, robotCode: 'R', technicianId: 4, technicianName: 'T', status: s,
            isRewrite: false, slotStart: DateTime.utc(2026), slotEnd: DateTime.utc(2026), durationMin: 5, packageHash: 'abc',
            downloadedAt: DateTime.utc(2026), simulationPassed: true,
          ),
          orderType: 'OT3_TEMPLATE', quantity: 1, canStart: false, incidents: const [],
          calibration: Calibration(id: 9, isValid: true, createdAt: DateTime.utc(2026)),
        );
    expect(paused(JobStatus.paused).permissions('abc').simulate, isTrue);
    expect(paused(JobStatus.preparing).permissions('abc').simulate, isTrue);
    expect(paused(JobStatus.writing).permissions('abc').simulate, isFalse);
    expect(paused(JobStatus.paused).permissions('other').simulate, isFalse);
  });
}

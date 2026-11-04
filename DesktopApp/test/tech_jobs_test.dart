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
import 'package:ai_vhrs_mobile/features/tech/domain/job.dart';
import 'package:ai_vhrs_mobile/features/tech/domain/robot.dart';
import 'package:ai_vhrs_mobile/features/tech/i18n/tech_strings.dart';
import 'package:ai_vhrs_mobile/features/tech/presentation/screens/job_detail_screen.dart';
import 'package:ai_vhrs_mobile/features/tech/presentation/screens/jobs_screen.dart';
import 'package:ai_vhrs_mobile/features/tech/presentation/screens/tech_dashboard_screen.dart';
import 'package:ai_vhrs_mobile/features/tech/presentation/widgets/job_widgets.dart';
import 'package:ai_vhrs_mobile/features/tech/presentation/widgets/tech_shell.dart';

TechJob _job(int id, JobStatus status, {int minutes = 25, bool rewrite = false}) => TechJob(
      id: id,
      orderId: id + 1000,
      orderCode: 'VHRS-$id',
      robotId: 46,
      robotCode: 'FR3-01',
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
];

TechJobDetail _detail(int id) => TechJobDetail(
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

Future<GoRouter> _pump(
  WidgetTester tester,
  Size size,
  String start, {
  Stream<List<TechJob>>? jobs,
  List<RobotStatus> status = const [_danger],
  Stream<TechJobDetail> Function(int id)? detail,
  String lang = 'en',
}) async {
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
            builder: (_, s) => JobsScreen(filter: JobFilter.parse(s.uri.queryParameters['filter'])),
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
      techJobsProvider.overrideWith((ref) => jobs ?? Stream.value(_jobs)),
      robotStatusProvider.overrideWith((ref) => Stream.value(status)),
      techJobProvider.overrideWith((ref, id) => detail?.call(id) ?? Stream.value(_detail(id))),
      jobEventsProvider.overrideWith((ref, id) async => const []),
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
      expect(find.text('6 assigned'), findsOneWidget);
      // 25 + 30 + 40 minutes wait to start; the groups with no jobs are not shown.
      expect(find.text('95 min'), findsOneWidget);
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
      expect(find.text('In progress · 3'), findsOneWidget);
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
        expect(find.text('Materials and instructions'), findsNothing);
        await tester.tap(find.text('VHRS-279'));
        await tester.pumpAndSettle();
        expect(router.routerDelegate.currentConfiguration.uri.toString(), '/tech/jobs/279?filter=history');
        expect(find.text('Job for VHRS-279'), findsOneWidget);
        expect(find.text('Materials and instructions'), findsOneWidget);
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

  test('times read on the workshop clock, and API errors translate', () {
    const t = T(Lang.en);
    expect(jobStamp(t, DateTime.utc(2026, 10, 23, 7, 50)), '14:50 23/10');
    expect(techErrorText(t, const ConflictException('x', 'JOB_NOT_ACTIVE')), 'This job is no longer active.');
    expect(techErrorText(t, const ConflictException('Lỗi lạ', 'SOME_NEW_CODE')), 'Lỗi lạ');
    expect(techErrorText(t, const ServerException('x', 500)), 'The server had a problem. Try again later.');
  });
}

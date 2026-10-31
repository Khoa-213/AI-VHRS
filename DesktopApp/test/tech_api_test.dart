import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:dio/dio.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ai_vhrs_mobile/core/network/dio_client.dart';
import 'package:ai_vhrs_mobile/core/network/network_exceptions.dart';
import 'package:ai_vhrs_mobile/core/storage/secure_storage_service.dart';
import 'package:ai_vhrs_mobile/features/tech/data/providers.dart';
import 'package:ai_vhrs_mobile/features/tech/data/tech_api.dart';
import 'package:ai_vhrs_mobile/features/tech/domain/job.dart';
import 'package:ai_vhrs_mobile/features/tech/domain/robot.dart';

typedef Reply = ({int status, Object? body, Map<String, List<String>>? headers});

Reply _ok(Object? body) => (status: 200, body: body, headers: null);
Reply _err(int status, String code, [Map<String, List<String>>? headers]) => (
      status: status,
      body: {
        'error': {'code': code, 'message': code, 'details': null},
      },
      headers: headers,
    );

/// Answers from a route table and records what was sent.
class FakeApi implements HttpClientAdapter {
  final Reply Function(RequestOptions o) handler;
  final requests = <RequestOptions>[];
  final bodies = <List<int>>[];
  FakeApi(this.handler);

  @override
  Future<ResponseBody> fetch(RequestOptions o, Stream<Uint8List>? body, Future<void>? cancel) async {
    requests.add(o);
    if (body != null) bodies.add([await for (final chunk in body) ...chunk]);
    final r = handler(o);
    final raw = r.body;
    if (raw is List<int>) {
      return ResponseBody.fromBytes(raw, r.status, headers: r.headers ?? {});
    }
    return ResponseBody.fromString(
      raw == null ? '' : jsonEncode(raw),
      r.status,
      headers: {
        Headers.contentTypeHeader: ['application/json'],
        ...?r.headers,
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

Map<String, dynamic> _job({int id = 276, String status = 'PREPARING', String? hash = 'abc'}) => {
      'id': id,
      'order_id': 9,
      'order_code': 'VHRS-SEED02',
      'robot_id': 46,
      'robot_code': 'FR3-01',
      'technician_id': 4,
      'technician_name': 'Technical Staff',
      'status': status,
      'is_rewrite': false,
      'slot_start': '2026-10-23T14:50:00Z',
      'slot_end': '2026-10-23T15:15:00Z',
      'estimated_duration_min': 25,
      'package_hash': hash,
      'progress_pct': 42.5,
      'downloaded_at': '2026-10-23T14:40:00Z',
      'started_at': null,
      'finished_at': null,
      'simulation_passed': true,
    };

Map<String, dynamic> _detail({String status = 'PREPARING', bool calibrated = true}) => {
      ..._job(status: status),
      'order_type': 'LETTER',
      'quantity': 2,
      'eta': '2026-10-30',
      'paper_name': 'A5',
      'pen_name': 'Ballpoint',
      'ink_name': 'Black',
      'approach_note': null,
      'can_start': true,
      'calibration': {
        'id': 1,
        'job_id': 276,
        'robot_id': 46,
        'technician_id': 4,
        'checklist': null,
        'force_zero_offset': 0.2,
        'probe_points': [],
        'frame_transform': null,
        'height_map': null,
        'force_curve': null,
        'is_valid': calibrated,
        'created_at': '2026-10-23T14:45:00Z',
      },
      'incidents': [
        {'id': 5, 'type': 'ROBOT', 'description': 'x', 'resolved_at': null, 'created_at': '2026-10-23T15:00:00Z'},
      ],
    };

Map<String, dynamic> _command({String status = 'PENDING'}) => {
      'id': 'c-1',
      'robot_id': 46,
      'job_id': 276,
      'kind': 'LOAD',
      'params': <String, dynamic>{},
      'status': status,
      'result': null,
      'error_code': null,
      'error_message': null,
      'created_at': '2026-10-23T15:00:00Z',
      'expires_at': '2026-10-23T15:01:00Z',
      'delivered_at': null,
      'finished_at': null,
    };

Map<String, dynamic> _statusRow() => {
      'robot_id': 46,
      'robot_code': 'FR3-01',
      'state': 'DANGER',
      'headline_vi': 'Nguy hiểm',
      'level': 4,
      'mode': 'REAL',
      'connection_state': 'OFFLINE',
      'last_seen_at': null,
      'job_id': 276,
      'job_status': 'PREPARING',
      'open_run': {'run_id': 7, 'mode': 'REAL', 'dry_run': false, 'completed_strokes': 15, 'total_strokes': 35},
      'open_alerts': [
        {
          'id': 1,
          'robot_id': 46,
          'job_id': null,
          'code': 'CONTROLLER_SAFETY_FAULT',
          'level': 4,
          'title_vi': 'Lỗi an toàn',
          'action_vi': 'Bấm E-Stop',
          'estop_advised': true,
          'occurrences': 3,
          'raised_at': '2026-10-23T13:23:00Z',
          'acknowledged_at': null,
        },
      ],
      'calibration_age_minutes': 12,
    };

({ProviderContainer c, FakeApi api, FakeApi store}) _setup(
  Reply Function(RequestOptions o) routes, {
  Reply Function(RequestOptions o)? storage,
}) {
  final api = FakeApi(routes);
  final store = FakeApi(storage ?? (_) => _err(404, 'NO_STORAGE'));
  final bare = Dio()..httpClientAdapter = store;
  final c = ProviderContainer(overrides: [
    secureStorageProvider.overrideWithValue(SecureStorageService()),
    storageDioProvider.overrideWithValue(bare),
  ]);
  c.read(dioClientProvider).dio.httpClientAdapter = api;
  addTearDown(c.dispose);
  return (c: c, api: api, store: store);
}

Reply _route(RequestOptions o, Map<String, Reply> table) =>
    table['${o.method} ${o.path}'] ?? _err(404, 'NO_ROUTE ${o.method} ${o.path}');

List<int> _trajectory({String format = 'vhrs-1', int pages = 1}) => utf8.encode(jsonEncode({
      'format': format,
      'pages': [
        for (var i = 0; i < pages; i++)
          {
            'paper': {'width_mm': 148, 'height_mm': 210},
            'strokes': [
              {
                'points': [
                  [1, 2, 0.5],
                  [3.5, 4],
                ],
              },
            ],
          },
      ],
    }));

Map<String, dynamic> _package(String hash) => {
      'job_id': 276,
      'order_code': 'VHRS-SEED02',
      'package_hash': hash,
      'trajectory_url': 'https://storage.example/t.json?sig=1',
      'trajectory_url_expires_in': 300,
      'trajectory_format': 'vhrs-1',
      'pages': 1,
      'paper': {'name': 'A5', 'size': 'A5', 'gsm': 100, 'surface': 'smooth'},
      'pen': {'name': 'Ball', 'f_target_n': 1, 'f_min_n': 0.5, 'f_max_n': 2, 'f_hard_n': 3, 'v_max_mm_s': 80},
      'preview_url': null,
    };

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => FlutterSecureStorage.setMockInitialValues({}));

  group('models', () {
    test('job detail parses, an unknown status does not throw', () {
      final d = TechJobDetail.fromJson(_detail());
      expect(d.job.status, JobStatus.preparing);
      expect(d.job.progress, 42.5);
      expect(d.calibration?.isValid, true);
      expect(d.incidents.single.type, 'ROBOT');
      expect(d.eta, DateTime.parse('2026-10-30'));
      expect(TechJob.fromJson(_job(status: 'BRAND_NEW')).status, JobStatus.unknown);
    });

    test('robot status keeps alerts and the E-Stop flag', () {
      final s = RobotStatus.fromJson(_statusRow());
      expect(s.state, RobotHealth.danger);
      expect(s.openRun?.runId, '7');
      expect(s.alerts.single.estopAdvised, true);
      expect(s.alerts.single.acknowledgedAt, isNull);
    });

    test('an unknown command status counts as final', () {
      expect(CommandStatus.parse('NEW').isFinal, true);
      expect(CommandStatus.pending.isFinal, false);
      expect(CommandStatus.delivered.isFinal, false);
      expect(CommandStatus.done.isFinal, true);
    });

    test('permissions need the verified hash', () {
      final d = TechJobDetail.fromJson(_detail());
      expect(d.permissions().start, false);
      expect(d.permissions('other').simulate, false);
      expect(d.permissions('abc').start, true);
      expect(d.permissions('abc').simulate, true);
      expect(d.permissions('abc').finish, false);
      expect(TechJobDetail.fromJson(_detail(calibrated: false)).permissions('abc').start, false);
      expect(TechJobDetail.fromJson(_detail(status: 'WRITING')).permissions().finish, true);
      expect(TechJobDetail.fromJson(_detail(status: 'BRAND_NEW')).permissions('abc').download, false);
    });

    test('events follow the job status', () {
      expect(ClientEvent.pause.allowedIn(JobStatus.writing), true);
      expect(ClientEvent.pause.allowedIn(JobStatus.paused), false);
      expect(ClientEvent.resume.allowedIn(JobStatus.paused), true);
      expect(ClientEvent.forceSummary.allowedIn(JobStatus.written), true);
      expect(ClientEvent.estop.allowedIn(JobStatus.written), false);
    });

    test('photos ready needs both kinds, all passed', () {
      ProductPhoto p(PhotoKind k, QcResult? r) =>
          ProductPhoto(id: 1, kind: k, qcResult: r, urlExpiresIn: 0, createdAt: DateTime(2026));
      expect(photosReady([p(PhotoKind.overall, QcResult.pass)]), false);
      expect(photosReady([p(PhotoKind.overall, QcResult.pass), p(PhotoKind.other, QcResult.pass)]), false);
      expect(photosReady([p(PhotoKind.overall, QcResult.pass), p(PhotoKind.closeUp, null)]), false);
      expect(photosReady([p(PhotoKind.overall, QcResult.pass), p(PhotoKind.closeUp, QcResult.pass)]), true);
    });
  });

  group('TechApi', () {
    test('allJobs reads every page', () async {
      final s = _setup((o) {
        final page = o.queryParameters['page'] as int;
        expect(o.path, '/technician/jobs');
        expect(o.queryParameters['page_size'], 200);
        return _ok({
          'items': [_job(id: page)],
          'total': 201,
          'page': page,
          'page_size': 200,
        });
      });
      final jobs = await s.c.read(techApiProvider).allJobs();
      expect(jobs.map((j) => j.id), [1, 2]);
      expect(s.api.requests, hasLength(2));
    });

    test('a package is verified before it is parsed, without the bearer token', () async {
      final bytes = _trajectory();
      final hash = sha256.convert(bytes).toString();
      final s = _setup(
        (o) => _route(o, {'GET /technician/jobs/276/package': _ok(_package(hash.toUpperCase()))}),
        storage: (_) => _ok(bytes),
      );
      final v = await s.c.read(techApiProvider).downloadPackage(276);
      expect(v.hash, hash);
      expect(v.pages.single.widthMm, 148);
      expect(v.pages.single.strokes.single.first, [1, 2, 0.5]);
      expect(s.store.requests.single.headers.containsKey('Authorization'), false);
      expect(s.store.requests.single.uri.toString(), 'https://storage.example/t.json?sig=1');
    });

    test('a wrong hash fails', () async {
      final s = _setup(
        (o) => _route(o, {'GET /technician/jobs/276/package': _ok(_package('00'))}),
        storage: (_) => _ok(_trajectory()),
      );
      await expectLater(
        s.c.read(techApiProvider).downloadPackage(276),
        throwsA(isA<ConflictException>().having((e) => e.code, 'code', 'JOB_HASH_MISMATCH')),
      );
    });

    test('a package off the expected shape is refused', () {
      final info = JobPackage.fromJson(_package('x'));
      Matcher invalid = throwsA(isA<TechFlowError>().having((e) => e.key, 'key', 'td.flow.invalidPackage'));
      expect(() => parseTrajectory(utf8.encode('not json'), info), invalid);
      expect(() => parseTrajectory(_trajectory(format: 'other'), info), invalid);
      expect(() => parseTrajectory(_trajectory(pages: 2), info), invalid);
      expect(
        () => parseTrajectory(
            utf8.encode(jsonEncode({
              'format': 'vhrs-1',
              'pages': [
                {
                  'paper': {'width_mm': 148, 'height_mm': 0},
                  'strokes': [],
                },
              ],
            })),
            info),
        invalid,
      );
      expect(
        () => parseTrajectory(
            utf8.encode(jsonEncode({
              'format': 'vhrs-1',
              'pages': [
                {
                  'paper': {'width_mm': 148, 'height_mm': 210},
                  'strokes': [
                    {
                      'points': [
                        [1],
                      ],
                    },
                  ],
                },
              ],
            })),
            info),
        invalid,
      );
    });

    test('a failed download is a translated error', () async {
      final s = _setup(
        (o) => _route(o, {'GET /technician/jobs/276/package': _ok(_package('00'))}),
        storage: (_) => _err(403, 'EXPIRED'),
      );
      await expectLater(
        s.c.read(techApiProvider).downloadPackage(276),
        throwsA(isA<TechFlowError>().having((e) => e.key, 'key', 'td.flow.downloadFailed')),
      );
    });

    test('photo upload sends the raw bytes with the ticket method and type, no token', () async {
      final s = _setup((_) => _err(404, 'X'), storage: (_) => _ok(null));
      final percents = <int>[];
      await s.c.read(techApiProvider).uploadPhotoBinary(
            const PhotoTicket(photoKey: 'k', uploadUrl: 'https://storage.example/up', method: 'PUT', expiresIn: 60),
            Uint8List.fromList([1, 2, 3, 4]),
            mimeType: 'image/jpeg',
            onProgress: percents.add,
          );
      final o = s.store.requests.single;
      expect(o.method, 'PUT');
      expect(o.contentType, 'image/jpeg');
      expect(o.headers.containsKey('Authorization'), false);
      expect(s.store.bodies.single, [1, 2, 3, 4]);
    });

    test('a failed upload is a translated error', () async {
      final s = _setup((_) => _err(404, 'X'), storage: (_) => _err(500, 'BOOM'));
      await expectLater(
        s.c.read(techApiProvider).uploadPhotoBinary(
              const PhotoTicket(photoKey: 'k', uploadUrl: 'https://storage.example/up', method: 'PUT', expiresIn: 60),
              Uint8List(1),
              mimeType: 'image/png',
            ),
        throwsA(isA<TechFlowError>().having((e) => e.key, 'key', 'td.flow.uploadFailed')),
      );
    });

    test('after a 429 it does not ask again inside the Retry-After window', () async {
      final s = _setup((_) => _err(429, 'RATE_LIMITED', {
            'retry-after': ['60'],
          }));
      final api = s.c.read(techApiProvider);
      await expectLater(api.getJob(1), throwsA(isA<TooManyAttemptsException>()));
      await expectLater(api.getJob(1), throwsA(isA<TooManyAttemptsException>()));
      expect(s.api.requests, hasLength(1));
    });

    test('events come back latest first across pages', () async {
      Map<String, dynamic> e(int id, String at) =>
          {'id': id, 'event_type': 'PROGRESS', 'occurred_at': at, 'stroke_index': null, 'force_summary': null, 'payload': null};
      final s = _setup((o) => _ok({
            'items': o.queryParameters['page'] == 1
                ? [e(1, '2026-10-23T10:00:00Z')]
                : [e(2, '2026-10-23T11:00:00Z'), e(3, '2026-10-23T11:00:00Z')],
            'total': 501,
            'page': o.queryParameters['page'],
            'page_size': 500,
          }));
      final events = await s.c.read(techApiProvider).allEvents(276);
      expect(events.map((x) => x.id), [3, 2, 1]);
    });

    test('an action posts to its path and an event carries its code', () async {
      Object? sent;
      final s = _setup((o) {
        sent = o.data;
        return _route(o, {
          'POST /technician/jobs/276/photos/submit': _ok(_job(status: 'PHOTO_UPLOADED')),
          'POST /technician/jobs/276/events': _ok({
            'id': 1,
            'event_type': 'ESTOP',
            'occurred_at': '2026-10-23T11:00:00Z',
            'stroke_index': null,
            'force_summary': null,
            'payload': null,
          }),
        });
      });
      final api = s.c.read(techApiProvider);
      expect((await api.submitPhotos(276)).status, JobStatus.photoUploaded);
      await api.postEvent(276, ClientEvent.estop);
      expect(sent, {'event_type': 'ESTOP'});
    });
  });

  group('RobotApi', () {
    test('each press gets its own idempotency key', () async {
      final keys = <String>[];
      final s = _setup((o) {
        keys.add((o.data as Map)['idempotency_key'] as String);
        return _ok(_command());
      });
      final api = s.c.read(robotApiProvider);
      await api.sendCommand(CommandKind.load, jobId: 276);
      await api.sendCommand(CommandKind.load, jobId: 276);
      expect(keys.toSet(), hasLength(2));
      expect(keys.first, matches(RegExp(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')));
      expect((s.api.requests.first.data as Map)['kind'], 'LOAD');
    });

    test('waitCommand rides out a 500 and stops at a final status', () async {
      final answers = [_err(500, 'BOOM'), _ok(_command(status: 'DELIVERED')), _ok(_command(status: 'DONE'))];
      final s = _setup((_) => answers.removeAt(0));
      final api = s.c.read(robotApiProvider);
      final seen = <CommandStatus>[];
      final done = await api.waitCommand(
        RobotCommand.fromJson(_command()),
        onUpdate: (c) => seen.add(c.status),
        every: Duration.zero,
      );
      expect(done.status, CommandStatus.done);
      expect(seen, [CommandStatus.delivered, CommandStatus.done]);
    });

    test('waitCommand throws on a refusal and stops when cancelled', () async {
      final s = _setup((_) => _err(403, 'NOT_YOURS'));
      final api = s.c.read(robotApiProvider);
      final cmd = RobotCommand.fromJson(_command());
      await expectLater(api.waitCommand(cmd, every: Duration.zero), throwsA(isA<ForbiddenException>()));
      final calls = s.api.requests.length;
      expect((await api.waitCommand(cmd, every: Duration.zero, cancelled: () => true)).status, CommandStatus.pending);
      expect(s.api.requests, hasLength(calls));
    });

    test('the view ticket URL is on the backend origin, not the API path', () async {
      final s = _setup((_) => _ok({'ticket': 't', 'expires_in': 600, 'viewer_path': '/viewer/robot.html?ticket=t'}));
      final t = await s.c.read(robotApiProvider).viewTicket(46);
      expect(t.url, 'https://ai-vhrs.onrender.com/viewer/robot.html?ticket=t');
    });
  });

  group('providers', () {
    Future<void> settle() => Future<void>.delayed(const Duration(milliseconds: 20));

    test('robot status is one poll however many views watch it', () async {
      final s = _setup((_) => _ok([_statusRow()]));
      final a = s.c.listen(robotStatusProvider, (_, _) {});
      final b = s.c.listen(robotStatusProvider, (_, _) {});
      await settle();
      expect(a.read().value?.single.robotCode, 'FR3-01');
      expect(b.read().value?.single.robotCode, 'FR3-01');
      expect(s.api.requests, hasLength(1));
    });

    test('live resumes after the last frame and resets when the server restarted', () async {
      Map<String, dynamic> live(int lastSeq, List<Map<String, dynamic>> frames) => {
            'robot_id': 46,
            'robot_code': 'FR3-01',
            'agent_online': true,
            'age_s': 0.5,
            'mode': 'REAL',
            'status': {'busy': true},
            'last_seq': lastSeq,
            'frames': frames,
          };
      final answers = [
        live(5, [
          {'seq': 5, 'progress_pct': 40},
        ]),
        live(5, []),
        live(1, []),
        live(1, []),
      ];
      final s = _setup((_) => _ok(answers.length > 1 ? answers.removeAt(0) : answers.first));
      final sub = s.c.listen(robotLiveProvider(46), (_, _) {});
      await Future<void>.delayed(const Duration(milliseconds: 900));
      final after = [for (final r in s.api.requests) r.queryParameters['after']];
      expect(after.take(4), [0, 5, 5, 0]);
      // A later answer with no frames keeps showing the last frame.
      expect(sub.read().value?.frame?.seq, 5);
    });

    test('a job that is not running asks once per 30 seconds, and stops on a 404', () async {
      final s = _setup((_) => _ok(_detail()));
      s.c.listen(techJobProvider(276), (_, _) {});
      await settle();
      expect(s.api.requests, hasLength(1));

      final gone = _setup((_) => _err(404, 'JOB_NOT_FOUND'));
      final sub = gone.c.listen(techJobProvider(276), (_, _) {});
      await settle();
      expect(sub.read().error, isA<NotFoundException>());
      expect(gone.api.requests, hasLength(1));
    });

    test('an error keeps the last data', () async {
      final answers = [_ok([_statusRow()]), _err(500, 'BOOM')];
      final s = _setup((_) => answers.length > 1 ? answers.removeAt(0) : answers.first);
      final sub = s.c.listen(robotStatusProvider, (_, _) {});
      await Future<void>.delayed(const Duration(milliseconds: 2100));
      expect(sub.read().hasError, true);
      expect(sub.read().value?.single.robotCode, 'FR3-01');
    });

    test('polling parks while the app is hidden, not when it only lost focus', () async {
      final binding = TestWidgetsFlutterBinding.instance;
      final s = _setup((_) => _ok([_statusRow()]));
      s.c.read(appVisibleProvider);
      binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      expect(s.c.read(appVisibleProvider), true);

      binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
      expect(s.c.read(appVisibleProvider), false);
      s.c.listen(robotStatusProvider, (_, _) {});
      await settle();
      expect(s.api.requests, isEmpty);

      binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      await settle();
      expect(s.api.requests, hasLength(1));
      binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    });
  });
}

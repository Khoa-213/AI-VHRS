import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:ai_vhrs_mobile/features/tech/data/agent_process.dart';

/// A stand-in for the Python agent: lines on stdout, an exit when stdin closes (as `--stop-on-stdin-eof` does).
class _FakeProcess implements Process {
  final _out = StreamController<List<int>>();
  final _err = StreamController<List<int>>();
  final _exit = Completer<int>();
  final _stdin = _FakeStdin();
  final bool exitOnStdinClose;
  bool killed = false;

  _FakeProcess({this.exitOnStdinClose = true}) {
    _stdin.closed.then((_) {
      if (exitOnStdinClose) finish(0);
    });
  }

  void say(String line) => _out.add(utf8.encode('$line\n'));
  void finish(int code) {
    if (!_exit.isCompleted) {
      _out.close();
      _err.close();
      _exit.complete(code);
    }
  }

  @override
  Stream<List<int>> get stdout => _out.stream;
  @override
  Stream<List<int>> get stderr => _err.stream;
  @override
  IOSink get stdin => _stdin;
  @override
  Future<int> get exitCode => _exit.future;
  @override
  int get pid => 4242;
  @override
  bool kill([ProcessSignal signal = ProcessSignal.sigterm]) {
    killed = true;
    finish(-9);
    return true;
  }
}

class _FakeStdin implements IOSink {
  final _closed = Completer<void>();
  final lines = <String>[];
  Future<void> get closed => _closed.future;
  @override
  void writeln([Object? object = '']) => lines.add('$object');
  @override
  Future<void> flush() async {}
  @override
  Future<void> close() async {
    if (!_closed.isCompleted) _closed.complete();
  }

  @override
  dynamic noSuchMethod(Invocation i) => null;
}

void main() {
  late Directory dir;

  setUp(() {
    dir = Directory.systemTemp.createTempSync('agent-test');
    File('${dir.path}/agent.json').writeAsStringSync(jsonEncode({
      'backend_url': 'https://ai-vhrs.onrender.com',
      'robot_id': 46,
      'modes': ['mock', 'sim', 'real'],
      'fairino': {'ip': '192.168.58.2'},
    }));
    Directory('${dir.path}/.simenv').createSync();
    File('${dir.path}/.simenv/python.exe').writeAsStringSync('');
  });
  tearDown(() => dir.deleteSync(recursive: true));

  test('finds robot_agent by walking up from the app folder, and reads agent.json', () {
    final app = Directory('${dir.path}/x/robot_agent')..createSync(recursive: true);
    File('${app.path}/agent.json').writeAsStringSync('{"robot_id": 7}');
    final deep = Directory('${dir.path}/x/DesktopApp/build/windows/x64/runner/Debug')..createSync(recursive: true);
    expect(File('${findAgentDir(starts: [deep.path])}/agent.json').readAsStringSync(), '{"robot_id": 7}');
    expect(findAgentDir(starts: [Directory.systemTemp.createTempSync('none').path]), isNull);
    final info = AgentInfo.read(dir.path)!;
    expect(info.robotId, 46);
    expect(info.robotIp, '192.168.58.2');
    expect(info.modes, ['mock', 'sim', 'real']);
    expect(info.backendMismatch, isFalse);
  });

  test('no agent.json: not found, Start does nothing', () async {
    final c = AgentController(dir: '${dir.path}/missing');
    expect(c.state.phase, AgentPhase.notFound);
    await c.start(email: 'a', password: 'b');
    expect(c.state.phase, AgentPhase.notFound);
  });

  test('starts with the account in the environment only, runs once linked and the screen answers, stops through stdin', () async {
    final p = _FakeProcess();
    late Map<String, String> env;
    late List<String> args;
    var screenUp = false;
    final c = AgentController(
      dir: dir.path,
      starter: (exe, a, wd, e) async {
        args = a;
        env = e;
        expect(wd, dir.path);
        return p;
      },
      probe: (_) async => screenUp,
    );
    await c.start(email: 'tech@netviet.vn', password: 'secret');
    expect(c.state.phase, AgentPhase.starting);
    expect(env['VHRS_TECH_EMAIL'], 'tech@netviet.vn');
    expect(env['VHRS_TECH_PASSWORD'], 'secret');
    expect(env['VHRS_AGENT_KEY'], '');
    expect(env['VHRS_SCREEN_CODE'], hasLength(64));
    expect(c.state.screenCode, env['VHRS_SCREEN_CODE']);
    expect(args, containsAll(['--screen', '--stop-on-stdin-eof', '--host', '127.0.0.1', '--parent-pid', '$pid']));
    expect(args.join(' '), isNot(contains('secret')));
    expect(c.state.log.join('\n'), isNot(contains('secret')));

    p.say('Backend link ON (session of tech@netviet.vn on robot 46); the key renews itself');
    await Future<void>.delayed(const Duration(milliseconds: 50));
    expect(c.state.linked, isTrue);
    screenUp = true;
    await Future<void>.delayed(const Duration(milliseconds: 900));
    expect(c.state.phase, AgentPhase.running);
    expect(c.state.screenReady, isTrue);

    await c.stop();
    await Future<void>.delayed(Duration.zero);
    expect(p._stdin.lines, ['STOP'], reason: 'the app asks with a STOP line');
    expect(p.killed, isFalse, reason: 'the agent stops safely on its own');
    expect(c.state.phase, AgentPhase.stopped);
    c.dispose();
  });

  test('a refused sign-in shows the agent\'s reason and fails', () async {
    final p = _FakeProcess();
    final c = AgentController(dir: dir.path, starter: (_, _, _, _) async => p, probe: (_) async => false);
    await c.start(email: 'staff@gmail.com', password: 'x');
    p.say('Cannot take control of the robot: LOGIN_FAILED: Đăng nhập thất bại');
    p.finish(1);
    await Future<void>.delayed(const Duration(milliseconds: 50));
    expect(c.state.phase, AgentPhase.failed);
    expect(c.state.error, contains('LOGIN_FAILED'));
    c.dispose();
  });

  test('an agent that ignores stdin is killed after the grace period', () async {
    final p = _FakeProcess(exitOnStdinClose: false);
    final c = AgentController(dir: dir.path, starter: (_, _, _, _) async => p, probe: (_) async => false,
        stopGrace: const Duration(milliseconds: 100));
    await c.start(email: 'a', password: 'b');
    await c.stop();
    await Future<void>.delayed(Duration.zero);
    expect(p.killed, isTrue);
    expect(c.state.phase, AgentPhase.stopped);
    c.dispose();
  });

  test('the REAL switch signs in with the run code once, and reads the agent\'s refusal', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final seen = <String>[];
    var logins = 0;
    server.listen((r) async {
      final body = await utf8.decoder.bind(r).join();
      seen.add('${r.method} ${r.uri.path} ${r.headers.value('authorization') ?? '-'}');
      r.response.headers.contentType = ContentType.json;
      if (r.uri.path == '/api/screen-login') {
        logins++;
        expect(jsonDecode(body), {'code': 'c0de'});
        r.response.write(jsonEncode({'access_token': 'tok', 'role': 'TECHNICAL_STAFF', 'name': 'T'}));
      } else if (r.uri.path == '/api/real') {
        r.response.write(jsonEncode({'real_enabled': null}));
      } else if (r.uri.path == '/api/jobs/276/real-enable') {
        expect(jsonDecode(body), {'minutes': 30});
        r.response.statusCode = 502;
        r.response.write(jsonEncode({'error': {'code': 'ROBOT_UNREACHABLE', 'message': 'no answer'}}));
      }
      await r.response.close();
    });
    final api = AgentLocalApi(base: 'http://127.0.0.1:${server.port}/', code: 'c0de');
    expect(await api.realState(), isNull);
    await expectLater(api.realEnable(276), throwsA(isA<AgentApiError>().having((e) => e.code, 'code', 'ROBOT_UNREACHABLE')));
    expect(logins, 1, reason: 'one sign-in for the run');
    expect(seen.where((l) => l.contains('/api/real')).every((l) => l.endsWith('Bearer tok')), isTrue);
    await server.close(force: true);
    await expectLater(api.realState(), throwsA(isA<AgentApiError>().having((e) => e.code, 'code', 'AGENT_UNREACHABLE')));
  });

  test('a controller that does not listen is reported, not thrown', () async {
    final server = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
    expect(await probeController('127.0.0.1', port: server.port), isNull);
    final port = server.port;
    await server.close();
    expect(await probeController('127.0.0.1', port: port, timeout: const Duration(seconds: 1)), isNotNull);
  });
}

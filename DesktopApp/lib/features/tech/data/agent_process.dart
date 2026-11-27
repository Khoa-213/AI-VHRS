import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/constants/api_constants.dart';
import '../../auth/domain/models/auth_state.dart';
import '../../auth/presentation/auth_notifier.dart';

/// The Robot Agent on this workstation, run by the app (owner 2026-11-26: the agent lives inside the desktop app).
///
/// The app starts `robot_agent\.simenv\python.exe -m vhrs_agent.cli serve` with the signed-in technician's
/// account in the environment (never on disk), the workstation screen on 127.0.0.1 only, and a pipe on stdin.
/// A `STOP` line on that pipe (Stop), the pipe closing, or this app's process ending (closed, crashed, killed: the agent
/// watches `--parent-pid`) makes the agent stop any move the normal way, give the robot session back to the backend and
/// exit. A hard kill is the last resort after 40 seconds.
enum AgentPhase { notFound, stopped, starting, running, stopping, failed }

class AgentInfo {
  /// `robot_agent` folder (holds `agent.json` and `.simenv`).
  final String dir;
  final int? robotId;
  final String? robotIp;
  final String? backendUrl;
  final List<String> modes;
  const AgentInfo({required this.dir, this.robotId, this.robotIp, this.backendUrl, this.modes = const []});

  String get python => '$dir${Platform.pathSeparator}.simenv${Platform.pathSeparator}python.exe';

  /// The backend the agent talks to differs from the app's: the robot would show offline in the app.
  bool get backendMismatch {
    final b = backendUrl?.replaceAll(RegExp(r'/+$'), '');
    final app = ApiConstants.baseUrl.replaceAll(RegExp(r'/api/v1/?$'), '').replaceAll(RegExp(r'/+$'), '');
    return b != null && b != app;
  }

  static AgentInfo? read(String dir) {
    final f = File('$dir${Platform.pathSeparator}agent.json');
    if (!f.existsSync()) return null;
    try {
      final j = jsonDecode(f.readAsStringSync()) as Map<String, dynamic>;
      final fairino = j['fairino'];
      return AgentInfo(
        dir: dir,
        robotId: (j['robot_id'] as num?)?.toInt(),
        robotIp: fairino is Map ? fairino['ip'] as String? : null,
        backendUrl: j['backend_url'] as String?,
        modes: [for (final m in (j['modes'] as List? ?? const [])) '$m'],
      );
    } catch (_) {
      return AgentInfo(dir: dir);
    }
  }
}

/// Finds `robot_agent` next to the app: `--dart-define=AGENT_DIR=...`, else walking up from the executable
/// and from the working folder (a debug build runs from `DesktopApp\build\...` inside the repository).
String? findAgentDir({String? override, List<String>? starts}) {
  const defined = String.fromEnvironment('AGENT_DIR');
  final explicit = override ?? (defined.isEmpty ? null : defined);
  if (explicit != null) return File('$explicit${Platform.pathSeparator}agent.json').existsSync() ? explicit : null;
  for (final start in starts ?? [File(Platform.resolvedExecutable).parent.path, Directory.current.path]) {
    var d = Directory(start).absolute;
    for (var i = 0; i < 8; i++) {
      final cand = '${d.path}${Platform.pathSeparator}robot_agent';
      if (File('$cand${Platform.pathSeparator}agent.json').existsSync()) return cand;
      if (d.parent.path == d.path) break;
      d = d.parent;
    }
  }
  return null;
}

class AgentState {
  final AgentPhase phase;
  final AgentInfo? info;

  /// Translation key or the agent's own words (the last line that explains a failure).
  final String? error;
  final List<String> log;

  /// True once the agent holds the robot session on the backend ("Backend link ON").
  final bool linked;

  /// True once the workstation screen answers on [screenUrl].
  final bool screenReady;

  /// Random code for this run of the agent: the app trades it at `POST /api/screen-login` for a session on the agent's own
  /// API as the technician it started the agent as (the REAL switch uses it).
  final String? screenCode;
  const AgentState({
    required this.phase,
    this.info,
    this.error,
    this.log = const [],
    this.linked = false,
    this.screenReady = false,
    this.screenCode,
  });

  static const host = '127.0.0.1';
  static const port = 8765;
  String get screenUrl => 'http://$host:$port/';

  AgentState copyWith({AgentPhase? phase, String? error, bool clearError = false, List<String>? log, bool? linked, bool? screenReady}) =>
      AgentState(
        phase: phase ?? this.phase,
        info: info,
        error: clearError ? null : error ?? this.error,
        log: log ?? this.log,
        linked: linked ?? this.linked,
        screenReady: screenReady ?? this.screenReady,
        screenCode: screenCode,
      );
}

typedef ProcessStarter = Future<Process> Function(String exe, List<String> args, String dir, Map<String, String> env);

Future<Process> _startProcess(String exe, List<String> args, String dir, Map<String, String> env) =>
    Process.start(exe, args, workingDirectory: dir, environment: env);

/// Answers true when the workstation screen is served. Replaced in tests.
typedef ScreenProbe = Future<bool> Function(String url);

Future<bool> _probeScreen(String url) async {
  final client = HttpClient()..connectionTimeout = const Duration(seconds: 2);
  try {
    final r = await (await client.getUrl(Uri.parse(url))).close().timeout(const Duration(seconds: 3));
    await r.drain<void>();
    return r.statusCode == 200;
  } catch (_) {
    return false;
  } finally {
    client.close(force: true);
  }
}

class AgentController extends StateNotifier<AgentState> {
  final ProcessStarter _start;
  final ScreenProbe _probe;
  final Duration stopGrace;
  Process? _proc;
  Timer? _probeTimer;

  AgentController({String? dir, ProcessStarter? starter, ScreenProbe? probe, this.stopGrace = const Duration(seconds: 40)})
      : _start = starter ?? _startProcess,
        _probe = probe ?? _probeScreen,
        super(_initial(dir));

  static AgentState _initial(String? dir) {
    final info = dir == null ? null : AgentInfo.read(dir);
    return info == null
        ? const AgentState(phase: AgentPhase.notFound, error: 'dk.agent.err.notFound')
        : AgentState(phase: AgentPhase.stopped, info: info);
  }

  bool get busy => state.phase == AgentPhase.starting || state.phase == AgentPhase.running || state.phase == AgentPhase.stopping;

  void _line(String l) {
    final s = l.trimRight();
    if (s.isEmpty || !mounted) return;
    final log = [...state.log, s];
    var next = state.copyWith(log: log.length > 400 ? log.sublist(log.length - 400) : log);
    if (s.contains('Backend link ON')) next = next.copyWith(linked: true);
    if (s.contains('Cannot take control') || s.contains('LỖI') || s.contains('Traceback') || s.contains('Error:')) {
      next = next.copyWith(error: s);
    }
    state = next;
  }

  /// Starts the agent as [email]. The password goes to the child's environment only.
  Future<void> start({required String email, required String password}) async {
    final info = state.info;
    if (info == null || busy) return;
    if (!File(info.python).existsSync()) {
      state = state.copyWith(phase: AgentPhase.failed, error: 'dk.agent.err.noPython');
      return;
    }
    final rnd = Random.secure();
    final code = List.generate(32, (_) => rnd.nextInt(256).toRadixString(16).padLeft(2, '0')).join();
    state = AgentState(phase: AgentPhase.starting, info: info, screenCode: code, log: ['> ${info.python} -m vhrs_agent.cli serve ($email)']);
    try {
      final p = await _start(
        info.python,
        ['-X', 'utf8', '-m', 'vhrs_agent.cli', 'serve', '--config', 'agent.json', '--host', AgentState.host, '--port', '${AgentState.port}',
          '--screen', '--stop-on-stdin-eof', '--parent-pid', '$pid'],
        info.dir,
        {
          'VHRS_TECH_EMAIL': email,
          'VHRS_TECH_PASSWORD': password,
          'VHRS_AGENT_KEY': '', // a key left in the shell must not replace this technician's session
          'VHRS_SCREEN_CODE': code, // the app's sign-in to the agent's local API as this technician (POST /api/screen-login)
          'PYTHONUNBUFFERED': '1',
          'PYTHONIOENCODING': 'utf-8',
        },
      );
      _proc = p;
      p.stdout.transform(const Utf8Decoder(allowMalformed: true)).transform(const LineSplitter()).listen(_line);
      p.stderr.transform(const Utf8Decoder(allowMalformed: true)).transform(const LineSplitter()).listen(_line);
      unawaited(p.exitCode.then(_exited));
      _probeTimer = Timer.periodic(const Duration(milliseconds: 700), (_) => _checkScreen());
    } catch (e) {
      state = state.copyWith(phase: AgentPhase.failed, error: '$e');
    }
  }

  Future<void> _checkScreen() async {
    if (!mounted || state.phase != AgentPhase.starting || !state.linked) return;
    if (await _probe(state.screenUrl) && mounted && state.phase == AgentPhase.starting) {
      _probeTimer?.cancel();
      state = state.copyWith(phase: AgentPhase.running, screenReady: true, clearError: true);
    }
  }

  void _exited(int code) {
    _probeTimer?.cancel();
    _proc = null;
    if (!mounted) return;
    final stopping = state.phase == AgentPhase.stopping;
    state = state.copyWith(
      phase: stopping ? AgentPhase.stopped : AgentPhase.failed,
      linked: false,
      screenReady: false,
      error: stopping ? null : state.error ?? 'dk.agent.err.exited',
      clearError: stopping,
      log: [...state.log, '< exit $code'],
    );
  }

  /// Asks the agent to stop the safe way (a STOP line on its stdin), then kills it if it is still there after [stopGrace].
  Future<void> stop() async {
    final p = _proc;
    if (p == null) return;
    state = state.copyWith(phase: AgentPhase.stopping);
    try {
      // A STOP line, not only closing the pipe: on Windows another child of the app may hold the pipe open.
      p.stdin.writeln('STOP');
      await p.stdin.flush();
      await p.stdin.close();
    } catch (_) {}
    final done = await p.exitCode.timeout(stopGrace, onTimeout: () {
      p.kill();
      return -1;
    });
    if (done == -1 && mounted) _line('Agent did not stop in ${stopGrace.inSeconds} s: killed');
  }

  @override
  void dispose() {
    _probeTimer?.cancel();
    // The app is going away: the agent also watches this process id and stops safely on its own.
    try {
      _proc?.stdin.close();
    } catch (_) {}
    super.dispose();
  }
}

final agentControllerProvider = StateNotifierProvider<AgentController, AgentState>((ref) {
  // Under `flutter test` the repository's own robot_agent must not be found (and never started).
  final c = AgentController(dir: Platform.isWindows && !Platform.environment.containsKey('FLUTTER_TEST') ? findAgentDir() : null);
  // The agent runs as the signed-in technician: when that session ends (sign out, expired), it stops the safe way.
  ref.listen<AuthState>(authNotifierProvider, (prev, next) {
    if (prev is AuthAuthenticated && next is! AuthAuthenticated) c.stop();
  });
  return c;
});

/// One read-only step of "Check the robot connection".
enum CheckState { waiting, running, ok, failed, skipped }

class CheckStep {
  final String key;
  final CheckState state;
  final String? detail;
  const CheckStep(this.key, this.state, [this.detail]);
}

/// Opens a TCP connection to the controller's XML-RPC port (20003) and closes it: no SDK call, nothing moves.
Future<String?> probeController(String ip, {int port = 20003, Duration timeout = const Duration(seconds: 3)}) async {
  try {
    final s = await Socket.connect(ip, port, timeout: timeout);
    s.destroy();
    return null;
  } on SocketException catch (e) {
    return e.osError?.message ?? e.message;
  }
}

/// An error from the agent's local API: its `error.code` and message, or AGENT_UNREACHABLE.
class AgentApiError implements Exception {
  final int status;
  final String code;
  final String message;
  const AgentApiError(this.status, this.code, this.message);
  @override
  String toString() => '$code: $message';
}

/// The agent on this computer (127.0.0.1 only), called as the technician the app started it as: the run's code buys a
/// session once (`POST /api/screen-login`). Used for the REAL switch, which on purpose has no backend API.
class AgentLocalApi {
  final String base;
  final String code;
  final HttpClient Function() _client;
  String? _token;
  AgentLocalApi({required this.base, required this.code, HttpClient Function()? client}) : _client = client ?? HttpClient.new;

  Future<Map<String, dynamic>> _send(String method, String path, {Map<String, dynamic>? body, bool auth = true, bool retry = true}) async {
    final c = _client()..connectionTimeout = const Duration(seconds: 3);
    try {
      final req = await c.openUrl(method, Uri.parse('$base${path.substring(1)}'));
      req.headers.contentType = ContentType.json;
      if (auth) req.headers.set('Authorization', 'Bearer ${await _login()}');
      if (body != null) req.write(jsonEncode(body));
      // real-enable checks the real robot first (SDK connect and reads): give it time.
      final res = await req.close().timeout(const Duration(seconds: 60));
      final text = await res.transform(utf8.decoder).join();
      final j = text.isEmpty ? <String, dynamic>{} : jsonDecode(text) as Map<String, dynamic>;
      if (res.statusCode == 401 && auth && retry) {
        _token = null; // the session ended (agent restarted): sign in again once
        return await _send(method, path, body: body, retry: false);
      }
      if (res.statusCode >= 400) {
        final e = j['error'] is Map ? j['error'] as Map : const {};
        throw AgentApiError(res.statusCode, '${e['code'] ?? 'HTTP_${res.statusCode}'}', '${e['message'] ?? text}');
      }
      return j;
    } on SocketException catch (e) {
      throw AgentApiError(0, 'AGENT_UNREACHABLE', e.message);
    } on TimeoutException {
      throw const AgentApiError(0, 'AGENT_UNREACHABLE', 'timeout');
    } finally {
      c.close(force: true);
    }
  }

  Future<String> _login() async =>
      _token ??= (await _send('POST', '/api/screen-login', body: {'code': code}, auth: false))['access_token'] as String;

  /// The REAL switch: `{job_id, expires_at, enabled_by, waive_dry_run}` or null when off or expired.
  Future<Map<String, dynamic>?> realState() async => (await _send('GET', '/api/real'))['real_enabled'] as Map<String, dynamic>?;

  /// Checks the real robot read-only, then allows the real arm for [jobId] for [minutes] (502 ROBOT_UNREACHABLE,
  /// 409 ROBOT_CONFIG_MISMATCH, 409 JOB_NOT_LOADED, 409 AGENT_BUSY otherwise).
  Future<Map<String, dynamic>> realEnable(int jobId, {int minutes = 30}) =>
      _send('POST', '/api/jobs/$jobId/real-enable', body: {'minutes': minutes});

  Future<void> realDisable() => _send('DELETE', '/api/real-enable');
}

/// The local API of the agent this app runs, while it runs; null otherwise (another computer, stopped, tests).
final agentLocalApiProvider = Provider<AgentLocalApi?>((ref) {
  final (phase, code) = ref.watch(agentControllerProvider.select((a) => (a.phase, a.screenCode)));
  if (phase != AgentPhase.running || code == null) return null;
  return AgentLocalApi(base: 'http://${AgentState.host}:${AgentState.port}/', code: code);
});

/// Robot control as the backend sends it (`BE/docs/FE_API_GUIDE.md` 7f and 7g, FE `services/robot.ts`).
library;

enum CommandKind {
  load('LOAD'),
  preflight('PREFLIGHT'),
  dryRun('DRY_RUN'),
  run('RUN'),
  pause('PAUSE'),
  resume('RESUME'),
  stop('STOP'),
  paperChanged('PAPER_CHANGED'),
  identify('IDENTIFY'),
  alignStart('ALIGN_START'),

  /// A kind newer than this build, kept so the command history still lists.
  unknown('UNKNOWN');

  final String code;
  const CommandKind(this.code);

  static CommandKind parse(String? code) => values.firstWhere((k) => k.code == code, orElse: () => unknown);
}

enum CommandStatus {
  pending('PENDING'),
  delivered('DELIVERED'),
  done('DONE'),
  failed('FAILED'),
  expired('EXPIRED'),
  cancelled('CANCELLED'),

  /// Counts as final: a build that does not know the status must not wait on it forever.
  unknown('UNKNOWN');

  final String code;
  const CommandStatus(this.code);

  bool get isFinal => this != pending && this != delivered;

  static CommandStatus parse(String? code) => values.firstWhere((s) => s.code == code, orElse: () => unknown);
}

DateTime? _time(Object? v) => v is String ? DateTime.tryParse(v) : null;
List<double>? _doubles(Object? v) => v is List ? [for (final n in v) (n as num).toDouble()] : null;

class RobotCommand {
  final String id;
  final int robotId;
  final int? jobId;
  final CommandKind kind;
  final Map<String, dynamic> params;
  final CommandStatus status;
  final Map<String, dynamic>? result;
  final String? errorCode;
  final String? errorMessage;
  final DateTime createdAt;
  final DateTime expiresAt;
  final DateTime? finishedAt;

  const RobotCommand({
    required this.id,
    required this.robotId,
    required this.kind,
    required this.params,
    required this.status,
    required this.createdAt,
    required this.expiresAt,
    this.jobId,
    this.result,
    this.errorCode,
    this.errorMessage,
    this.finishedAt,
  });

  factory RobotCommand.fromJson(Map<String, dynamic> j) => RobotCommand(
        id: j['id'] as String,
        robotId: j['robot_id'] as int,
        jobId: j['job_id'] as int?,
        kind: CommandKind.parse(j['kind'] as String?),
        params: j['params'] as Map<String, dynamic>? ?? const {},
        status: CommandStatus.parse(j['status'] as String?),
        result: j['result'] as Map<String, dynamic>?,
        errorCode: j['error_code'] as String?,
        errorMessage: j['error_message'] as String?,
        createdAt: DateTime.parse(j['created_at'] as String),
        expiresAt: DateTime.parse(j['expires_at'] as String),
        finishedAt: _time(j['finished_at']),
      );
}

/// An alert inside a live frame. Its text comes from the backend, in Vietnamese only.
class FrameAlert {
  final String code;
  final int level;
  final String title;
  final String action;
  final bool estopAdvised;
  const FrameAlert({
    required this.code,
    required this.level,
    required this.title,
    required this.action,
    required this.estopAdvised,
  });

  factory FrameAlert.fromJson(Map<String, dynamic> j) => FrameAlert(
        code: j['code'] as String,
        level: j['level'] as int,
        title: j['title_vi'] as String,
        action: j['action_vi'] as String,
        estopAdvised: j['estop_advised'] as bool? ?? false,
      );
}

/// One frame of the agent's live state (joints in degrees, tool position in mm).
class LiveFrame {
  final int seq;
  final String state;
  final String mode;
  final int? jobId;
  final List<double>? tcp;
  final String moveKind;
  final int stroke;
  final int totalStrokes;
  final double progressPct;
  final double? forceN;
  final bool touching;
  final String? fault;
  final String message;
  final List<double>? jointsDeg;
  final int level;
  final List<FrameAlert> alerts;

  const LiveFrame({
    required this.seq,
    required this.state,
    required this.mode,
    required this.moveKind,
    required this.stroke,
    required this.totalStrokes,
    required this.progressPct,
    required this.touching,
    required this.message,
    required this.level,
    required this.alerts,
    this.jobId,
    this.tcp,
    this.forceN,
    this.fault,
    this.jointsDeg,
  });

  factory LiveFrame.fromJson(Map<String, dynamic> j) => LiveFrame(
        seq: j['seq'] as int,
        state: j['state'] as String? ?? '',
        mode: j['mode'] as String? ?? '',
        jobId: j['job_id'] as int?,
        tcp: _doubles(j['tcp']),
        moveKind: j['move_kind'] as String? ?? '',
        stroke: j['stroke'] as int? ?? 0,
        totalStrokes: j['total_strokes'] as int? ?? 0,
        progressPct: (j['progress_pct'] as num?)?.toDouble() ?? 0,
        forceN: (j['force_n'] as num?)?.toDouble(),
        touching: j['touching'] as bool? ?? false,
        fault: j['fault'] as String?,
        message: j['message'] as String? ?? '',
        jointsDeg: _doubles(j['joints_deg']),
        level: j['level'] as int? ?? 0,
        alerts: [
          for (final a in (j['alerts'] as List<dynamic>? ?? const [])) FrameAlert.fromJson(a as Map<String, dynamic>),
        ],
      );
}

/// The agent's own status line. Its nested parts stay as JSON, the console reads what it needs.
class AgentStatus {
  final String? mode;
  final bool busy;
  final String? state;
  final int? level;
  final Map<String, dynamic>? current;
  final Map<String, dynamic>? last;
  final List<String> enabledModes;
  final String? agentVersion;

  const AgentStatus({
    this.mode,
    this.busy = false,
    this.state,
    this.level,
    this.current,
    this.last,
    this.enabledModes = const [],
    this.agentVersion,
  });

  factory AgentStatus.fromJson(Map<String, dynamic> j) => AgentStatus(
        mode: j['mode'] as String?,
        busy: j['busy'] as bool? ?? false,
        state: j['state'] as String?,
        level: j['level'] as int?,
        current: j['current'] as Map<String, dynamic>?,
        last: j['last'] as Map<String, dynamic>?,
        enabledModes: [for (final m in (j['enabled_modes'] as List<dynamic>? ?? const [])) m as String],
        agentVersion: j['agent_version'] as String?,
      );
}

class Live {
  final int robotId;
  final String robotCode;
  final bool online;
  final double? ageS;
  final String? mode;
  final AgentStatus status;
  final int lastSeq;
  final List<LiveFrame> frames;

  const Live({
    required this.robotId,
    required this.robotCode,
    required this.online,
    required this.status,
    required this.lastSeq,
    required this.frames,
    this.ageS,
    this.mode,
  });

  factory Live.fromJson(Map<String, dynamic> j) => Live(
        robotId: j['robot_id'] as int,
        robotCode: j['robot_code'] as String? ?? '',
        online: j['agent_online'] as bool? ?? false,
        ageS: (j['age_s'] as num?)?.toDouble(),
        mode: j['mode'] as String?,
        status: AgentStatus.fromJson(j['status'] as Map<String, dynamic>? ?? const {}),
        lastSeq: j['last_seq'] as int? ?? 0,
        frames: [
          for (final f in (j['frames'] as List<dynamic>? ?? const [])) LiveFrame.fromJson(f as Map<String, dynamic>),
        ],
      );
}

/// The latest answer, plus the last frame seen: most answers carry no new frame.
class LiveView {
  final Live live;
  final LiveFrame? frame;
  const LiveView(this.live, this.frame);
}

class ViewTicket {
  final String url;
  final int expiresIn;
  const ViewTicket({required this.url, required this.expiresIn});
}

class RobotAlert {
  final int id;
  final int robotId;
  final int? jobId;
  final String code;
  final int level;
  final String title;
  final String action;
  final bool estopAdvised;
  final int occurrences;
  final DateTime raisedAt;
  final DateTime? acknowledgedAt;

  const RobotAlert({
    required this.id,
    required this.robotId,
    required this.code,
    required this.level,
    required this.title,
    required this.action,
    required this.estopAdvised,
    required this.occurrences,
    required this.raisedAt,
    this.jobId,
    this.acknowledgedAt,
  });

  factory RobotAlert.fromJson(Map<String, dynamic> j) => RobotAlert(
        id: j['id'] as int,
        robotId: j['robot_id'] as int,
        jobId: j['job_id'] as int?,
        code: j['code'] as String,
        level: j['level'] as int,
        title: j['title_vi'] as String,
        action: j['action_vi'] as String,
        estopAdvised: j['estop_advised'] as bool? ?? false,
        occurrences: j['occurrences'] as int? ?? 1,
        raisedAt: DateTime.parse(j['raised_at'] as String),
        acknowledgedAt: _time(j['acknowledged_at']),
      );
}

enum RobotHealth {
  offline('OFFLINE'),
  idle('IDLE'),
  preparing('PREPARING'),
  writing('WRITING'),
  pausedSafe('PAUSED_SAFE'),
  danger('DANGER'),
  unknown('UNKNOWN');

  final String code;
  const RobotHealth(this.code);

  static RobotHealth parse(String? code) => values.firstWhere((s) => s.code == code, orElse: () => unknown);
}

class OpenRun {
  final String runId;
  final String mode;
  final bool dryRun;
  final int completedStrokes;
  final int totalStrokes;
  const OpenRun({
    required this.runId,
    required this.mode,
    required this.dryRun,
    required this.completedStrokes,
    required this.totalStrokes,
  });

  factory OpenRun.fromJson(Map<String, dynamic> j) => OpenRun(
        runId: '${j['run_id']}',
        mode: j['mode'] as String? ?? '',
        dryRun: j['dry_run'] as bool? ?? false,
        completedStrokes: j['completed_strokes'] as int? ?? 0,
        totalStrokes: j['total_strokes'] as int? ?? 0,
      );
}

class RobotStatus {
  final int robotId;
  final String robotCode;
  final RobotHealth state;

  /// Plain Vietnamese sentence from the backend.
  final String headline;
  final int level;
  final String? mode;
  final String connection;
  final DateTime? lastSeenAt;
  final int? jobId;
  final String? jobStatus;
  final OpenRun? openRun;
  final List<RobotAlert> alerts;
  final int? calibrationAgeMin;

  const RobotStatus({
    required this.robotId,
    required this.robotCode,
    required this.state,
    required this.headline,
    required this.level,
    required this.connection,
    required this.alerts,
    this.mode,
    this.lastSeenAt,
    this.jobId,
    this.jobStatus,
    this.openRun,
    this.calibrationAgeMin,
  });

  factory RobotStatus.fromJson(Map<String, dynamic> j) => RobotStatus(
        robotId: j['robot_id'] as int,
        robotCode: j['robot_code'] as String? ?? '',
        state: RobotHealth.parse(j['state'] as String?),
        headline: j['headline_vi'] as String? ?? '',
        level: j['level'] as int? ?? 0,
        mode: j['mode'] as String?,
        connection: j['connection_state'] as String? ?? '',
        lastSeenAt: _time(j['last_seen_at']),
        jobId: j['job_id'] as int?,
        jobStatus: j['job_status'] as String?,
        openRun: j['open_run'] == null ? null : OpenRun.fromJson(j['open_run'] as Map<String, dynamic>),
        alerts: [
          for (final a in (j['open_alerts'] as List<dynamic>? ?? const [])) RobotAlert.fromJson(a as Map<String, dynamic>),
        ],
        calibrationAgeMin: (j['calibration_age_minutes'] as num?)?.toInt(),
      );
}

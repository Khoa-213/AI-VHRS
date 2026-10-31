/// Technician jobs as the backend sends them (`/technician/jobs`, FE `services/technician.ts`).
library;

import 'dart:typed_data';

enum JobStatus {
  scheduled('SCHEDULED'),
  preparing('PREPARING'),
  writing('WRITING'),
  paused('PAUSED'),
  written('WRITTEN'),
  photoUploaded('PHOTO_UPLOADED'),
  done('DONE'),
  failed('FAILED'),
  rewriteRequired('REWRITE_REQUIRED'),
  cancelled('CANCELLED'),

  /// A status newer than this build. Allows nothing, but the job still lists.
  unknown('UNKNOWN');

  final String code;
  const JobStatus(this.code);

  static JobStatus parse(String? code) =>
      values.firstWhere((s) => s.code == code, orElse: () => unknown);
}

const activeJobStatuses = [
  JobStatus.scheduled,
  JobStatus.preparing,
  JobStatus.writing,
  JobStatus.paused,
  JobStatus.written,
];
const previewJobStatuses = [JobStatus.scheduled, JobStatus.preparing, JobStatus.writing, JobStatus.paused];

DateTime? _time(Object? v) => v is String ? DateTime.tryParse(v) : null;
double? _double(Object? v) => v is num ? v.toDouble() : null;

class TechJob {
  final int id;
  final int orderId;
  final String orderCode;
  final int robotId;
  final String robotCode;
  final int technicianId;
  final String technicianName;
  final JobStatus status;
  final bool isRewrite;
  final DateTime slotStart;
  final DateTime slotEnd;
  final int durationMin;
  final double? progress;
  final DateTime? downloadedAt;
  final DateTime? startedAt;
  final DateTime? finishedAt;
  final bool? simulationPassed;
  final String? packageHash;

  const TechJob({
    required this.id,
    required this.orderId,
    required this.orderCode,
    required this.robotId,
    required this.robotCode,
    required this.technicianId,
    required this.technicianName,
    required this.status,
    required this.isRewrite,
    required this.slotStart,
    required this.slotEnd,
    required this.durationMin,
    this.progress,
    this.downloadedAt,
    this.startedAt,
    this.finishedAt,
    this.simulationPassed,
    this.packageHash,
  });

  factory TechJob.fromJson(Map<String, dynamic> j) => TechJob(
        id: j['id'] as int,
        orderId: j['order_id'] as int,
        orderCode: j['order_code'] as String? ?? '',
        robotId: j['robot_id'] as int,
        robotCode: j['robot_code'] as String? ?? '',
        technicianId: j['technician_id'] as int,
        technicianName: j['technician_name'] as String? ?? '',
        status: JobStatus.parse(j['status'] as String?),
        isRewrite: j['is_rewrite'] as bool? ?? false,
        slotStart: DateTime.parse(j['slot_start'] as String),
        slotEnd: DateTime.parse(j['slot_end'] as String),
        durationMin: j['estimated_duration_min'] as int,
        progress: _double(j['progress_pct']),
        downloadedAt: _time(j['downloaded_at']),
        startedAt: _time(j['started_at']),
        finishedAt: _time(j['finished_at']),
        simulationPassed: j['simulation_passed'] as bool?,
        packageHash: j['package_hash'] as String?,
      );
}

class Calibration {
  final int id;
  final bool isValid;
  final DateTime createdAt;
  final double? forceZeroOffset;

  const Calibration({required this.id, required this.isValid, required this.createdAt, this.forceZeroOffset});

  factory Calibration.fromJson(Map<String, dynamic> j) => Calibration(
        id: j['id'] as int,
        isValid: j['is_valid'] as bool,
        createdAt: DateTime.parse(j['created_at'] as String),
        forceZeroOffset: _double(j['force_zero_offset']),
      );
}

class Incident {
  final int id;
  final String type;
  final String description;
  final DateTime? resolvedAt;
  final DateTime createdAt;

  const Incident({
    required this.id,
    required this.type,
    required this.description,
    required this.createdAt,
    this.resolvedAt,
  });

  factory Incident.fromJson(Map<String, dynamic> j) => Incident(
        id: j['id'] as int,
        type: j['type'] as String,
        description: j['description'] as String,
        resolvedAt: _time(j['resolved_at']),
        createdAt: DateTime.parse(j['created_at'] as String),
      );
}

class TechJobDetail {
  final TechJob job;
  final String orderType;
  final int quantity;
  final DateTime? eta;
  final String? paper;
  final String? pen;
  final String? ink;
  final String? note;
  final bool canStart;
  final Calibration? calibration;
  final List<Incident> incidents;

  const TechJobDetail({
    required this.job,
    required this.orderType,
    required this.quantity,
    required this.canStart,
    required this.incidents,
    this.eta,
    this.paper,
    this.pen,
    this.ink,
    this.note,
    this.calibration,
  });

  factory TechJobDetail.fromJson(Map<String, dynamic> j) => TechJobDetail(
        job: TechJob.fromJson(j),
        orderType: j['order_type'] as String? ?? '',
        quantity: j['quantity'] as int? ?? 1,
        eta: _time(j['eta']),
        paper: j['paper_name'] as String?,
        pen: j['pen_name'] as String?,
        ink: j['ink_name'] as String?,
        note: j['approach_note'] as String?,
        canStart: j['can_start'] as bool? ?? false,
        calibration: j['calibration'] == null ? null : Calibration.fromJson(j['calibration'] as Map<String, dynamic>),
        incidents: [
          for (final i in (j['incidents'] as List<dynamic>? ?? const [])) Incident.fromJson(i as Map<String, dynamic>),
        ],
      );

  /// What the technician may do now. [hash] is the SHA-256 of the package this client verified.
  JobPermissions permissions([String? hash]) {
    final s = job.status;
    final verified = hash != null && job.packageHash != null && hash == job.packageHash;
    final calibrated = calibration?.isValid ?? false;
    return JobPermissions(
      download: previewJobStatuses.contains(s),
      prepare: s == JobStatus.scheduled && verified && job.downloadedAt != null,
      simulate: s == JobStatus.preparing && verified && calibrated,
      start: s == JobStatus.preparing &&
          verified &&
          job.downloadedAt != null &&
          calibrated &&
          job.simulationPassed == true &&
          canStart,
      finish: s == JobStatus.writing,
      incident: s == JobStatus.preparing || s == JobStatus.writing || s == JobStatus.paused,
      photos: s == JobStatus.written,
    );
  }
}

class JobPermissions {
  final bool download, prepare, simulate, start, finish, incident, photos;
  const JobPermissions({
    required this.download,
    required this.prepare,
    required this.simulate,
    required this.start,
    required this.finish,
    required this.incident,
    required this.photos,
  });
}

class JobPage {
  final List<TechJob> items;
  final int total, page, pageSize;
  const JobPage({required this.items, required this.total, required this.page, required this.pageSize});
}

// ─── Package ─────────────────────────────────────────────────────────

class PackagePaper {
  final String name, size;
  final int gsm;
  const PackagePaper({required this.name, required this.size, required this.gsm});

  factory PackagePaper.fromJson(Map<String, dynamic> j) =>
      PackagePaper(name: j['name'] as String, size: j['size'] as String, gsm: j['gsm'] as int);
}

class PackagePen {
  final String name;
  final double fTargetN, fMinN, fMaxN, fHardN, vMaxMmS;
  const PackagePen({
    required this.name,
    required this.fTargetN,
    required this.fMinN,
    required this.fMaxN,
    required this.fHardN,
    required this.vMaxMmS,
  });

  factory PackagePen.fromJson(Map<String, dynamic> j) => PackagePen(
        name: j['name'] as String,
        fTargetN: (j['f_target_n'] as num).toDouble(),
        fMinN: (j['f_min_n'] as num).toDouble(),
        fMaxN: (j['f_max_n'] as num).toDouble(),
        fHardN: (j['f_hard_n'] as num).toDouble(),
        vMaxMmS: (j['v_max_mm_s'] as num).toDouble(),
      );
}

class JobPackage {
  final int jobId;
  final String orderCode, packageHash, trajectoryUrl, trajectoryFormat;
  final int trajectoryUrlExpiresIn, pages;
  final PackagePaper? paper;
  final PackagePen? pen;
  final String? previewUrl;

  const JobPackage({
    required this.jobId,
    required this.orderCode,
    required this.packageHash,
    required this.trajectoryUrl,
    required this.trajectoryFormat,
    required this.trajectoryUrlExpiresIn,
    required this.pages,
    this.paper,
    this.pen,
    this.previewUrl,
  });

  factory JobPackage.fromJson(Map<String, dynamic> j) => JobPackage(
        jobId: j['job_id'] as int,
        orderCode: j['order_code'] as String,
        packageHash: j['package_hash'] as String,
        trajectoryUrl: j['trajectory_url'] as String,
        trajectoryFormat: j['trajectory_format'] as String,
        trajectoryUrlExpiresIn: j['trajectory_url_expires_in'] as int,
        pages: j['pages'] as int,
        paper: j['paper'] == null ? null : PackagePaper.fromJson(j['paper'] as Map<String, dynamic>),
        pen: j['pen'] == null ? null : PackagePen.fromJson(j['pen'] as Map<String, dynamic>),
        previewUrl: j['preview_url'] as String?,
      );
}

class TrajectoryPage {
  final double widthMm, heightMm;

  /// Each stroke is a list of points; a point has at least x and y.
  final List<List<List<double>>> strokes;
  const TrajectoryPage({required this.widthMm, required this.heightMm, required this.strokes});
}

class VerifiedPackage {
  final JobPackage info;
  final Uint8List bytes;
  final List<TrajectoryPage> pages;
  final String hash;
  const VerifiedPackage({required this.info, required this.bytes, required this.pages, required this.hash});
}

// ─── Events ──────────────────────────────────────────────────────────

enum ClientEvent {
  progress('PROGRESS'),
  pause('PAUSE'),
  resume('RESUME'),
  estop('ESTOP'),
  overForce('OVER_FORCE'),
  strokeLost('STROKE_LOST'),
  sensorLost('SENSOR_LOST'),
  forceSummary('FORCE_SUMMARY');

  final String code;
  const ClientEvent(this.code);

  /// Which job status accepts this event.
  bool allowedIn(JobStatus s) => switch (this) {
        progress || pause => s == JobStatus.writing,
        resume => s == JobStatus.paused,
        forceSummary => s == JobStatus.writing || s == JobStatus.paused || s == JobStatus.written,
        _ => s == JobStatus.writing || s == JobStatus.paused,
      };
}

class JobEvent {
  final int id;
  final String eventType;
  final DateTime occurredAt;
  final int? strokeIndex;
  final Map<String, dynamic>? forceSummary;
  final Map<String, dynamic>? payload;

  const JobEvent({
    required this.id,
    required this.eventType,
    required this.occurredAt,
    this.strokeIndex,
    this.forceSummary,
    this.payload,
  });

  factory JobEvent.fromJson(Map<String, dynamic> j) => JobEvent(
        id: j['id'] as int,
        eventType: j['event_type'] as String,
        occurredAt: DateTime.parse(j['occurred_at'] as String),
        strokeIndex: j['stroke_index'] as int?,
        forceSummary: j['force_summary'] as Map<String, dynamic>?,
        payload: j['payload'] as Map<String, dynamic>?,
      );
}

enum IncidentType {
  robot('ROBOT'),
  material('MATERIAL'),
  forceModule('FORCE_MODULE'),
  other('OTHER');

  final String code;
  const IncidentType(this.code);
}

// ─── Photos ──────────────────────────────────────────────────────────

enum PhotoKind {
  overall('OVERALL'),
  closeUp('CLOSE_UP'),
  other('OTHER');

  final String code;
  const PhotoKind(this.code);

  static PhotoKind parse(String? code) => values.firstWhere((k) => k.code == code, orElse: () => other);
}

enum QcResult {
  pass('PASS'),
  fail('FAIL');

  final String code;
  const QcResult(this.code);

  static QcResult? parse(String? code) {
    for (final r in values) {
      if (r.code == code) return r;
    }
    return null;
  }
}

class ProductPhoto {
  final int id;
  final PhotoKind kind;
  final QcResult? qcResult;
  final String? qcNote;
  final String? url;
  final int urlExpiresIn;
  final DateTime createdAt;

  const ProductPhoto({
    required this.id,
    required this.kind,
    required this.urlExpiresIn,
    required this.createdAt,
    this.qcResult,
    this.qcNote,
    this.url,
  });

  factory ProductPhoto.fromJson(Map<String, dynamic> j) => ProductPhoto(
        id: j['id'] as int,
        kind: PhotoKind.parse(j['kind'] as String?),
        qcResult: QcResult.parse(j['qc_result'] as String?),
        qcNote: j['qc_note'] as String?,
        url: j['url'] as String?,
        urlExpiresIn: j['url_expires_in'] as int? ?? 0,
        createdAt: DateTime.parse(j['created_at'] as String),
      );
}

class PhotoTicket {
  final String photoKey, uploadUrl, method;
  final int expiresIn;
  const PhotoTicket({required this.photoKey, required this.uploadUrl, required this.method, required this.expiresIn});

  factory PhotoTicket.fromJson(Map<String, dynamic> j) => PhotoTicket(
        photoKey: j['photo_key'] as String,
        uploadUrl: j['upload_url'] as String,
        method: j['method'] as String? ?? 'PUT',
        expiresIn: j['expires_in'] as int? ?? 0,
      );
}

/// 2 to 10 photos, an overall and a close-up among them, all passed.
bool photosReady(List<ProductPhoto> photos) =>
    photos.length >= 2 &&
    photos.length <= 10 &&
    photos.any((p) => p.kind == PhotoKind.overall) &&
    photos.any((p) => p.kind == PhotoKind.closeUp) &&
    photos.every((p) => p.qcResult == QcResult.pass);

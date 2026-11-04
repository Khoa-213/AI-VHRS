import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:dio/dio.dart';

import '../../../core/constants/api_constants.dart';
import '../../../core/network/dio_client.dart';
import '../../../core/network/network_exceptions.dart';
import '../domain/job.dart';

/// A failure this client found itself. [key] is a translation key (`td.flow.*`).
class TechFlowError implements Exception {
  final String key;
  const TechFlowError(this.key);

  @override
  String toString() => 'TechFlowError($key)';
}

/// Technician job calls, one to one with FE `services/technician.ts`. The backend scopes every
/// call to the signed-in technician.
class TechApi {
  final DioClient _client;

  /// For signed storage URLs: no base URL, and never the app's bearer token.
  final Dio _storage;

  TechApi({required DioClient client, required Dio storage})
      : _client = client,
        _storage = storage;

  // Avoid hammering technician endpoints while the server's Retry-After window is active.
  DateTime? _rateLimitedUntil;
  TooManyAttemptsException? _rateLimitError;

  Future<T> _guard<T>(Future<T> Function() call) async {
    final until = _rateLimitedUntil;
    if (until != null && DateTime.now().isBefore(until)) throw _rateLimitError!;
    try {
      return await call();
    } on TooManyAttemptsException catch (e) {
      final seconds = e.retryAfterSeconds ?? 30;
      _rateLimitError = e;
      _rateLimitedUntil = DateTime.now().add(Duration(seconds: seconds < 1 ? 1 : seconds));
      rethrow;
    }
  }

  Future<Map<String, dynamic>> _get(String path, [Map<String, dynamic>? query]) =>
      _guard(() => _client.get<Map<String, dynamic>>(path, queryParameters: query));

  Future<Map<String, dynamic>> _post(String path, [Object? body]) =>
      _guard(() => _client.post<Map<String, dynamic>>(path, data: body));

  String _job(int id) => '${ApiConstants.technicianJobs}/$id';

  // ─── Jobs ──────────────────────────────────────────────────────────

  Future<JobPage> listJobs({
    List<JobStatus> status = const [],
    DateTime? from,
    DateTime? to,
    int page = 1,
    int pageSize = 50,
  }) async {
    final r = await _get(ApiConstants.technicianJobs, {
      if (status.isNotEmpty) 'status': [for (final s in status) s.code],
      if (from != null) 'from': from.toUtc().toIso8601String(),
      if (to != null) 'to': to.toUtc().toIso8601String(),
      'page': page,
      'page_size': pageSize,
    });
    return JobPage(
      items: [for (final j in r['items'] as List<dynamic>) TechJob.fromJson(j as Map<String, dynamic>)],
      total: r['total'] as int,
      page: r['page'] as int,
      pageSize: r['page_size'] as int,
    );
  }

  /// Every page, so dashboard totals and robot assignments are not cut at one page of jobs.
  Future<List<TechJob>> allJobs() async {
    final jobs = <int, TechJob>{};
    for (var page = 1;; page++) {
      final r = await listJobs(page: page, pageSize: 200);
      for (final j in r.items) {
        jobs[j.id] = j;
      }
      if (r.items.isEmpty || r.page * r.pageSize >= r.total) return jobs.values.toList();
    }
  }

  Future<TechJobDetail> getJob(int id) async {
    if (id <= 0) throw const NotFoundException('Job not found', 'JOB_NOT_FOUND');
    return TechJobDetail.fromJson(await _get(_job(id)));
  }

  Future<TechJob> _action(int id, String action, [Object? body]) async =>
      TechJob.fromJson(await _post('${_job(id)}/$action', body));

  Future<TechJob> prepare(int id) => _action(id, 'prepare');
  Future<TechJob> start(int id) => _action(id, 'start');
  Future<TechJob> finish(int id) => _action(id, 'finish');
  Future<TechJob> simulate(int id, {required bool passed, List<String> errors = const [], Map<String, dynamic>? report}) =>
      _action(id, 'simulation', {'passed': passed, 'errors': errors, if (report != null) 'report': report});

  // ─── Package ───────────────────────────────────────────────────────

  /// Downloads the job package and checks its SHA-256 against the backend's hash. The bytes are
  /// parsed only after they have been verified.
  Future<VerifiedPackage> downloadPackage(int id) async {
    final info = JobPackage.fromJson(await _get('${_job(id)}/package'));
    final bytes = await _storageBytes(info.trajectoryUrl);
    final hash = verifyPackageBytes(bytes, info.packageHash);
    return VerifiedPackage(info: info, bytes: bytes, hash: hash, pages: parseTrajectory(bytes, info));
  }

  Future<Uint8List> _storageBytes(String url) async {
    try {
      final r = await _storage.get<List<int>>(
        url,
        options: Options(responseType: ResponseType.bytes, receiveTimeout: ApiConstants.receiveTimeout),
      );
      return Uint8List.fromList(r.data ?? const []);
    } on DioException {
      throw const TechFlowError('td.flow.downloadFailed');
    }
  }

  // ─── Events and incidents ──────────────────────────────────────────

  Future<JobEvent> postEvent(
    int id,
    ClientEvent event, {
    double? progressPct,
    int? strokeIndex,
    Map<String, num>? forceSummary,
    Map<String, dynamic>? payload,
  }) async =>
      JobEvent.fromJson(await _post('${_job(id)}/events', {
        'event_type': event.code,
        if (progressPct != null) 'progress_pct': progressPct,
        if (strokeIndex != null) 'stroke_index': strokeIndex,
        if (forceSummary != null) 'force_summary': forceSummary,
        if (payload != null) 'payload': payload,
      }));

  /// The whole history of a job, latest first (the backend pages it oldest first).
  Future<List<JobEvent>> allEvents(int id) async {
    const pageSize = 500;
    final out = <JobEvent>[];
    for (var page = 1;; page++) {
      final r = await _get('${_job(id)}/events', {'page': page, 'page_size': pageSize});
      final items = r['items'] as List<dynamic>;
      out.addAll([for (final e in items) JobEvent.fromJson(e as Map<String, dynamic>)]);
      if (items.isEmpty || page * pageSize >= (r['total'] as int)) break;
    }
    out.sort((a, b) {
      final at = b.occurredAt.compareTo(a.occurredAt);
      return at != 0 ? at : b.id - a.id;
    });
    return out;
  }

  /// [robotStatusAfter] is `MAINTENANCE` or `BROKEN`.
  Future<void> reportIncident(int id, {required IncidentType type, required String description, String? robotStatusAfter}) =>
      _post('${_job(id)}/incidents', {
        'type': type.code,
        'description': description,
        if (robotStatusAfter != null) 'robot_status_after': robotStatusAfter,
      });

  // ─── Photos ────────────────────────────────────────────────────────

  Future<List<ProductPhoto>> photos(int id) async {
    final r = await _guard(() => _client.get<List<dynamic>>('${_job(id)}/photos'));
    return [for (final p in r) ProductPhoto.fromJson(p as Map<String, dynamic>)];
  }

  Future<PhotoTicket> requestPhotoUpload(int id, {required String mimeType, required int sizeBytes}) async =>
      PhotoTicket.fromJson(await _post('${_job(id)}/photos/upload-url', {'mime_type': mimeType, 'size_bytes': sizeBytes}));

  Future<void> uploadPhotoBinary(
    PhotoTicket ticket,
    Uint8List bytes, {
    required String mimeType,
    void Function(int percent)? onProgress,
  }) async {
    try {
      await _storage.request<void>(
        ticket.uploadUrl,
        data: bytes,
        onSendProgress: onProgress == null || bytes.isEmpty ? null : (sent, total) => onProgress(sent * 100 ~/ total),
        options: Options(
          method: ticket.method,
          contentType: mimeType,
          sendTimeout: ApiConstants.receiveTimeout,
          receiveTimeout: ApiConstants.receiveTimeout,
          headers: {Headers.contentLengthHeader: bytes.length},
        ),
      );
    } on DioException {
      throw const TechFlowError('td.flow.uploadFailed');
    }
  }

  Future<ProductPhoto> registerPhoto(int id, {required String photoKey, required PhotoKind kind}) async =>
      ProductPhoto.fromJson(await _post('${_job(id)}/photos', {'photo_key': photoKey, 'kind': kind.code}));

  Future<ProductPhoto> setPhotoQc(int id, int photoId, QcResult result, {String? note}) async {
    final trimmed = note?.trim() ?? '';
    return ProductPhoto.fromJson(await _guard(() => _client.patch<Map<String, dynamic>>(
          '${_job(id)}/photos/$photoId',
          data: {'qc_result': result.code, 'qc_note': trimmed.isEmpty ? null : trimmed},
        )));
  }

  Future<void> removePhoto(int id, int photoId) => _guard(() => _client.delete<void>('${_job(id)}/photos/$photoId'));
  Future<TechJob> submitPhotos(int id) => _action(id, 'photos/submit');
  Future<TechJob> failQc(int id, String note) => _action(id, 'qc-fail', {'note': note.trim()});
}

/// Returns the lowercase SHA-256 of [bytes], or fails when it differs from [expected].
String verifyPackageBytes(List<int> bytes, String expected) {
  final hash = sha256.convert(bytes).toString();
  if (hash != expected.toLowerCase()) {
    throw const ConflictException('td.flow.hashMismatch', 'JOB_HASH_MISMATCH');
  }
  return hash;
}

/// Parses verified package bytes. Anything off the expected shape is `td.flow.invalidPackage`.
List<TrajectoryPage> parseTrajectory(List<int> bytes, JobPackage info) {
  const invalid = TechFlowError('td.flow.invalidPackage');
  final Object? data;
  try {
    data = jsonDecode(utf8.decode(bytes));
  } on FormatException {
    throw invalid;
  }
  if (data is! Map || data['format'] != info.trajectoryFormat) throw invalid;
  final pages = data['pages'];
  if (pages is! List || pages.isEmpty || pages.length != info.pages) throw invalid;

  double size(Object? v) {
    if (v is! num || !v.isFinite || v <= 0) throw invalid;
    return v.toDouble();
  }

  List<double> point(Object? p) {
    if (p is! List || p.length < 2) throw invalid;
    return [
      for (final (i, n) in p.indexed)
        if (n is num && n.isFinite) n.toDouble() else if (i < 2) throw invalid else double.nan,
    ];
  }

  return [
    for (final p in pages)
      () {
        if (p is! Map || p['paper'] is! Map || p['strokes'] is! List) throw invalid;
        return TrajectoryPage(
          widthMm: size(p['paper']['width_mm']),
          heightMm: size(p['paper']['height_mm']),
          strokes: [
            for (final s in p['strokes'] as List)
              () {
                if (s is! Map || s['points'] is! List) throw invalid;
                return [for (final pt in s['points'] as List) point(pt)];
              }(),
          ],
        );
      }(),
  ];
}

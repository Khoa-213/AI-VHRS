import 'dart:convert';
import 'dart:math' as math;

/// Checklist items of `POST /technician/jobs/{id}/calibration` (`CalibrationIn.checklist`).
const calibrationChecklist = ['frame_mounted', 'paper_clamped', 'pen_installed', 'force_zeroed'];

/// The workstation file is not a calibration file. [key] is a translation key (`td.cal.*`).
class CalibrationFileError implements Exception {
  final String key;

  /// For `td.cal.todo`: the paths of the values not measured yet, e.g. `probe_points[0].x`.
  final List<String> paths;
  const CalibrationFileError(this.key, [this.paths = const []]);

  @override
  String toString() => 'CalibrationFileError($key, $paths)';
}

/// The workstation's `calibration.json`, read the way `robot_agent/scripts/robot_console.py calibrate` reads it: keys starting
/// with `_` are notes for people and are dropped; a `null` or a string starting with `<` is a value not measured yet, and the
/// file is refused with their paths. What is left is sent as it is.
Map<String, dynamic> readCalibrationFile(String text) {
  Object? raw;
  try {
    raw = jsonDecode(text.startsWith('﻿') ? text.substring(1) : text);
  } on FormatException {
    throw const CalibrationFileError('td.cal.notJson');
  }
  if (raw is! Map<String, dynamic>) throw const CalibrationFileError('td.cal.notJson');

  Object? strip(Object? x) => switch (x) {
        Map<String, dynamic>() => {for (final e in x.entries) if (!e.key.startsWith('_')) e.key: strip(e.value)},
        List<dynamic>() => [for (final v in x) strip(v)],
        _ => x,
      };
  final body = strip(raw) as Map<String, dynamic>;

  final todo = <String>[];
  void walk(Object? x, String p) {
    if (x is Map<String, dynamic>) {
      for (final e in x.entries) {
        walk(e.value, p.isEmpty ? e.key : '$p.${e.key}');
      }
    } else if (x is List<dynamic>) {
      for (var i = 0; i < x.length; i++) {
        walk(x[i], '$p[$i]');
      }
    } else if (x == null || (x is String && x.startsWith('<'))) {
      todo.add(p);
    }
  }

  walk(body, '');
  if (todo.isNotEmpty) throw CalibrationFileError('td.cal.todo', todo);
  if (body['checklist'] is! Map || body['force_zero_offset'] is! num || body['probe_points'] is! List) {
    throw const CalibrationFileError('td.cal.shape');
  }
  return body;
}

/// True when P0, P1, P2 are finite and span a plane; the backend refuses collinear or repeated points.
bool probePlaneValid(List<({double x, double y, double z})> p) {
  if (p.length < 3 || p.take(3).any((q) => ![q.x, q.y, q.z].every((v) => v.isFinite))) return false;
  final a = p[0], b = p[1], c = p[2];
  final u = [b.x - a.x, b.y - a.y, b.z - a.z];
  final v = [c.x - a.x, c.y - a.y, c.z - a.z];
  final n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]];
  return math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2]) > 1e-6;
}

/// The body of a calibration typed by hand: the checklist, the force zero and P0 to P2 (no frame transform).
Map<String, dynamic> manualCalibration({
  required Map<String, bool> checklist,
  required double forceZeroOffset,
  required List<({double x, double y, double z})> points,
}) =>
    {
      'checklist': {for (final k in calibrationChecklist) k: checklist[k] ?? false},
      'force_zero_offset': forceZeroOffset,
      'probe_points': [for (final p in points) {'x': p.x, 'y': p.y, 'z': p.z}],
    };

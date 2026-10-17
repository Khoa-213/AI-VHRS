import 'package:flutter/foundation.dart';

import 'tech_models.dart';

/// Stand-in for the workshop roster (FE `pages/staff/technicians.ts`).
/// Each technician owns several FR3 robots. Robot state is deterministic per
/// day so the desk looks the same after a restart.

enum RobotState {
  idle('Idle'),
  writing('Writing'),
  calibrating('Calibrating'),
  offline('Offline');

  /// English catalog label, shown through `tn`.
  final String label;
  const RobotState(this.label);
}

class Robot {
  final String id;
  final RobotState state;

  /// Ink level, percent.
  final int ink;
  const Robot({required this.id, required this.state, required this.ink});
}

class Technician {
  final String id;
  final String name;
  final String shift;
  final List<String> skills;
  final List<Robot> robots;
  const Technician({
    required this.id,
    required this.name,
    required this.shift,
    required this.skills,
    required this.robots,
  });

  String get initials => name.split(' ').where((w) => w.isNotEmpty).map((w) => w[0]).join();
}

/// Same hash as FE `evaluate.ts`, so robot states match the web desk on the same day.
int hashOf(String s) {
  var h = 7;
  for (final c in s.codeUnits) {
    h = (h * 31 + c) % 9973;
  }
  return h;
}

const _roster = [
  (id: 'T-01', name: 'Hà Trần', shift: 'Morning, 07:00 to 15:00', skills: ['Fountain pens', 'Brush pens'], robots: ['FR3-01', 'FR3-02', 'FR3-03']),
  (id: 'T-02', name: 'Phúc Lê', shift: 'Morning, 07:00 to 15:00', skills: ['Ballpoint', 'Fine liner'], robots: ['FR3-04', 'FR3-05']),
  (id: 'T-03', name: 'Anh Vũ', shift: 'Afternoon, 13:00 to 21:00', skills: ['Fountain pens', 'Gel pens'], robots: ['FR3-06', 'FR3-07', 'FR3-08', 'FR3-09']),
  (id: 'T-04', name: 'Thảo Đinh', shift: 'Afternoon, 13:00 to 21:00', skills: ['Brush pens', 'Large format'], robots: ['FR3-10', 'FR3-11']),
];

/// Tests pin the day so robot states (and the offline gate) are predictable.
@visibleForTesting
String? rosterDayOverride;

String _day() => rosterDayOverride ?? DateTime.now().toUtc().toIso8601String().substring(0, 10);

Robot _robot(String id) {
  final h = hashOf(_day() + id);
  final state = h % 11 == 0
      ? RobotState.offline
      : h % 5 == 0
          ? RobotState.calibrating
          : h % 2 == 0
              ? RobotState.writing
              : RobotState.idle;
  return Robot(id: id, state: state, ink: 25 + (h % 70));
}

List<Technician> roster() => [
      for (final t in _roster)
        Technician(
          id: t.id,
          name: t.name,
          shift: t.shift,
          skills: t.skills,
          robots: t.robots.map(_robot).toList(),
        ),
    ];

Technician? technicianById(String? id) {
  for (final t in roster()) {
    if (t.id == id) return t;
  }
  return null;
}

/// Backend accounts have no roster id yet, so the mock orders are matched by
/// email. Any other technical-staff account gets T-01's queue.
const _rosterByEmail = {
  'tech@netviet.vn': 'T-01',
};

String rosterIdForEmail(String email) => _rosterByEmail[email.trim().toLowerCase()] ?? 'T-01';

/// Orders a technician is carrying: assigned and not yet written.
int loadOf(String techId, List<TechOrder> orders) => orders
    .where((o) => o.assignment?.techId == techId && !finishedStatuses.contains(o.status))
    .length;

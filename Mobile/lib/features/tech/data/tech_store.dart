import 'dart:async';
import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../auth/domain/models/auth_state.dart';
import '../../auth/presentation/auth_notifier.dart';
import '../domain/roster.dart';
import '../domain/tech_models.dart';
import 'prefs.dart';
import 'seed_orders.dart';

/// Local mock backend for the technician desk, the Flutter twin of FE
/// `store/store.ts`. Everything is saved with shared_preferences. To move to
/// the real API, keep these method names and replace the bodies with calls
/// through `DioClient`.

const _ordersKey = 'aivhrs-tech-orders';
const _protoKey = 'aivhrs-prototype';

// ─── Orders ──────────────────────────────────────────────────────────

class TechOrdersNotifier extends StateNotifier<List<TechOrder>> {
  final Prefs _prefs;
  TechOrdersNotifier(this._prefs) : super(_load(_prefs));

  static List<TechOrder> _load(Prefs prefs) {
    final raw = prefs.getString(_ordersKey);
    if (raw != null) {
      try {
        final list = (jsonDecode(raw) as List).map((e) => TechOrder.fromJson(e as Map<String, dynamic>)).toList();
        if (list.isNotEmpty) return list;
      } catch (_) {
        // Saved shape from an older build: fall back to the seed.
      }
    }
    return seedTechOrders();
  }

  @override
  set state(List<TechOrder> value) {
    super.state = value;
    _prefs.setString(_ordersKey, jsonEncode(value.map((o) => o.toJson()).toList()));
  }

  TechOrder? byId(String id) {
    for (final o in state) {
      if (o.id == id) return o;
    }
    return null;
  }

  void _patch(String id, TechOrder Function(TechOrder o) fn) {
    state = [for (final o in state) o.id == id ? fn(o) : o];
  }

  /// Technician presses Start on the real robot. The run is simulated.
  void startRobotRun(String id, String robotId, {int seconds = 45}) => _patch(
        id,
        (o) => o.copyWith(run: RobotRun(robotId: robotId, startedAt: DateTime.now().millisecondsSinceEpoch, seconds: seconds)),
      );

  /// Prototype only: jumps a running robot job to its end so photo and QC can open.
  void finishRobotRun(String id) => _patch(id, (o) {
        final run = o.run;
        if (run == null) return o;
        return o.copyWith(
          run: RobotRun(
            robotId: run.robotId,
            startedAt: DateTime.now().millisecondsSinceEpoch - run.seconds * 1000,
            seconds: run.seconds,
          ),
        );
      });

  /// QC passed: the order is Written and the customer gets the photos.
  void submitQc(String id, QcReport qc) =>
      _patch(id, (o) => o.copyWith(status: OrderStatus.Written, qc: qc, clearRun: true, clearQcFail: true));

  /// QC failed: back to the robot queue to be rescheduled.
  void failQc(String id, List<String> reasons, String note) => _patch(
        id,
        (o) => o.copyWith(
          status: OrderStatus.Queued,
          clearRun: true,
          clearQc: true,
          qcFail: QcFail(reasons: reasons, note: note, at: DateTime.now()),
        ),
      );

  /// Prototype only: the customer pays the deposit.
  void simulateDeposit(String id) =>
      _patch(id, (o) => o.copyWith(status: OrderStatus.Queued, depositMethod: 'Prototype'));

  void resetDemo() => state = seedTechOrders();
}

final techOrdersProvider =
    StateNotifierProvider<TechOrdersNotifier, List<TechOrder>>((ref) => TechOrdersNotifier(ref.watch(prefsProvider)));

/// Orders assigned to the signed-in technician.
final myOrdersProvider = Provider<List<TechOrder>>((ref) {
  final techId = ref.watch(sessionProvider)?.techId;
  return ref.watch(techOrdersProvider).where((o) => o.assignment?.techId == techId).toList();
});

final orderByIdProvider = Provider.family<TechOrder?, String>((ref, id) {
  for (final o in ref.watch(techOrdersProvider)) {
    if (o.id == id) return o;
  }
  return null;
});

// ─── Session ─────────────────────────────────────────────────────────

/// The signed-in technician, from the real backend session.
class TechSession {
  final String name;

  /// Roster id the mock orders are assigned to (T-01 ...).
  final String techId;
  final String email;
  const TechSession(this.name, this.techId, this.email);
}

/// Null until a `TECHNICAL_STAFF` account is signed in. Sign in and out go
/// through `authNotifierProvider`.
final sessionProvider = Provider<TechSession?>((ref) {
  final auth = ref.watch(authNotifierProvider);
  if (auth is! AuthAuthenticated) return null;
  return TechSession(auth.fullName, rosterIdForEmail(auth.email), auth.email);
});

final myTechnicianProvider = Provider<Technician?>((ref) => technicianById(ref.watch(sessionProvider)?.techId));

// ─── Prototype mode ─────────────────────────────────────────────────

class PrototypeNotifier extends StateNotifier<bool> {
  final Prefs _prefs;
  PrototypeNotifier(this._prefs) : super(_prefs.getBool(_protoKey) ?? true);

  void set(bool on) {
    state = on;
    _prefs.setBool(_protoKey, on);
  }
}

final prototypeProvider =
    StateNotifierProvider<PrototypeNotifier, bool>((ref) => PrototypeNotifier(ref.watch(prefsProvider)));

// ─── Clock ───────────────────────────────────────────────────────────

/// Ticks every second so time-based phases (live → qc) flip by themselves.
final nowProvider = StreamProvider<int>((ref) {
  final controller = StreamController<int>();
  controller.add(DateTime.now().millisecondsSinceEpoch);
  final timer = Timer.periodic(const Duration(seconds: 1), (_) => controller.add(DateTime.now().millisecondsSinceEpoch));
  ref.onDispose(() {
    timer.cancel();
    controller.close();
  });
  return controller.stream;
});

/// `ref.now` inside a build method: rebuilds every second, and returns the
/// real current time so a run that just ended is seen as ended right away.
extension NowRef on WidgetRef {
  int get now {
    watch(nowProvider);
    return DateTime.now().millisecondsSinceEpoch;
  }
}

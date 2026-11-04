import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/dio_client.dart';
import '../../../core/network/network_exceptions.dart';
import '../domain/job.dart';
import '../domain/robot.dart';
import 'robot_api.dart';
import 'tech_api.dart';

/// A bare client for signed storage URLs: no base URL, no bearer token.
final storageDioProvider = Provider<Dio>((ref) => Dio());

final techApiProvider = Provider<TechApi>(
  (ref) => TechApi(client: ref.watch(dioClientProvider), storage: ref.watch(storageDioProvider)),
);

final robotApiProvider = Provider<RobotApi>((ref) => RobotApi(client: ref.watch(dioClientProvider)));

// ─── App visibility ──────────────────────────────────────────────────

class _AppVisible extends StateNotifier<bool> with WidgetsBindingObserver {
  _AppVisible() : super(_visible(WidgetsBinding.instance.lifecycleState)) {
    WidgetsBinding.instance.addObserver(this);
  }

  // A desktop window that merely lost focus is `inactive`, and still on screen beside the
  // robot: alerts must keep coming. Polling stops only when it is minimised or in the background.
  static bool _visible(AppLifecycleState? s) => s != AppLifecycleState.hidden && s != AppLifecycleState.paused;

  @override
  void didChangeAppLifecycleState(AppLifecycleState s) => state = _visible(s);

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }
}

final appVisibleProvider = StateNotifierProvider<_AppVisible, bool>((ref) => _AppVisible());

// ─── Polling ─────────────────────────────────────────────────────────

/// Calls [load] now and again after each answer, never two at once. [next] picks the wait from
/// the answer; null stops polling (invalidate the provider to load again). Pauses while the app
/// is hidden and asks at once when it returns. An error keeps the last data: it retries after
/// the server's Retry-After or 3 seconds, and stops on 401, 403 and 404, where asking again
/// cannot help.
Stream<T> pollStream<T>(
  Ref ref,
  Future<T> Function() load, {
  required Duration? Function(T value) next,
}) {
  final out = StreamController<T>();
  Timer? timer;
  var stopped = false;
  var parked = false;

  Future<void> tick() async {
    if (stopped) return;
    if (!ref.read(appVisibleProvider)) {
      parked = true;
      return;
    }
    Duration? wait;
    try {
      final value = await load();
      if (stopped) return;
      out.add(value);
      wait = next(value);
    } catch (e, st) {
      if (stopped) return;
      out.addError(e, st);
      wait = switch (e) {
        UnauthorizedException() || ForbiddenException() || NotFoundException() => null,
        TooManyAttemptsException(:final retryAfterSeconds) =>
          Duration(seconds: (retryAfterSeconds ?? 5) < 1 ? 1 : (retryAfterSeconds ?? 5)),
        _ => const Duration(seconds: 3),
      };
    }
    if (wait != null) timer = Timer(wait, tick);
  }

  ref.listen<bool>(appVisibleProvider, (_, visible) {
    if (visible && parked) {
      parked = false;
      tick();
    }
  });
  ref.onDispose(() {
    stopped = true;
    timer?.cancel();
    out.close();
  });
  tick();
  return out.stream;
}

// ─── Jobs ────────────────────────────────────────────────────────────

/// All my jobs, every 30 seconds.
final techJobsProvider = StreamProvider.autoDispose<List<TechJob>>((ref) => pollStream(
      ref,
      ref.watch(techApiProvider).allJobs,
      next: (_) => const Duration(seconds: 30),
    ));

/// One job: every 5 seconds while the robot writes it, otherwise every 30.
final techJobProvider = StreamProvider.autoDispose.family<TechJobDetail, int>((ref, id) => pollStream(
      ref,
      () => ref.read(techApiProvider).getJob(id),
      next: (j) => j.job.status == JobStatus.writing || j.job.status == JobStatus.paused
          ? const Duration(seconds: 5)
          : const Duration(seconds: 30),
    ));

/// The job package this client downloaded and verified, kept while moving between a job's pages.
final verifiedPackageProvider = StateProvider.family<VerifiedPackage?, int>((ref, id) => null);

final jobPhotosProvider = StreamProvider.autoDispose.family<List<ProductPhoto>, int>((ref, id) => pollStream(
      ref,
      () => ref.read(techApiProvider).photos(id),
      next: (_) => const Duration(seconds: 30),
    ));

final jobEventsProvider = FutureProvider.autoDispose.family<List<JobEvent>, int>(
  (ref, id) => ref.watch(techApiProvider).allEvents(id),
);

final jobCommandsProvider = FutureProvider.autoDispose.family<List<RobotCommand>, int>(
  (ref, id) => ref.watch(robotApiProvider).jobCommands(id),
);

// ─── Robots ──────────────────────────────────────────────────────────

/// `GET /technician/robot-status`, shared by every view that needs it (the alert bell, Robot
/// control, the dashboard): one request every 2 seconds while one of them is on screen.
final robotStatusProvider = StreamProvider.autoDispose<List<RobotStatus>>((ref) => pollStream(
      ref,
      ref.watch(robotApiProvider).robotStatus,
      next: (_) => const Duration(seconds: 2),
    ));

/// Live frames of a robot: 4 times a second while it runs, once a second otherwise.
final robotLiveProvider = StreamProvider.autoDispose.family<LiveView, int>((ref, robotId) {
  var after = 0;
  LiveFrame? frame;
  return pollStream(
    ref,
    () async {
      final l = await ref.read(robotApiProvider).getLive(robotId, after);
      // The backend keeps frames in memory; after a restart its counter starts again from zero.
      after = l.lastSeq < after ? 0 : l.lastSeq;
      if (l.frames.isNotEmpty) frame = l.frames.last;
      return LiveView(l, frame);
    },
    next: (v) => Duration(milliseconds: v.live.status.busy ? 250 : 1000),
  );
});

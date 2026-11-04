import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/widgets/widgets.dart';
import '../../../auth/domain/models/auth_state.dart';
import '../../../auth/presentation/auth_notifier.dart';
import '../../data/providers.dart';
import '../../domain/robot.dart';
import '../../i18n/tech_strings.dart';
import 'job_widgets.dart';

/// Alerts that tell the operator to press the E-Stop and that nobody has acknowledged yet.
List<RobotAlert> pendingEstops(List<RobotStatus>? robots) =>
    (robots ?? const <RobotStatus>[]).expand((r) => r.alerts).where((a) => a.estopAdvised && a.acknowledgedAt == null).toList();

String _robotCode(List<RobotStatus> robots, int id) =>
    robots.where((r) => r.robotId == id).firstOrNull?.robotCode ?? '$id';

/// Covers the whole app, dialogs included, while an E-Stop alert is unacknowledged. It cannot be
/// dismissed: no close button, no Esc, nothing behind it takes a tap or a key. It only checks while
/// someone is signed in.
class EstopGate extends ConsumerWidget {
  final Widget child;
  const EstopGate({super.key, required this.child});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (ref.watch(authNotifierProvider) is! AuthAuthenticated) return child;
    final robots = ref.watch(robotStatusProvider).valueOrNull;
    final pending = pendingEstops(robots);
    if (pending.isEmpty) return child;
    return Stack(
      children: [
        ExcludeFocus(child: BlockSemantics(child: child)),
        Positioned.fill(child: EstopTakeover(alerts: pending, robots: robots!)),
      ],
    );
  }
}

class EstopTakeover extends ConsumerStatefulWidget {
  final List<RobotAlert> alerts;
  final List<RobotStatus> robots;
  const EstopTakeover({super.key, required this.alerts, required this.robots});

  @override
  ConsumerState<EstopTakeover> createState() => _EstopTakeoverState();
}

class _EstopTakeoverState extends ConsumerState<EstopTakeover> with SingleTickerProviderStateMixin {
  // One flash a second on the word only, never the whole red screen: large red flashes are unsafe.
  late final _blink = AnimationController(vsync: this, duration: const Duration(seconds: 1))..repeat();
  late final Timer _beep;
  bool _busy = false;
  String? _error;
  String? _notice;

  @override
  void initState() {
    super.initState();
    SystemSound.play(SystemSoundType.alert);
    _beep = Timer.periodic(const Duration(seconds: 2), (_) => SystemSound.play(SystemSoundType.alert));
  }

  @override
  void dispose() {
    _blink.dispose();
    _beep.cancel();
    super.dispose();
  }

  Future<void> _act(Future<void> Function() action, {String? done}) async {
    if (_busy) return;
    final t = ref.read(tProvider);
    setState(() {
      _busy = true;
      _error = null;
      _notice = null;
    });
    try {
      await action();
      if (mounted) setState(() => _notice = done);
    } catch (e) {
      if (mounted) setState(() => _error = techErrorText(t, e));
    }
    if (mounted) setState(() => _busy = false);
  }

  /// Records that the operator says they pressed it. The app cannot see the physical button.
  Future<void> _acknowledge() => _act(() async {
        final api = ref.read(robotApiProvider);
        for (final a in widget.alerts) {
          await api.ackAlert(a.id);
        }
        ref.invalidate(robotStatusProvider);
      });

  Future<void> _stop(String done) => _act(() async {
        final api = ref.read(robotApiProvider);
        for (final id in widget.alerts.map((a) => a.robotId).toSet()) {
          await api.sendCommand(CommandKind.stop, robotId: id);
        }
      }, done: done);

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(tProvider);
    final a = widget.alerts.first;
    final phone = MediaQuery.sizeOf(context).width < 700;
    final stripe = SizedBox(height: phone ? 16 : 24, width: double.infinity, child: const CustomPaint(painter: _HazardStripes()));
    return Semantics(
      scopesRoute: true,
      explicitChildNodes: true,
      liveRegion: true,
      label: t('rb.estopNow'),
      child: Material(
        color: AppColors.alarm,
        child: DefaultTextStyle.merge(
          style: const TextStyle(color: Colors.white, decoration: TextDecoration.none),
          child: Column(
            children: [
              stripe,
              Expanded(
                child: SafeArea(
                  child: Center(
                    child: SingleChildScrollView(
                      padding: EdgeInsets.all(phone ? 20 : 40),
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 1200),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            AnimatedBuilder(
                              animation: _blink,
                              builder: (context, _) {
                                // Honours the system's "reduce motion" setting.
                                final still = MediaQuery.disableAnimationsOf(context);
                                final on = still || _blink.value < 0.5;
                                final fg = on ? AppColors.alarm : Colors.white;
                                return Container(
                                  padding: EdgeInsets.symmetric(horizontal: phone ? 20 : 28, vertical: phone ? 10 : 14),
                                  decoration: BoxDecoration(color: on ? Colors.white : AppColors.ink, borderRadius: BorderRadius.circular(8)),
                                  child: Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      Icon(Icons.warning_amber_rounded, size: phone ? 28 : 40, color: fg),
                                      const SizedBox(width: 12),
                                      Text(t('dk.estop.word'), style: TextStyle(fontSize: phone ? 20 : 28, fontWeight: FontWeight.w700, color: fg)),
                                    ],
                                  ),
                                );
                              },
                            ),
                            SizedBox(height: phone ? 20 : 28),
                            Text(
                              t('rb.estopNow'),
                              textAlign: TextAlign.center,
                              style: TextStyle(fontSize: phone ? 46 : 92, fontWeight: FontWeight.w700, height: 1.08, letterSpacing: phone ? -1.4 : -3, color: Colors.white),
                            ),
                            SizedBox(height: phone ? 20 : 28),
                            // The title comes from the backend in Vietnamese and is shown as data.
                            Text(
                              '${_robotCode(widget.robots, a.robotId)} · ${a.title}',
                              textAlign: TextAlign.center,
                              style: TextStyle(fontSize: phone ? 17 : 24, fontWeight: FontWeight.w600, height: 1.35, color: Colors.white),
                            ),
                            const SizedBox(height: 8),
                            Text(
                              '${t('dk.estop.manager')} ${a.code} · ${t('rb.level', {'n': a.level})} · ${jobStamp(t, a.raisedAt)}',
                              textAlign: TextAlign.center,
                              style: TextStyle(fontSize: phone ? 13 : 16, height: 1.4, color: Colors.white),
                            ),
                            if (_error != null || _notice != null) ...[
                              const SizedBox(height: 16),
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                                decoration: BoxDecoration(color: AppColors.ink, borderRadius: BorderRadius.circular(8)),
                                child: Text(_error ?? _notice!, textAlign: TextAlign.center, style: const TextStyle(fontSize: 14, height: 1.4, color: Colors.white)),
                              ),
                            ],
                            SizedBox(height: phone ? 24 : 40),
                            Wrap(
                              alignment: WrapAlignment.center,
                              spacing: 12,
                              runSpacing: 10,
                              children: [
                                _TakeoverButton(label: t('dk.estop.done'), filled: true, onTap: _busy ? null : _acknowledge),
                                _TakeoverButton(label: t('dk.estop.stop'), filled: false, onTap: _busy ? null : () => _stop(t('dk.estop.stopSent'))),
                              ],
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ),
              stripe,
            ],
          ),
        ),
      ),
    );
  }
}

class _TakeoverButton extends StatelessWidget {
  final String label;
  final bool filled;
  final VoidCallback? onTap;
  const _TakeoverButton({required this.label, required this.filled, this.onTap});

  @override
  Widget build(BuildContext context) => MouseRegion(
        cursor: onTap == null ? SystemMouseCursors.forbidden : SystemMouseCursors.click,
        child: Pressable(
          onTap: onTap,
          semanticLabel: label,
          child: Container(
            constraints: const BoxConstraints(minHeight: 68),
            padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 12),
            decoration: BoxDecoration(
              color: filled ? Colors.white : Colors.transparent,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: Colors.white, width: 2),
            ),
            child: Text(
              label,
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: filled ? 20 : 18, fontWeight: filled ? FontWeight.w700 : FontWeight.w600, color: filled ? AppColors.ink : Colors.white),
            ),
          ),
        ),
      );
}

/// Black and yellow hazard stripes.
class _HazardStripes extends CustomPainter {
  const _HazardStripes();

  @override
  void paint(Canvas canvas, Size size) {
    canvas.clipRect(Offset.zero & size);
    canvas.drawRect(Offset.zero & size, Paint()..color = AppColors.hazardYellow);
    final black = Paint()..color = AppColors.ink;
    final w = size.height;
    for (var x = -w; x < size.width + w; x += w * 2) {
      canvas.drawPath(
        Path()
          ..moveTo(x, size.height)
          ..lineTo(x + w, 0)
          ..lineTo(x + w * 2, 0)
          ..lineTo(x + w, size.height)
          ..close(),
        black,
      );
    }
  }

  @override
  bool shouldRepaint(_HazardStripes old) => false;
}

/// A thin steady red band above every page while a red or E-Stop alert stays open after being
/// acknowledged, until a Manager closes it.
class EstopBand extends ConsumerWidget {
  const EstopBand({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    final robots = ref.watch(robotStatusProvider).valueOrNull ?? const <RobotStatus>[];
    final open = robots.expand((r) => r.alerts).where((a) => a.estopAdvised || a.level >= 4).toList();
    if (open.isEmpty) return const SizedBox.shrink();
    final a = open.firstWhere((x) => x.acknowledgedAt != null, orElse: () => open.first);
    final code = _robotCode(robots, a.robotId);
    return Semantics(
      container: true,
      liveRegion: true,
      child: Material(
        color: AppColors.alarm,
        child: SafeArea(
          bottom: false,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 10),
            child: Row(
              children: [
                const Icon(Icons.warning_amber_rounded, size: 20, color: Colors.white),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    a.acknowledgedAt != null
                        ? t('dk.estop.band', {'robot': code, 'time': jobStamp(t, a.acknowledgedAt!)})
                        : t('dk.estop.bandNew', {'robot': code}),
                    style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, height: 1.3, color: Colors.white),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

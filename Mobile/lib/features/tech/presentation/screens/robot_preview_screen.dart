import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../core/utils/formatters.dart';
import '../../../../core/widgets/widgets.dart';
import '../../data/tech_store.dart';
import '../../domain/qc_items.dart';
import '../../domain/roster.dart';
import '../../domain/tech_models.dart';
import '../../i18n/tech_strings.dart';
import '../../sim/sim.dart';
import '../../sim/sim_painter.dart';
import '../widgets/tech_shell.dart';
import '../widgets/tech_ui.dart';

const _rates = [1, 10, 30, 60];

String _clock(double s) =>
    '${(s ~/ 60).toString().padLeft(2, '0')}:${(s % 60).floor().toString().padLeft(2, '0')}';

/// Simulator and robot start for one order (FE `RobotPreview.tsx`).
///
/// Play the preview, tick the preflight, and once every gate is green the
/// technician can start the real robot. While the run is live the viewport
/// follows it; when it ends the page links on to photo and QC.
class RobotPreviewScreen extends ConsumerStatefulWidget {
  final String orderId;
  const RobotPreviewScreen({super.key, required this.orderId});

  @override
  ConsumerState<RobotPreviewScreen> createState() => _RobotPreviewScreenState();
}

class _RobotPreviewScreenState extends ConsumerState<RobotPreviewScreen> with SingleTickerProviderStateMixin {
  final _measure = TextMeasurer();
  final _z = ZState();
  late final Ticker _ticker;
  Duration _last = Duration.zero;

  Tuning _tuning = const Tuning();
  ViewFlags _flags = const ViewFlags();
  int _rate = 30;
  bool _playing = false;
  double _progress = 0;
  bool _watched = false;
  final Map<String, bool> _checks = {for (final c in preflightChecks) c: false};

  // Cached layout, rebuilt when the order text, font or layout changes.
  String? _planKey;
  Plan? _plan;
  SimViewport? _vp;
  InkLayer? _ink;
  String? _inkKey;

  @override
  void initState() {
    super.initState();
    _ticker = createTicker(_onTick)..start();
  }

  @override
  void dispose() {
    _ticker.dispose();
    _measure.dispose();
    _ink?.dispose();
    super.dispose();
  }

  bool _isLive(TechOrder? o) =>
      o?.run != null && (o!.status == OrderStatus.Queued || o.status == OrderStatus.Rewriting);

  void _onTick(Duration elapsed) {
    final dt = (elapsed - _last).inMicroseconds / 1e6;
    _last = elapsed;
    final o = ref.read(orderByIdProvider(widget.orderId));
    if (_isLive(o)) {
      setState(() {}); // live progress comes from the clock
      return;
    }
    if (!_playing || _plan == null) return;
    final seconds = pieceSeconds(_plan!, _tuning);
    setState(() {
      _progress = math.min(1, _progress + dt * _rate / seconds);
      if (_progress >= 1) {
        _playing = false;
        _watched = true;
      }
    });
  }

  void _ensurePlan(TechOrder o) {
    final key = '${o.id}|${o.spec.font}|${o.recognizedText}|${o.layout.name}|${o.spec.aspect}';
    if (key != _planKey) {
      _planKey = key;
      _vp = viewportFor(o.spec.aspect);
      _plan = buildPlan(_measure, o, _vp!);
      _inkKey = null;
    }
    final inkKey = '$key|${_tuning.force}';
    if (inkKey != _inkKey) {
      _ink?.dispose();
      _ink = InkLayer.build(o, _plan!, _tuning);
      _inkKey = inkKey;
    }
  }

  void _scrub(double v) => setState(() {
        _progress = v;
        _playing = false;
        if (v >= 1) _watched = true;
      });

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(tProvider);
    final session = ref.watch(sessionProvider);
    final prototype = ref.watch(prototypeProvider);
    final order = ref.watch(orderByIdProvider(widget.orderId));

    final another = TechButton(t('rp.another'), style: CustomButtonStyle.outline, small: true, onPressed: () => context.go('/tech/preview'));

    if (order == null) {
      return TechPage(
        title: t('rp.titleShort'),
        subtitle: t('rp.notFound'),
        actions: [another],
        body: EmptyCard(title: t('rp.notFound'), body: t('rp.noOrder', {'id': widget.orderId})),
      );
    }
    final asg = order.assignment;
    if (asg == null || asg.techId != session?.techId) {
      return TechPage(
        title: t('rp.title', {'id': order.id}),
        actions: [another],
        body: EmptyCard(
          title: t('rp.notYours'),
          body: asg != null ? t('rp.assignedTo', {'id': order.id, 'name': asg.techName}) : t('rp.unassigned', {'id': order.id}),
        ),
      );
    }

    _ensurePlan(order);
    final plan = _plan!;
    final vp = _vp!;
    final sp = order.spec;
    final run = order.run;
    final live = _isLive(order);
    final seconds = pieceSeconds(plan, _tuning);
    final now = DateTime.now().millisecondsSinceEpoch;
    final shown = live ? ((now - run!.startedAt) / (run.seconds * 1000)).clamp(0.0, 1.0) : _progress;
    final pen = penAt(_measure, plan, order, shown);
    final arm = solveArm(vp, Offset(pen.x, pen.y), shown * 40);
    final strokes = strokeCount(plan.text);
    final pieces = sp.qty == 0 ? 1 : sp.qty;
    final totalSeconds = seconds * pieces;
    final robot = technicianById(asg.techId)?.robots.where((r) => r.id == asg.robotId).firstOrNull;
    final finished = live && shown >= 1;
    String piecesLabel(int n) => t(n > 1 ? 'rp.pieces' : 'rp.piece', {'n': n});

    final paid = order.status == OrderStatus.Queued || order.status == OrderStatus.Rewriting;
    final robotOk = robot?.state != RobotState.offline;
    final checked = _checks.values.every((v) => v);
    final gates = [
      (ok: _watched || live, label: t('rp.gate.preview')),
      (ok: checked, label: t('rp.gate.preflight')),
      (ok: paid, label: t(paid ? 'rp.gate.paid' : 'rp.gate.unpaid')),
      (ok: robotOk, label: t(robotOk ? 'rp.gate.robotOk' : 'rp.gate.robotOff', {'robot': asg.robotId})),
    ];
    final canStart = gates.every((g) => g.ok) && !live;

    final checkLabel = {
      'paper': t('rp.check.paper', {'paper': t.tn(sp.paper)}),
      'pen': t('rp.check.pen', {'pen': t.tn(sp.pen), 'mm': _fmtNum(sp.penW)}),
      'ink': t('rp.check.ink', {'ink': t.tn(sp.ink), 'pct': robot?.ink ?? 80}),
      'calibration': t('rp.check.cal'),
      'clear': t('rp.check.clear'),
    };

    Future<void> confirmStart() async {
      final ok = await showConfirm(
        context,
        title: t('rp.startQ'),
        body: t('rp.startBody', {
          'robot': asg.robotId,
          'pieces': piecesLabel(pieces),
          'id': order.id,
          'pen': t.tn(sp.pen),
          'ink': t.tn(sp.ink),
        }),
        facts: [
          (t('rp.estTime'), t('rp.aboutMin', {'n': math.max(1, (totalSeconds / 60).round())})),
          (t('rp.penSpeed'), '${_fmtNum(_tuning.speed)} mm/s'),
        ],
        confirm: t('rp.startWriting'),
        cancel: t('rp.notYet'),
      );
      if (ok) ref.read(techOrdersProvider.notifier).startRobotRun(order.id, asg.robotId);
    }

    // ── Viewport ──
    final viewport = ClipRRect(
      borderRadius: BorderRadius.circular(TechRadius.card),
      child: Container(
        color: const Color(0xFF0E0E10),
        child: Column(
          children: [
            AspectRatio(
              aspectRatio: simW / simH,
              child: Stack(
                children: [
                  Positioned.fill(
                    child: Semantics(
                      image: true,
                      label: t('sc.canvasAria', {'id': order.id, 'pct': (pen.char / plan.chars * 100).round()}),
                      child: CustomPaint(
                        painter: SimPainter(
                          order: order,
                          plan: plan,
                          vp: vp,
                          pen: pen,
                          arm: arm,
                          tuning: _tuning,
                          flags: _flags,
                          ink: _ink!,
                          z: _z,
                          live: live,
                          sideViewLabel: t('sc.sideView'),
                        ),
                      ),
                    ),
                  ),
                  Positioned(left: 20, top: 18, child: _Badge(live ? t('rp.badgeLive', {'robot': asg.robotId}) : t('rp.badgePreview'), live: live)),
                  Positioned(right: 20, top: 18, child: _Badge(t('rp.pieceOf', {'n': pieces}))),
                  if (!live)
                    Positioned(
                      left: 20,
                      bottom: 16,
                      child: Text(t('rp.simNote'), style: const TextStyle(fontSize: 11, color: AppColors.onInkMuted)),
                    ),
                ],
              ),
            ),
            Container(
              color: AppColors.inkSoft,
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
              child: live
                  ? Row(
                      children: [
                        MonoText('${(shown * 100).round()}%', color: AppColors.onInk),
                        const SizedBox(width: 16),
                        Expanded(child: Meter(shown, color: const Color(0xFF6FBF8B), semanticLabel: t('rp.liveProgress'))),
                        const SizedBox(width: 16),
                        MonoText(
                          finished ? t('rp.done') : t('rp.secLeft', {'n': (run!.seconds * (1 - shown)).ceil()}),
                          size: 13,
                          color: AppColors.onInkMuted,
                        ),
                      ],
                    )
                  : Row(
                      children: [
                        TechButton(
                          t(_playing ? 'rp.pause' : shown >= 1 ? 'rp.replay' : 'rp.play'),
                          style: CustomButtonStyle.inverted,
                          small: true,
                          icon: _playing ? Icons.pause_rounded : Icons.play_arrow_rounded,
                          onPressed: () => setState(() {
                            if (shown >= 1) _progress = 0;
                            _playing = !_playing;
                          }),
                        ),
                        const SizedBox(width: 8),
                        _DarkTextButton(t('rp.reset'), () => setState(() {
                              _progress = 0;
                              _playing = false;
                            })),
                        Expanded(
                          child: SliderTheme(
                            data: SliderTheme.of(context).copyWith(
                              activeTrackColor: AppColors.onInk,
                              inactiveTrackColor: const Color(0xFF3F3F46),
                              thumbColor: AppColors.onInk,
                            ),
                            child: Slider(value: _progress, onChanged: _scrub, semanticFormatterCallback: (_) => t('rp.scrub')),
                          ),
                        ),
                        MonoText('${_clock(shown * seconds)} / ${_clock(seconds)}', size: 12, color: AppColors.onInkMuted),
                        const SizedBox(width: 16),
                        Semantics(
                          label: t('rp.speed'),
                          child: Row(
                            children: [
                              for (final r in _rates)
                                _RatePill('${r}x', on: r == _rate, onTap: () => setState(() => _rate = r)),
                            ],
                          ),
                        ),
                      ],
                    ),
            ),
          ],
        ),
      ),
    );

    // ── Telemetry ──
    final words = plan.text.split(RegExp(r'\s+')).where((s) => s.isNotEmpty).length;
    final tele = [
      (t('rp.tele.progress'), '${(shown * 100).round()}%'),
      (t('rp.tele.words'), '${pen.words} / $words'),
      (t('rp.tele.strokes'), '${(shown * strokes).round()} / $strokes'),
      (t('rp.tele.pen'), t(pen.down ? 'rp.tele.down' : 'rp.tele.lifted')),
      (t('rp.tele.tip'), '${mmOf(arm.tip.dx - vp.paper.left).toStringAsFixed(0)}, ${mmOf(arm.tip.dy - vp.paper.top).toStringAsFixed(0)} mm'),
      (t('rp.tele.reach'), t(arm.reachable ? 'rp.tele.inRange' : 'rp.tele.clamped')),
    ];
    final telemetry = Semantics(
      label: t('rp.telemetry'),
      child: Row(
        children: [
          for (var i = 0; i < tele.length; i++) ...[
            if (i > 0) const SizedBox(width: 12),
            Expanded(
              child: TechCard(
                padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [Label(tele[i].$1), const SizedBox(height: 6), MonoText(tele[i].$2, size: 15)],
                ),
              ),
            ),
          ],
        ],
      ),
    );

    final joints = TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('rp.joints'), tag: t('rp.simulated')),
          Row(
            children: [
              for (var i = 0; i < arm.q.length; i++)
                Expanded(
                  child: Column(
                    children: [Label('J${i + 1}'), const SizedBox(height: 4), MonoText('${arm.q[i].toStringAsFixed(1)}°', size: 14)],
                  ),
                ),
            ],
          ),
        ],
      ),
    );

    // ── Side ──
    final options = TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('rp.options'), tag: t('rp.fromOrder')),
          FactList([
            (t('rp.opt.format'), valueText('${t.tn(sp.type)}${sp.land ? t('rp.opt.landscape') : ''}')),
            (t('rp.opt.input'), valueText(t.tn(sp.mode.label))),
            (t('rp.opt.paper'), Swatch(sp.paperColor, t.tn(sp.paper))),
            (t('rp.opt.pen'), valueText('${t.tn(sp.pen)}, ${_fmtNum(sp.penW)} mm')),
            (t('rp.opt.ink'), Swatch(sp.inkColor, t.tn(sp.ink))),
            (t('rp.opt.font'), valueText(t.tn(sp.fontName))),
            (t('rp.opt.layout'), valueText(t.tn(order.layout.label))),
            (t('rp.opt.pieces'), valueText('$pieces')),
          ]),
          const SizedBox(height: 14),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(color: Color(sp.paperColor), borderRadius: BorderRadius.circular(TechRadius.inner)),
            child: Text(plan.text, style: inkStyle(sp, 22)),
          ),
        ],
      ),
    );

    Widget slider(String label, double value, double min, double max, double step, String unit, Tuning Function(double) set) =>
        Padding(
          padding: const EdgeInsets.only(bottom: 4),
          child: Row(
            children: [
              SizedBox(width: 110, child: Label(label)),
              Expanded(
                child: Slider(
                  value: value,
                  min: min,
                  max: max,
                  divisions: ((max - min) / step).round(),
                  onChanged: live ? null : (v) => setState(() => _tuning = set(v)),
                ),
              ),
              SizedBox(width: 70, child: Align(alignment: Alignment.centerRight, child: MonoText('${_fmtNum(value)} $unit', size: 13))),
            ],
          ),
        );

    final tuning = TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('rp.tuningTitle')),
          slider(t('rp.t.speed'), _tuning.speed, 20, 120, 5, 'mm/s', (v) => _tuning.copyWith(speed: v)),
          slider(t('rp.t.force'), _tuning.force, 0.5, 3, 0.1, 'N', (v) => _tuning.copyWith(force: (v * 10).round() / 10)),
          slider(t('rp.t.lift'), _tuning.lift, 2, 20, 1, 'mm', (v) => _tuning.copyWith(lift: v)),
          const SizedBox(height: 4),
          Text(
            t('rp.tuneNote', {
              'one': math.max(1, (seconds / 60).round()),
              'pieces': piecesLabel(pieces),
              'all': math.max(1, (totalSeconds / 60).round()),
            }),
            style: const TextStyle(fontSize: 12, color: AppColors.textSecondary, height: 1.4),
          ),
          const SizedBox(height: 12),
          Semantics(
            label: t('rp.viewOptions'),
            child: Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                FilterChip(
                  label: Text(t('rp.f.trajectory')),
                  selected: _flags.trajectory,
                  onSelected: (v) => setState(() => _flags = _flags.copyWith(trajectory: v)),
                ),
                FilterChip(
                  label: Text(t('rp.f.reach')),
                  selected: _flags.reach,
                  onSelected: (v) => setState(() => _flags = _flags.copyWith(reach: v)),
                ),
                FilterChip(
                  label: Text(t('rp.f.joints')),
                  selected: _flags.joints,
                  onSelected: (v) => setState(() => _flags = _flags.copyWith(joints: v)),
                ),
              ],
            ),
          ),
        ],
      ),
    );

    final start = TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('rp.preflight'), tag: robot == null ? null : '${asg.robotId} · ${t.tn(robot.state.label)}'),
          for (final c in preflightChecks)
            InkCheck(
              value: _checks[c]!,
              title: checkLabel[c]!,
              onChanged: live ? null : (v) => setState(() => _checks[c] = v),
            ),
          const SizedBox(height: 16),
          if (live)
            _RunState(
              finished: finished,
              title: t(finished ? 'rp.finished' : 'rp.writing'),
              body: finished
                  ? t('rp.finishedBody', {'pieces': piecesLabel(pieces), 'robot': run!.robotId})
                  : t('rp.writingBody', {'robot': run!.robotId}),
              action: finished
                  ? TechButton(t('rp.goQc'), expand: true, onPressed: () => context.go('/tech/qc/${Uri.encodeComponent(order.id)}'))
                  : prototype
                      ? TechButton(t('rp.protoFinish'),
                          style: CustomButtonStyle.outline,
                          small: true,
                          onPressed: () => ref.read(techOrdersProvider.notifier).finishRobotRun(order.id))
                      : null,
            )
          else ...[
            for (final g in gates)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(
                  children: [
                    Icon(g.ok ? Icons.check_circle_rounded : Icons.radio_button_unchecked_rounded,
                        size: 18, color: g.ok ? AppColors.success : AppColors.textTertiary),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(g.label,
                          style: TextStyle(fontSize: 13, color: g.ok ? AppColors.textPrimary : AppColors.textSecondary)),
                    ),
                  ],
                ),
              ),
            const SizedBox(height: 16),
            TechButton(t('rp.startReal'), expand: true, onPressed: canStart ? confirmStart : null),
            if (prototype && !(_watched && checked)) ...[
              const SizedBox(height: 10),
              TechButton(
                t('rp.protoPlay'),
                style: CustomButtonStyle.text,
                small: true,
                onPressed: () => setState(() {
                  _progress = 1;
                  _playing = false;
                  _watched = true;
                  for (final c in preflightChecks) {
                    _checks[c] = true;
                  }
                }),
              ),
            ],
            if (!paid && prototype) ...[
              const SizedBox(height: 6),
              TechButton(
                t('rp.protoDeposit', {'amount': Formatters.formatVND((order.total * 0.3 / 1000).round() * 1000)}),
                style: CustomButtonStyle.text,
                small: true,
                onPressed: () => ref.read(techOrdersProvider.notifier).simulateDeposit(order.id),
              ),
            ],
          ],
        ],
      ),
    );

    return TechPage(
      title: t('rp.title', {'id': order.id}),
      subtitle: t('rp.subtitle', {'title': t.tn(order.title), 'name': order.name ?? t('common.customer')}),
      actions: [another],
      body: LayoutBuilder(builder: (context, c) {
        final main = Column(
          children: [
            Semantics(label: t('rp.viewport'), child: viewport),
            const SizedBox(height: 16),
            telemetry,
            const SizedBox(height: 16),
            joints,
          ],
        );
        final side = Column(children: [start, const SizedBox(height: 16), options, const SizedBox(height: 16), tuning]);
        if (c.maxWidth < 1100) return Column(children: [main, const SizedBox(height: 16), side]);
        return Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(child: main),
            const SizedBox(width: 16),
            SizedBox(width: 400, child: side),
          ],
        );
      }),
    );
  }
}

String _fmtNum(double v) => v == v.roundToDouble() ? v.toStringAsFixed(0) : v.toStringAsFixed(1);

class _Badge extends StatelessWidget {
  final String text;
  final bool live;
  const _Badge(this.text, {this.live = false});

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: live ? const Color(0xFF2F5E40) : const Color(0xCC18181B),
          borderRadius: BorderRadius.circular(TechRadius.control),
          border: Border.all(color: const Color(0x1FFFFFFF)),
        ),
        child: MonoText(text, size: 11, weight: FontWeight.w700, color: AppColors.onInk),
      );
}

class _RatePill extends StatelessWidget {
  final String label;
  final bool on;
  final VoidCallback onTap;
  const _RatePill(this.label, {required this.on, required this.onTap});

  @override
  Widget build(BuildContext context) => Semantics(
        button: true,
        selected: on,
        child: MouseRegion(
          cursor: SystemMouseCursors.click,
          child: GestureDetector(
            onTap: onTap,
            child: AnimatedContainer(
              duration: AppTheme.motionFast,
              margin: const EdgeInsets.only(left: 4),
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: on ? AppColors.onInk : Colors.transparent,
                borderRadius: BorderRadius.circular(TechRadius.control),
              ),
              child: MonoText(label, size: 12, color: on ? AppColors.ink : AppColors.onInkMuted),
            ),
          ),
        ),
      );
}

class _DarkTextButton extends StatelessWidget {
  final String label;
  final VoidCallback onTap;
  const _DarkTextButton(this.label, this.onTap);

  @override
  Widget build(BuildContext context) => TextButton(
        onPressed: onTap,
        style: TextButton.styleFrom(foregroundColor: AppColors.onInkMuted),
        child: Text(label),
      );
}

class _RunState extends StatelessWidget {
  final bool finished;
  final String title;
  final String body;
  final Widget? action;
  const _RunState({required this.finished, required this.title, required this.body, this.action});

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: finished ? AppColors.ink : AppColors.surfaceVariant,
          borderRadius: BorderRadius.circular(TechRadius.inner),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                if (!finished) ...[
                  const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2)),
                  const SizedBox(width: 10),
                ],
                Text(title,
                    style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: finished ? AppColors.onInk : AppColors.textPrimary)),
              ],
            ),
            const SizedBox(height: 6),
            Text(body,
                style: TextStyle(fontSize: 13, height: 1.45, color: finished ? AppColors.onInkMuted : AppColors.textSecondary)),
            if (action != null) ...[const SizedBox(height: 14), finished ? _inverted(action!) : action!],
          ],
        ),
      );

  // The finished card is ink, so its button flips to white.
  Widget _inverted(Widget a) => a is TechButton
      ? TechButton(a.label, onPressed: a.onPressed, style: CustomButtonStyle.inverted, expand: true)
      : a;
}

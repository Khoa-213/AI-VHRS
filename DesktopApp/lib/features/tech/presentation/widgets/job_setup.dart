import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/widgets/widgets.dart';
import '../../data/providers.dart';
import '../../domain/calibration.dart';
import '../../domain/job.dart';
import '../../domain/robot.dart';
import '../../i18n/tech_strings.dart';
import 'job_flow.dart';
import 'my_robots.dart';
import 'real_switch.dart';
import 'tech_ui.dart';

// ─── Steps ───────────────────────────────────────────────────────────

/// One step of a job's workflow (`BE/docs/FE_TECH_WORKSPACE_HANDOFF.md` 2.4). [why] is the translation key of what holds it.
class JobStep {
  final String key;
  final bool done;
  final String? why;

  /// No API on purpose (allowing the real arm): never ticked, shown with the workstation command.
  final bool manual;
  const JobStep(this.key, {this.done = false, this.why, this.manual = false});
}

const _afterPrepare = [JobStatus.preparing, JobStatus.writing, JobStatus.paused, JobStatus.written, JobStatus.photoUploaded, JobStatus.done];
const _afterStart = [JobStatus.writing, JobStatus.paused, JobStatus.written, JobStatus.photoUploaded, JobStatus.done];
const _afterFinish = [JobStatus.written, JobStatus.photoUploaded, JobStatus.done];

/// The twelve steps of a job, in order, with what is done and why the next ones wait. A LOAD, PREFLIGHT or DRY_RUN counts
/// only when it finished after the current calibration, since a new calibration asks for them again.
List<JobStep> jobSteps(TechJobDetail d, {required bool verified, List<RobotCommand> commands = const []}) {
  final j = d.job;
  final s = j.status;
  final cal = d.calibration;
  final calibrated = cal?.isValid ?? false;
  bool ran(CommandKind k) => commands.any((c) =>
      c.jobId == j.id && c.kind == k && c.status == CommandStatus.done && (cal == null || !c.createdAt.isBefore(cal.createdAt)));
  final prepared = _afterPrepare.contains(s);
  final started = _afterStart.contains(s);
  final finished = _afterFinish.contains(s);
  final loaded = started || ran(CommandKind.load);
  final checked = started || ran(CommandKind.preflight);
  final simulated = started || j.simulationPassed == true;
  return [
    JobStep('package', done: prepared || (j.downloadedAt != null && verified)),
    JobStep('robot', done: j.robotId != null),
    JobStep('prepare', done: prepared, why: j.downloadedAt == null || !verified ? 'tw.why.download' : j.robotId == null ? 'tw.why.robot' : null),
    JobStep('calibrate', done: started || calibrated, why: prepared ? null : 'tw.why.prepare'),
    JobStep('load', done: loaded, why: calibrated ? null : 'tw.why.calibrate'),
    JobStep('real', manual: true, why: prepared ? null : 'tw.why.prepare'),
    JobStep('preflight', done: checked, why: loaded ? null : 'tw.why.load'),
    JobStep('simulate', done: simulated, why: calibrated ? null : 'tw.why.calibrate'),
    JobStep('dryRun', done: started || ran(CommandKind.dryRun), why: simulated ? null : 'tw.why.simulate'),
    JobStep('write', done: started, why: simulated ? null : 'tw.why.simulate'),
    JobStep('finish', done: finished, why: s == JobStatus.writing || finished ? null : 'tw.why.finish'),
    JobStep('photos', done: s == JobStatus.photoUploaded || s == JobStatus.done, why: finished ? null : 'tw.why.photos'),
  ];
}

/// The workstation command that allows the real arm for this job: shown where the app does not run that robot's agent.
/// On the workstation itself the REAL step is a button (`RealSwitch`, the agent's local API; still no backend API).
String realEnableCommand(int jobId) => 'real-enable --config agent.json --job $jobId --minutes 30';

/// Vertical list of the job's steps: ✓ for done, the current step in ink, a lock and the reason for one that waits.
class JobStepList extends ConsumerWidget {
  final TechJobDetail detail;
  final bool verified;
  const JobStepList({super.key, required this.detail, required this.verified});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    final commands = ref.watch(jobCommandsProvider(detail.job.id)).valueOrNull ?? const <RobotCommand>[];
    final steps = jobSteps(detail, verified: verified, commands: commands);
    final current = steps.indexWhere((s) => !s.done && !s.manual && s.why == null);
    final live = !const [JobStatus.cancelled, JobStatus.failed, JobStatus.rewriteRequired].contains(detail.job.status);

    Widget rows(int from, int to) => Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            for (var i = from; i < to; i++)
              _StepRow(n: i + 1, step: steps[i], current: live && i == current, last: i == to - 1, jobId: detail.job.id,
                  robotId: detail.job.robotId),
          ],
        );
    final half = (steps.length / 2).ceil();

    return TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('tw.steps')),
          // Two columns (1 to 6, 7 to 12) where the window is wide, so the twelve steps stay in view above the forms.
          LayoutBuilder(builder: (context, c) {
            if (c.maxWidth < 860) return rows(0, steps.length);
            return Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [Expanded(child: rows(0, half)), const SizedBox(width: 32), Expanded(child: rows(half, steps.length))],
            );
          }),
        ],
      ),
    );
  }
}

class _StepRow extends ConsumerWidget {
  final int n;
  final JobStep step;
  final bool current;
  final bool last;
  final int jobId;
  final int? robotId;
  const _StepRow({required this.n, required this.step, required this.current, required this.last, required this.jobId, this.robotId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    final s = step;
    final locked = !s.done && s.why != null;
    final Widget mark = s.done
        ? Container(
            width: 26,
            height: 26,
            decoration: const BoxDecoration(color: AppColors.success, shape: BoxShape.circle),
            child: const Icon(Icons.check_rounded, size: 16, color: AppColors.onInk),
          )
        : Container(
            width: 26,
            height: 26,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: current ? AppColors.ink : AppColors.surfaceVariant,
              shape: BoxShape.circle,
            ),
            child: locked
                ? const Icon(Icons.lock_outline_rounded, size: 13, color: AppColors.textSecondary)
                : MonoText('$n', size: 12, color: current ? AppColors.onInk : AppColors.textSecondary),
          );
    final state = s.done ? t('td.api.passed') : (locked ? t(s.why!) : null);

    return Semantics(
      label: [t('tw.step.${s.key}'), if (state != null) state].join(', '),
      excludeSemantics: !s.manual,
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Column(
              children: [
                mark,
                if (!last) Expanded(child: Container(width: 1.5, color: s.done ? AppColors.success : AppColors.border)),
              ],
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Padding(
                padding: EdgeInsets.only(top: 3, bottom: last ? 0 : 16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      t('tw.step.${s.key}'),
                      style: TextStyle(
                        fontSize: 14,
                        height: 1.35,
                        fontWeight: current ? FontWeight.w700 : FontWeight.w500,
                        color: s.done || current ? AppColors.textPrimary : AppColors.secondaryLight,
                      ),
                    ),
                    if (locked)
                      Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: Text(t(s.why!), style: const TextStyle(fontSize: 12, color: AppColors.textSecondary, height: 1.4)),
                      ),
                    if (s.manual && !locked) ...[
                      const SizedBox(height: 4),
                      Text(t('tw.realHelp'), style: const TextStyle(fontSize: 12, color: AppColors.textSecondary, height: 1.4)),
                      const SizedBox(height: 8),
                      RealSwitch(jobId: jobId, robotId: robotId, fallback: _CopyCommand(command: realEnableCommand(jobId))),
                    ],
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _CopyCommand extends ConsumerStatefulWidget {
  final String command;
  const _CopyCommand({required this.command});

  @override
  ConsumerState<_CopyCommand> createState() => _CopyCommandState();
}

class _CopyCommandState extends ConsumerState<_CopyCommand> {
  bool _copied = false;

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(tProvider);
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 6, 6, 6),
      decoration: BoxDecoration(color: AppColors.inkSoft, borderRadius: BorderRadius.circular(TechRadius.inner)),
      child: Row(
        children: [
          Expanded(
            child: SelectableText(
              widget.command,
              style: const TextStyle(fontSize: 12, color: AppColors.onInk, height: 1.4, fontFeatures: [FontFeature.tabularFigures()]),
            ),
          ),
          const SizedBox(width: 8),
          TechButton(
            t(_copied ? 'tw.copied' : 'tw.copy'),
            small: true,
            style: CustomButtonStyle.inverted,
            icon: _copied ? Icons.check_rounded : Icons.copy_rounded,
            onPressed: () async {
              await Clipboard.setData(ClipboardData(text: widget.command));
              if (mounted) setState(() => _copied = true);
            },
          ),
        ],
      ),
    );
  }
}

// ─── Choose the robot ────────────────────────────────────────────────

/// Step 2 on a SCHEDULED job: one of the robots the Manager gave me (`PUT /technician/jobs/{id}/robot`). A robot in maintenance
/// or broken cannot be chosen; an offline one can, with a warning. The pen fit is the backend's (`ROBOT_NOT_SUITABLE`).
class ChooseRobotCard extends ConsumerStatefulWidget {
  final TechJob job;
  final bool disabled;
  final TechRun run;
  const ChooseRobotCard({super.key, required this.job, required this.disabled, required this.run});

  @override
  ConsumerState<ChooseRobotCard> createState() => _ChooseRobotCardState();
}

class _ChooseRobotCardState extends ConsumerState<ChooseRobotCard> {
  int? _pick;

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(tProvider);
    final q = ref.watch(myRobotsProvider);
    final robots = q.valueOrNull?.robots ?? const <RobotStatus>[];
    final current = widget.job.robotId;
    final pick = _pick ?? current;
    final picked = robots.where((r) => r.robotId == pick).firstOrNull;
    final changed = pick != null && pick != current;

    return TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('tw.step.robot'), tag: current == null ? t('tw.noRobot') : widget.job.robotCode),
          Text(t('tw.pickRobotHelp'), style: const TextStyle(fontSize: 13, color: AppColors.textSecondary, height: 1.4)),
          const SizedBox(height: 12),
          if (q.hasError && !q.hasValue) Text(t('tw.robots.none'), style: const TextStyle(fontSize: 13, color: AppColors.error)),
          if (q.hasValue && robots.isEmpty) Text(t('tw.robots.none'), style: const TextStyle(fontSize: 14, height: 1.5)),
          for (final r in robots)
            _RobotOption(
              robot: r,
              selected: r.robotId == pick,
              onTap: widget.disabled || r.outOfService ? null : () => setState(() => _pick = r.robotId),
            ),
          if (picked != null && !picked.online) ...[
            const SizedBox(height: 8),
            Semantics(
              liveRegion: true,
              child: Text(t('tw.pickOffline', {'code': picked.robotCode}), style: const TextStyle(fontSize: 13, color: AppColors.warning, height: 1.4)),
            ),
          ],
          const SizedBox(height: 12),
          Align(
            alignment: Alignment.centerLeft,
            child: TechButton(
              t(current == null ? 'tw.chooseRobot' : 'tw.changeRobot'),
              small: true,
              onPressed: widget.disabled || !changed
                  ? null
                  : () async {
                      final ok = await widget.run(() => ref.read(techApiProvider).chooseRobot(widget.job.id, pick));
                      if (ok && mounted) setState(() => _pick = null);
                    },
            ),
          ),
        ],
      ),
    );
  }
}

class _RobotOption extends ConsumerWidget {
  final RobotStatus robot;
  final bool selected;
  final VoidCallback? onTap;
  const _RobotOption({required this.robot, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    final r = robot;
    final row = Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: selected ? AppColors.surfaceVariant : AppColors.surface,
        borderRadius: BorderRadius.circular(TechRadius.inner),
        border: Border.all(color: selected ? AppColors.ink : AppColors.border, width: selected ? 1.5 : 1),
      ),
      child: Opacity(
        opacity: r.outOfService ? 0.5 : 1,
        child: Row(
          children: [
            Icon(selected ? Icons.radio_button_checked_rounded : Icons.radio_button_unchecked_rounded, size: 20,
                color: selected ? AppColors.ink : AppColors.textTertiary),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  MonoText(r.robotCode, size: 14),
                  if (r.penCategories.isNotEmpty)
                    Text(t('tw.pens', {'list': r.penCategories.map(t.tn).join(', ')}),
                        style: const TextStyle(fontSize: 12, color: AppColors.textSecondary, height: 1.4)),
                ],
              ),
            ),
            const SizedBox(width: 8),
            Flexible(
              child: Align(
                alignment: Alignment.centerRight,
                child: Wrap(
                  alignment: WrapAlignment.end,
                  spacing: 6,
                  runSpacing: 6,
                  children: [
                    if (r.outOfService) StatusPill(t('tw.out.${r.robotStatus}'), r.robotStatus == 'BROKEN' ? AppColors.error : AppColors.warning),
                    StatusPill(robotLinkLabel(t, r.connection), robotLinkColor(r.connection)),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
    return Semantics(
      inMutuallyExclusiveGroup: true,
      checked: selected,
      enabled: onTap != null,
      child: MouseRegion(
        cursor: onTap == null ? SystemMouseCursors.forbidden : SystemMouseCursors.click,
        child: GestureDetector(behavior: HitTestBehavior.opaque, onTap: onTap, child: row),
      ),
    );
  }
}

// ─── Calibration ─────────────────────────────────────────────────────

/// Step 4 on a PREPARING or PAUSED job (`POST /technician/jobs/{id}/calibration`): the workstation's `calibration.json`, read
/// like `robot_console.py calibrate`, or the checklist, force zero and P0 to P2 by hand. A new calibration clears the earlier
/// simulation result (stale on a PAUSED job), so it asks first when there is one.
class CalibrationCard extends ConsumerStatefulWidget {
  final TechJobDetail detail;
  final bool disabled;
  final TechRun run;
  const CalibrationCard({super.key, required this.detail, required this.disabled, required this.run});

  @override
  ConsumerState<CalibrationCard> createState() => _CalibrationCardState();
}

class _CalibrationCardState extends ConsumerState<CalibrationCard> {
  bool _manual = false;
  String? _fileName;
  Map<String, dynamic>? _fileBody;
  String? _fileError;

  final Map<String, bool> _checks = {for (final k in calibrationChecklist) k: false};
  final _offset = TextEditingController();
  final _points = [for (var i = 0; i < 9; i++) TextEditingController()];

  @override
  void dispose() {
    _offset.dispose();
    for (final c in _points) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _pickFile() async {
    final t = ref.read(tProvider);
    final file = await openFile(acceptedTypeGroups: const [XTypeGroup(label: 'JSON', extensions: ['json'])]);
    if (file == null || !mounted) return;
    final text = await file.readAsString();
    if (!mounted) return;
    setState(() {
      _fileName = file.name;
      try {
        _fileBody = readCalibrationFile(text);
        _fileError = null;
      } on CalibrationFileError catch (e) {
        _fileBody = null;
        _fileError = e.key == 'td.cal.todo' ? t(e.key, {'list': e.paths.join(', ')}) : t(e.key);
      }
    });
  }

  double? _num(TextEditingController c) => double.tryParse(c.text.trim().replaceAll(',', '.'));

  /// The hand-typed body, or the translation key of what is wrong with it.
  (Map<String, dynamic>?, String?) _manualBody() {
    final offset = _num(_offset);
    final values = [for (final c in _points) _num(c)];
    if (offset == null || values.any((v) => v == null)) return (null, 'td.cal.number');
    final points = [for (var i = 0; i < 3; i++) (x: values[i * 3]!, y: values[i * 3 + 1]!, z: values[i * 3 + 2]!)];
    if (!probePlaneValid(points)) return (null, 'td.cal.line');
    return (manualCalibration(checklist: _checks, forceZeroOffset: offset, points: points), null);
  }

  Future<void> _send(Map<String, dynamic> body) async {
    final t = ref.read(tProvider);
    final d = widget.detail;
    final clears = d.job.simulationPassed != null || d.calibration != null;
    final ok = await widget.run(
      () => ref.read(techApiProvider).calibrate(d.job.id, body),
      confirm: clears ? t('td.cal.confirmRedo') : null,
    );
    if (ok && mounted) {
      setState(() {
        _fileBody = null;
        _fileName = null;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(tProvider);
    final cal = widget.detail.calibration;
    final off = widget.disabled;
    final (manualBody, manualError) = _manualBody();
    final anyTyped = _offset.text.isNotEmpty || _points.any((c) => c.text.isNotEmpty);

    Widget modeButton(String label, bool on, VoidCallback tap) => TechButton(
          label,
          small: true,
          style: on ? CustomButtonStyle.primary : CustomButtonStyle.outline,
          onPressed: off ? null : tap,
        );

    return TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(
            t('tw.step.calibrate'),
            tag: cal == null ? null : t(cal.isValid ? 'td.api.passed' : 'td.api.notPassed'),
          ),
          Text(t('td.cal.clears'), style: const TextStyle(fontSize: 13, color: AppColors.warning, height: 1.4)),
          const SizedBox(height: 12),
          Wrap(spacing: 8, runSpacing: 8, children: [
            modeButton(t('td.cal.file'), !_manual, () => setState(() => _manual = false)),
            modeButton(t('td.cal.manual'), _manual, () => setState(() => _manual = true)),
          ]),
          const SizedBox(height: 16),
          if (!_manual) ...[
            Text(t('td.cal.help'), style: const TextStyle(fontSize: 13, color: AppColors.textSecondary, height: 1.4)),
            const SizedBox(height: 12),
            Wrap(spacing: 8, runSpacing: 8, children: [
              TechButton(t('td.cal.pickFile'), small: true, style: CustomButtonStyle.outline, icon: Icons.upload_file_rounded, onPressed: off ? null : _pickFile),
              TechButton(
                t('td.cal.send'),
                small: true,
                onPressed: off || _fileBody == null ? null : () => _send(_fileBody!),
              ),
            ]),
            if (_fileError != null || _fileBody != null) ...[
              const SizedBox(height: 10),
              Semantics(
                liveRegion: true,
                child: Text(
                  _fileError ?? t('td.cal.ready', {'name': _fileName ?? '', 'n': (_fileBody!['probe_points'] as List).length}),
                  style: TextStyle(fontSize: 13, height: 1.4, color: _fileError != null ? AppColors.error : AppColors.success),
                ),
              ),
            ],
          ] else ...[
            Label(t('td.cal.checklist')),
            // The card paints its own white; ticks and ripples need a Material of their own on top of it.
            Material(
              type: MaterialType.transparency,
              child: Column(
                children: [
                  for (final k in calibrationChecklist)
                    CheckboxListTile(
                      value: _checks[k],
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      controlAffinity: ListTileControlAffinity.leading,
                      title: Text(t('td.cal.chk.$k'), style: const TextStyle(fontSize: 14)),
                      onChanged: off ? null : (v) => setState(() => _checks[k] = v ?? false),
                    ),
                ],
              ),
            ),
            const SizedBox(height: 8),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 260),
              child: CustomTextField(
                label: t('td.cal.offset'),
                controller: _offset,
                enabled: !off,
                keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
                onChanged: (_) => setState(() {}),
              ),
            ),
            for (var p = 0; p < 3; p++) ...[
              const SizedBox(height: 12),
              Label(t('td.cal.point', {'n': p})),
              const SizedBox(height: 6),
              Row(
                children: [
                  for (var a = 0; a < 3; a++) ...[
                    if (a > 0) const SizedBox(width: 8),
                    Expanded(
                      child: CustomTextField(
                        label: const ['x', 'y', 'z'][a],
                        controller: _points[p * 3 + a],
                        enabled: !off,
                        keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
                        onChanged: (_) => setState(() {}),
                      ),
                    ),
                  ],
                ],
              ),
            ],
            if (anyTyped && manualError != null) ...[
              const SizedBox(height: 8),
              Text(t(manualError), style: const TextStyle(fontSize: 13, color: AppColors.error, height: 1.4)),
            ],
            const SizedBox(height: 12),
            Align(
              alignment: Alignment.centerLeft,
              child: TechButton(
                t('td.cal.send'),
                small: true,
                onPressed: off || manualBody == null || _checks.values.any((v) => !v) ? null : () => _send(manualBody),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

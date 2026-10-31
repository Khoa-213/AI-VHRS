import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/widgets/widgets.dart';
import '../../data/providers.dart';
import '../../data/tech_api.dart';
import '../../domain/job.dart';
import '../../domain/robot.dart';
import '../../i18n/tech_strings.dart';
import '../widgets/job_flow.dart';
import '../widgets/job_widgets.dart';
import '../widgets/robot_view_3d.dart';
import '../widgets/tech_shell.dart';
import '../widgets/tech_ui.dart';

/// The workshop runs the real arm only; MOCK and SIM stay on the workstation for testing.
const _mode = 'REAL';
const _loadable = [JobStatus.preparing, JobStatus.writing, JobStatus.paused];
final _authCode = RegExp(r'^AUTHORIZE-\S+$');

/// The agent's answer to a command, in words: a translated code when known, else its own message.
String commandError(RobotCommand c, T t) {
  if (c.status == CommandStatus.expired) return t('rb.err.expired');
  if (c.status == CommandStatus.cancelled) return t('rb.err.cancelled');
  final key = 'rb.agentErr.${c.errorCode}';
  final known = c.errorCode == null ? key : t(key);
  return known != key ? known : (c.errorMessage ?? c.errorCode ?? t('rb.err.failed'));
}

/// Robot control through the backend (FE `RobotConsole.tsx`): the app sends commands, the Robot
/// Agent on the workstation pulls and runs them on the real arm. Order of a job: LOAD, PREFLIGHT,
/// record the simulation, DRY_RUN (pen up), start writing, RUN, then PAUSE, RESUME, STOP. A
/// software Stop never replaces the physical E-Stop.
class RobotControlScreen extends ConsumerStatefulWidget {
  final int jobId;
  const RobotControlScreen({super.key, required this.jobId});

  @override
  ConsumerState<RobotControlScreen> createState() => _RobotControlScreenState();
}

class _RobotControlScreenState extends ConsumerState<RobotControlScreen> with JobRunner {
  @override
  int get runnerJobId => widget.jobId;

  final _auth = TextEditingController();
  final _resumeFrom = TextEditingController();
  bool _confirmUnknown = false;
  bool _advanced = false;
  bool _showHistory = false;
  RobotCommand? _pending;
  bool _controlBusy = false;
  String? _error;
  String? _notice;

  @override
  void dispose() {
    _auth.dispose();
    _resumeFrom.dispose();
    super.dispose();
  }

  /// A command that takes time (load, check, run). One at a time, followed until the agent answers.
  Future<void> _exec(CommandKind kind, {Map<String, dynamic> params = const {}, String? confirm}) async {
    if (_pending != null) return;
    final t = ref.read(tProvider);
    if (confirm != null && !await confirmAction(context, t, confirm)) return;
    if (!mounted) return;
    setState(() {
      _error = null;
      _notice = null;
    });
    final api = ref.read(robotApiProvider);
    try {
      final cmd = await api.sendCommand(kind, jobId: widget.jobId, params: params);
      if (!mounted) return;
      setState(() => _pending = cmd);
      final done = await api.waitCommand(
        cmd,
        onUpdate: (c) {
          if (mounted) setState(() => _pending = c);
        },
        cancelled: () => !mounted,
      );
      if (!mounted) return;
      setState(() {
        if (done.status == CommandStatus.done) {
          _notice = t('rb.done', {'kind': t('rb.kind.${kind.code}')});
        } else {
          _error = commandError(done, t);
        }
      });
    } catch (e) {
      if (mounted) setState(() => _error = techErrorText(t, e));
    }
    if (!mounted) return;
    setState(() => _pending = null);
    await refreshJob(ref, widget.jobId);
  }

  /// PAUSE, RESUME, STOP, PAPER_CHANGED: never wait behind a running command.
  Future<void> _control(CommandKind kind, {String? confirm}) async {
    if (_controlBusy) return;
    final t = ref.read(tProvider);
    if (confirm != null && !await confirmAction(context, t, confirm)) return;
    if (!mounted) return;
    setState(() {
      _controlBusy = true;
      _error = null;
    });
    final api = ref.read(robotApiProvider);
    try {
      final cmd = await api.sendCommand(kind, jobId: widget.jobId);
      final done = await api.waitCommand(cmd, cancelled: () => !mounted);
      if (mounted && done.status != CommandStatus.done) setState(() => _error = commandError(done, t));
    } catch (e) {
      if (mounted) setState(() => _error = techErrorText(t, e));
    }
    if (!mounted) return;
    setState(() => _controlBusy = false);
    await refreshJob(ref, widget.jobId);
  }

  Map<String, dynamic> _modeParams([Map<String, dynamic> extra = const {}]) => {'mode': _mode, 'authorization': _auth.text.trim(), ...extra};

  /// Backend and agent codes we have words for; anything new is shown as it came.
  String _label(T t, String key, String raw) {
    final s = t(key);
    return s == key ? raw : s;
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(tProvider);
    final q = ref.watch(techJobProvider(widget.jobId));
    final d = q.valueOrNull;
    final feedback = JobFeedback(loading: !q.hasValue && q.isLoading, error: q.hasError ? q.error : null, retry: () => reloadTechData(ref));
    if (d == null) {
      return TechPage(title: t('rb.title'), body: feedback);
    }
    final j = d.job;
    final disabled = flowBusy || q.hasError || q.isLoading;
    final liveQ = ref.watch(robotLiveProvider(j.robotId));
    final view = liveQ.valueOrNull;
    final live = view?.live;
    final frame = view?.frame;
    final status = ref.watch(robotStatusProvider).valueOrNull;
    final row = status?.where((r) => r.robotId == j.robotId).firstOrNull;
    final commands = ref.watch(jobCommandsProvider(j.id)).valueOrNull ?? const <RobotCommand>[];
    final verifiedPack = ref.watch(verifiedPackageProvider(j.id));
    final verified = verifiedPack != null && verifiedPack.hash == j.packageHash;

    // The workstation lists the modes it allows; without REAL nothing can run from here.
    final enabled = live?.status.enabledModes ?? const <String>[];
    final realEnabled = enabled.isEmpty || enabled.map((m) => m.toUpperCase()).contains(_mode);
    final online = live?.online ?? false;
    final busy = live?.status.busy ?? false;
    final agentState = frame?.state ?? live?.status.state ?? '';
    RobotCommand? latest(CommandKind k) => commands.where((c) => c.kind == k && c.jobId == j.id).firstOrNull;
    final load = latest(CommandKind.load);
    final loaded = load?.status == CommandStatus.done ? load : null;
    final preflight = latest(CommandKind.preflight);
    final loadResult = loaded?.result ?? const <String, dynamic>{};
    final validation = loadResult['validation'] as Map<String, dynamic>?;
    final pre = preflight?.status == CommandStatus.done ? preflight?.result : null;
    final authValid = _authCode.hasMatch(_auth.text.trim());
    final locked = disabled || _pending != null || !online || !realEnabled;
    final canLoad = _loadable.contains(j.status) && (d.calibration?.isValid ?? false);
    final simRecorded = j.simulationPassed == true;
    final writing = j.status == JobStatus.writing || j.status == JobStatus.paused;
    final paused = agentState == 'PAUSED';
    final pct = (frame?.progressPct ?? j.progress ?? 0).clamp(0, 100).round();
    final compact = isCompact(context);
    final code = j.orderCode.isEmpty ? '${j.orderId}' : j.orderCode;

    Future<void> recordSimulation() => run(() async {
          if (pre == null || preflight == null || loaded == null) return;
          final errors = <String>[
            for (final e in (validation?['errors'] as List<dynamic>? ?? const [])) '${(e as Map)['code']}: ${e['message']}',
            if (pre['ok'] != true) '${pre['code'] ?? 'PREFLIGHT_REFUSED'}: ${pre['message'] ?? ''}',
          ].map((s) => s.length > 500 ? s.substring(0, 500) : s).take(100).toList();
          final passed = pre['ok'] == true && validation?['passed'] != false && errors.isEmpty;
          final warnings = validation?['warnings'] as List<dynamic>?;
          final saved = await ref.read(techApiProvider).simulate(
            j.id,
            passed: passed,
            errors: errors,
            report: {
              'source': 'robot_agent',
              'mode': (pre['mode'] as String?)?.toUpperCase() ?? preflight.params['mode'],
              'load_command_id': loaded.id,
              'preflight_command_id': preflight.id,
              'plan_digest': loadResult['plan_digest'],
              'moves': pre['moves'],
              'checks': validation?['checks'],
              'warnings': warnings?.length ?? 0,
              'calibration_id': d.calibration?.id,
            },
          );
          // The server rebuilds the plan and may turn a claimed pass into a fail.
          if (passed && saved.simulationPassed == false) throw const TechFlowError('td.flow.simServerRejected');
        });

    final strip = Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
      child: Row(
        children: [
          MonoText('$pct%', color: AppColors.onInk),
          const SizedBox(width: 16),
          Expanded(child: _Bar(pct / 100, label: t('rb.progress'))),
          const SizedBox(width: 16),
          MonoText('${t('rb.stroke')} ${frame == null ? '–' : '${frame.stroke} / ${frame.totalStrokes}'}', size: 13, color: AppColors.onInkMuted),
        ],
      ),
    );
    final viewer = RobotView3D(robotId: j.robotId, robotCode: j.robotCode, height: compact ? 220 : 420, footer: ColoredBox(color: AppColors.inkSoft, child: strip));

    Widget tile(String label, String value) => TechCard(
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [Label(label), const SizedBox(height: 6), Text(value, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600))],
          ),
        );
    final telemetry = LayoutBuilder(builder: (context, c) {
      final cols = c.maxWidth >= 620 ? 4 : 2;
      final width = (c.maxWidth - (cols - 1) * 12) / cols;
      final force = frame?.forceN == null ? '–' : '${frame!.forceN!.toStringAsFixed(2)} N${frame.touching ? ' · ${t('rb.touching')}' : ''}';
      return Wrap(
        spacing: 12,
        runSpacing: 12,
        children: [
          for (final w in [
            tile(t('rb.agentState'), agentState.isEmpty ? '–' : _label(t, 'rb.agent.$agentState', agentState)),
            tile(t('rb.force'), force),
            tile(t('rb.tcp'), frame?.tcp == null ? '–' : frame!.tcp!.take(3).map((v) => v.toStringAsFixed(1)).join(', ')),
            tile(t('rb.lastSeen'), live?.ageS == null ? '–' : t('rb.secondsAgo', {'n': live!.ageS!.round()})),
          ])
            SizedBox(width: width, child: w),
        ],
      );
    });

    final stopEnabled = online && !_controlBusy && busy;
    final goEnabled = !locked && !busy && loaded != null && writing && authValid;
    final runButtons = Row(
      children: [
        Expanded(
          child: _BigButton(
            label: t('rb.kind.RUN'),
            icon: Icons.play_arrow_rounded,
            bg: AppColors.ink,
            fg: AppColors.onInk,
            onTap: !goEnabled
                ? null
                : () {
                    final from = int.tryParse(_resumeFrom.text.trim());
                    _exec(
                      CommandKind.run,
                      params: _modeParams({
                        if (from != null) 'resume_from': from,
                        if (_confirmUnknown) 'confirm_unknown': true,
                      }),
                      confirm: t('rb.confirmReal'),
                    );
                  },
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: paused
              ? _BigButton(
                  label: t('rb.do.RESUME'),
                  icon: Icons.play_arrow_outlined,
                  bg: AppColors.surface,
                  fg: AppColors.textPrimary,
                  border: AppColors.border,
                  onTap: stopEnabled ? () => _control(CommandKind.resume) : null,
                )
              : _BigButton(
                  label: t('rb.do.PAUSE'),
                  icon: Icons.pause_rounded,
                  bg: AppColors.surface,
                  fg: AppColors.textPrimary,
                  border: AppColors.border,
                  onTap: stopEnabled ? () => _control(CommandKind.pause) : null,
                ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: _BigButton(
            label: t('rb.do.STOP'),
            icon: Icons.stop_rounded,
            bg: AppColors.alarm,
            fg: Colors.white,
            onTap: stopEnabled ? () => _control(CommandKind.stop, confirm: t('rb.confirmStop')) : null,
          ),
        ),
      ],
    );

    final badges = Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        StatusPill(t(online ? 'rb.online' : 'rb.offline'), online ? AppColors.success : AppColors.error),
        StatusPill(_label(t, 'rb.mode.$_mode', _mode), AppColors.ink),
        if (row != null && row.state != RobotHealth.unknown) StatusPill(t('rb.state.${row.state.code}'), robotHealthColor(row.state)),
        if (busy) StatusPill(t('rb.busy'), AppColors.warning),
      ],
    );

    Widget errorText(String s) => Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Semantics(liveRegion: true, child: Text(s, style: const TextStyle(fontSize: 13, color: AppColors.error, height: 1.4))),
        );

    final last = live?.status.last;
    final consoleCard = TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('rb.title')),
          badges,
          if (live != null && !realEnabled) errorText(t('rb.realDisabled')),
          if (liveQ.hasError && live == null) errorText(techErrorText(t, liveQ.error)),
          if (_error != null) errorText(_error!),
          if (_pending != null || _notice != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Semantics(
                liveRegion: true,
                child: Text(
                  _pending != null
                      ? t('rb.waiting', {'kind': t('rb.kind.${_pending!.kind.code}'), 'status': t('rb.cmd.${_pending!.status.code}')})
                      : _notice!,
                  style: const TextStyle(fontSize: 13, color: AppColors.textSecondary, height: 1.4),
                ),
              ),
            ),
          const SizedBox(height: 14),
          // The operator types this code each time. It is never filled in for them.
          TextFormField(
            controller: _auth,
            autocorrect: false,
            enableSuggestions: false,
            onChanged: (_) => setState(() {}),
            decoration: InputDecoration(
              labelText: t('rb.authLabel'),
              hintText: (loadResult['authorization_token'] as String?) ?? t('rb.authPlaceholder'),
            ),
          ),
          if (frame?.jointsDeg != null) ...[
            const SizedBox(height: 8),
            Text(
              [for (final (i, v) in frame!.jointsDeg!.indexed) 'J${i + 1} ${v.toStringAsFixed(1)}°'].join('  '),
              style: const TextStyle(fontSize: 11, color: AppColors.textSecondary, fontFeatures: [FontFeature.tabularFigures()]),
            ),
          ],
          if (!compact) ...[const SizedBox(height: 14), runButtons],
          if (agentState == 'AWAITING_PAPER') ...[
            const SizedBox(height: 8),
            TechButton(t('rb.do.PAPER_CHANGED'), expand: true, onPressed: online && !_controlBusy ? () => _control(CommandKind.paperChanged) : null),
          ],
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: () => setState(() => _advanced = !_advanced),
              icon: Icon(_advanced ? Icons.expand_less_rounded : Icons.expand_more_rounded, size: 18),
              label: Text(t('td.flow.advanced')),
            ),
          ),
          if (_advanced) ...[
            CustomTextField(label: t('rb.resumeFrom'), controller: _resumeFrom, keyboardType: TextInputType.number),
            CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              controlAffinity: ListTileControlAffinity.leading,
              value: _confirmUnknown,
              onChanged: (v) => setState(() => _confirmUnknown = v ?? false),
              title: Text(t('rb.confirmUnknown'), style: const TextStyle(fontSize: 13)),
            ),
            Align(
              alignment: Alignment.centerLeft,
              child: Tooltip(
                message: t('rb.help.ALIGN_START'),
                child: TechButton(
                  t('rb.do.ALIGN_START'),
                  small: true,
                  style: CustomButtonStyle.outline,
                  onPressed: locked || busy || loaded == null || !authValid
                      ? null
                      : () => _exec(CommandKind.alignStart, params: _modeParams(), confirm: t('rb.confirmReal')),
                ),
              ),
            ),
          ],
          if (last != null && !busy) ...[
            const SizedBox(height: 8),
            Text(t('rb.lastRun'), style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
            if (last['refused'] case final Map<String, dynamic> r) errorText('${r['code']}: ${r['message']}'),
            if (last['error'] case final String e) errorText(e),
            if (last['result'] != null)
              SelectableText(
                const JsonEncoder.withIndent('  ').convert(last['result']),
                style: const TextStyle(fontSize: 11, color: AppColors.textSecondary),
              ),
          ],
        ],
      ),
    );

    Widget stepRow(int n, String title, bool? ok, Widget button, {Widget? result}) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Container(
                    width: 22,
                    height: 22,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: ok == true ? AppColors.ink : AppColors.surface,
                      borderRadius: BorderRadius.circular(7),
                      border: Border.all(color: ok == true ? AppColors.ink : (ok == false ? AppColors.warning : AppColors.textTertiary), width: 1.4),
                    ),
                    child: ok == true
                        ? const Icon(Icons.check_rounded, size: 16, color: AppColors.onInk)
                        : Text('$n', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600)),
                  ),
                  const SizedBox(width: 14),
                  Expanded(child: Text(title, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600))),
                  if (ok != null) ...[
                    const SizedBox(width: 8),
                    Flexible(child: Align(alignment: Alignment.centerRight, child: StatusPill(t(ok ? 'rb.stepDone' : 'rb.stepTodo'), ok ? AppColors.success : AppColors.warning))),
                  ],
                ],
              ),
              const SizedBox(height: 8),
              Align(alignment: Alignment.centerLeft, child: button),
              ?result,
            ],
          ),
        );
    Widget resultText(String s, {bool bad = false}) => Padding(
          padding: const EdgeInsets.only(top: 6),
          child: Text(s, style: TextStyle(fontSize: 13, height: 1.4, color: bad ? AppColors.error : AppColors.textSecondary)),
        );

    final estimated = (loadResult['estimated_seconds'] as num?)?.round();
    final loadSummary = [
      t('rb.loadSummary', {'pages': loadResult['pages'] ?? '–', 'strokes': loadResult['strokes'] ?? '–'}),
      if (estimated != null) t('rb.seconds', {'n': estimated}),
    ].join(' · ');
    final validationErrors = validation?['passed'] == false
        ? (validation?['errors'] as List<dynamic>? ?? const []).map((e) => (e as Map)['code']).join(', ')
        : null;

    final prepareCard = TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('rb.prepare')),
          stepRow(
            1,
            t('rb.kind.LOAD'),
            loaded != null ? true : (load != null && load.status != CommandStatus.done ? false : null),
            Tooltip(
              message: t(canLoad ? 'rb.help.LOAD' : 'rb.help.loadBlocked'),
              child: TechButton(t('rb.do.LOAD'), small: true, onPressed: locked || busy || !canLoad ? null : () => _exec(CommandKind.load)),
            ),
            result: loaded != null
                ? Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [resultText(loadSummary), if (validationErrors != null) resultText(validationErrors, bad: true)],
                  )
                : (load != null ? resultText(commandError(load, t), bad: true) : null),
          ),
          stepRow(
            2,
            t('rb.kind.PREFLIGHT'),
            pre != null ? pre['ok'] == true : (preflight != null && preflight.status != CommandStatus.done ? false : null),
            Tooltip(
              message: t('rb.help.PREFLIGHT'),
              child: TechButton(
                t('rb.do.PREFLIGHT', {'mode': _mode}),
                small: true,
                onPressed: locked || busy || loaded == null ? null : () => _exec(CommandKind.preflight, params: {'mode': _mode}),
              ),
            ),
            result: pre != null
                ? (pre['ok'] == true
                    ? resultText(t('rb.preflightOk', {'n': pre['moves'] ?? 0, 'mode': _mode}))
                    : resultText('${pre['code']}: ${pre['message']}', bad: true))
                : (preflight != null ? resultText(commandError(preflight, t), bad: true) : null),
          ),
          stepRow(
            3,
            t('rb.recordSim'),
            j.simulationPassed == null ? null : simRecorded,
            Tooltip(
              message: t('rb.help.record'),
              child: TechButton(
                t('rb.do.record'),
                small: true,
                onPressed: disabled || _pending != null || j.status != JobStatus.preparing || pre == null || loaded == null ? null : recordSimulation,
              ),
            ),
          ),
          stepRow(
            4,
            t('rb.kind.DRY_RUN'),
            null,
            Tooltip(
              message: t('rb.help.DRY_RUN'),
              child: TechButton(
                t('rb.do.DRY_RUN', {'mode': _mode}),
                small: true,
                onPressed: locked || busy || loaded == null || !(j.status == JobStatus.preparing || j.status == JobStatus.paused) || !authValid
                    ? null
                    : () => _exec(CommandKind.dryRun, params: _modeParams(), confirm: t('rb.confirmReal')),
              ),
            ),
          ),
          stepRow(
            5,
            t('td.flow.start'),
            j.status == JobStatus.preparing ? null : writing,
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                if (!verified)
                  TechButton(t('dk.control.preparing'), small: true, style: CustomButtonStyle.outline, onPressed: disabled ? null : () => run(() => downloadPackage(ref, j.id))),
                TechButton(
                  t('td.flow.start'),
                  small: true,
                  onPressed: disabled || _pending != null || j.status != JobStatus.preparing || !verified || !d.canStart
                      ? null
                      : () => run(() => ref.read(techApiProvider).start(j.id), confirm: t('td.flow.confirmStart')),
                ),
              ],
            ),
            result: Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Wrap(
                spacing: 8,
                runSpacing: 4,
                children: [
                  for (final (key, ok) in [
                    ('td.flow.verified', verified),
                    ('td.api.calibration', d.calibration?.isValid ?? false),
                    ('td.api.simulation', simRecorded),
                  ])
                    StatusPill(t(key), ok ? AppColors.success : AppColors.textSecondary),
                ],
              ),
            ),
          ),
        ],
      ),
    );

    final historyCard = TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: () => setState(() => _showHistory = !_showHistory),
              icon: Icon(_showHistory ? Icons.expand_less_rounded : Icons.expand_more_rounded, size: 18),
              label: Text(t('rb.history', {'n': commands.length})),
            ),
          ),
          if (_showHistory)
            for (final c in commands)
              Container(
                padding: const EdgeInsets.symmetric(vertical: 10),
                decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: AppColors.divider))),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(child: Text('${jobStamp(t, c.createdAt)} · ${_label(t, 'rb.kind.${c.kind.code}', c.kind.code)}', style: const TextStyle(fontSize: 14))),
                        Flexible(
                          child: Align(
                            alignment: Alignment.centerRight,
                            child: StatusPill(
                              _label(t, 'rb.cmd.${c.status.code}', c.status.code),
                              c.status == CommandStatus.done
                                  ? AppColors.success
                                  : (c.status == CommandStatus.failed || c.status == CommandStatus.expired ? AppColors.error : AppColors.textSecondary),
                            ),
                          ),
                        ),
                      ],
                    ),
                    if (c.status != CommandStatus.done && (c.errorCode != null || c.errorMessage != null))
                      resultText(commandError(c, t)),
                  ],
                ),
              ),
        ],
      ),
    );

    final page = TechPage(
      title: '$code · ${t('td.api.jobId', {'id': j.id})}',
      subtitle: [j.robotCode, d.paper, d.pen, d.ink].whereType<String>().where((s) => s.isNotEmpty).map(t.tn).join(' · '),
      actions: [
        TechButton(t('td.api.back'), small: true, style: CustomButtonStyle.outline, icon: Icons.arrow_back_rounded, onPressed: () => context.go(jobPath(j.id))),
        TechButton(t('td.api.reload'), small: true, style: CustomButtonStyle.outline, onPressed: () => reloadTechData(ref)),
      ],
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          feedback,
          FlowMessages(busy: flowBusy, error: flowError, notice: flowNotice),
          LayoutBuilder(builder: (context, c) {
            if (c.maxWidth < 980) {
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  viewer,
                  const SizedBox(height: 16),
                  consoleCard,
                  const SizedBox(height: 16),
                  telemetry,
                  const SizedBox(height: 16),
                  prepareCard,
                  const SizedBox(height: 16),
                  historyCard,
                ],
              );
            }
            return Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [viewer, const SizedBox(height: 16), telemetry, const SizedBox(height: 16), historyCard],
                  ),
                ),
                const SizedBox(width: 16),
                SizedBox(
                  width: 400,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [consoleCard, const SizedBox(height: 16), prepareCard],
                  ),
                ),
              ],
            );
          }),
        ],
      ),
    );
    if (!compact) return page;
    // On a phone the Run, Pause and Stop buttons stay in reach while the page scrolls.
    return Column(
      children: [
        Expanded(child: page),
        Container(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
          decoration: const BoxDecoration(
            color: AppColors.background,
            border: Border(top: BorderSide(color: AppColors.divider)),
          ),
          child: runButtons,
        ),
      ],
    );
  }
}

class _Bar extends StatelessWidget {
  final double value;
  final String label;
  const _Bar(this.value, {required this.label});

  @override
  Widget build(BuildContext context) => Semantics(
        label: label,
        value: '${(value * 100).round()}%',
        child: ClipRRect(
          borderRadius: BorderRadius.circular(6),
          child: SizedBox(
            height: 6,
            child: Stack(
              children: [
                Container(color: AppColors.primaryLight),
                FractionallySizedBox(widthFactor: value.clamp(0.0, 1.0), child: Container(color: const Color(0xFF6FBF8B))),
              ],
            ),
          ),
        ),
      );
}

class _BigButton extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color bg;
  final Color fg;
  final Color? border;
  final VoidCallback? onTap;
  const _BigButton({required this.label, required this.icon, required this.bg, required this.fg, this.border, this.onTap});

  @override
  Widget build(BuildContext context) => MouseRegion(
        cursor: onTap == null ? SystemMouseCursors.forbidden : SystemMouseCursors.click,
        child: Pressable(
          onTap: onTap,
          semanticLabel: label,
          child: Container(
            constraints: const BoxConstraints(minHeight: 64),
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 8),
            decoration: BoxDecoration(
              color: bg,
              borderRadius: BorderRadius.circular(TechRadius.control),
              border: border == null ? null : Border.all(color: border!, width: 1.2),
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(icon, size: 20, color: fg),
                const SizedBox(height: 4),
                Text(label, textAlign: TextAlign.center, style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: fg)),
              ],
            ),
          ),
        ),
      );
}

import 'dart:io';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/widgets/widgets.dart';
import '../../data/providers.dart';
import '../../domain/job.dart';
import '../../domain/robot.dart';
import '../../i18n/tech_strings.dart';
import 'job_flow.dart';
import 'job_sections.dart';
import 'job_setup.dart';
import 'job_stock.dart';
import 'job_widgets.dart';
import 'job_workspace.dart';
import 'real_switch.dart';
import 'tech_shell.dart';
import 'tech_ui.dart';

/// The open job: assignment, materials, progress and its workflow up to writing finished. Robot
/// control and the QC photos have their own pages, reached from the buttons here.
class JobDetailPane extends ConsumerStatefulWidget {
  final int jobId;
  const JobDetailPane({super.key, required this.jobId});

  @override
  ConsumerState<JobDetailPane> createState() => _JobDetailPaneState();
}

class _JobDetailPaneState extends ConsumerState<JobDetailPane> with JobRunner {
  @override
  int get runnerJobId => widget.jobId;

  bool _manualOpen = false;

  /// The step the technician opened; null follows the current step.
  String? _pickKey;
  String _simResult = '';
  final _simErrors = TextEditingController();

  @override
  void dispose() {
    _simErrors.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(tProvider);
    final q = ref.watch(techJobProvider(widget.jobId));
    final d = q.valueOrNull;
    final feedback = JobFeedback(
      loading: !q.hasValue && q.isLoading,
      error: q.hasError ? q.error : null,
      retry: () => reloadTechData(ref),
    );
    if (d == null) return feedback;

    final j = d.job;
    final code = j.orderCode.isEmpty ? '${j.orderId}' : j.orderCode;
    final pct = (j.progress ?? 0).clamp(0, 100).toDouble();
    final verified = ref.watch(verifiedPackageProvider(j.id));
    final current = verified?.hash == j.packageHash ? verified : null;
    final gates = d.permissions(verified?.hash);
    final disabled = flowBusy || q.hasError || q.isLoading;
    final canControl = previewJobStatuses.contains(j.status);
    final hasPhotos = const [JobStatus.written, JobStatus.photoUploaded, JobStatus.done, JobStatus.rewriteRequired].contains(j.status);

    Widget fact(String label, String value) => Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          decoration: BoxDecoration(
            border: Border.all(color: AppColors.border),
            borderRadius: BorderRadius.circular(TechRadius.card),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [Label(label), const SizedBox(height: 6), Text(value, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600))],
          ),
        );
    final orderType = t('ot.${d.orderType}');

    final summary = TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Wrap(
            spacing: 12,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text(code, style: Theme.of(context).textTheme.headlineLarge),
              JobStatusPill(j.status),
              // A job without a robot yet has nothing to control: the robot is chosen below first.
              if (canControl && j.robotId != null)
                TechButton(t('rb.title'), small: true, onPressed: () => context.go('${jobPath(j.id)}/control')),
              if (hasPhotos)
                TechButton(t('td.flow.photos'), small: true, onPressed: () => context.go('/tech/qc/${j.id}')),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            [
              t('td.api.jobId', {'id': j.id}),
              if (orderType != 'ot.${d.orderType}') orderType,
              '${t('po.pieces')}: ${d.quantity}',
              if (j.isRewrite) t('wk.rewrite'),
            ].join(' · '),
            style: const TextStyle(fontSize: 13, color: AppColors.textSecondary),
          ),
          const SizedBox(height: 16),
          // Four across when they fit, otherwise two: same width either way.
          LayoutBuilder(builder: (context, c) {
            final cols = c.maxWidth >= 620 ? 4 : 2;
            final width = (c.maxWidth - (cols - 1) * 12) / cols;
            return Wrap(
              spacing: 12,
              runSpacing: 12,
              children: [
                for (final f in [
                  fact(t('po.robot'), jobRobotLabel(t, j)),
                  fact(t('td.api.slotStart'), jobStamp(t, j.slotStart)),
                  fact(t('td.api.slotEnd'), jobStamp(t, j.slotEnd)),
                  fact(t('po.time'), t('td.min', {'n': j.durationMin})),
                ])
                  SizedBox(width: width, child: f),
              ],
            );
          }),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(child: Meter(pct / 100, semanticLabel: t('td.api.progress'))),
              const SizedBox(width: 12),
              MonoText('${pct.round()}%'),
            ],
          ),
        ],
      ),
    );

    final package = !gates.download
        ? null
        : TechCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                CardHead(t('td.flow.package')),
                Align(
                  alignment: Alignment.centerLeft,
                  child: StatusPill(t(current != null ? 'td.flow.verified' : 'td.flow.verifyRequired'), current != null ? AppColors.success : AppColors.warning),
                ),
                const SizedBox(height: 8),
                Text(t('td.flow.packageHelp'), style: const TextStyle(fontSize: 13, color: AppColors.textSecondary, height: 1.4)),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    TechButton(
                      t('td.flow.download'),
                      small: true,
                      onPressed: disabled ? null : () => run(() => downloadPackage(ref, j.id)),
                    ),
                    if (current != null && (Platform.isWindows || Platform.isMacOS || Platform.isLinux))
                      TechButton(
                        t('td.flow.saveFile'),
                        small: true,
                        style: CustomButtonStyle.outline,
                        onPressed: () async {
                          final name = 'job-${j.id}-trajectory.json';
                          final to = await getSaveLocation(suggestedName: name);
                          if (to != null) {
                            await XFile.fromData(current.bytes, mimeType: 'application/json', name: name).saveTo(to.path);
                          }
                        },
                      ),
                  ],
                ),
                if (current != null) ...[
                  const SizedBox(height: 12),
                  SelectableText(current.hash, style: const TextStyle(fontSize: 12, color: AppColors.textSecondary, fontFeatures: [FontFeature.tabularFigures()])),
                  const SizedBox(height: 6),
                  Text(t(current.info.signed ? 'td.pkg.signed' : 'td.pkg.legacy'), style: const TextStyle(fontSize: 13, color: AppColors.textSecondary, height: 1.4)),
                  if (current.info.materialDrift.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Semantics(
                      liveRegion: true,
                      child: Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: AppColors.warning.withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(t('td.pkg.drift'), style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, height: 1.4)),
                            for (final d in current.info.materialDrift)
                              Text('• $d', style: const TextStyle(fontSize: 13, height: 1.4)),
                          ],
                        ),
                      ),
                    ),
                  ],
                  if (current.info.pen case final pen?) ...[
                    const SizedBox(height: 8),
                    FactList([
                      (t('td.flow.forceBand'), valueText('${pen.fMinN} / ${pen.fTargetN} / ${pen.fMaxN} N')),
                      (t('td.flow.forceHard'), valueText('${pen.fHardN} N')),
                      (t('td.flow.speed'), valueText('${pen.vMaxMmS} mm/s')),
                    ]),
                  ],
                  const SizedBox(height: 12),
                  TrajectoryPreview(pages: current.pages),
                  const SizedBox(height: 8),
                  Text(t('td.flow.previewOnly'), style: const TextStyle(fontSize: 12, color: AppColors.textSecondary, height: 1.4)),
                ],
              ],
            ),
          );

    final errorLines = _simErrors.text.split('\n').map((v) => v.trim()).where((v) => v.isNotEmpty).toList();
    final simConsistent = _simResult.isNotEmpty &&
        errorLines.length <= 100 &&
        errorLines.every((v) => v.length <= 500) &&
        (_simResult != 'pass' || errorLines.isEmpty);

    // 0033 (Q3): Prepare waits until the job's paper is taken from the shelf.
    final stockReady = stockLetsPrepare(ref.watch(jobStockProvider(j.id)));
    final Widget prepareCard = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        StockIssueCard(jobId: j.id, disabled: disabled, run: run),
        const SizedBox(height: 16),
        TechCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                CardHead(t('td.flow.prepare')),
                Text(t('td.flow.prepareHelp'), style: const TextStyle(fontSize: 13, color: AppColors.textSecondary, height: 1.4)),
                if (!stockReady) ...[
                  const SizedBox(height: 6),
                  Text(t('dk.st.prepareWait'), style: const TextStyle(fontSize: 13, color: AppColors.warning, height: 1.4)),
                ],
                const SizedBox(height: 12),
                Align(
                  alignment: Alignment.centerLeft,
                  child: TechButton(
                    t('td.flow.prepare'),
                    small: true,
                    onPressed: disabled || !gates.prepare || !stockReady ? null : () => run(() => ref.read(techApiProvider).prepare(j.id)),
                  ),
                ),
              ],
            ),
          ),
      ],
    );
    final Widget simulationCard = TechCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                CardHead(t('td.api.simulation')),
                Text(t('td.flow.simulationHelp'), style: const TextStyle(fontSize: 13, color: AppColors.textSecondary, height: 1.4)),
                const SizedBox(height: 8),
                Align(
                  alignment: Alignment.centerLeft,
                  child: TextButton.icon(
                    onPressed: () => setState(() => _manualOpen = !_manualOpen),
                    icon: Icon(_manualOpen ? Icons.expand_less_rounded : Icons.expand_more_rounded, size: 18),
                    label: Text(t('td.flow.manualSimulation')),
                  ),
                ),
                if (_manualOpen) ...[
                  Text(t('td.flow.manualSimulationHelp'), style: const TextStyle(fontSize: 13, color: AppColors.warning, height: 1.4)),
                  const SizedBox(height: 12),
                  FlowSelect<String>(
                    label: t('td.flow.result'),
                    value: _simResult,
                    options: {'': t('td.flow.choose'), 'pass': t('td.api.passed'), 'fail': t('td.api.notPassed')},
                    onChanged: disabled || !gates.simulate ? null : (v) => setState(() => _simResult = v),
                  ),
                  const SizedBox(height: 12),
                  CustomTextField(
                    label: t('td.flow.simulationErrors'),
                    controller: _simErrors,
                    maxLines: 4,
                    enabled: !disabled && gates.simulate,
                    onChanged: (_) => setState(() {}),
                  ),
                  if (_simResult == 'pass' && errorLines.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Text(t('td.flow.inconsistent'), style: const TextStyle(fontSize: 13, color: AppColors.error)),
                  ],
                  const SizedBox(height: 12),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: TechButton(
                      t('td.flow.saveSimulation'),
                      small: true,
                      onPressed: disabled || !gates.simulate || !simConsistent
                          ? null
                          : () => run(() => ref.read(techApiProvider).simulate(
                                j.id,
                                passed: _simResult == 'pass',
                                errors: errorLines,
                                report: {'source': 'desktop_manual', 'calibration_id': d.calibration?.id},
                              )),
                    ),
                  ),
                ],
              ],
            ),
          );
    final Widget finishCard = FinishStockCard(jobId: j.id, disabled: disabled, run: run);

    final commands = ref.watch(jobCommandsProvider(j.id)).valueOrNull ?? const <RobotCommand>[];
    final steps = jobSteps(d, verified: current != null, commands: commands);
    final live = !const [JobStatus.cancelled, JobStatus.failed, JobStatus.rewriteRequired].contains(j.status);
    final now = live ? currentStepIndex(steps) : -1;
    final picked = _pickKey == null ? -1 : steps.indexWhere((s) => s.key == _pickKey);
    final fallback = now >= 0 ? now : (steps.lastIndexWhere((s) => s.done) + 1).clamp(0, steps.length - 1);
    final sel = picked >= 0 ? picked : fallback;
    final step = steps[sel];
    void pick(int i) => setState(() => _pickKey = i == now ? null : steps[i].key);

    final control = canControl && j.robotId != null
        ? TechCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(t('dk.ws.controlHelp'), style: const TextStyle(fontSize: 13, color: AppColors.textSecondary, height: 1.4)),
                const SizedBox(height: 12),
                Align(
                  alignment: Alignment.centerLeft,
                  child: TechButton(t('dk.ws.openControl'), small: true, onPressed: () => context.go('${jobPath(j.id)}/control')),
                ),
              ],
            ),
          )
        : null;
    final Widget? work = switch (step.key) {
      'package' => package,
      'robot' => gates.chooseRobot ? ChooseRobotCard(job: j, disabled: disabled, run: run) : null,
      'prepare' => j.status == JobStatus.scheduled ? prepareCard : null,
      'calibrate' => gates.calibrate ? CalibrationCard(detail: d, disabled: disabled, run: run) : null,
      'real' => step.why == null
          ? TechCard(child: RealSwitch(jobId: j.id, robotId: j.robotId, fallback: CopyCommand(command: realEnableCommand(j.id))))
          : null,
      'simulate' => j.status == JobStatus.preparing || j.status == JobStatus.paused ? simulationCard : null,
      'load' || 'preflight' || 'dryRun' || 'write' => control,
      'finish' => gates.finish ? finishCard : null,
      'photos' => hasPhotos
          ? TechCard(
              child: Align(
                alignment: Alignment.centerLeft,
                child: TechButton(t('dk.ws.openPhotos'), small: true, onPressed: () => context.go('/tech/qc/${j.id}')),
              ),
            )
          : null,
      _ => null,
    };

    final rail = StepRail(steps: steps, current: now, selected: sel, onSelect: pick);
    final center = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        FlowMessages(busy: flowBusy, error: flowError, notice: flowNotice),
        StepPanel(
          index: sel,
          total: steps.length,
          step: step,
          current: sel == now,
          work: work,
          onPrev: sel > 0 ? () => pick(sel - 1) : null,
          onNext: sel < steps.length - 1 ? () => pick(sel + 1) : null,
        ),
      ],
    );
    final reference = JobReferenceColumn(
      detail: d,
      verifiedPages: current?.pages,
      highlight: (stepUses[step.key] ?? const <String>[]).toSet(),
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        feedback,
        summary,
        const SizedBox(height: 12),
        Text(t('td.flow.scope'), style: const TextStyle(fontSize: 13, color: AppColors.warning, height: 1.4)),
        const SizedBox(height: 16),
        // Always the three columns of the design (steps | work of the step | sketch, materials, instructions), whatever
        // the step; the side columns narrow with the window. Only a phone-width window stacks them.
        LayoutBuilder(builder: (context, c) {
          if (c.maxWidth >= 860) {
            final railW = (c.maxWidth * 0.22).clamp(220.0, 280.0);
            final refW = (c.maxWidth * 0.28).clamp(280.0, 400.0);
            return Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(width: railW, child: rail),
                const SizedBox(width: 16),
                Expanded(child: center),
                const SizedBox(width: 16),
                SizedBox(width: refW, child: reference),
              ],
            );
          }
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [rail, const SizedBox(height: 16), center, const SizedBox(height: 16), reference],
          );
        }),
        const SizedBox(height: 16),
        JobEventCards(job: d, disabled: disabled, run: run),
        JobHistoryCards(job: d),
      ],
    );
  }
}

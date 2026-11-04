import 'dart:io';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/widgets/widgets.dart';
import '../../data/providers.dart';
import '../../domain/job.dart';
import '../../i18n/tech_strings.dart';
import 'job_flow.dart';
import 'job_sections.dart';
import 'job_widgets.dart';
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

    String name(String? s) => s == null ? t('td.api.unavailable') : t.tn(s);
    String stamp(DateTime? v) => v == null ? t('td.api.unavailable') : jobStamp(t, v);
    String outcome(bool? v) => t(v == null ? 'td.api.notRecorded' : v ? 'td.api.passed' : 'td.api.notPassed');
    Color outcomeColor(bool? v) => v == null ? AppColors.warning : v ? AppColors.success : AppColors.error;

    Widget step(String label, String value, Color color) => Container(
          padding: const EdgeInsets.symmetric(vertical: 10),
          decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: AppColors.divider))),
          child: Row(
            children: [
              Expanded(child: Text(label, style: const TextStyle(fontSize: 14))),
              const SizedBox(width: 12),
              Flexible(
                child: Text(value, textAlign: TextAlign.right, style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: color)),
              ),
            ],
          ),
        );
    Widget stampStep(String label, DateTime? v) =>
        step(label, stamp(v), v == null ? AppColors.textSecondary : AppColors.success);
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
              if (canControl)
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
                  fact(t('po.robot'), j.robotCode.isEmpty ? '${j.robotId}' : j.robotCode),
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

    final materials = TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('td.api.materials')),
          FactList([
            (t('po.paper'), valueText(name(d.paper))),
            (t('po.pen'), valueText(name(d.pen))),
            (t('po.ink'), valueText(name(d.ink))),
          ]),
          if (d.note != null) ...[
            const SizedBox(height: 12),
            Text(d.note!, style: const TextStyle(fontSize: 14, height: 1.5)),
          ],
        ],
      ),
    );
    final steps = TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('td.api.progress')),
          stampStep(t('td.api.downloaded'), j.downloadedAt),
          step(t('td.api.calibration'), outcome(d.calibration?.isValid), outcomeColor(d.calibration?.isValid)),
          step(t('td.api.simulation'), outcome(j.simulationPassed), outcomeColor(j.simulationPassed)),
          stampStep(t('td.api.started'), j.startedAt),
          stampStep(t('td.api.finished'), j.finishedAt),
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

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        feedback,
        summary,
        const SizedBox(height: 16),
        LayoutBuilder(builder: (context, c) {
          if (c.maxWidth < 640) {
            return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [materials, const SizedBox(height: 16), steps]);
          }
          return Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [Expanded(child: materials), const SizedBox(width: 16), Expanded(child: steps)],
          );
        }),
        const SizedBox(height: 16),
        Text(t('td.flow.scope'), style: const TextStyle(fontSize: 13, color: AppColors.warning, height: 1.4)),
        const SizedBox(height: 12),
        FlowMessages(busy: flowBusy, error: flowError, notice: flowNotice),
        if (package != null) ...[package, const SizedBox(height: 16)],
        if (j.status == JobStatus.scheduled) ...[
          TechCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                CardHead(t('td.flow.prepare')),
                Text(t('td.flow.prepareHelp'), style: const TextStyle(fontSize: 13, color: AppColors.textSecondary, height: 1.4)),
                const SizedBox(height: 12),
                Align(
                  alignment: Alignment.centerLeft,
                  child: TechButton(
                    t('td.flow.prepare'),
                    small: true,
                    onPressed: disabled || !gates.prepare ? null : () => run(() => ref.read(techApiProvider).prepare(j.id)),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
        ],
        if (j.status == JobStatus.preparing) ...[
          TechCard(
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
          ),
          const SizedBox(height: 16),
        ],
        JobEventCards(job: d, disabled: disabled, run: run),
        if (gates.finish) ...[
          TechCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                CardHead(t('td.flow.finish')),
                Text(t('td.flow.finishHelp'), style: const TextStyle(fontSize: 13, color: AppColors.textSecondary, height: 1.4)),
                const SizedBox(height: 12),
                Align(
                  alignment: Alignment.centerLeft,
                  child: TechButton(
                    t('td.flow.finish'),
                    small: true,
                    onPressed: disabled ? null : () => run(() => ref.read(techApiProvider).finish(j.id), confirm: t('td.flow.confirmFinish')),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
        ],
        JobHistoryCards(job: d),
      ],
    );
  }
}

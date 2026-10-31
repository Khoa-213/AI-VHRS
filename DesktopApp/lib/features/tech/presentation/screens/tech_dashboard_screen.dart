import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../core/widgets/widgets.dart';
import '../../../auth/domain/models/auth_state.dart';
import '../../../auth/presentation/auth_notifier.dart';
import '../../data/providers.dart';
import '../../domain/job.dart';
import '../../domain/robot.dart';
import '../../i18n/tech_strings.dart';
import '../widgets/job_widgets.dart';
import '../widgets/tech_shell.dart';
import '../widgets/tech_ui.dart';

const _groups = [
  (key: 'qc', statuses: [JobStatus.written]),
  (key: 'live', statuses: [JobStatus.writing, JobStatus.paused]),
  (key: 'ready', statuses: [JobStatus.scheduled, JobStatus.preparing]),
  (key: 'attention', statuses: [JobStatus.failed, JobStatus.rewriteRequired]),
  (key: 'history', statuses: [JobStatus.photoUploaded, JobStatus.done, JobStatus.cancelled]),
];

/// My jobs by what they need next, my robots and the waiting queue (FE `TechDashboard.tsx`).
class TechDashboardScreen extends ConsumerWidget {
  const TechDashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    final auth = ref.watch(authNotifierProvider);
    final name = auth is AuthAuthenticated ? auth.fullName : t('td.technician');
    final q = ref.watch(techJobsProvider);
    final status = ref.watch(robotStatusProvider).valueOrNull;
    final mine = q.valueOrNull ?? const <TechJob>[];
    final loaded = q.hasValue;

    List<TechJob> inStatus(List<JobStatus> s) => mine.where((j) => s.contains(j.status)).toList();
    final queued = inStatus(const [JobStatus.scheduled, JobStatus.preparing]);
    final open = inStatus(activeJobStatuses);
    final queueMinutes = queued.fold<int>(0, (a, j) => a + j.durationMin);
    final maxMin = queued.fold<int>(1, (a, j) => math.max(a, j.durationMin));
    final compact = isCompact(context);
    String count(int n) => loaded ? '$n' : '...';

    final tiles = [
      KpiTile(
        label: t('td.kpi.qc'),
        value: count(inStatus(const [JobStatus.written]).length),
        hint: t('td.kpi.qcHint'),
        accent: true,
        dense: compact,
        onTap: () => context.go('/tech/qc'),
      ),
      KpiTile(
        label: t('td.api.live'),
        value: count(inStatus(const [JobStatus.writing, JobStatus.paused]).length),
        hint: t('td.api.liveHint'),
        dense: compact,
        onTap: () => context.go('/tech/jobs'),
      ),
      KpiTile(
        label: t('td.api.ready'),
        value: count(queued.length),
        hint: t('td.api.readyHint'),
        dense: compact,
        onTap: () => context.go('/tech/jobs'),
      ),
    ];
    final kpis = IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (var i = 0; i < tiles.length; i++) ...[
            if (i > 0) SizedBox(width: compact ? 8 : 16),
            Expanded(child: tiles[i]),
          ],
        ],
      ),
    );

    final ordersCard = TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('td.api.myJobs'), tag: loaded ? t('td.assigned', {'n': mine.length}) : null),
          if (queued.isNotEmpty)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
              decoration: BoxDecoration(color: AppColors.surfaceVariant, borderRadius: BorderRadius.circular(TechRadius.inner)),
              child: Row(
                children: [
                  Expanded(child: Text(t('td.queueTime'), style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500, color: AppColors.secondaryLight))),
                  MonoText(t('td.min', {'n': queueMinutes}), size: 16),
                ],
              ),
            ),
          for (final g in _groups)
            if (inStatus(g.statuses).isNotEmpty) _Group(id: g.key, rows: inStatus(g.statuses)),
          if (loaded && mine.isEmpty && !q.hasError)
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(t('td.none'), style: const TextStyle(fontWeight: FontWeight.w600)),
                const SizedBox(height: 4),
                Text(t('td.api.noneBody'), style: const TextStyle(color: AppColors.textSecondary, height: 1.5)),
              ],
            ),
        ],
      ),
    );

    final robots = <int, TechJob>{for (final j in open) j.robotId: j};
    final robotsCard = TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('td.api.assignedRobots')),
          for (final r in robots.values)
            _RobotRow(
              job: r,
              status: status?.where((s) => s.robotId == r.robotId).firstOrNull,
              jobs: open.where((j) => j.robotId == r.robotId).toList(),
            ),
          if (loaded && robots.isEmpty && !q.hasError)
            Text(t('td.noRobots'), style: const TextStyle(color: AppColors.textSecondary)),
          const SizedBox(height: 12),
          Text(t('td.api.robotNote'), style: const TextStyle(fontSize: 12, color: AppColors.textSecondary, height: 1.4)),
        ],
      ),
    );

    final queueCard = TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('td.queueTitle')),
          if (loaded && queued.isEmpty && !q.hasError) Text(t('td.api.noQueued'), style: const TextStyle(color: AppColors.textSecondary)),
          for (final j in queued)
            MouseRegion(
              cursor: SystemMouseCursors.click,
              child: Pressable(
                onTap: () => context.go(jobPath(j.id)),
                semanticLabel: j.orderCode,
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 6),
                  child: Row(
                    children: [
                      SizedBox(
                        width: 104,
                        child: Text(j.orderCode.isEmpty ? '${j.orderId}' : j.orderCode,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AppColors.textSecondary)),
                      ),
                      Expanded(child: Meter(j.durationMin / maxMin, height: 8)),
                      const SizedBox(width: 12),
                      MonoText(t('td.min', {'n': j.durationMin}), size: 12),
                    ],
                  ),
                ),
              ),
            ),
          const SizedBox(height: 12),
          Text(t('td.api.queueNote'), style: const TextStyle(fontSize: 12, color: AppColors.textSecondary, height: 1.4)),
        ],
      ),
    );

    final today = DateFormat('EEEE d MMMM', t.locale).format(workshopTime(DateTime.now()));
    return TechPage(
      title: t('wk.hello', {'name': name}),
      subtitle: today,
      actions: [
        TechButton(
          t('td.api.reload'),
          small: true,
          style: CustomButtonStyle.outline,
          onPressed: () => reloadTechData(ref),
        ),
      ],
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          JobFeedback(loading: !loaded && q.isLoading, error: q.hasError ? q.error : null, retry: () => reloadTechData(ref)),
          LayoutBuilder(builder: (context, c) {
            final stats = Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [kpis, const SizedBox(height: 16), robotsCard, const SizedBox(height: 16), queueCard],
            );
            if (c.maxWidth < 1000) {
              return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [stats, const SizedBox(height: 16), ordersCard]);
            }
            return Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(flex: 5, child: ordersCard),
                const SizedBox(width: 16),
                Expanded(flex: 7, child: stats),
              ],
            );
          }),
        ],
      ),
    );
  }
}

/// One group of jobs; finished ones start folded away.
class _Group extends ConsumerStatefulWidget {
  final String id;
  final List<TechJob> rows;
  const _Group({required this.id, required this.rows});

  @override
  ConsumerState<_Group> createState() => _GroupState();
}

class _GroupState extends ConsumerState<_Group> {
  late bool _open = widget.id != 'history';

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(tProvider);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        MouseRegion(
          cursor: SystemMouseCursors.click,
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () => setState(() => _open = !_open),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(4, 16, 4, 8),
              child: Row(
                children: [
                  AnimatedRotation(
                    turns: _open ? 0.25 : 0,
                    duration: AppTheme.motionFast,
                    child: const Icon(Icons.chevron_right_rounded, size: 20, color: AppColors.textSecondary),
                  ),
                  const SizedBox(width: 6),
                  Expanded(child: Text(t('td.api.group.${widget.id}'), style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600))),
                  MonoText('${widget.rows.length}', size: 13, color: AppColors.textSecondary),
                ],
              ),
            ),
          ),
        ),
        if (_open)
          for (final j in widget.rows) JobRow(job: j),
      ],
    );
  }
}

class _RobotRow extends ConsumerWidget {
  final TechJob job;
  final RobotStatus? status;
  final List<TechJob> jobs;
  const _RobotRow({required this.job, required this.status, required this.jobs});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    final s = status;
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 12),
      decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: AppColors.divider))),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(child: MonoText(job.robotCode.isEmpty ? '${job.robotId}' : job.robotCode, size: 13)),
              if (s != null && s.state != RobotHealth.unknown) Flexible(child: Align(alignment: Alignment.centerRight, child: StatusPill(t('rb.state.${s.state.code}'), robotHealthColor(s.state)))),
            ],
          ),
          // The backend writes this sentence in Vietnamese only; it is shown as data.
          if (s != null && s.headline.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(s.headline, style: const TextStyle(fontSize: 12, color: AppColors.textSecondary, height: 1.4)),
          ],
          const SizedBox(height: 6),
          Wrap(
            spacing: 12,
            runSpacing: 4,
            children: [
              for (final j in jobs)
                MouseRegion(
                  cursor: SystemMouseCursors.click,
                  child: GestureDetector(
                    onTap: () => context.go(jobPath(j.id)),
                    child: Text('${j.orderCode.isEmpty ? j.orderId : j.orderCode} · ${jobStatusLabel(t, j.status)}',
                        style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500, decoration: TextDecoration.underline)),
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

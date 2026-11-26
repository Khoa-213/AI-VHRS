import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/widgets/widgets.dart';
import '../../data/providers.dart';
import '../../domain/job.dart';
import '../../domain/robot.dart';
import '../../i18n/tech_strings.dart';
import 'job_widgets.dart';
import 'tech_ui.dart';

/// Connection chip colour: the link to the Robot Agent, kept apart from what the robot is doing.
Color robotLinkColor(String connection) => switch (connection) {
      'ONLINE' => AppColors.success,
      'OFFLINE' => AppColors.textSecondary,
      _ => AppColors.textTertiary,
    };

String robotLinkLabel(T t, String connection) => t('tw.link.${const ['ONLINE', 'OFFLINE'].contains(connection) ? connection : 'UNKNOWN'}');

Color alertLevelColor(int level) => level >= 4
    ? AppColors.alarm
    : level == 3
        ? AppColors.error
        : level == 2
            ? AppColors.warning
            : AppColors.textSecondary;

/// "My robots": the robots the Manager gave me (`GET /technician/robots`, migration 0032), with the line "Connected online / total
/// · Working active" above the cards. A card filters my jobs by that robot ([onPick]); [picked] is the robot filtered now.
class MyRobotsStrip extends ConsumerWidget {
  final int? picked;
  final ValueChanged<int?>? onPick;
  const MyRobotsStrip({super.key, this.picked, this.onPick});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    final q = ref.watch(myRobotsProvider);
    final m = q.valueOrNull;

    return TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // The summary goes under the title, not beside it: in Vietnamese it does not fit next to it on a phone.
          Text(t('tw.robots.title'), style: Theme.of(context).textTheme.headlineSmall),
          if (m != null) ...[
            const SizedBox(height: 4),
            MonoText(t('tw.robots.summary', {'online': m.online, 'total': m.total, 'active': m.active}), size: 13, color: AppColors.textSecondary),
          ],
          const SizedBox(height: 16),
          if (m == null && q.hasError) Text(techErrorText(t, q.error), style: const TextStyle(fontSize: 14, color: AppColors.error, height: 1.4)),
          if (m == null && !q.hasError) const LinearProgressIndicator(minHeight: 2),
          if (m != null && m.robots.isEmpty)
            Text(t('tw.robots.none'), style: const TextStyle(fontSize: 14, color: AppColors.textSecondary, height: 1.5)),
          if (m != null && m.robots.isNotEmpty)
            LayoutBuilder(builder: (context, c) {
              final cols = c.maxWidth >= 1000 ? 3 : (c.maxWidth >= 600 ? 2 : 1);
              final width = (c.maxWidth - (cols - 1) * 12) / cols;
              return Wrap(
                spacing: 12,
                runSpacing: 12,
                children: [
                  for (final r in m.robots)
                    SizedBox(
                      width: width,
                      child: RobotCard(
                        robot: r,
                        selected: picked == r.robotId,
                        onTap: onPick == null ? null : () => onPick!(picked == r.robotId ? null : r.robotId),
                      ),
                    ),
                ],
              );
            }),
        ],
      ),
    );
  }
}

/// One of my robots: code and station, the connection chip, its state and the backend's headline, then the Manager's
/// status when it is out of service, the agent's modes, its job and its open alerts. A working robot has an ink edge.
class RobotCard extends ConsumerWidget {
  final RobotStatus robot;
  final bool selected;
  final VoidCallback? onTap;
  const RobotCard({super.key, required this.robot, this.selected = false, this.onTap});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    final r = robot;
    final emphasis = r.active || selected;
    final job = r.jobId;

    final body = Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: selected ? AppColors.surfaceVariant : AppColors.surface,
        borderRadius: BorderRadius.circular(TechRadius.card),
        border: Border.all(color: emphasis ? AppColors.ink : AppColors.border, width: emphasis ? 1.5 : 1),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    MonoText(r.robotCode.isEmpty ? '#${r.robotId}' : r.robotCode, size: 16),
                    if ((r.station ?? '').isNotEmpty)
                      Text(r.station!, style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Flexible(
                child: Align(alignment: Alignment.topRight, child: StatusPill(robotLinkLabel(t, r.connection), robotLinkColor(r.connection))),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              if (r.active) StatusPill(t('tw.active'), AppColors.ink),
              if (r.state != RobotHealth.unknown && r.state != RobotHealth.offline) StatusPill(t('rb.state.${r.state.code}'), robotHealthColor(r.state)),
              if (r.outOfService) StatusPill(t('tw.out.${r.robotStatus}'), r.robotStatus == 'BROKEN' ? AppColors.error : AppColors.warning),
              if (r.alerts.isNotEmpty) StatusPill(t('tw.alerts', {'n': r.alerts.length, 'level': r.level}), alertLevelColor(r.level)),
            ],
          ),
          // The backend writes this sentence in Vietnamese only; it is shown as data.
          if (r.headline.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(r.headline, style: const TextStyle(fontSize: 12, color: AppColors.textSecondary, height: 1.4)),
          ],
          if (!r.online && r.lastSeenAt != null) ...[
            const SizedBox(height: 4),
            Text('${t('rb.lastSeen')}: ${jobStamp(t, r.lastSeenAt!)}', style: const TextStyle(fontSize: 12, color: AppColors.textTertiary)),
          ],
          if (r.enabledModes.isNotEmpty) ...[
            const SizedBox(height: 8),
            Wrap(spacing: 6, runSpacing: 6, children: [for (final mode in r.enabledModes) TagText(t('rb.mode.$mode'))]),
          ],
          if (job != null) ...[
            const SizedBox(height: 8),
            MouseRegion(
              cursor: SystemMouseCursors.click,
              child: GestureDetector(
                onTap: () => context.go(jobPath(job)),
                child: Text(
                  t('tw.robotJob', {'id': job, 'status': r.jobStatus == null ? '' : jobStatusLabel(t, JobStatus.parse(r.jobStatus))}),
                  style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, decoration: TextDecoration.underline),
                ),
              ),
            ),
          ],
        ],
      ),
    );

    if (onTap == null) return body;
    return Semantics(
      button: true,
      selected: selected,
      child: MouseRegion(cursor: SystemMouseCursors.click, child: Pressable(onTap: onTap, semanticLabel: r.robotCode, child: body)),
    );
  }
}

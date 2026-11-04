import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/network/network_exceptions.dart';
import '../../../../core/widgets/widgets.dart';
import '../../data/tech_api.dart';
import '../../domain/job.dart';
import '../../domain/robot.dart';
import '../../i18n/tech_strings.dart';
import 'tech_ui.dart';

String jobPath(int id) => '/tech/jobs/$id';

/// The workshop's clock (Vietnam, UTC+7), whatever the device is set to, as the FE shows it.
DateTime workshopTime(DateTime d) => d.toUtc().add(const Duration(hours: 7));

String jobStamp(T t, DateTime d) => DateFormat('HH:mm dd/MM', t.locale).format(workshopTime(d));

Color jobStatusColor(JobStatus s) => switch (s) {
      JobStatus.written || JobStatus.writing || JobStatus.paused || JobStatus.preparing => AppColors.ink,
      JobStatus.photoUploaded || JobStatus.done => AppColors.success,
      JobStatus.failed => AppColors.error,
      JobStatus.rewriteRequired => AppColors.warning,
      JobStatus.scheduled || JobStatus.cancelled || JobStatus.unknown => AppColors.textSecondary,
    };

String jobStatusLabel(T t, JobStatus s) => s == JobStatus.unknown ? t('td.api.unavailable') : t('js.${s.code}');

class JobStatusPill extends ConsumerWidget {
  final JobStatus status;
  const JobStatusPill(this.status, {super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => StatusPill(jobStatusLabel(ref.watch(tProvider), status), jobStatusColor(status));
}

Color robotHealthColor(RobotHealth s) => switch (s) {
      RobotHealth.danger => AppColors.alarm,
      RobotHealth.pausedSafe => AppColors.warning,
      RobotHealth.idle => AppColors.success,
      RobotHealth.preparing || RobotHealth.writing => AppColors.ink,
      RobotHealth.offline || RobotHealth.unknown => AppColors.textSecondary,
    };

/// Text for an API failure. Known codes are translated; any other refusal shows the backend's
/// own message, so a code nobody mapped yet still says something useful.
String techErrorText(T t, Object? e) {
  if (e is TechFlowError) return t(e.key);
  if (e is! NetworkException) return t('dk.err.unknown');
  if (e is NotFoundException) return t('td.api.notFound');
  final key = 'td.flow.error.${e.code}';
  if (techDictionaries[t.lang]!.containsKey(key)) return t(key);
  return switch (e) {
    TimeoutException() => t('dk.err.timeout'),
    NoInternetException() => t('dk.err.offline'),
    ServerException() => t('dk.err.server'),
    TooManyAttemptsException() => t('dk.err.rate'),
    CancelException() || UnknownException() => t('dk.err.unknown'),
    _ => e.message,
  };
}

/// Loading and retry feedback. A failed refresh never reads as an empty job queue.
class JobFeedback extends ConsumerWidget {
  final bool loading;
  final Object? error;
  final VoidCallback retry;
  const JobFeedback({super.key, required this.loading, required this.error, required this.retry});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    if (error != null) {
      return Padding(
        padding: const EdgeInsets.only(bottom: 16),
        child: TechCard(
          padding: const EdgeInsets.all(16),
          child: Wrap(
            spacing: 16,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Semantics(
                liveRegion: true,
                child: Text(techErrorText(t, error), style: const TextStyle(fontSize: 14, color: AppColors.error, height: 1.4)),
              ),
              TechButton(t('td.api.reload'), small: true, style: CustomButtonStyle.outline, onPressed: retry),
            ],
          ),
        ),
      );
    }
    if (!loading) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Row(
        children: [
          const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
          const SizedBox(width: 12),
          Text(t('co.loading'), style: const TextStyle(fontSize: 14, color: AppColors.textSecondary)),
        ],
      ),
    );
  }
}

/// One job as a row: code, status, then number, start and duration.
class JobRow extends ConsumerWidget {
  final TechJob job;
  /// Keeps the job list's filter when a row opens the job from there.
  final String query;
  const JobRow({super.key, required this.job, this.query = ''});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    final j = job;
    final code = j.orderCode.isEmpty ? '${j.orderId}' : j.orderCode;
    final facts = [
      t('td.api.jobId', {'id': j.id}),
      if (j.isRewrite) t('wk.rewrite'),
      j.robotCode.isEmpty ? '${j.robotId}' : j.robotCode,
      jobStamp(t, j.slotStart),
      t('td.min', {'n': j.durationMin}),
    ].join(' · ');
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: MouseRegion(
        cursor: SystemMouseCursors.click,
        child: Pressable(
          onTap: () => context.go(j.status == JobStatus.written ? '/tech/qc/${j.id}' : '${jobPath(j.id)}$query'),
          semanticLabel: '$code, ${jobStatusLabel(t, j.status)}',
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
            decoration: BoxDecoration(
              color: AppColors.background,
              borderRadius: BorderRadius.circular(TechRadius.inner),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(code, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
                    ),
                    const SizedBox(width: 8),
                    Flexible(child: Align(alignment: Alignment.centerRight, child: JobStatusPill(j.status))),
                  ],
                ),
                const SizedBox(height: 4),
                Text(facts, style: const TextStyle(fontSize: 12, color: AppColors.textSecondary, height: 1.4)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

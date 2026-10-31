import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../core/widgets/widgets.dart';
import '../../data/providers.dart';
import '../../domain/job.dart';
import '../../i18n/tech_strings.dart';
import '../widgets/job_widgets.dart';
import '../widgets/tech_shell.dart';
import '../widgets/tech_ui.dart';

enum JobFilter {
  active('dk.jobs.active'),
  qc('td.kpi.qc'),
  history('td.api.group.history');

  final String labelKey;
  const JobFilter(this.labelKey);

  bool matches(JobStatus s) => switch (this) {
        active => previewJobStatuses.contains(s),
        qc => s == JobStatus.written,
        history => !previewJobStatuses.contains(s) && s != JobStatus.written,
      };

  static JobFilter parse(String? name) => values.firstWhere((f) => f.name == name, orElse: () => active);
}

/// My jobs: filter and search above the list. Opening a job goes to its own page.
class JobsScreen extends ConsumerStatefulWidget {
  final JobFilter filter;
  const JobsScreen({super.key, this.filter = JobFilter.active});

  @override
  ConsumerState<JobsScreen> createState() => _JobsScreenState();
}

class _JobsScreenState extends ConsumerState<JobsScreen> {
  final _search = TextEditingController();
  String _needle = '';

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  void _pick(JobFilter f) {
    if (f == widget.filter) return;
    context.go(f == JobFilter.qc ? '/tech/qc' : '/tech/jobs${f == JobFilter.active ? '' : '?filter=${f.name}'}');
  }

  bool _found(TechJob j) => _needle.isEmpty || j.orderCode.toLowerCase().contains(_needle) || '${j.id}'.contains(_needle);

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(tProvider);
    final q = ref.watch(techJobsProvider);
    final all = q.valueOrNull ?? const <TechJob>[];
    final rows = all.where((j) => widget.filter.matches(j.status) && _found(j)).toList();
    final query = widget.filter == JobFilter.active ? '' : '?filter=${widget.filter.name}';
    final isQc = widget.filter == JobFilter.qc;

    final reload = TechButton(t('td.api.reload'), small: true, style: CustomButtonStyle.outline, onPressed: () => reloadTechData(ref));

    return TechPage(
      title: t(isQc ? 'td.api.qcTitle' : 'td.api.myJobs'),
      subtitle: isQc ? t('td.api.qcBody') : (q.hasValue ? t('td.assigned', {'n': all.length}) : null),
      actions: [reload],
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          JobFeedback(loading: !q.hasValue && q.isLoading, error: q.hasError ? q.error : null, retry: () => reloadTechData(ref)),
          TechCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 560),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      CustomTextField(
                        label: t('dk.jobs.search'),
                        hint: t('dk.jobs.searchHint'),
                        controller: _search,
                        textInputAction: TextInputAction.search,
                        onChanged: (v) => setState(() => _needle = v.trim().toLowerCase()),
                      ),
                      const SizedBox(height: 12),
                      _FilterTabs(
                        filter: widget.filter,
                        count: (f) => q.hasValue ? all.where((j) => f.matches(j.status)).length : null,
                        onPick: _pick,
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),
                LayoutBuilder(builder: (context, c) {
                  final cols = c.maxWidth >= 1000 ? 3 : (c.maxWidth >= 620 ? 2 : 1);
                  final width = (c.maxWidth - (cols - 1) * 8) / cols;
                  return Wrap(
                    spacing: 8,
                    children: [for (final j in rows) SizedBox(width: width, child: JobRow(job: j, query: query))],
                  );
                }),
                if (q.hasValue && rows.isEmpty && !q.hasError)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    child: Text(
                      _needle.isNotEmpty ? t('dk.jobs.noMatch') : t(isQc ? 'td.api.emptyQc' : widget.filter == JobFilter.active ? 'td.api.emptyPreview' : 'dk.jobs.noHistory'),
                      style: const TextStyle(fontSize: 14, color: AppColors.textSecondary, height: 1.5),
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _FilterTabs extends ConsumerWidget {
  final JobFilter filter;
  final int? Function(JobFilter) count;
  final ValueChanged<JobFilter> onPick;
  const _FilterTabs({required this.filter, required this.count, required this.onPick});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    return Semantics(
      container: true,
      label: t('dk.jobs.filter'),
      child: Container(
        padding: const EdgeInsets.all(4),
        decoration: BoxDecoration(color: AppColors.surfaceVariant, borderRadius: BorderRadius.circular(TechRadius.control)),
        child: Row(
          children: [
            for (final f in JobFilter.values)
              Expanded(
                child: Semantics(
                  button: true,
                  selected: f == filter,
                  child: MouseRegion(
                    cursor: SystemMouseCursors.click,
                    child: GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTap: () => onPick(f),
                      child: AnimatedContainer(
                        duration: AppTheme.motionFast,
                        constraints: const BoxConstraints(minHeight: 40),
                        alignment: Alignment.center,
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 6),
                        decoration: BoxDecoration(
                          color: f == filter ? AppColors.surface : Colors.transparent,
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Text(
                          count(f) == null ? t(f.labelKey) : '${t(f.labelKey)} · ${count(f)}',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: f == filter ? FontWeight.w600 : FontWeight.w500,
                            color: f == filter ? AppColors.textPrimary : AppColors.secondaryLight,
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/widgets/widgets.dart';
import '../../data/providers.dart';
import '../../i18n/tech_strings.dart';
import '../widgets/job_detail_pane.dart';
import '../widgets/tech_shell.dart';
import '../widgets/tech_ui.dart';

/// One job on its own page, under the job list (FE `JobDetail.tsx`). [backTo] is the list it came from.
class JobDetailScreen extends ConsumerWidget {
  final int jobId;
  final String backTo;
  const JobDetailScreen({super.key, required this.jobId, this.backTo = '/tech/jobs'});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    final job = ref.watch(techJobProvider(jobId)).valueOrNull?.job;
    return TechPage(
      title: job == null ? t('td.api.view') : t('td.api.detailTitle', {'code': job.orderCode.isEmpty ? job.orderId : job.orderCode}),
      subtitle: t('td.api.jobId', {'id': jobId}),
      actions: [
        TechButton(t('td.api.back'), small: true, style: CustomButtonStyle.outline, icon: Icons.arrow_back_rounded, onPressed: () => context.go(backTo)),
        TechButton(t('td.api.reload'), small: true, style: CustomButtonStyle.outline, onPressed: () => reloadTechData(ref)),
      ],
      body: JobDetailPane(jobId: jobId),
    );
  }
}

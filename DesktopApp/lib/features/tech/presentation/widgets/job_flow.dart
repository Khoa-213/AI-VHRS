import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/network/network_exceptions.dart';
import '../../data/providers.dart';
import '../../data/tech_api.dart';
import '../../i18n/tech_strings.dart';
import 'job_widgets.dart';
import 'tech_ui.dart';

/// Runs one write action. Answers true when the backend accepted it.
typedef TechRun = Future<bool> Function(Future<void> Function() action, {String? confirm});

Future<bool> confirmAction(BuildContext context, T t, String body) => showConfirm(
      context,
      title: t('dk.confirm.title'),
      body: body,
      confirm: t('dk.confirm.ok'),
      cancel: t('dk.confirm.cancel'),
    );

/// Asks the backend again for everything shown about a job.
Future<void> refreshJob(WidgetRef ref, int id) async {
  ref.invalidate(techJobsProvider);
  ref.invalidate(jobEventsProvider(id));
  ref.invalidate(jobPhotosProvider(id));
  ref.invalidate(jobCommandsProvider(id));
  try {
    // ignore: unused_result
    await ref.refresh(techJobProvider(id).future);
  } catch (_) {
    // The job's own provider now holds the error, and the page shows it.
  }
}

/// Downloads the job package and keeps it when its hash is right.
Future<void> downloadPackage(WidgetRef ref, int id) async {
  final holder = ref.read(verifiedPackageProvider(id).notifier);
  holder.state = null;
  holder.state = await ref.read(techApiProvider).downloadPackage(id);
}

/// One write action at a time on a job (FE `JobWorkflow.run`): asks first when told to, reports
/// the outcome, and always loads the job again, since a network failure may come after the
/// server committed the change.
mixin JobRunner<W extends ConsumerStatefulWidget> on ConsumerState<W> {
  int get runnerJobId;

  bool flowBusy = false;
  String? flowError;
  String? flowNotice;

  Future<bool> run(Future<void> Function() action, {String? confirm}) async {
    if (flowBusy) return false;
    final t = ref.read(tProvider);
    if (confirm != null && !await confirmAction(context, t, confirm)) return false;
    if (!mounted) return false;
    setState(() {
      flowBusy = true;
      flowError = null;
      flowNotice = null;
    });
    var ok = false;
    String? error;
    try {
      await action();
      ok = true;
    } catch (e) {
      if (e is NetworkException && e.code == 'JOB_HASH_MISMATCH') {
        ref.read(verifiedPackageProvider(runnerJobId).notifier).state = null;
      }
      error = e is TechFlowError || e is NetworkException ? techErrorText(t, e) : t('dk.err.unknown');
    }
    if (!mounted) return ok;
    await refreshJob(ref, runnerJobId);
    if (!mounted) return ok;
    setState(() {
      flowBusy = false;
      flowError = error;
      flowNotice = ok ? t('td.flow.saved') : null;
    });
    return ok;
  }
}

/// The outcome line of the last action.
class FlowMessages extends ConsumerWidget {
  final bool busy;
  final String? error;
  final String? notice;
  const FlowMessages({super.key, required this.busy, this.error, this.notice});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    final text = error ?? (busy ? t('td.flow.working') : notice);
    if (text == null) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Semantics(
        liveRegion: true,
        child: Text(
          text,
          style: TextStyle(fontSize: 14, height: 1.4, color: error != null ? AppColors.error : AppColors.textSecondary),
        ),
      ),
    );
  }
}

/// A dropdown with a label, in the app's field style.
class FlowSelect<V> extends StatelessWidget {
  final String label;
  final V value;
  final Map<V, String> options;
  final ValueChanged<V>? onChanged;
  const FlowSelect({super.key, required this.label, required this.value, required this.options, this.onChanged});

  @override
  Widget build(BuildContext context) => DropdownButtonFormField<V>(
        key: ValueKey(value),
        initialValue: value,
        isExpanded: true,
        decoration: InputDecoration(labelText: label),
        items: [
          for (final e in options.entries)
            DropdownMenuItem(value: e.key, child: Text(e.value, overflow: TextOverflow.ellipsis)),
        ],
        onChanged: onChanged == null ? null : (v) => onChanged!(v as V),
      );
}

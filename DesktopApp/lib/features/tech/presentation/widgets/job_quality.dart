import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/constants/app_colors.dart';
import '../../data/providers.dart';
import '../../domain/job.dart';
import '../../i18n/tech_strings.dart';
import 'job_flow.dart';
import 'job_widgets.dart';
import 'tech_ui.dart';

/// Service G, as in FE `pages/tech/JobQuality.tsx`: compares each product photo with a page of the approved sketch
/// (`POST .../photos/{id}/evaluate`) and lists the job's results (`GET .../quality`). The verdict is the backend's; the
/// technician still sets each photo's QC result.
class JobQualityCard extends ConsumerStatefulWidget {
  final int jobId;
  final List<ProductPhoto> photos;
  final bool disabled;
  const JobQualityCard({super.key, required this.jobId, required this.photos, required this.disabled});

  @override
  ConsumerState<JobQualityCard> createState() => _JobQualityCardState();
}

class _JobQualityCardState extends ConsumerState<JobQualityCard> {
  int? _busy;
  final Map<int, int> _pages = {};
  ({int photo, String text})? _error;
  bool _history = false;

  Future<void> _evaluate(int photo) async {
    if (_busy != null) return;
    final t = ref.read(tProvider);
    setState(() {
      _busy = photo;
      _error = null;
    });
    try {
      await ref.read(techApiProvider).evaluatePhoto(widget.jobId, photo, page: _pages[photo] ?? 1);
    } catch (e) {
      if (mounted) setState(() => _error = (photo: photo, text: techErrorText(t, e)));
    }
    if (!mounted) return;
    ref.invalidate(jobQualityProvider(widget.jobId));
    setState(() => _busy = null);
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(tProvider);
    final q = ref.watch(jobQualityProvider(widget.jobId));
    final results = q.valueOrNull ?? const <QualityEvaluation>[];
    String kind(int photoId) {
      final p = widget.photos.where((x) => x.id == photoId).firstOrNull;
      return p == null ? t('tq.photoN', {'id': photoId}) : t('td.flow.photo.${p.kind.code}');
    }

    return TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('tq.title'), tag: t('tq.count', {'n': results.length})),
          Text(t('tq.help'), style: const TextStyle(fontSize: 13, color: AppColors.textSecondary, height: 1.4)),
          const SizedBox(height: 12),
          for (final p in widget.photos) ...[
            _PhotoRow(
              label: t('td.flow.photo.${p.kind.code}'),
              latest: results.where((r) => r.photoId == p.id).firstOrNull,
              page: _pages[p.id] ?? 1,
              busy: _busy == p.id,
              locked: widget.disabled || _busy != null,
              error: _error?.photo == p.id ? _error!.text : null,
              onPage: (v) => setState(() => _pages[p.id] = v),
              onRun: () => _evaluate(p.id),
            ),
            const SizedBox(height: 8),
          ],
          JobFeedback(
            loading: !q.hasValue && q.isLoading,
            error: q.hasError ? q.error : null,
            retry: () => ref.invalidate(jobQualityProvider(widget.jobId)),
          ),
          if (q.hasValue && !q.hasError && results.isEmpty)
            Text(t('tq.none'), style: const TextStyle(fontSize: 13, color: AppColors.textSecondary)),
          if (results.isNotEmpty) ...[
            Semantics(
              button: true,
              expanded: _history,
              child: InkWell(
                onTap: () => setState(() => _history = !_history),
                borderRadius: BorderRadius.circular(8),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  child: Row(
                    children: [
                      Expanded(child: Text(t('tq.history', {'n': results.length}), style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600))),
                      Icon(_history ? Icons.expand_less_rounded : Icons.expand_more_rounded, size: 20, color: AppColors.textSecondary),
                    ],
                  ),
                ),
              ),
            ),
            if (_history)
              for (final r in results) _ResultTile(r: r, title: '${kind(r.photoId)} · ${t('tq.pageN', {'n': r.page})}'),
            const SizedBox(height: 6),
            Text(t('tq.unvalidated'), style: const TextStyle(fontSize: 12, color: AppColors.textSecondary, height: 1.4)),
          ],
        ],
      ),
    );
  }
}

class _PhotoRow extends ConsumerWidget {
  final String label;
  final QualityEvaluation? latest;
  final int page;
  final bool busy, locked;
  final String? error;
  final ValueChanged<int> onPage;
  final VoidCallback onRun;
  const _PhotoRow({
    required this.label,
    required this.latest,
    required this.page,
    required this.busy,
    required this.locked,
    required this.error,
    required this.onPage,
    required this.onRun,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(border: Border.all(color: AppColors.border), borderRadius: BorderRadius.circular(16)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Wrap(
            spacing: 8,
            runSpacing: 6,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text(label, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
              if (latest case final r?) VerdictPill(r.verdict) else Text(t('tq.notYet'), style: const TextStyle(fontSize: 13, color: AppColors.textSecondary)),
            ],
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.end,
            children: [
              SizedBox(
                width: 150,
                child: FlowSelect<int>(
                  label: t('tq.page'),
                  value: page,
                  options: {for (var i = 1; i <= 10; i++) i: '$i'},
                  onChanged: locked ? null : onPage,
                ),
              ),
              TechButton(t(busy ? 'tq.running' : latest != null ? 'tq.again' : 'tq.run'), small: true, onPressed: locked ? null : onRun),
            ],
          ),
          if (busy) ...[const SizedBox(height: 6), Text(t('tq.running'), style: const TextStyle(fontSize: 13, color: AppColors.textSecondary))],
          if (error != null) ...[const SizedBox(height: 6), Text(error!, style: const TextStyle(fontSize: 13, color: AppColors.error))],
        ],
      ),
    );
  }
}

/// The backend's verdict as a word and a colour (never colour alone). A verdict this build does not know is shown as sent.
class VerdictPill extends ConsumerWidget {
  final String verdict;
  const VerdictPill(this.verdict, {super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    final key = 'tq.v.$verdict';
    final word = t(key) == key ? verdict : t(key);
    final color = switch (verdict) {
      'PASS' => AppColors.success,
      'FAIL' => AppColors.error,
      'NEEDS_REVIEW' => AppColors.warning,
      _ => AppColors.textSecondary,
    };
    return StatusPill(word, color);
  }
}

class _ResultTile extends ConsumerWidget {
  final QualityEvaluation r;
  final String title;
  const _ResultTile({required this.r, required this.title});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 10),
      decoration: const BoxDecoration(border: Border(top: BorderSide(color: AppColors.divider))),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Wrap(
            spacing: 8,
            runSpacing: 4,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text(title, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
              Text(jobStamp(t, r.createdAt), style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
              VerdictPill(r.verdict),
            ],
          ),
          if (r.numbers.isNotEmpty) ...[
            const SizedBox(height: 6),
            FactList([for (final (k, v, unit) in r.numbers) (t('tq.m.$k'), Text('$v $unit', style: const TextStyle(fontSize: 13)))]),
          ],
          for (final w in r.warnings) Text(w, style: const TextStyle(fontSize: 13, color: AppColors.warning, height: 1.4)),
          if (r.advisory.isNotEmpty) ...[const SizedBox(height: 6), Text(r.advisory, style: const TextStyle(fontSize: 13, height: 1.4))],
          if (r.overlayUrl case final url?) ...[
            const SizedBox(height: 8),
            Text(t('tq.overlay'), style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
            const SizedBox(height: 4),
            ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: Image.network(
                url,
                height: 220,
                fit: BoxFit.contain,
                semanticLabel: t('tq.overlay'),
                errorBuilder: (_, _, _) => Text(t('td.flow.photoLinkExpired'), style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

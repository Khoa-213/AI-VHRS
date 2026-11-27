import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/constants/app_colors.dart';
import '../../data/providers.dart';
import '../../domain/job.dart';
import '../../i18n/tech_strings.dart';
import 'job_sections.dart';
import 'job_setup.dart';
import 'tech_ui.dart';

// The job page as three parts (design "v2: bước + công việc + sketch, vật tư, hướng dẫn", 2026-11-27): the step rail on the
// left, the work of the selected step in the middle, and the reference column (final sketch, materials, instructions)
// that stays in view on the right whatever the step.

/// Materials each step handles, highlighted in the reference column while that step is open.
const stepUses = <String, List<String>>{
  'robot': ['pen'],
  'prepare': ['paper', 'pen', 'ink'],
  'calibrate': ['paper', 'pen'],
  'preflight': ['paper', 'pen'],
  'dryRun': ['pen'],
  'write': ['paper', 'pen', 'ink'],
};

/// Steps with a practical tip (`dk.ws.tip.<key>`).
const stepTips = {'prepare', 'calibrate', 'simulate', 'write', 'photos'};

/// Index of the step to work on now: the first one not done and not held; -1 when none.
int currentStepIndex(List<JobStep> steps) => steps.indexWhere((s) => !s.done && !s.manual && s.why == null);

// ─── Step rail ───────────────────────────────────────────────────────

/// The twelve steps as a selectable list: ✓ done, the current one in ink, a lock and its reason for one that waits.
class StepRail extends ConsumerWidget {
  final List<JobStep> steps;
  final int current;
  final int selected;
  final ValueChanged<int> onSelect;
  const StepRail({super.key, required this.steps, required this.current, required this.selected, required this.onSelect});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    final done = steps.where((s) => s.done).length;
    return TechCard(
      padding: const EdgeInsets.fromLTRB(12, 20, 12, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: CardHead(t('tw.steps'), tag: '$done/${steps.length}'),
          ),
          for (var i = 0; i < steps.length; i++)
            _RailItem(n: i + 1, step: steps[i], current: i == current, selected: i == selected, onTap: () => onSelect(i)),
        ],
      ),
    );
  }
}

class _RailItem extends ConsumerWidget {
  final int n;
  final JobStep step;
  final bool current, selected;
  final VoidCallback onTap;
  const _RailItem({required this.n, required this.step, required this.current, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    final s = step;
    final locked = !s.done && s.why != null;
    final sub = s.done
        ? t('dk.ws.done')
        : current
            ? t('dk.ws.now')
            : locked
                ? t(s.why!)
                : s.manual
                    ? t('dk.ws.manual')
                    : null;
    final mark = Container(
      width: 24,
      height: 24,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: s.done ? AppColors.success : (current ? AppColors.ink : AppColors.surfaceVariant),
        shape: BoxShape.circle,
      ),
      child: s.done
          ? const Icon(Icons.check_rounded, size: 15, color: AppColors.onInk)
          : locked
              ? const Icon(Icons.lock_outline_rounded, size: 12, color: AppColors.textSecondary)
              : MonoText('$n', size: 11, color: current ? AppColors.onInk : AppColors.textSecondary),
    );
    return Semantics(
      button: true,
      selected: selected,
      label: [t('dk.ws.stepOf', {'n': n, 'total': 12}), t('tw.step.${s.key}'), if (sub != null) sub].join(', '),
      excludeSemantics: true,
      child: Material(
        color: selected ? AppColors.surfaceVariant : Colors.transparent,
        borderRadius: BorderRadius.circular(TechRadius.inner),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(TechRadius.inner),
          child: Container(
            constraints: const BoxConstraints(minHeight: 48),
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
            decoration: selected
                ? const BoxDecoration(border: Border(left: BorderSide(color: AppColors.ink, width: 3)))
                : null,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                mark,
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        t('tw.step.${s.key}'),
                        style: TextStyle(
                          fontSize: 14,
                          height: 1.3,
                          fontWeight: selected || current ? FontWeight.w700 : FontWeight.w500,
                          color: s.done || current || selected ? AppColors.textPrimary : AppColors.secondaryLight,
                        ),
                      ),
                      if (sub != null)
                        Text(
                          sub,
                          style: TextStyle(
                            fontSize: 12,
                            height: 1.35,
                            color: s.done ? AppColors.success : AppColors.textSecondary,
                          ),
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ─── Step panel ──────────────────────────────────────────────────────

/// The selected step: what it is, its state, a tip, the materials it uses, then [work] (the existing action cards).
class StepPanel extends ConsumerWidget {
  final int index;
  final int total;
  final JobStep step;
  final bool current;
  final Widget? work;
  final VoidCallback? onPrev, onNext;
  const StepPanel({
    super.key,
    required this.index,
    required this.total,
    required this.step,
    required this.current,
    this.work,
    this.onPrev,
    this.onNext,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    final s = step;
    final locked = !s.done && s.why != null;
    final uses = stepUses[s.key] ?? const [];
    final kind = {'paper': t('po.paper'), 'pen': t('po.pen'), 'ink': t('po.ink')};

    final head = TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(child: TagText(t('dk.ws.stepOf', {'n': index + 1, 'total': total}))),
              IconButton(
                tooltip: t('dk.ws.prev'),
                onPressed: onPrev,
                icon: const Icon(Icons.chevron_left_rounded),
              ),
              IconButton(
                tooltip: t('dk.ws.next'),
                onPressed: onNext,
                icon: const Icon(Icons.chevron_right_rounded),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Wrap(
            spacing: 12,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text(t('tw.step.${s.key}'), style: Theme.of(context).textTheme.headlineSmall),
              if (s.done)
                StatusPill(t('dk.ws.done'), AppColors.success)
              else if (current)
                StatusPill(t('dk.ws.now'), AppColors.ink)
              else if (locked)
                StatusPill(t(s.why!), AppColors.warning),
            ],
          ),
          const SizedBox(height: 8),
          Text(t('dk.ws.desc.${s.key}'), style: const TextStyle(fontSize: 14, height: 1.5, color: AppColors.secondaryLight)),
          if (stepTips.contains(s.key)) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppColors.surfaceVariant,
                borderRadius: BorderRadius.circular(TechRadius.inner),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.lightbulb_outline_rounded, size: 18, color: AppColors.secondaryLight),
                  const SizedBox(width: 8),
                  Expanded(child: Text(t('dk.ws.tip.${s.key}'), style: const TextStyle(fontSize: 13, height: 1.45))),
                ],
              ),
            ),
          ],
          if (uses.isNotEmpty) ...[
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Text(t('dk.ws.uses'), style: const TextStyle(fontSize: 13, color: AppColors.textSecondary)),
                for (final k in uses)
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      border: Border.all(color: AppColors.ink),
                      borderRadius: BorderRadius.circular(999),
                    ),
                    child: Text(kind[k]!, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
                  ),
              ],
            ),
          ],
          if (work == null) ...[
            const SizedBox(height: 16),
            Text(
              t(s.done ? 'dk.ws.doneHere' : 'dk.ws.nothing'),
              style: const TextStyle(fontSize: 13, color: AppColors.textSecondary),
            ),
          ],
        ],
      ),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [head, if (work != null) ...[const SizedBox(height: 16), work!]],
    );
  }
}

// ─── Reference column ────────────────────────────────────────────────

/// Final sketch, materials and instructions, beside every step. Works without `/reference` (older server): names come
/// from the job detail and the sketch from the verified package.
class JobReferenceColumn extends ConsumerWidget {
  final TechJobDetail detail;
  final List<TrajectoryPage>? verifiedPages;
  final Set<String> highlight;
  const JobReferenceColumn({super.key, required this.detail, this.verifiedPages, this.highlight = const {}});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    final jobId = detail.job.id;
    final q = ref.watch(jobReferenceProvider(jobId));
    final r = q.valueOrNull;
    final offline = r == null && q.hasError;
    final stock = ref.watch(jobStockProvider(jobId)).valueOrNull;

    // ── sketch
    final url = r?.previewUrl;
    Widget picture;
    if (url != null) {
      picture = _Zoomable(
        label: t('dk.ref.zoom'),
        close: t('dk.ref.close'),
        child: (fit) => Image.network(
          url,
          fit: fit,
          errorBuilder: (_, _, _) => _placeholder(t('dk.ref.noPreview')),
          loadingBuilder: (_, child, p) => p == null ? child : const Center(child: CircularProgressIndicator(strokeWidth: 2)),
        ),
      );
    } else if (verifiedPages != null && verifiedPages!.isNotEmpty) {
      picture = Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          TrajectoryPreview(pages: verifiedPages!),
          const SizedBox(height: 6),
          Text(t('dk.ref.pathPreview'), style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
        ],
      );
    } else {
      picture = _placeholder(t('dk.ref.noPreview'));
    }
    final sketch = TechCard(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('dk.ref.sketch'),
              tag: r?.sketchVersion == null ? t('dk.ref.approved') : t('dk.ref.version', {'v': r!.sketchVersion})),
          picture,
          if (r != null && !r.pagesAssumed) ...[
            const SizedBox(height: 8),
            Text(t('dk.ref.pages', {'n': r.pages}), style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
          ],
        ],
      ),
    );

    // ── materials
    final rows = <(String, String?, RefMaterial?)>[
      ('paper', detail.paper, r?.paper),
      ('pen', detail.pen, r?.pen),
      ('ink', detail.ink, r?.ink),
    ];
    // What the job has taken (0033): paper before Prepare; a pen and its ink only when the pen on the robot is replaced.
    String? takenText(String key) {
      if (stock == null) return null;
      final l = stock.line(key.toUpperCase());
      if (l == null) return null;
      if (key == 'paper') return t('dk.ref.takenOf', {'n': l.issued, 'need': l.need});
      return l.issued > 0 ? t('dk.ref.takenOf', {'n': l.issued, 'need': l.issued}) : t('dk.ref.onPenChange');
    }

    final paperLine = stock?.paper;

    final materials = TechCard(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('dk.ref.materials'),
              tag: paperLine == null ? null : t(stock!.issued ? 'dk.ref.paperTaken' : 'dk.ref.paperWaiting')),
          for (final (key, name, m) in rows) ...[
            _MaterialRow(
              kind: t('po.$key'),
              keyName: key,
              name: m?.name ?? name,
              material: m,
              used: highlight.contains(key),
              taken: takenText(key),
              takenOk: key != 'paper' || (stock?.issued ?? false),
            ),
            if (key != 'ink') const SizedBox(height: 8),
          ],
          if (offline) ...[
            const SizedBox(height: 10),
            Text(t('dk.ref.offline'), style: const TextStyle(fontSize: 12, color: AppColors.textSecondary, height: 1.4)),
          ],
        ],
      ),
    );

    // ── instructions
    final note = r?.approachNote ?? detail.note;
    final guide = TechCard(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('dk.ref.guide')),
          Text(
            note == null || note.trim().isEmpty ? t('dk.ref.noGuide') : note,
            style: TextStyle(fontSize: 14, height: 1.5, color: note == null ? AppColors.textSecondary : AppColors.textPrimary),
          ),
        ],
      ),
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [sketch, const SizedBox(height: 16), materials, const SizedBox(height: 16), guide],
    );
  }

  static Widget _placeholder(String text) => Container(
        height: 160,
        alignment: Alignment.center,
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: AppColors.surfaceVariant,
          borderRadius: BorderRadius.circular(TechRadius.inner),
        ),
        child: Text(text, textAlign: TextAlign.center, style: const TextStyle(fontSize: 13, color: AppColors.textSecondary, height: 1.4)),
      );
}

class _MaterialRow extends StatelessWidget {
  final String kind, keyName;
  final String? name;
  final RefMaterial? material;
  final bool used;
  /// What the job has taken of this material (stock sheet); null when unknown.
  final String? taken;
  final bool takenOk;
  const _MaterialRow({
    required this.kind,
    required this.keyName,
    required this.name,
    required this.material,
    required this.used,
    required this.taken,
    required this.takenOk,
  });

  @override
  Widget build(BuildContext context) {
    return Consumer(builder: (context, ref, _) {
      final t = ref.watch(tProvider);
      final m = material;
      Color? hex(String? v) {
        final s = (v ?? '').replaceFirst('#', '');
        final n = int.tryParse(s, radix: 16);
        return s.length == 6 && n != null ? Color(0xFF000000 | n) : null;
      }

      final swatch = Container(
        width: 36,
        height: 36,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: switch (keyName) {
            'paper' => const Color(0xFFFBF7EE),
            'pen' => AppColors.ink,
            _ => hex(m?.hex) ?? AppColors.surfaceVariant,
          },
          border: Border.all(color: AppColors.border),
          borderRadius: BorderRadius.circular(8),
        ),
        child: keyName == 'paper'
            ? Text(m?.spec.split(' · ').first ?? '', style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w600, color: AppColors.secondaryLight))
            : keyName == 'pen'
                ? const Icon(Icons.edit_rounded, size: 16, color: AppColors.onInk)
                : null,
      );
      return Container(
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          border: Border.all(color: used ? AppColors.ink : AppColors.border, width: used ? 1.5 : 1),
          borderRadius: BorderRadius.circular(TechRadius.inner),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            swatch,
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    used ? '$kind · ${t('dk.ref.usedNow')}' : kind,
                    style: TextStyle(fontSize: 11, color: used ? AppColors.textPrimary : AppColors.textSecondary, fontWeight: FontWeight.w600),
                  ),
                  Text(name ?? t('dk.ref.none'), style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, height: 1.3)),
                  if (m != null && m.spec.isNotEmpty)
                    Text(m.spec, style: const TextStyle(fontSize: 12, color: AppColors.textSecondary, height: 1.35)),
                  if (m != null)
                    Text(
                      m.need == 0
                          ? t('dk.ref.inStock', {'s': m.stock})
                          : m.short
                              ? '${t('dk.ref.need', {'n': m.need, 's': m.stock})} · ${t('dk.ref.short')}'
                              : t('dk.ref.need', {'n': m.need, 's': m.stock}),
                      style: TextStyle(fontSize: 12, height: 1.35, color: m.short ? AppColors.error : AppColors.secondaryLight),
                    ),
                ],
              ),
            ),
            if (taken != null) ...[
              const SizedBox(width: 8),
              Row(mainAxisSize: MainAxisSize.min, children: [
                Icon(takenOk ? Icons.check_circle_rounded : Icons.radio_button_unchecked_rounded,
                    size: 16, color: takenOk ? AppColors.success : AppColors.secondaryLight),
                const SizedBox(width: 4),
                Text(taken!, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
              ]),
            ],
          ],
        ),
      );
    });
  }
}

/// A picture that opens full size (pan and zoom) in a dialog.
class _Zoomable extends StatelessWidget {
  final String label, close;
  final Widget Function(BoxFit fit) child;
  const _Zoomable({required this.label, required this.close, required this.child});

  @override
  Widget build(BuildContext context) => Tooltip(
        message: label,
        child: InkWell(
          borderRadius: BorderRadius.circular(TechRadius.inner),
          onTap: () => showDialog<void>(
            context: context,
            builder: (ctx) => Dialog(
              insetPadding: const EdgeInsets.all(32),
              child: Stack(
                children: [
                  Positioned.fill(
                    child: InteractiveViewer(maxScale: 6, child: Center(child: child(BoxFit.contain))),
                  ),
                  Positioned(
                    top: 8,
                    right: 8,
                    child: IconButton.filledTonal(
                      tooltip: close,
                      onPressed: () => Navigator.of(ctx).pop(),
                      icon: const Icon(Icons.close_rounded),
                    ),
                  ),
                ],
              ),
            ),
          ),
          child: Container(
            height: 280,
            decoration: BoxDecoration(
              color: AppColors.surface,
              border: Border.all(color: AppColors.border),
              borderRadius: BorderRadius.circular(TechRadius.inner),
            ),
            clipBehavior: Clip.antiAlias,
            child: Stack(
              children: [
                Positioned.fill(child: child(BoxFit.contain)),
                const Positioned(
                  right: 8,
                  bottom: 8,
                  child: Icon(Icons.zoom_in_rounded, size: 20, color: AppColors.secondaryLight),
                ),
              ],
            ),
          ),
        ),
      );
}

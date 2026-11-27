import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/constants/app_colors.dart';
import '../../data/providers.dart';
import '../../domain/job.dart';
import '../../i18n/tech_strings.dart';
import 'tech_ui.dart';

/// Runs an action on the job with the pane's busy flag and error line ([JobRunner.run]).
typedef JobRun = Future<bool> Function(Future<void> Function() action, {String? confirm});

/// Spare sheets, sheets spoiled: a small number with − and + (40 px targets).
class _Stepper extends StatelessWidget {
  final String label, less, more;
  final int value, max;
  final bool enabled;
  final ValueChanged<int> onChanged;
  const _Stepper({
    required this.label,
    required this.less,
    required this.more,
    required this.value,
    required this.onChanged,
    this.max = 99,
    this.enabled = true,
  });

  @override
  Widget build(BuildContext context) => Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(label, style: const TextStyle(fontSize: 13, color: AppColors.textSecondary)),
          const SizedBox(width: 8),
          IconButton(
            tooltip: less,
            onPressed: enabled && value > 0 ? () => onChanged(value - 1) : null,
            icon: const Icon(Icons.remove_rounded, size: 18),
            constraints: const BoxConstraints(minWidth: 40, minHeight: 40),
          ),
          SizedBox(
            width: 32,
            child: Text('$value',
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600, fontFeatures: [FontFeature.tabularFigures()])),
          ),
          IconButton(
            tooltip: more,
            onPressed: enabled && value < max ? () => onChanged(value + 1) : null,
            icon: const Icon(Icons.add_rounded, size: 18),
            constraints: const BoxConstraints(minWidth: 40, minHeight: 40),
          ),
        ],
      );
}

Widget _line(String text, {Color color = AppColors.textSecondary, FontWeight weight = FontWeight.w400}) =>
    Text(text, style: TextStyle(fontSize: 13, height: 1.4, color: color, fontWeight: weight));

/// Prepare step, Q2/Q3 (2026-11-27): take the job's paper (plus spare sheets) from the shelf, and a new pen with its ink
/// only when the pen on the robot is replaced. Prepare stays closed until the paper is taken.
class StockIssueCard extends ConsumerStatefulWidget {
  final int jobId;
  final bool disabled;
  final JobRun run;
  const StockIssueCard({super.key, required this.jobId, required this.disabled, required this.run});

  @override
  ConsumerState<StockIssueCard> createState() => _StockIssueCardState();
}

class _StockIssueCardState extends ConsumerState<StockIssueCard> {
  int _spare = 0;
  bool _newPen = false;

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(tProvider);
    final q = ref.watch(jobStockProvider(widget.jobId));
    final s = q.valueOrNull;
    final children = <Widget>[CardHead(t('dk.st.title')), _line(t('dk.st.help'))];

    if (s == null) {
      children.add(const SizedBox(height: 10));
      children.add(q.hasError ? _line(t('dk.st.offline')) : const LinearProgressIndicator(minHeight: 2));
      return TechCard(child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children));
    }

    final paper = s.paper;
    final pen = s.line('PEN');
    final remaining = paper == null ? 0 : (paper.need - paper.issued).clamp(0, 1 << 30);
    final want = remaining + _spare;
    final short = paper != null && want > paper.stock;
    final penShort = _newPen && pen != null && pen.stock < 1;
    final can = !widget.disabled && s.canIssue && (want > 0 || _newPen) && !short && !penShort;

    children.add(const SizedBox(height: 12));
    if (paper == null) {
      children.add(_line(t('dk.st.noPaper')));
    } else {
      children.add(Text(paper.name, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)));
      children.add(_line(t('dk.st.paperLine', {'need': paper.need, 'issued': paper.issued, 'stock': paper.stock, 'unit': t('dk.st.u.PAPER')})));
      if (s.issued) {
        children.add(Padding(
          padding: const EdgeInsets.only(top: 4),
          child: Row(children: [
            const Icon(Icons.check_circle_rounded, size: 16, color: AppColors.success),
            const SizedBox(width: 6),
            Expanded(child: _line(t('dk.st.done'), color: AppColors.textPrimary, weight: FontWeight.w600)),
          ]),
        ));
      }
      children.add(const SizedBox(height: 4));
      children.add(_Stepper(
        label: t('dk.st.spare'),
        less: t('dk.st.less'),
        more: t('dk.st.more'),
        value: _spare,
        enabled: !widget.disabled,
        onChanged: (v) => setState(() => _spare = v),
      ));
      if (short) children.add(_line(t('dk.st.short', {'stock': paper.stock, 'unit': t('dk.st.u.PAPER')}), color: AppColors.error));
    }
    if (pen != null) {
      children.add(const SizedBox(height: 4));
      final toggle = widget.disabled ? null : () => setState(() => _newPen = !_newPen);
      children.add(Semantics(
        checked: _newPen,
        label: t('dk.st.newPen'),
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: toggle,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(
                width: 40,
                height: 40,
                child: Checkbox(value: _newPen, activeColor: AppColors.ink, onChanged: toggle == null ? null : (_) => toggle()),
              ),
              const SizedBox(width: 4),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.only(top: 10),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(t('dk.st.newPen'), style: const TextStyle(fontSize: 13, height: 1.4)),
                      _line(t('dk.st.penLine', {'name': pen.name, 'stock': pen.stock, 'unit': t('dk.st.u.PEN')}),
                          color: penShort ? AppColors.error : AppColors.textSecondary),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ));
    }
    final label = want > 0 && _newPen
        ? t('dk.st.takeBoth', {'n': want})
        : _newPen
            ? t('dk.st.takePen')
            : t('dk.st.take', {'n': want});
    children.add(const SizedBox(height: 8));
    children.add(Align(
      alignment: Alignment.centerLeft,
      child: TechButton(
        label,
        small: true,
        onPressed: !can
            ? null
            : () async {
                final ok = await widget.run(() => ref.read(techApiProvider).issueStock(
                      widget.jobId,
                      paper: paper == null ? 0 : want,
                      newPen: _newPen,
                      seenIssued: paper?.issued ?? 0,
                    ));
                if (ok && mounted) {
                  setState(() {
                    _spare = 0;
                    _newPen = false;
                  });
                }
              },
      ),
    ));
    return TechCard(child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children));
  }
}

/// Prepare is open: the paper is taken, or the server has no stock sheet (an older server, offline) and decides itself.
bool stockLetsPrepare(AsyncValue<JobStock> q) => q.valueOrNull?.issued ?? q.hasError;

/// Writing done: the sheets spoiled at the robot, and what goes back to the shelf.
class FinishStockCard extends ConsumerStatefulWidget {
  final int jobId;
  final bool disabled;
  final JobRun run;
  const FinishStockCard({super.key, required this.jobId, required this.disabled, required this.run});

  @override
  ConsumerState<FinishStockCard> createState() => _FinishStockCardState();
}

class _FinishStockCardState extends ConsumerState<FinishStockCard> {
  int _waste = 0;

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(tProvider);
    final paper = ref.watch(jobStockProvider(widget.jobId)).valueOrNull?.paper;
    String? outcome;
    if (paper != null) {
      if (paper.issued == 0) {
        outcome = t('dk.st.legacy');
      } else {
        final back = paper.issued - paper.need - _waste;
        outcome = back > 0
            ? t('dk.st.back', {'n': back, 'unit': t('dk.st.u.PAPER')})
            : back < 0
                ? t('dk.st.extra', {'n': -back, 'unit': t('dk.st.u.PAPER')})
                : t('dk.st.even');
      }
    }
    return TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('td.flow.finish')),
          _line(t('td.flow.finishHelp')),
          if (paper != null) ...[
            const SizedBox(height: 8),
            _Stepper(
              label: t('dk.st.waste'),
              less: t('dk.st.less'),
              more: t('dk.st.more'),
              value: _waste,
              max: 999,
              enabled: !widget.disabled,
              onChanged: (v) => setState(() => _waste = v),
            ),
            if (outcome != null) _line(outcome, color: AppColors.textPrimary),
          ],
          const SizedBox(height: 12),
          Align(
            alignment: Alignment.centerLeft,
            child: TechButton(
              t('td.flow.finish'),
              small: true,
              onPressed: widget.disabled
                  ? null
                  : () => widget.run(() => ref.read(techApiProvider).finish(widget.jobId, waste: _waste),
                      confirm: t('td.flow.confirmFinish')),
            ),
          ),
        ],
      ),
    );
  }
}

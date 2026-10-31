import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/widgets/widgets.dart';
import '../../data/providers.dart';
import '../../domain/job.dart';
import '../../i18n/tech_strings.dart';
import 'job_flow.dart';
import 'job_widgets.dart';
import 'tech_ui.dart';

const _forceKeys = ['f_mean', 'f_max', 'rms_err_pct', 'in_band_pct', 'samples'];
const _safetyEvents = [ClientEvent.estop, ClientEvent.overForce, ClientEvent.strokeLost, ClientEvent.sensorLost];
const _help = TextStyle(fontSize: 13, color: AppColors.textSecondary, height: 1.4);

/// Draws the verified trajectory, one page at a time. A preview only: the agent runs its own plan.
class TrajectoryPreview extends ConsumerStatefulWidget {
  final List<TrajectoryPage> pages;
  const TrajectoryPreview({super.key, required this.pages});

  @override
  ConsumerState<TrajectoryPreview> createState() => _TrajectoryPreviewState();
}

class _TrajectoryPreviewState extends ConsumerState<TrajectoryPreview> {
  int _page = 0;

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(tProvider);
    final page = widget.pages[_page.clamp(0, widget.pages.length - 1)];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (widget.pages.length > 1) ...[
          FlowSelect<int>(
            label: t('td.flow.page'),
            value: _page,
            options: {for (var i = 0; i < widget.pages.length; i++) i: '${i + 1}'},
            onChanged: (v) => setState(() => _page = v),
          ),
          const SizedBox(height: 12),
        ],
        Container(
          height: 260,
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(color: AppColors.surfaceVariant, borderRadius: BorderRadius.circular(TechRadius.inner)),
          child: Center(
            child: AspectRatio(
              aspectRatio: page.widthMm / page.heightMm,
              child: Semantics(
                image: true,
                label: t('td.flow.trajectory'),
                child: DecoratedBox(
                  decoration: BoxDecoration(color: AppColors.surface, border: Border.all(color: AppColors.border)),
                  child: CustomPaint(painter: _TrajectoryPainter(page)),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _TrajectoryPainter extends CustomPainter {
  final TrajectoryPage page;
  _TrajectoryPainter(this.page);

  @override
  void paint(Canvas canvas, Size size) {
    final k = size.width / page.widthMm;
    final ink = Paint()
      ..color = AppColors.ink
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    for (final stroke in page.strokes) {
      if (stroke.isEmpty) continue;
      final path = Path()..moveTo(stroke.first[0] * k, stroke.first[1] * k);
      for (final p in stroke.skip(1)) {
        path.lineTo(p[0] * k, p[1] * k);
      }
      canvas.drawPath(path, ink);
    }
  }

  @override
  bool shouldRepaint(_TrajectoryPainter old) => old.page != page;
}

/// Manual job events and incident reports (FE `JobEvents.tsx`).
class JobEventCards extends ConsumerStatefulWidget {
  final TechJobDetail job;
  final bool disabled;
  final TechRun run;
  const JobEventCards({super.key, required this.job, required this.disabled, required this.run});

  @override
  ConsumerState<JobEventCards> createState() => _JobEventCardsState();
}

class _JobEventCardsState extends ConsumerState<JobEventCards> {
  ClientEvent _event = ClientEvent.progress;
  IncidentType _incident = IncidentType.other;
  String _robotAfter = '';
  final _progress = TextEditingController();
  final _stroke = TextEditingController();
  final _note = TextEditingController();
  final _description = TextEditingController();
  final _force = {for (final k in _forceKeys) k: TextEditingController()};

  @override
  void dispose() {
    for (final c in [_progress, _stroke, _note, _description, ..._force.values]) {
      c.dispose();
    }
    super.dispose();
  }

  void _changed(String _) => setState(() {});

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(tProvider);
    final d = widget.job;
    final j = d.job;
    final api = ref.read(techApiProvider);
    final allowed = ClientEvent.values.where((e) => e.allowedIn(j.status)).toList();
    final canIncident = d.permissions().incident;
    if (allowed.isEmpty && !canIncident) return const SizedBox.shrink();
    final selected = allowed.contains(_event) ? _event : (allowed.isEmpty ? _event : allowed.first);

    final progress = double.tryParse(_progress.text.trim());
    final stroke = _stroke.text.trim().isEmpty ? null : int.tryParse(_stroke.text.trim());
    final strokeOk = _stroke.text.trim().isEmpty || (stroke != null && stroke >= 0 && stroke <= 10000000);
    final force = <String, num>{};
    var forceOk = true;
    _force.forEach((k, c) {
      if (c.text.trim().isEmpty) return;
      final v = double.tryParse(c.text.trim());
      if (v == null || !v.isFinite) {
        forceOk = false;
      } else {
        force[k] = v;
      }
    });
    final inBand = force['in_band_pct'];
    forceOk = forceOk && force.isNotEmpty && (inBand == null || (inBand >= 0 && inBand <= 100));
    final valid = strokeOk &&
        (selected != ClientEvent.progress || (progress != null && progress >= (j.progress ?? 0) && progress <= 100)) &&
        (selected != ClientEvent.forceSummary || forceOk);

    Widget gap(Widget w) => Padding(padding: const EdgeInsets.only(top: 12), child: w);

    final events = TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('td.flow.events')),
          Text(t('td.flow.eventHelp'), style: _help),
          gap(FlowSelect<ClientEvent>(
            label: t('td.flow.eventType'),
            value: selected,
            options: {for (final e in allowed) e: t('td.flow.event.${e.code}')},
            onChanged: widget.disabled ? null : (v) => setState(() => _event = v),
          )),
          if (selected == ClientEvent.progress)
            gap(CustomTextField(
              label: t('td.flow.progressPct'),
              controller: _progress,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              enabled: !widget.disabled,
              onChanged: _changed,
            )),
          gap(CustomTextField(
            label: t('td.flow.strokeIndex'),
            controller: _stroke,
            keyboardType: TextInputType.number,
            enabled: !widget.disabled,
            onChanged: _changed,
          )),
          if (selected == ClientEvent.forceSummary)
            for (final k in _forceKeys)
              gap(CustomTextField(
                label: t('td.flow.force.$k'),
                controller: _force[k],
                keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
                enabled: !widget.disabled,
                onChanged: _changed,
              )),
          gap(CustomTextField(label: t('td.flow.note'), controller: _note, maxLines: 2, maxLength: 1000, enabled: !widget.disabled)),
          gap(Align(
            alignment: Alignment.centerLeft,
            child: TechButton(
              t('td.flow.sendEvent'),
              small: true,
              onPressed: widget.disabled || !valid
                  ? null
                  : () async {
                      final note = _note.text.trim();
                      final ok = await widget.run(
                        () => api.postEvent(
                          j.id,
                          selected,
                          progressPct: selected == ClientEvent.progress ? progress : null,
                          strokeIndex: stroke,
                          forceSummary: selected == ClientEvent.forceSummary ? force : null,
                          payload: {'source': 'desktop_manual', if (note.isNotEmpty) 'note': note},
                        ),
                        confirm: _safetyEvents.contains(selected) ? t('td.flow.confirmSafety') : null,
                      );
                      if (ok && mounted) {
                        setState(() {
                          _progress.clear();
                          _stroke.clear();
                          _note.clear();
                        });
                      }
                    },
            ),
          )),
        ],
      ),
    );

    final description = _description.text.trim();
    final incident = TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('td.flow.incident')),
          Text(t('td.flow.incidentHelp'), style: _help),
          gap(FlowSelect<IncidentType>(
            label: t('td.flow.incidentType'),
            value: _incident,
            options: {for (final v in IncidentType.values) v: t('td.flow.incident.${v.code}')},
            onChanged: widget.disabled ? null : (v) => setState(() => _incident = v),
          )),
          gap(CustomTextField(
            label: t('td.flow.description'),
            controller: _description,
            maxLines: 3,
            maxLength: 1000,
            enabled: !widget.disabled,
            onChanged: _changed,
          )),
          gap(FlowSelect<String>(
            label: t('td.flow.robotAfter'),
            value: _robotAfter,
            options: {'': t('td.flow.unchanged'), 'MAINTENANCE': t('td.flow.maintenance'), 'BROKEN': t('td.flow.broken')},
            onChanged: widget.disabled ? null : (v) => setState(() => _robotAfter = v),
          )),
          gap(Align(
            alignment: Alignment.centerLeft,
            child: TechButton(
              t('td.flow.reportIncident'),
              small: true,
              onPressed: widget.disabled || description.isEmpty
                  ? null
                  : () async {
                      final ok = await widget.run(
                        () => api.reportIncident(j.id, type: _incident, description: description, robotStatusAfter: _robotAfter.isEmpty ? null : _robotAfter),
                        confirm: t('td.flow.confirmIncident'),
                      );
                      if (ok && mounted) setState(_description.clear);
                    },
            ),
          )),
        ],
      ),
    );

    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: LayoutBuilder(builder: (context, c) {
        final cards = [if (allowed.isNotEmpty) events, if (canIncident) incident];
        if (c.maxWidth < 640 || cards.length == 1) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              for (var i = 0; i < cards.length; i++) ...[if (i > 0) const SizedBox(height: 16), cards[i]],
            ],
          );
        }
        return Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [Expanded(child: cards[0]), const SizedBox(width: 16), Expanded(child: cards[1])],
        );
      }),
    );
  }
}

/// The job's event history, latest first, and its incidents (FE `JobHistory.tsx`).
class JobHistoryCards extends ConsumerStatefulWidget {
  final TechJobDetail job;
  const JobHistoryCards({super.key, required this.job});

  @override
  ConsumerState<JobHistoryCards> createState() => _JobHistoryCardsState();
}

class _JobHistoryCardsState extends ConsumerState<JobHistoryCards> {
  static const _pageSize = 50;
  int _page = 1;

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(tProvider);
    final id = widget.job.job.id;
    final q = ref.watch(jobEventsProvider(id));
    final events = q.valueOrNull ?? const <JobEvent>[];
    final shown = events.skip((_page - 1) * _pageSize).take(_pageSize);
    String eventName(String code) {
      final key = 'td.flow.event.$code';
      final name = t(key);
      return name == key ? code : name;
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TechCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              CardHead(t('td.flow.history')),
              JobFeedback(loading: q.isLoading && !q.hasValue, error: q.hasError ? q.error : null, retry: () => ref.invalidate(jobEventsProvider(id))),
              for (final e in shown)
                Container(
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: AppColors.divider))),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(child: Text(eventName(e.eventType), style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600))),
                          Text(jobStamp(t, e.occurredAt), style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                        ],
                      ),
                      if (e.strokeIndex != null)
                        Text('${t('td.flow.strokeIndex')}: ${e.strokeIndex}', style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                      if (e.payload != null || e.forceSummary != null)
                        Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: SelectableText(
                            jsonEncode({if (e.payload != null) 'payload': e.payload, if (e.forceSummary != null) 'force_summary': e.forceSummary}),
                            style: const TextStyle(fontSize: 11, color: AppColors.textSecondary),
                          ),
                        ),
                    ],
                  ),
                ),
              if (q.hasValue && !q.hasError && events.isEmpty) Text(t('td.flow.noEvents'), style: _help),
              if (events.length > _pageSize) ...[
                const SizedBox(height: 12),
                Row(
                  children: [
                    TechButton(t('td.flow.previous'), small: true, style: CustomButtonStyle.outline, onPressed: _page <= 1 ? null : () => setState(() => _page--)),
                    Padding(padding: const EdgeInsets.symmetric(horizontal: 12), child: MonoText('$_page')),
                    TechButton(t('td.flow.next'), small: true, style: CustomButtonStyle.outline, onPressed: _page * _pageSize >= events.length ? null : () => setState(() => _page++)),
                  ],
                ),
              ],
            ],
          ),
        ),
        if (widget.job.incidents.isNotEmpty) ...[
          const SizedBox(height: 16),
          TechCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                CardHead(t('td.flow.incidents')),
                for (final i in widget.job.incidents)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(t('td.flow.incident.${i.type}'), style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
                        Text(i.description, style: const TextStyle(fontSize: 14, height: 1.4)),
                        Text(
                          '${jobStamp(t, i.createdAt)} · ${t(i.resolvedAt != null ? 'td.flow.resolved' : 'td.flow.unresolved')}',
                          style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ],
      ],
    );
  }
}

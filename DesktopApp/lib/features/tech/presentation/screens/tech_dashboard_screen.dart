import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../core/widgets/widgets.dart';
import '../../data/tech_store.dart';
import '../../domain/roster.dart';
import '../../domain/tech_models.dart';
import '../../i18n/tech_strings.dart';
import '../widgets/tech_shell.dart';
import '../widgets/tech_ui.dart';

/// Labels are English catalog names, shown through `tn` (FE `TechDashboard.tsx`).
const _groups = [
  (id: Phase.qc, label: 'Photo and QC', note: 'Robot finished, check and send'),
  (id: Phase.live, label: 'Writing now', note: 'Robot is running'),
  (id: Phase.ready, label: 'Ready to preview', note: 'Deposit paid'),
  (id: Phase.wait, label: 'Waiting for deposit', note: 'Preview allowed'),
  (id: Phase.done, label: 'Finished', note: 'Written and shipped'),
];

Color _robotColor(RobotState s) => switch (s) {
      RobotState.idle => AppColors.success,
      RobotState.writing => AppColors.ink,
      RobotState.calibrating => AppColors.warning,
      RobotState.offline => AppColors.textTertiary,
    };

String orderRoute(TechOrder o, Phase p) =>
    p == Phase.qc ? '/tech/qc/${Uri.encodeComponent(o.id)}' : '/tech/preview/${Uri.encodeComponent(o.id)}';

class TechDashboardScreen extends ConsumerWidget {
  const TechDashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    final user = ref.watch(sessionProvider);
    final tech = ref.watch(myTechnicianProvider);
    final mine = ref.watch(myOrdersProvider);
    final all = ref.watch(techOrdersProvider);
    final now = ref.now;
    final robots = tech?.robots ?? const <Robot>[];

    List<TechOrder> inPhase(Phase p) => mine.where((o) => phaseOf(o, now) == p).toList();
    final counts = {for (final p in Phase.values) p: inPhase(p).length};
    final open = mine.where((o) => const [Phase.qc, Phase.live, Phase.ready, Phase.wait].contains(phaseOf(o, now))).toList();
    final queueMinutes = open.fold<int>(0, (a, o) => a + o.minutes);
    final maxMin = math.max(1, open.fold<int>(1, (a, o) => math.max(a, o.minutes)));

    final hr = DateTime.now().hour;
    final greeting = t(hr < 12 ? 'sd.morning' : hr < 18 ? 'sd.afternoon' : 'sd.evening');
    final today = DateFormat('EEEE d MMMM', t.locale).format(DateTime.now());

    TechOrder? robotJob(String id) =>
        mine.where((o) => phaseOf(o, now) == Phase.live && o.run?.robotId == id).firstOrNull;

    final ordersCard = TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('td.myOrders'), tag: t('td.assigned', {'n': mine.length})),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
            decoration: BoxDecoration(color: AppColors.surfaceVariant, borderRadius: BorderRadius.circular(TechRadius.inner)),
            child: Row(
              children: [
                Expanded(child: Label(t('td.queueTime'))),
                MonoText(t('td.min', {'n': queueMinutes}), size: 16),
              ],
            ),
          ),
          const SizedBox(height: 8),
          for (final g in _groups) _Group(label: t.tn(g.label), note: t.tn(g.note), phase: g.id, rows: inPhase(g.id)),
          if (mine.isEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(t('td.none'), style: const TextStyle(fontWeight: FontWeight.w600)),
                  const SizedBox(height: 4),
                  Text(t('td.noneBody'), style: const TextStyle(color: AppColors.textSecondary, height: 1.5)),
                ],
              ),
            ),
        ],
      ),
    );

    final tiles = [
      KpiTile(label: t('td.kpi.qc'), value: '${counts[Phase.qc]}', hint: t('td.kpi.qcHint'), accent: true),
      KpiTile(label: t('td.kpi.live'), value: '${counts[Phase.live]}', hint: t('td.kpi.liveHint')),
      KpiTile(label: t('td.kpi.ready'), value: '${counts[Phase.ready]}', hint: t('td.kpi.readyHint')),
      KpiTile(label: t('td.kpi.wait'), value: '${counts[Phase.wait]}', hint: t('td.kpi.waitHint')),
    ];
    final kpis = IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (var i = 0; i < tiles.length; i++) ...[
            if (i > 0) const SizedBox(width: 16),
            Expanded(child: tiles[i]),
          ],
        ],
      ),
    );

    final states = [
      for (final s in RobotState.values) DonutSlice(t.tn(s.label), robots.where((r) => r.state == s).length, _robotColor(s)),
    ];

    final robotsCard = TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('td.myRobots'), tag: t('sd.simulated')),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Column(
                children: [
                  Donut(slices: states, center: '${robots.length}', caption: t('td.robotsCaption')),
                  const SizedBox(height: 16),
                  for (final s in states)
                    SizedBox(
                      width: 150,
                      child: Padding(
                        padding: const EdgeInsets.symmetric(vertical: 3),
                        child: Row(
                          children: [
                            Container(width: 8, height: 8, decoration: BoxDecoration(color: s.color, shape: BoxShape.circle)),
                            const SizedBox(width: 8),
                            Expanded(child: Text(s.label, style: const TextStyle(fontSize: 12))),
                            MonoText('${s.value}', size: 12),
                          ],
                        ),
                      ),
                    ),
                ],
              ),
              const SizedBox(width: 28),
              Expanded(
                child: Column(
                  children: [
                    for (final r in robots)
                      Container(
                        padding: const EdgeInsets.symmetric(vertical: 12),
                        decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: AppColors.divider))),
                        child: Row(
                          children: [
                            SizedBox(width: 64, child: MonoText(r.id, size: 13)),
                            SizedBox(width: 120, child: Align(alignment: Alignment.centerLeft, child: StatusPill(t.tn(r.state.label), _robotColor(r.state)))),
                            Expanded(child: Meter(r.ink / 100, semanticLabel: t('td.inkAria', {'id': r.id}))),
                            SizedBox(width: 48, child: Align(alignment: Alignment.centerRight, child: MonoText('${r.ink}%', size: 12))),
                            const SizedBox(width: 16),
                            SizedBox(
                              width: 120,
                              child: Text(
                                robotJob(r.id)?.id ??
                                    (mine.any((o) => o.assignment?.robotId == r.id && phaseOf(o, now) != Phase.done)
                                        ? t('td.orderWaiting')
                                        : t('td.noOrder')),
                                style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );

    final queueCard = TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('td.queueTitle')),
          if (open.isEmpty)
            Text(t('td.noOpen'), style: const TextStyle(color: AppColors.textSecondary))
          else
            for (final o in open)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Row(
                  children: [
                    SizedBox(width: 72, child: MonoText(o.id, size: 12, color: AppColors.textSecondary)),
                    Expanded(child: Meter(o.minutes / maxMin, height: 8)),
                    SizedBox(width: 56, child: Align(alignment: Alignment.centerRight, child: MonoText('${o.minutes}m', size: 12))),
                  ],
                ),
              ),
          const SizedBox(height: 12),
          Text(t('td.queueNote'), style: const TextStyle(fontSize: 12, color: AppColors.textSecondary, height: 1.4)),
        ],
      ),
    );

    final workloadCard = TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          CardHead(t('td.workload')),
          Row(
            children: [
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  MonoText('${tech == null ? 0 : loadOf(tech.id, all)}', size: 34),
                  Label(t('td.inQueue')),
                ]),
              ),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  MonoText('${robots.where((r) => r.state == RobotState.idle).length}', size: 34),
                  Label(t('td.idleRobots')),
                ]),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Text(tech?.skills.map(t.tn).join(' · ') ?? '', style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
        ],
      ),
    );

    final busy = (counts[Phase.live] ?? 0) > 0;
    return TechPage(
      title: '$greeting, ${user?.name ?? t('td.technician')}',
      subtitle: '$today · ${t.tn(tech?.shift ?? 'Technician desk')}',
      actions: [
        StatusPill(
          t('td.robotsState', {'n': robots.length, 'state': t(busy ? 'td.stWriting' : 'td.stReady')}),
          busy ? AppColors.ink : AppColors.success,
        ),
      ],
      body: LayoutBuilder(builder: (context, c) {
        final stats = Column(
          children: [
            kpis,
            const SizedBox(height: 16),
            robotsCard,
            const SizedBox(height: 16),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(child: queueCard),
                const SizedBox(width: 16),
                Expanded(child: workloadCard),
              ],
            ),
          ],
        );
        if (c.maxWidth < 1100) {
          return Column(children: [stats, const SizedBox(height: 16), ordersCard]);
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
    );
  }
}

class _Group extends ConsumerStatefulWidget {
  final String label;
  final String note;
  final Phase phase;
  final List<TechOrder> rows;
  const _Group({required this.label, required this.note, required this.phase, required this.rows});

  @override
  ConsumerState<_Group> createState() => _GroupState();
}

class _GroupState extends ConsumerState<_Group> {
  late bool _open = widget.phase != Phase.done;

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
                  Text(widget.label, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(widget.note,
                        style: const TextStyle(fontSize: 12, color: AppColors.textSecondary), overflow: TextOverflow.ellipsis),
                  ),
                  MonoText('${widget.rows.length}', size: 13, color: AppColors.textSecondary),
                ],
              ),
            ),
          ),
        ),
        if (_open)
          if (widget.rows.isEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(30, 0, 0, 8),
              child: Text(t('sd.nothing'), style: const TextStyle(fontSize: 13, color: AppColors.textTertiary)),
            )
          else
            for (final o in widget.rows) _Row(order: o, phase: widget.phase),
      ],
    );
  }
}

class _Row extends ConsumerWidget {
  final TechOrder order;
  final Phase phase;
  const _Row({required this.order, required this.phase});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    final o = order;
    final label = phase == Phase.done ? t('status.${o.status.name}') : t('td.row.${phase.name}');
    return Pressable(
      onTap: () => context.go(orderRoute(o, phase)),
      semanticLabel: '${o.id} ${t.tn(o.title)}',
      child: MouseRegion(
        cursor: SystemMouseCursors.click,
        child: Container(
          margin: const EdgeInsets.only(bottom: 8),
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
          decoration: BoxDecoration(
            color: AppColors.background,
            borderRadius: BorderRadius.circular(TechRadius.inner),
          ),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(t.tn(o.title), style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 2),
                    Text('${o.id} · ${o.name ?? t('common.customer')}',
                        style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  StatusPill(label, phase == Phase.done ? statusColor(o.status) : phaseColor(phase)),
                  const SizedBox(height: 4),
                  MonoText('${o.assignment?.robotId} · ${t('td.min', {'n': o.minutes})}', size: 11, color: AppColors.textSecondary),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

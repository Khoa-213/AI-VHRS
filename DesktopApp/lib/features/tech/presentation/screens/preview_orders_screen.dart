import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/widgets/widgets.dart';
import '../../data/tech_store.dart';
import '../../domain/tech_models.dart';
import '../../i18n/tech_strings.dart';
import '../widgets/tech_shell.dart';
import '../widgets/tech_ui.dart';
import 'tech_dashboard_screen.dart';

enum PickMode { preview, qc }

const _order = {
  PickMode.preview: [Phase.live, Phase.ready, Phase.wait],
  PickMode.qc: [Phase.qc, Phase.live],
};

/// First step of the Preview and QC tabs: pick which assigned order to work on
/// (FE `PreviewOrders.tsx`).
class PreviewOrdersScreen extends ConsumerWidget {
  final PickMode mode;
  const PreviewOrdersScreen({super.key, required this.mode});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    final mine = ref.watch(myOrdersProvider);
    final now = ref.now;
    final open = [
      for (final p in _order[mode]!)
        for (final o in mine.where((o) => phaseOf(o, now) == p)) (o: o, p: p),
    ];
    final qc = mode == PickMode.qc;

    return TechPage(
      title: t(qc ? 'po.titleQc' : 'po.title'),
      subtitle: t(qc ? 'po.bodyQc' : 'po.body'),
      body: open.isEmpty
          ? EmptyCard(
              title: t(qc ? 'po.emptyQc' : 'po.empty'),
              body: qc ? t('po.emptyQcBody') : t('po.emptyBody', {'link': t('po.dashboard')}),
              actions: [TechButton(t('qc.toDash'), style: CustomButtonStyle.outline, small: true, onPressed: () => context.go('/tech'))],
            )
          : Semantics(
              label: t('po.aria'),
              child: LayoutBuilder(builder: (context, c) {
                final cols = c.maxWidth > 1300 ? 3 : c.maxWidth > 820 ? 2 : 1;
                final w = (c.maxWidth - (cols - 1) * 16) / cols;
                return Wrap(
                  spacing: 16,
                  runSpacing: 16,
                  children: [
                    for (var i = 0; i < open.length; i++)
                      SizedBox(width: w, child: _OrderCard(order: open[i].o, phase: open[i].p, first: i == 0)),
                  ],
                );
              }),
            ),
    );
  }
}

class _OrderCard extends ConsumerWidget {
  final TechOrder order;
  final Phase phase;
  final bool first;
  const _OrderCard({required this.order, required this.phase, required this.first});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    final tech = ref.watch(myTechnicianProvider);
    final o = order;
    final sp = o.spec;
    final robotId = o.assignment!.robotId;
    final robot = tech?.robots.where((r) => r.id == robotId).firstOrNull;
    final p = phase.name;
    final cta = t('po.$p.cta');

    return TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(child: MonoText(o.id, size: 13, color: AppColors.textSecondary)),
              StatusPill(t('po.$p.label'), phaseColor(phase)),
            ],
          ),
          const SizedBox(height: 14),
          Text(t.tn(o.title), style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 4),
          Text('${o.name ?? t('common.customer')} · ${t.tn(sp.mode.label)}',
              style: const TextStyle(fontSize: 13, color: AppColors.textSecondary)),
          const SizedBox(height: 14),
          FactList([
            (t('po.paper'), Swatch(sp.paperColor, t.tn(sp.paper))),
            (t('po.pen'), valueText(t.tn(sp.pen))),
            (t('po.ink'), Swatch(sp.inkColor, t.tn(sp.ink))),
            (t('po.pieces'), valueText('${sp.qty}')),
            (t('po.time'), valueText(t('po.timeVal', {'n': o.minutes}))),
            (t('po.robot'), valueText(robot == null ? robotId : '$robotId, ${t.tn(robot.state.label)}')),
          ]),
          const SizedBox(height: 14),
          Text(t('po.$p.note'), style: const TextStyle(fontSize: 13, color: AppColors.textSecondary, height: 1.4)),
          const SizedBox(height: 18),
          TechButton(
            first && phase != Phase.wait ? t('po.nextUp', {'cta': cta}) : cta,
            style: phase == Phase.wait ? CustomButtonStyle.outline : CustomButtonStyle.primary,
            expand: true,
            onPressed: () => context.go(orderRoute(o, phase)),
          ),
        ],
      ),
    );
  }
}

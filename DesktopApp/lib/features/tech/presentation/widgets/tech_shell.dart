import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../auth/presentation/auth_notifier.dart';
import '../../data/tech_store.dart';
import '../../domain/tech_models.dart';
import '../../i18n/tech_strings.dart';
import 'tech_ui.dart';

enum TechTab { dashboard, preview, qc }

/// Desktop frame for every technician page: icon rail on the left (FE
/// `TechRail`), content on the right. The rail follows the mobile bottom bar:
/// paper background, hairline divider, ink for the active item.
class TechShell extends ConsumerWidget {
  final Widget child;
  final String location;
  const TechShell({super.key, required this.child, required this.location});

  TechTab get _active {
    if (location.startsWith('/tech/qc')) return TechTab.qc;
    if (location.startsWith('/tech/preview')) return TechTab.preview;
    return TechTab.dashboard;
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    final now = ref.now;
    final waiting = ref.watch(myOrdersProvider).where((o) => phaseOf(o, now) == Phase.qc).length;

    Widget item(TechTab tab, String to, String label, IconData icon, IconData activeIcon, [int count = 0]) {
      final on = _active == tab;
      final color = on ? AppColors.textPrimary : AppColors.textTertiary;
      return _RailButton(
        onTap: () => context.go(to),
        label: label,
        selected: on,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Stack(
              clipBehavior: Clip.none,
              children: [
                AnimatedContainer(
                  duration: AppTheme.motionFast,
                  width: 52,
                  height: 36,
                  decoration: BoxDecoration(
                    color: on ? AppColors.surfaceVariant : Colors.transparent,
                    borderRadius: BorderRadius.circular(TechRadius.control),
                  ),
                  child: Icon(on ? activeIcon : icon, size: 22, color: color),
                ),
                if (count > 0)
                  Positioned(
                    right: 2,
                    top: -4,
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                      decoration: BoxDecoration(color: AppColors.ink, borderRadius: BorderRadius.circular(TechRadius.control)),
                      child: MonoText('$count', size: 11, color: AppColors.onInk),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              label,
              textAlign: TextAlign.center,
              maxLines: 2,
              style: TextStyle(fontSize: 11, fontWeight: on ? FontWeight.w600 : FontWeight.w500, color: color),
            ),
          ],
        ),
      );
    }

    return Scaffold(
      body: Row(
        children: [
          Semantics(
            container: true,
            label: t('rail.tech'),
            child: Container(
              width: 104,
              decoration: const BoxDecoration(
                color: AppColors.background,
                border: Border(right: BorderSide(color: AppColors.divider)),
              ),
              padding: const EdgeInsets.symmetric(vertical: 24),
              child: Column(
                children: [
                  Tooltip(
                    message: t('rail.techMark'),
                    child: Container(
                      width: 48,
                      height: 48,
                      alignment: Alignment.center,
                      decoration: const BoxDecoration(color: AppColors.ink, shape: BoxShape.circle),
                      child: const Text('AV',
                          style: TextStyle(color: AppColors.onInk, fontWeight: FontWeight.w700, fontSize: 15, letterSpacing: -0.4)),
                    ),
                  ),
                  const SizedBox(height: 32),
                  item(TechTab.dashboard, '/tech', t('rail.dashboard'), Icons.grid_view_outlined, Icons.grid_view_rounded),
                  const SizedBox(height: 14),
                  item(TechTab.preview, '/tech/preview', t('rail.preview'), Icons.play_circle_outline_rounded, Icons.play_circle_rounded),
                  const SizedBox(height: 14),
                  item(TechTab.qc, '/tech/qc', t('rail.qc'), Icons.assignment_outlined, Icons.assignment_rounded, waiting),
                  const Spacer(),
                  const _PrototypeMenu(),
                  const SizedBox(height: 14),
                  _RailButton(
                    onTap: () => ref.read(authNotifierProvider.notifier).logout(),
                    label: t('rail.signOut'),
                    child: Column(
                      children: [
                        const Icon(Icons.logout_rounded, size: 22, color: AppColors.textTertiary),
                        const SizedBox(height: 6),
                        Text(t('rail.signOut'),
                            textAlign: TextAlign.center,
                            style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w500, color: AppColors.textTertiary)),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          Expanded(child: child),
        ],
      ),
    );
  }
}

class _RailButton extends StatelessWidget {
  final VoidCallback onTap;
  final String label;
  final bool selected;
  final Widget child;
  const _RailButton({required this.onTap, required this.label, required this.child, this.selected = false});

  @override
  Widget build(BuildContext context) => Semantics(
        button: true,
        selected: selected,
        label: label,
        excludeSemantics: true,
        child: MouseRegion(
          cursor: SystemMouseCursors.click,
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: onTap,
            child: SizedBox(width: 96, child: child),
          ),
        ),
      );
}

/// Prototype switch and demo reset, in place of the FE AssistiveTouch button.
class _PrototypeMenu extends ConsumerWidget {
  const _PrototypeMenu();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    final on = ref.watch(prototypeProvider);
    return PopupMenuButton<String>(
      tooltip: t('dk.prototype'),
      color: AppColors.surface,
      position: PopupMenuPosition.over,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(TechRadius.inner)),
      onSelected: (v) {
        if (v == 'toggle') ref.read(prototypeProvider.notifier).set(!on);
        if (v == 'reset') {
          ref.read(techOrdersProvider.notifier).resetDemo();
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(t('dk.resetDone'))));
        }
      },
      itemBuilder: (_) => [
        PopupMenuItem(
          value: 'toggle',
          child: SizedBox(
            width: 260,
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(t('dk.prototype'), style: const TextStyle(fontWeight: FontWeight.w600)),
                      Text(t('dk.prototypeHint'), style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                    ],
                  ),
                ),
                Switch(value: on, onChanged: null, activeTrackColor: AppColors.ink),
              ],
            ),
          ),
        ),
        PopupMenuItem(value: 'reset', child: Text(t('dk.reset'))),
      ],
      child: Column(
        children: [
          Icon(on ? Icons.science_rounded : Icons.science_outlined, size: 22, color: on ? AppColors.textPrimary : AppColors.textTertiary),
          const SizedBox(height: 6),
          Text(t('dk.prototype'),
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w500, color: AppColors.textTertiary)),
        ],
      ),
    );
  }
}

/// Page body inside the shell: header with title, subtitle and actions
/// (always ending with the language toggle), then the content, scrollable.
class TechPage extends ConsumerWidget {
  final String title;
  final String? subtitle;
  final List<Widget> actions;
  final Widget body;
  final bool scroll;
  const TechPage({super.key, required this.title, this.subtitle, this.actions = const [], required this.body, this.scroll = true});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final header = Padding(
      padding: const EdgeInsets.fromLTRB(40, 36, 40, 28),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: Theme.of(context).textTheme.displaySmall),
                if (subtitle != null) ...[
                  const SizedBox(height: 6),
                  Text(subtitle!, style: const TextStyle(fontSize: 14, color: AppColors.textSecondary, height: 1.4)),
                ],
              ],
            ),
          ),
          const SizedBox(width: 24),
          Wrap(spacing: 12, crossAxisAlignment: WrapCrossAlignment.center, children: [...actions, const LanguageToggle()]),
        ],
      ),
    );
    final content = Padding(padding: const EdgeInsets.fromLTRB(40, 0, 40, 40), child: body);
    return ColoredBox(
      color: AppColors.background,
      child: scroll
          ? CustomScrollView(slivers: [
              SliverToBoxAdapter(child: header),
              SliverToBoxAdapter(child: content),
            ])
          : Column(children: [header, Expanded(child: content)]),
    );
  }
}

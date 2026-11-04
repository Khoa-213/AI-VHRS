import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../auth/presentation/auth_notifier.dart';
import '../../data/providers.dart';
import '../../domain/job.dart';
import '../../i18n/tech_strings.dart';
import 'alert_bell.dart';
import 'estop.dart';
import 'tech_ui.dart';

/// Asks the backend again now: the buttons labelled Refresh, and Ctrl+R.
void reloadTechData(WidgetRef ref) {
  ref.invalidate(techJobsProvider);
  ref.invalidate(techJobProvider);
  ref.invalidate(robotStatusProvider);
  ref.invalidate(jobPhotosProvider);
  ref.invalidate(jobEventsProvider);
  ref.invalidate(jobCommandsProvider);
}

enum TechTab {
  dashboard('/tech', 'rail.dashboard', Icons.grid_view_outlined, Icons.grid_view_rounded),
  jobs('/tech/jobs', 'dk.nav.jobs', Icons.play_circle_outline_rounded, Icons.play_circle_rounded),
  qc('/tech/qc', 'rail.qc', Icons.assignment_outlined, Icons.assignment_rounded),
  settings('/settings', 'dk.settings.title', Icons.settings_outlined, Icons.settings_rounded);

  final String path;
  final String labelKey;
  final IconData icon;
  final IconData activeIcon;
  const TechTab(this.path, this.labelKey, this.icon, this.activeIcon);
}

/// Frame for every technician page. From [compactWidth] up: icon rail on the left (FE `TechRail`),
/// content on the right. On a phone: the content, with tabs at the bottom. Both use paper
/// background, a hairline divider and ink for the active item.
class TechShell extends ConsumerWidget {
  final Widget child;
  final String location;
  const TechShell({super.key, required this.child, required this.location});

  TechTab get _active {
    if (location.startsWith('/settings')) return TechTab.settings;
    if (location.startsWith('/tech/qc') || location.contains('filter=qc')) return TechTab.qc;
    if (location.startsWith('/tech/jobs')) return TechTab.jobs;
    return TechTab.dashboard;
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final jobs = ref.watch(techJobsProvider).valueOrNull ?? const [];
    final waiting = jobs.where((j) => j.status == JobStatus.written).length;
    int badge(TechTab tab) => tab == TechTab.qc ? waiting : 0;

    final Widget frame = isCompact(context)
        ? Scaffold(
            body: child,
            bottomNavigationBar: _BottomTabs(active: _active, badge: badge),
          )
        : Scaffold(
            body: Row(
              children: [
                _Rail(active: _active, badge: badge),
                Expanded(child: child),
              ],
            ),
          );
    final body = Column(children: [const EstopBand(), Expanded(child: frame)]);
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.keyR, control: true): () => reloadTechData(ref),
        const SingleActivator(LogicalKeyboardKey.keyR, meta: true): () => reloadTechData(ref),
      },
      child: Focus(autofocus: true, child: body),
    );
  }
}

/// Ink pill with a count, on the corner of a tab's icon.
class _CountBadge extends StatelessWidget {
  final int count;
  const _CountBadge(this.count);

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
        decoration: BoxDecoration(color: AppColors.ink, borderRadius: BorderRadius.circular(TechRadius.control)),
        child: MonoText('$count', size: 11, color: AppColors.onInk),
      );
}

class _Rail extends ConsumerWidget {
  final TechTab active;
  final int Function(TechTab) badge;
  const _Rail({required this.active, required this.badge});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);

    Widget item(TechTab tab) {
      final on = active == tab;
      final color = on ? AppColors.textPrimary : AppColors.textSecondary;
      final count = badge(tab);
      final label = t(tab.labelKey);
      return Padding(
        padding: const EdgeInsets.only(bottom: 14),
        child: _RailButton(
          onTap: () => context.go(tab.path),
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
                    child: Icon(on ? tab.activeIcon : tab.icon, size: 22, color: color),
                  ),
                  if (count > 0) Positioned(right: 2, top: -4, child: _CountBadge(count)),
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
        ),
      );
    }

    return Semantics(
      container: true,
      label: t('rail.tech'),
      child: Container(
        width: 104,
        decoration: const BoxDecoration(
          color: AppColors.background,
          border: Border(right: BorderSide(color: AppColors.divider)),
        ),
        // Scrolls on a short window, such as a tablet held sideways.
        child: LayoutBuilder(
          builder: (context, c) => SingleChildScrollView(
            child: ConstrainedBox(
              constraints: BoxConstraints(minHeight: c.maxHeight),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 24),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Column(
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
                        item(TechTab.dashboard),
                        item(TechTab.jobs),
                        item(TechTab.qc),
                      ],
                    ),
                    Column(
                      children: [
                        item(TechTab.settings),
                        _RailButton(
                          onTap: () => ref.read(authNotifierProvider.notifier).logout(),
                          label: t('rail.signOut'),
                          child: Column(
                            children: [
                              const Icon(Icons.logout_rounded, size: 22, color: AppColors.textSecondary),
                              const SizedBox(height: 6),
                              Text(t('rail.signOut'),
                                  textAlign: TextAlign.center,
                                  style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w500, color: AppColors.textSecondary)),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _BottomTabs extends ConsumerWidget {
  final TechTab active;
  final int Function(TechTab) badge;
  const _BottomTabs({required this.active, required this.badge});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    return DecoratedBox(
      decoration: const BoxDecoration(border: Border(top: BorderSide(color: AppColors.divider))),
      child: NavigationBarTheme(
        data: NavigationBarThemeData(
          height: 68,
          elevation: 0,
          backgroundColor: AppColors.background,
          surfaceTintColor: Colors.transparent,
          indicatorColor: AppColors.surfaceVariant,
          indicatorShape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(TechRadius.control)),
          iconTheme: WidgetStateProperty.resolveWith((s) => IconThemeData(
                size: 22,
                color: s.contains(WidgetState.selected) ? AppColors.textPrimary : AppColors.textSecondary,
              )),
          labelTextStyle: WidgetStateProperty.resolveWith((s) {
            final on = s.contains(WidgetState.selected);
            return TextStyle(
              fontSize: 11,
              fontWeight: on ? FontWeight.w600 : FontWeight.w500,
              color: on ? AppColors.textPrimary : AppColors.textSecondary,
            );
          }),
        ),
        child: NavigationBar(
          selectedIndex: active.index,
          onDestinationSelected: (i) => context.go(TechTab.values[i].path),
          destinations: [
            for (final tab in TechTab.values)
              NavigationDestination(
                label: t(tab.labelKey),
                selectedIcon: Icon(tab.activeIcon),
                icon: badge(tab) > 0
                    ? Stack(
                        clipBehavior: Clip.none,
                        children: [Icon(tab.icon), Positioned(right: -14, top: -6, child: _CountBadge(badge(tab)))],
                      )
                    : Icon(tab.icon),
              ),
          ],
        ),
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

/// Page body inside the shell: header with title, subtitle and actions
/// (always ending with the language toggle), then the content, scrollable.
/// On a phone the actions go under the title and the margins shrink.
class TechPage extends ConsumerWidget {
  final String title;
  final String? subtitle;
  final List<Widget> actions;
  final Widget body;
  final bool scroll;
  const TechPage({super.key, required this.title, this.subtitle, this.actions = const [], required this.body, this.scroll = true});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final compact = isCompact(context);
    final side = compact ? 16.0 : 40.0;
    final heading = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title, style: Theme.of(context).textTheme.displaySmall),
        if (subtitle != null) ...[
          const SizedBox(height: 6),
          Text(subtitle!, style: const TextStyle(fontSize: 14, color: AppColors.textSecondary, height: 1.4)),
        ],
      ],
    );
    final buttons = Wrap(
      spacing: 12,
      runSpacing: 8,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [...actions, const AlertBell(), const LanguageToggle()],
    );
    final header = Padding(
      padding: EdgeInsets.fromLTRB(side, compact ? 20 : 36, side, compact ? 16 : 28),
      child: compact
          ? Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [heading, const SizedBox(height: 12), buttons],
            )
          : Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [Expanded(child: heading), const SizedBox(width: 24), buttons],
            ),
    );
    final content = Padding(padding: EdgeInsets.fromLTRB(side, 0, side, compact ? 16 : 40), child: body);
    return ColoredBox(
      color: AppColors.background,
      child: SafeArea(
        bottom: false,
        child: scroll
            ? CustomScrollView(slivers: [
                SliverToBoxAdapter(child: header),
                SliverToBoxAdapter(child: content),
              ])
            : Column(children: [header, Expanded(child: content)]),
      ),
    );
  }
}

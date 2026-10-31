import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/widgets/widgets.dart';
import '../../data/providers.dart';
import '../../domain/robot.dart';
import '../../i18n/tech_strings.dart';
import 'job_widgets.dart';
import 'tech_ui.dart';

/// The open robot alerts behind a bell next to the language button: a dialog by the bell on a
/// desktop, a bottom sheet on a phone. Red while a level 4 alert is open.
class AlertBell extends ConsumerWidget {
  const AlertBell({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    final robots = ref.watch(robotStatusProvider).valueOrNull ?? const <RobotStatus>[];
    final alerts = robots.expand((r) => r.alerts).toList();
    final count = alerts.length;
    final red = alerts.any((a) => a.level >= 4);
    final fg = red ? Colors.white : AppColors.textPrimary;

    void open() {
      if (isCompact(context)) {
        showModalBottomSheet<void>(
          context: context,
          isScrollControlled: true,
          builder: (_) => ConstrainedBox(
            constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.85),
            child: const SafeArea(child: AlertList()),
          ),
        );
      } else {
        showDialog<void>(
          context: context,
          builder: (_) => const Dialog(
            alignment: Alignment.topRight,
            insetPadding: EdgeInsets.fromLTRB(24, 84, 40, 24),
            backgroundColor: AppColors.surface,
            child: SizedBox(width: 440, child: AlertList()),
          ),
        );
      }
    }

    return MouseRegion(
      cursor: SystemMouseCursors.click,
      child: Tooltip(
        message: t('rb.bell'),
        child: Pressable(
          onTap: open,
          semanticLabel: count > 0 ? t('rb.bellCount', {'n': count}) : t('rb.bell'),
          child: Container(
            height: 40,
            padding: const EdgeInsets.symmetric(horizontal: 14),
            decoration: BoxDecoration(
              color: red ? AppColors.alarm : AppColors.surface,
              borderRadius: BorderRadius.circular(TechRadius.control),
              border: red ? null : Border.all(color: AppColors.border),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(count > 0 ? Icons.notifications_active_rounded : Icons.notifications_none_rounded, size: 18, color: fg),
                if (count > 0) ...[const SizedBox(width: 8), MonoText(count > 99 ? '99+' : '$count', size: 13, color: fg)],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Acknowledge any alert; close levels 1 to 3 with a note. A red (level 4) alert closes only by a
/// Manager. Titles and actions come from the backend in Vietnamese and are shown as data.
class AlertList extends ConsumerStatefulWidget {
  const AlertList({super.key});

  @override
  ConsumerState<AlertList> createState() => _AlertListState();
}

class _AlertListState extends ConsumerState<AlertList> {
  final Map<int, TextEditingController> _notes = {};
  int? _busy;
  String? _error;

  @override
  void dispose() {
    for (final c in _notes.values) {
      c.dispose();
    }
    super.dispose();
  }

  TextEditingController _note(int id) => _notes.putIfAbsent(id, TextEditingController.new);

  Future<void> _act(RobotAlert a, {required bool resolve}) async {
    final t = ref.read(tProvider);
    setState(() {
      _busy = a.id;
      _error = null;
    });
    final api = ref.read(robotApiProvider);
    try {
      if (resolve) {
        await api.resolveAlert(a.id, _note(a.id).text.trim());
      } else {
        await api.ackAlert(a.id);
      }
      _note(a.id).clear();
    } catch (e) {
      if (mounted) setState(() => _error = techErrorText(t, e));
    }
    if (!mounted) return;
    setState(() => _busy = null);
    ref.invalidate(robotStatusProvider);
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(tProvider);
    final q = ref.watch(robotStatusProvider);
    final robots = (q.valueOrNull ?? const <RobotStatus>[]).where((r) => r.alerts.isNotEmpty).toList();
    final count = robots.fold<int>(0, (n, r) => n + r.alerts.length);

    (Color, Color) levelColors(int level) => switch (level) {
          >= 4 => (AppColors.alarm, Colors.white),
          3 => (AppColors.warning.withValues(alpha: 0.08), AppColors.warning),
          _ => (AppColors.surfaceVariant, AppColors.secondaryLight),
        };

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(count > 0 ? '${t('rb.alerts')} · $count' : t('rb.alerts'), style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 12),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Semantics(liveRegion: true, child: Text(_error!, style: const TextStyle(fontSize: 13, color: AppColors.error))),
            ),
          if (q.hasError && !q.hasValue) Text(techErrorText(t, q.error), style: const TextStyle(fontSize: 13, color: AppColors.error)),
          if (q.hasValue && count == 0) Text(t('rb.noAlerts'), style: const TextStyle(fontSize: 14, color: AppColors.textSecondary)),
          for (final r in robots) ...[
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Text('${r.robotCode} · ${r.headline}', style: const TextStyle(fontSize: 13, color: AppColors.textSecondary, height: 1.4)),
            ),
            for (final a in r.alerts)
              Container(
                margin: const EdgeInsets.only(bottom: 10),
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(color: AppColors.background, borderRadius: BorderRadius.circular(TechRadius.inner)),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                      decoration: BoxDecoration(color: levelColors(a.level).$1, borderRadius: BorderRadius.circular(6)),
                      child: Text(
                        [t('rb.level', {'n': a.level}), if (a.occurrences > 1) '×${a.occurrences}', jobStamp(t, a.raisedAt)].join(' · '),
                        style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: levelColors(a.level).$2),
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(a.title, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, height: 1.4)),
                    Text(a.action, style: const TextStyle(fontSize: 13, color: AppColors.textSecondary, height: 1.4)),
                    Text(a.code, style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                    const SizedBox(height: 8),
                    if (a.acknowledgedAt == null)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: TechButton(t('rb.ack'), small: true, style: CustomButtonStyle.outline, onPressed: _busy == a.id ? null : () => _act(a, resolve: false)),
                      ),
                    if (a.level >= 4)
                      Text(t('rb.redManagerOnly'), style: const TextStyle(fontSize: 12, color: AppColors.textSecondary))
                    else
                      Row(
                        children: [
                          Expanded(
                            child: TextField(
                              controller: _note(a.id),
                              onChanged: (_) => setState(() {}),
                              decoration: InputDecoration(hintText: t('rb.resolveNote'), isDense: true),
                            ),
                          ),
                          const SizedBox(width: 8),
                          TechButton(
                            t('rb.resolve'),
                            small: true,
                            onPressed: _busy == a.id || _note(a.id).text.trim().length < 3 ? null : () => _act(a, resolve: true),
                          ),
                        ],
                      ),
                  ],
                ),
              ),
          ],
        ],
      ),
    );
  }
}

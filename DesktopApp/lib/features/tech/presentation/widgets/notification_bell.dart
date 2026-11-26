import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/widgets/widgets.dart';
import '../../data/providers.dart';
import '../../domain/notification.dart';
import '../../i18n/tech_strings.dart';
import 'job_widgets.dart';
import 'tech_ui.dart';

/// The signed-in technician's notifications (a job assigned or cancelled), as FE `components/ui/NotificationBell.tsx`:
/// a bell with the unread count, a dialog by the bell on a desktop and a bottom sheet on a phone.
class NotificationBell extends ConsumerWidget {
  const NotificationBell({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    final unread = ref.watch(notificationsProvider).valueOrNull?.unreadCount ?? 0;

    void open() {
      if (isCompact(context)) {
        showModalBottomSheet<void>(
          context: context,
          isScrollControlled: true,
          builder: (_) => ConstrainedBox(
            constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.85),
            child: const SafeArea(child: NotificationList()),
          ),
        );
      } else {
        showDialog<void>(
          context: context,
          builder: (_) => const Dialog(
            alignment: Alignment.topRight,
            insetPadding: EdgeInsets.fromLTRB(24, 84, 40, 24),
            backgroundColor: AppColors.surface,
            child: SizedBox(width: 440, child: NotificationList()),
          ),
        );
      }
    }

    return MouseRegion(
      cursor: SystemMouseCursors.click,
      child: Tooltip(
        message: t('nt.bell'),
        child: Pressable(
          onTap: open,
          semanticLabel: unread > 0 ? t('nt.bellCount', {'n': unread}) : t('nt.bell'),
          child: Container(
            height: 40,
            padding: const EdgeInsets.symmetric(horizontal: 14),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(TechRadius.control),
              border: Border.all(color: AppColors.border),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.mail_outline_rounded, size: 18, color: AppColors.textPrimary),
                if (unread > 0) ...[const SizedBox(width: 8), MonoText(unread > 99 ? '99+' : '$unread', size: 13, color: AppColors.textPrimary)],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Newest first. Opening one marks it read; "Mark all as read" clears the count; "Load more" pages back.
class NotificationList extends ConsumerStatefulWidget {
  const NotificationList({super.key});

  @override
  ConsumerState<NotificationList> createState() => _NotificationListState();
}

class _NotificationListState extends ConsumerState<NotificationList> {
  /// Older pages loaded with "Load more", kept below the polled first page.
  final List<AppNotification> _older = [];
  final Set<int> _read = {};
  int? _olderNext;
  bool _olderLoaded = false;
  bool _busy = false;
  String? _error;

  Future<void> _act(Future<void> Function() action) async {
    if (_busy) return;
    final t = ref.read(tProvider);
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
    } catch (e) {
      if (mounted) setState(() => _error = techErrorText(t, e));
    }
    if (mounted) setState(() => _busy = false);
  }

  Future<void> _open(AppNotification n) => _act(() async {
        if (n.isRead || _read.contains(n.id)) return;
        await ref.read(notificationApiProvider).markRead(n.id);
        if (!mounted) return;
        setState(() => _read.add(n.id));
        ref.invalidate(notificationsProvider);
      });

  Future<void> _readAll() => _act(() async {
        await ref.read(notificationApiProvider).markAllRead();
        if (!mounted) return;
        ref.invalidate(notificationsProvider);
        setState(() {
          _read.addAll([..._older.map((n) => n.id)]);
        });
      });

  Future<void> _more(int beforeId) => _act(() async {
        final page = await ref.read(notificationApiProvider).list(beforeId: beforeId);
        if (!mounted) return;
        setState(() {
          _older.addAll(page.items);
          _olderNext = page.nextBeforeId;
          _olderLoaded = true;
        });
      });

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(tProvider);
    final q = ref.watch(notificationsProvider);
    final first = q.valueOrNull;
    final items = [...?first?.items, ..._older];
    final next = _olderLoaded ? _olderNext : first?.nextBeforeId;
    final unread = first?.unreadCount ?? 0;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(child: Text(t('nt.title'), style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700))),
              if (unread > 0) TechButton(t('nt.readAll'), small: true, style: CustomButtonStyle.outline, onPressed: _busy ? null : _readAll),
            ],
          ),
          const SizedBox(height: 12),
          if (q.hasError && first == null) Text(t('nt.error'), style: const TextStyle(fontSize: 13, color: AppColors.error)),
          if (!q.hasValue && q.isLoading) const Padding(padding: EdgeInsets.all(12), child: Center(child: CircularProgressIndicator())),
          if (first != null && items.isEmpty) Text(t('nt.empty'), style: const TextStyle(fontSize: 13, color: AppColors.textSecondary)),
          for (final n in items) _Row(n: n, read: n.isRead || _read.contains(n.id), onTap: _busy ? null : () => _open(n)),
          if (_error != null) ...[const SizedBox(height: 8), Text(_error!, style: const TextStyle(fontSize: 13, color: AppColors.error))],
          if (next != null) ...[
            const SizedBox(height: 12),
            TechButton(t('nt.more'), small: true, style: CustomButtonStyle.outline, onPressed: _busy ? null : () => _more(next)),
          ],
        ],
      ),
    );
  }
}

class _Row extends ConsumerWidget {
  final AppNotification n;
  final bool read;
  final VoidCallback? onTap;
  const _Row({required this.n, required this.read, required this.onTap});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    return Semantics(
      button: !read,
      child: InkWell(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 12),
          decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: AppColors.divider))),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Wrap(
                spacing: 8,
                runSpacing: 4,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  if (!read) StatusPill(t('nt.unread'), AppColors.ink),
                  Text(jobStamp(t, n.createdAt), style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                  if (n.orderId case final id?) Text(t('nt.order', {'id': id}), style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                ],
              ),
              const SizedBox(height: 4),
              Text(n.title, style: TextStyle(fontSize: 14, fontWeight: read ? FontWeight.w500 : FontWeight.w700, height: 1.4)),
              if (n.body.isNotEmpty) Text(n.body, style: const TextStyle(fontSize: 13, color: AppColors.textSecondary, height: 1.4)),
            ],
          ),
        ),
      ),
    );
  }
}

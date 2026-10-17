import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../core/widgets/widgets.dart';
import '../../data/qc_photos.dart';
import '../../data/tech_store.dart';
import '../../domain/qc_items.dart';
import '../../domain/tech_models.dart';
import '../../i18n/tech_strings.dart';
import '../../sim/sim.dart';
import '../widgets/tech_shell.dart';
import '../widgets/tech_ui.dart';

enum _Tab { qc, photos }

enum _Sent { ok, failed }

/// Photo and QC for one finished robot run (FE `QualityCheck.tsx`).
///
/// Step 1: tick all 11 checks. Step 2: add the two required photos, an
/// optional note, and send to the customer (order becomes Written). Anything
/// wrong sends the order back to the robot queue with reasons.
class QualityCheckScreen extends ConsumerStatefulWidget {
  final String orderId;
  const QualityCheckScreen({super.key, required this.orderId});

  @override
  ConsumerState<QualityCheckScreen> createState() => _QualityCheckScreenState();
}

class _QualityCheckScreenState extends ConsumerState<QualityCheckScreen> {
  final Map<String, bool> _ticked = {};
  final Map<String, String> _photos = {};
  final _note = TextEditingController();
  final _failNote = TextEditingController();
  _Tab _tab = _Tab.qc;
  bool _failing = false;
  final List<String> _reasons = [];
  String _error = '';
  _Sent? _sent;
  int _sentPhotos = 0;

  @override
  void dispose() {
    _note.dispose();
    _failNote.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(tProvider);
    final session = ref.watch(sessionProvider);
    final prototype = ref.watch(prototypeProvider);
    final now = ref.now;
    final order = ref.watch(orderByIdProvider(widget.orderId));
    final another = TechButton(t('qc.another'), style: CustomButtonStyle.outline, small: true, onPressed: () => context.go('/tech/qc'));

    TechPage page(Widget body) => TechPage(
          title: order == null ? t('qc.titleShort') : t('qc.title', {'id': order.id}),
          subtitle: order == null
              ? t('qc.notFound')
              : t('qc.subtitle', {'title': t.tn(order.title), 'name': order.name ?? t('qc.theCustomer')}),
          actions: [another],
          body: body,
        );

    if (order == null) {
      return page(EmptyCard(title: t('qc.notFound'), body: t('qc.notFoundBody', {'id': widget.orderId})));
    }
    final asg = order.assignment;
    if (asg == null || asg.techId != session?.techId) {
      return page(EmptyCard(
        title: t('qc.notYours'),
        body: asg != null ? t('qc.belongsTo', {'id': order.id, 'name': asg.techName}) : t('qc.noTech', {'id': order.id}),
      ));
    }
    final name = order.name ?? t('qc.theCustomer');

    if (_sent != null) {
      final ok = _sent == _Sent.ok;
      return page(EmptyCard(
        title: ok ? t('qc.sentOk', {'name': name}) : t('qc.sentFail'),
        body: ok
            ? t('qc.sentOkBody', {'id': order.id, 'photos': _photoCount(t, _sentPhotos)})
            : t('qc.sentFailBody', {'id': order.id}),
        actions: [
          TechButton(t('qc.toDash'), small: true, onPressed: () => context.go('/tech')),
          TechButton(t('qc.nextOrder'), style: CustomButtonStyle.outline, small: true, onPressed: () => context.go('/tech/qc')),
        ],
      ));
    }
    if (!runDone(order, now)) {
      return page(EmptyCard(
        title: t(order.run != null ? 'qc.stillWriting' : 'qc.notWritten'),
        body: t('qc.opensAfter'),
        actions: [
          TechButton(t('qc.openSim'),
              style: CustomButtonStyle.outline, small: true, onPressed: () => context.go('/tech/preview/${Uri.encodeComponent(order.id)}')),
          if (prototype && order.run != null)
            TechButton(t('qc.protoFinish'),
                style: CustomButtonStyle.text, small: true, onPressed: () => ref.read(techOrdersProvider.notifier).finishRobotRun(order.id)),
        ],
      ));
    }

    final sp = order.spec;
    final groups = qcGroups(order, t);
    final all = groups.expand((g) => g.items).toList();
    final done = all.where((i) => _ticked[i.id] == true).length;
    final qcDone = done == all.length;
    final missing = photoSlots.where((s) => s.required && _photos[s.id] == null).toList();
    final ready = qcDone && missing.isEmpty;
    final requiredTotal = photoSlots.where((s) => s.required).length;
    final requiredDone = requiredTotal - missing.length;

    void tick(String id, bool on) => setState(() {
          _ticked[id] = on;
          // The last box moves the technician straight on to the photos.
          if (on && all.every((i) => _ticked[i.id] == true)) _tab = _Tab.photos;
        });

    Future<void> addPhoto(PhotoSlot s) async {
      setState(() => _error = '');
      try {
        final path = await pickQcPhoto('${order.id}-${s.id}');
        if (path != null) setState(() => _photos[s.id] = path);
      } on QcPhotoError catch (e) {
        setState(() => _error = t(e.key));
      } catch (_) {
        setState(() => _error = t('qc.photoErr'));
      }
    }

    Future<void> send() async {
      final count = _photos.length;
      final ok = await showConfirm(
        context,
        title: t('qc.confirmTitle', {'name': name}),
        body: t('qc.confirmBody', {'photos': _photoCount(t, count), 'note': _note.text.trim().isEmpty ? '' : t('qc.andNote')}),
        confirm: t('qc.sendCustomer'),
        cancel: t('qc.notYet'),
      );
      if (!ok) return;
      ref.read(techOrdersProvider.notifier).submitQc(
            order.id,
            QcReport(
              checked: all.where((i) => _ticked[i.id] == true).map((i) => i.id).toList(),
              total: all.length,
              photos: [
                for (final s in photoSlots)
                  if (_photos[s.id] != null) QcPhoto(slot: s.label, path: _photos[s.id]!),
              ],
              note: _note.text.trim(),
              by: session?.name ?? t('td.technician'),
              at: DateTime.now(),
            ),
          );
      setState(() {
        _sentPhotos = count;
        _sent = _Sent.ok;
      });
    }

    final tabs = Semantics(
      label: t('qc.stepsAria'),
      child: Container(
        padding: const EdgeInsets.all(4),
        decoration: BoxDecoration(color: AppColors.surfaceVariant, borderRadius: BorderRadius.circular(TechRadius.control)),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            _TabPill('${t('qc.tabChecklist')}  $done/${all.length}', on: _tab == _Tab.qc, onTap: () => setState(() => _tab = _Tab.qc)),
            Tooltip(
              message: qcDone ? '' : t('qc.finishFirst'),
              child: _TabPill('${t('qc.tabPhotos')}  $requiredDone/$requiredTotal',
                  on: _tab == _Tab.photos, onTap: qcDone ? () => setState(() => _tab = _Tab.photos) : null),
            ),
          ],
        ),
      ),
    );

    final reference = TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('qc.compare')),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(color: Color(sp.paperColor), borderRadius: BorderRadius.circular(TechRadius.inner)),
            child: Text(
              order.recognizedText.isEmpty ? t('qc.noText') : order.recognizedText,
              style: inkStyle(sp, 22).copyWith(height: 1.3),
            ),
          ),
          const SizedBox(height: 12),
          FactList([
            (t('qc.input'), valueText(t.tn(sp.mode.label))),
            (t('qc.paperRow'), Swatch(sp.paperColor, t.tn(sp.paper))),
            (t('qc.inkRow'), Swatch(sp.inkColor, t.tn(sp.ink))),
            (t('qc.piecesRow'), valueText('${sp.qty}')),
            (t('qc.robotRow'), valueText(asg.robotId)),
          ]),
        ],
      ),
    );

    Widget checklist() => Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TechCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(t('qc.progress', {'done': done, 'total': all.length}),
                      style: const TextStyle(fontSize: 14, color: AppColors.textSecondary)),
                  const SizedBox(height: 12),
                  Semantics(
                    label: t('qc.checked'),
                    value: '$done/${all.length}',
                    child: Row(
                      children: [
                        for (var i = 0; i < all.length; i++) ...[
                          if (i > 0) const SizedBox(width: 4),
                          Expanded(
                            child: AnimatedContainer(
                              duration: AppTheme.motionFast,
                              height: 6,
                              decoration: BoxDecoration(
                                color: _ticked[all[i].id] == true ? AppColors.ink : AppColors.surfaceVariant,
                                borderRadius: BorderRadius.circular(6),
                              ),
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ],
              ),
            ),
            for (final g in groups) ...[
              const SizedBox(height: 16),
              TechCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    CardHead(g.title, tag: '${g.items.where((i) => _ticked[i.id] == true).length}/${g.items.length}'),
                    for (final i in g.items)
                      InkCheck(value: _ticked[i.id] == true, title: i.title, detail: i.detail, onChanged: (v) => tick(i.id, v)),
                  ],
                ),
              ),
            ],
            const SizedBox(height: 16),
            _failCard(t, order),
          ],
        );

    Widget photosStep() => Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(t('qc.photosFor'), style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: 6),
            Text(t('qc.photosBody'), style: const TextStyle(fontSize: 14, color: AppColors.textSecondary)),
            const SizedBox(height: 16),
            LayoutBuilder(builder: (context, c) {
              final cols = c.maxWidth > 900 ? 3 : 2;
              final w = (c.maxWidth - (cols - 1) * 16) / cols;
              return Wrap(
                spacing: 16,
                runSpacing: 16,
                children: [
                  for (final s in photoSlots)
                    SizedBox(
                      width: w,
                      child: _PhotoSlotCard(
                        slot: s,
                        path: _photos[s.id],
                        onPick: () => addPhoto(s),
                        onRemove: () => setState(() => _photos.remove(s.id)),
                        orderId: order.id,
                      ),
                    ),
                ],
              );
            }),
            if (_error.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text(_error, style: const TextStyle(color: AppColors.error, fontSize: 13)),
            ],
          ],
        );

    final sendCard = TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('qc.checklist')),
          Row(children: [
            const Icon(Icons.check_rounded, size: 18, color: AppColors.success),
            const SizedBox(width: 8),
            Text(t('qc.passed', {'n': all.length}), style: const TextStyle(fontWeight: FontWeight.w500)),
          ]),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: () => setState(() => _tab = _Tab.qc),
              icon: const Icon(Icons.arrow_back_rounded, size: 16),
              label: Text(t('qc.backList')),
            ),
          ),
          const SizedBox(height: 8),
          CustomTextField(label: t('qc.customerNote'), hint: t('qc.notePh'), controller: _note, maxLines: 3),
          const SizedBox(height: 12),
          Semantics(
            liveRegion: true,
            child: Text(
              ready
                  ? t('qc.allIn')
                  : t('qc.addPhotos', {
                      'list': missing.map((s) => t.tn(s.label).toLowerCase()).join(t('qc.and')),
                      's': missing.length > 1 ? 's' : '',
                    }),
              style: const TextStyle(fontSize: 13, color: AppColors.textSecondary),
            ),
          ),
          const SizedBox(height: 14),
          TechButton(t('qc.sendCustomer'), icon: Icons.send_rounded, expand: true, onPressed: ready ? send : null),
          if (prototype && !ready) ...[
            const SizedBox(height: 8),
            TechButton(
              t('qc.protoPhotos'),
              style: CustomButtonStyle.text,
              small: true,
              onPressed: () async {
                for (final s in photoSlots.where((s) => s.required && _photos[s.id] == null)) {
                  final path = await samplePhoto('${order.id}-${s.id}', s.label, sp.paperColor, sp.inkColor);
                  if (mounted) setState(() => _photos[s.id] = path);
                }
              },
            ),
          ],
        ],
      ),
    );

    final side = _tab == _Tab.qc
        ? Column(children: [
            reference,
            if (prototype && !qcDone) ...[
              const SizedBox(height: 12),
              TechButton(
                t('qc.protoTick'),
                style: CustomButtonStyle.text,
                small: true,
                onPressed: () => setState(() {
                  for (final i in all) {
                    _ticked[i.id] = true;
                  }
                  _tab = _Tab.photos;
                }),
              ),
            ],
          ])
        : Column(children: [sendCard, const SizedBox(height: 16), reference]);

    return page(Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        tabs,
        const SizedBox(height: 20),
        LayoutBuilder(builder: (context, c) {
          final main = _tab == _Tab.qc ? checklist() : photosStep();
          if (c.maxWidth < 1100) return Column(children: [main, const SizedBox(height: 16), side]);
          return Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [Expanded(child: main), const SizedBox(width: 16), SizedBox(width: 400, child: side)],
          );
        }),
      ],
    ));
  }

  String _photoCount(T t, int n) => t(n == 1 ? 'qc.photoOne' : 'qc.photoMany', {'n': n});

  Widget _failCard(T t, TechOrder order) => TechCard(
        child: !_failing
            ? Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: () => setState(() => _failing = true),
                  icon: const Icon(Icons.warning_amber_rounded, size: 18, color: AppColors.error),
                  label: Text(t('qc.reschedule'), style: const TextStyle(color: AppColors.error)),
                ),
              )
            : Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  CardHead(t('qc.whatWrong')),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      for (final r in qcFailReasons)
                        FilterChip(
                          label: Text(t.tn(r)),
                          selected: _reasons.contains(r),
                          onSelected: (on) => setState(() => on ? _reasons.add(r) : _reasons.remove(r)),
                        ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  CustomTextField(label: t('qc.scheduleNote'), controller: _failNote, maxLines: 2),
                  const SizedBox(height: 16),
                  Row(
                    children: [
                      MouseRegion(
                        cursor: _reasons.isEmpty ? SystemMouseCursors.forbidden : SystemMouseCursors.click,
                        child: FilledButton.icon(
                          style: FilledButton.styleFrom(backgroundColor: AppColors.error, foregroundColor: AppColors.onInk),
                          onPressed: _reasons.isEmpty
                              ? null
                              : () {
                                  ref.read(techOrdersProvider.notifier).failQc(order.id, List.of(_reasons), _failNote.text.trim());
                                  setState(() => _sent = _Sent.failed);
                                },
                          icon: const Icon(Icons.refresh_rounded, size: 18),
                          label: Text(t('qc.rescheduleBtn')),
                        ),
                      ),
                      const SizedBox(width: 12),
                      TechButton(t('qc.cancel'), style: CustomButtonStyle.text, small: true, onPressed: () => setState(() => _failing = false)),
                    ],
                  ),
                ],
              ),
      );
}

class _TabPill extends StatelessWidget {
  final String label;
  final bool on;
  final VoidCallback? onTap;
  const _TabPill(this.label, {required this.on, this.onTap});

  @override
  Widget build(BuildContext context) => Semantics(
        button: true,
        selected: on,
        enabled: onTap != null,
        child: MouseRegion(
          cursor: onTap == null ? SystemMouseCursors.forbidden : SystemMouseCursors.click,
          child: GestureDetector(
            onTap: onTap,
            child: AnimatedContainer(
              duration: AppTheme.motionFast,
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
              decoration: BoxDecoration(
                color: on ? AppColors.ink : Colors.transparent,
                borderRadius: BorderRadius.circular(TechRadius.control),
              ),
              child: Text(
                label,
                style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                  color: on ? AppColors.onInk : onTap == null ? AppColors.textTertiary : AppColors.textPrimary,
                  fontFeatures: const [FontFeature.tabularFigures()],
                ),
              ),
            ),
          ),
        ),
      );
}

class _PhotoSlotCard extends ConsumerWidget {
  final PhotoSlot slot;
  final String? path;
  final VoidCallback onPick;
  final VoidCallback onRemove;
  final String orderId;
  const _PhotoSlotCard({required this.slot, required this.path, required this.onPick, required this.onRemove, required this.orderId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    final label = t.tn(slot.label);
    final has = path != null;
    return TechCard(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(child: Text(label, style: const TextStyle(fontWeight: FontWeight.w600))),
              StatusPill(
                has ? t('qc.added') : slot.required ? t('qc.required') : t('qc.optional'),
                has ? AppColors.success : slot.required ? AppColors.ink : AppColors.textSecondary,
              ),
            ],
          ),
          const SizedBox(height: 12),
          AspectRatio(
            aspectRatio: 4 / 3,
            child: has
                ? ClipRRect(
                    borderRadius: BorderRadius.circular(TechRadius.inner),
                    child: Stack(
                      fit: StackFit.expand,
                      children: [
                        Image.file(File(path!), fit: BoxFit.cover, semanticLabel: t('rs.photoAlt', {'slot': label, 'id': orderId})),
                        Positioned(
                          left: 0,
                          right: 0,
                          bottom: 0,
                          child: Container(
                            color: const Color(0xB3121212),
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                            child: Row(
                              children: [
                                Expanded(
                                  child: Text(t.tn(slot.hint),
                                      style: const TextStyle(fontSize: 12, color: AppColors.onInk), overflow: TextOverflow.ellipsis),
                                ),
                                IconButton(
                                  tooltip: t('qc.retake', {'label': label}),
                                  onPressed: onPick,
                                  icon: const Icon(Icons.refresh_rounded, size: 18, color: AppColors.onInk),
                                ),
                                IconButton(
                                  tooltip: t('qc.removePhoto', {'label': label}),
                                  onPressed: onRemove,
                                  icon: const Icon(Icons.close_rounded, size: 18, color: AppColors.onInk),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ],
                    ),
                  )
                : Semantics(
                    button: true,
                    label: t('qc.photoLabel', {'label': label}),
                    child: MouseRegion(
                      cursor: SystemMouseCursors.click,
                      child: GestureDetector(
                        onTap: onPick,
                        child: Container(
                          decoration: BoxDecoration(
                            color: AppColors.background,
                            borderRadius: BorderRadius.circular(TechRadius.inner),
                            border: Border.all(color: slot.required ? AppColors.textTertiary : AppColors.border, width: 1.2),
                          ),
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              const Icon(Icons.add_a_photo_outlined, size: 28, color: AppColors.textSecondary),
                              const SizedBox(height: 10),
                              Text(t('qc.takePhoto'), style: const TextStyle(fontWeight: FontWeight.w600)),
                              const SizedBox(height: 4),
                              Padding(
                                padding: const EdgeInsets.symmetric(horizontal: 12),
                                child: Text(t.tn(slot.hint),
                                    textAlign: TextAlign.center, style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}

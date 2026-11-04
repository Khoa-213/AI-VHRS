import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/widgets/widgets.dart';
import '../../data/providers.dart';
import '../../data/tech_api.dart';
import '../../domain/job.dart';
import '../../i18n/tech_strings.dart';
import '../widgets/job_flow.dart';
import '../widgets/job_widgets.dart';
import '../widgets/tech_shell.dart';
import '../widgets/tech_ui.dart';

/// Checks a chosen photo before it is sent: JPG or PNG by content, long side at least 1280 px.
/// Answers its MIME type.
Future<String> validateProductPhoto(Uint8List bytes) async {
  final isJpeg = bytes.length > 3 && bytes[0] == 0xFF && bytes[1] == 0xD8 && bytes[2] == 0xFF;
  final isPng = bytes.length > 4 && bytes[0] == 0x89 && bytes[1] == 0x50 && bytes[2] == 0x4E && bytes[3] == 0x47;
  if (!isJpeg && !isPng) throw const TechFlowError('td.flow.invalidPhoto');
  final int width, height;
  try {
    final codec = await ui.instantiateImageCodec(bytes);
    final frame = await codec.getNextFrame();
    width = frame.image.width;
    height = frame.image.height;
    frame.image.dispose();
    codec.dispose();
  } catch (_) {
    throw const TechFlowError('td.flow.invalidPhoto');
  }
  if ((width > height ? width : height) < 1280) throw const TechFlowError('td.flow.photoTooSmall');
  return isJpeg ? 'image/jpeg' : 'image/png';
}

/// Product photos and QC of a written job (FE `JobPhotos.tsx`).
class JobPhotosScreen extends ConsumerStatefulWidget {
  final int jobId;
  const JobPhotosScreen({super.key, required this.jobId});

  @override
  ConsumerState<JobPhotosScreen> createState() => _JobPhotosScreenState();
}

class _JobPhotosScreenState extends ConsumerState<JobPhotosScreen> with JobRunner {
  @override
  int get runnerJobId => widget.jobId;

  PhotoKind _kind = PhotoKind.overall;
  int? _progress;

  /// An uploaded photo whose registration failed: retried without uploading it again.
  ({String key, PhotoKind kind})? _pending;
  final _failNote = TextEditingController();

  @override
  void dispose() {
    _failNote.dispose();
    super.dispose();
  }

  bool get _desktop => Platform.isWindows || Platform.isMacOS || Platform.isLinux;

  Future<void> _upload(Uint8List bytes) async {
    final api = ref.read(techApiProvider);
    final mime = await validateProductPhoto(bytes);
    setState(() => _progress = 0);
    final ticket = await api.requestPhotoUpload(widget.jobId, mimeType: mime, sizeBytes: bytes.length);
    await api.uploadPhotoBinary(ticket, bytes, mimeType: mime, onProgress: (p) {
      if (mounted) setState(() => _progress = p);
    });
    final kind = _kind;
    setState(() => _pending = (key: ticket.photoKey, kind: kind));
    await api.registerPhoto(widget.jobId, photoKey: ticket.photoKey, kind: kind);
    if (mounted) {
      setState(() {
        _pending = null;
        _progress = null;
      });
    }
  }

  Future<void> _pickFile() async {
    final file = await openFile(acceptedTypeGroups: const [
      XTypeGroup(label: 'JPG, PNG', extensions: ['jpg', 'jpeg', 'png'], uniformTypeIdentifiers: ['public.jpeg', 'public.png']),
    ]);
    if (file == null) return;
    final bytes = await file.readAsBytes();
    await run(() => _upload(bytes));
  }

  Future<void> _pickImage(ImageSource source) async {
    final file = await ImagePicker().pickImage(source: source);
    if (file == null) return;
    final bytes = await file.readAsBytes();
    await run(() => _upload(bytes));
  }

  Future<void> _fail(ProductPhoto p) async {
    final t = ref.read(tProvider);
    final note = TextEditingController(text: p.qcNote ?? '');
    final save = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setInner) => Dialog(
          backgroundColor: AppColors.surface,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 440),
            child: Padding(
              padding: const EdgeInsets.all(28),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(t('dk.photo.failNote'), style: Theme.of(ctx).textTheme.headlineSmall),
                  const SizedBox(height: 16),
                  CustomTextField(label: t('td.flow.note'), controller: note, maxLines: 3, maxLength: 500, autofocus: true, onChanged: (_) => setInner(() {})),
                  const SizedBox(height: 16),
                  Wrap(
                    spacing: 12,
                    runSpacing: 8,
                    children: [
                      TechButton(t('td.flow.saveQc'), small: true, onPressed: note.text.trim().length < 3 ? null : () => Navigator.of(ctx).pop(true)),
                      TechButton(t('dk.confirm.cancel'), small: true, style: CustomButtonStyle.text, onPressed: () => Navigator.of(ctx).pop(false)),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
    final text = note.text;
    note.dispose();
    if (save == true) await run(() => ref.read(techApiProvider).setPhotoQc(widget.jobId, p.id, QcResult.fail, note: text));
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(tProvider);
    final id = widget.jobId;
    final q = ref.watch(techJobProvider(id));
    final d = q.valueOrNull;
    final photosQ = ref.watch(jobPhotosProvider(id));
    final photos = photosQ.valueOrNull ?? const <ProductPhoto>[];
    final j = d?.job;
    final editable = j?.status == JobStatus.written;
    final blocked = flowBusy || q.hasError || q.isLoading || photosQ.hasError || !photosQ.hasValue || photosQ.isLoading;
    final api = ref.read(techApiProvider);

    final grid = LayoutBuilder(builder: (context, c) {
      final cols = c.maxWidth >= 720 ? 3 : (c.maxWidth >= 300 ? 2 : 1);
      final width = (c.maxWidth - (cols - 1) * 16) / cols;
      return Wrap(
        spacing: 16,
        runSpacing: 16,
        children: [
          for (final p in photos)
            SizedBox(
              width: width,
              child: _PhotoCard(
                photo: p,
                editable: editable,
                disabled: blocked,
                onPass: () => run(() => api.setPhotoQc(id, p.id, QcResult.pass)),
                onFail: () => _fail(p),
                onRemove: () => run(() => api.removePhoto(id, p.id), confirm: t('td.flow.confirmDeletePhoto')),
                onReload: () => ref.invalidate(jobPhotosProvider(id)),
              ),
            ),
        ],
      );
    });

    final canAdd = !blocked && _pending == null && photos.length < 10;
    final upload = TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('td.flow.upload'), tag: '${photos.length}/10'),
          FlowSelect<PhotoKind>(
            label: t('td.flow.photoKind'),
            value: _kind,
            options: {for (final v in PhotoKind.values) v: t('td.flow.photo.${v.code}')},
            onChanged: _pending != null ? null : (v) => setState(() => _kind = v),
          ),
          const SizedBox(height: 8),
          Text(t('dk.photo.rules'), style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
          const SizedBox(height: 12),
          if (_progress != null && _pending == null) ...[
            Meter(_progress! / 100, semanticLabel: t('td.flow.uploadProgress')),
            const SizedBox(height: 12),
          ],
          if (_pending case final pending?) ...[
            Text(t('td.flow.registrationPending'), style: const TextStyle(fontSize: 13, color: AppColors.warning, height: 1.4)),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                TechButton(
                  t('td.flow.retryRegister'),
                  small: true,
                  onPressed: flowBusy
                      ? null
                      : () => run(() async {
                            await api.registerPhoto(id, photoKey: pending.key, kind: pending.kind);
                            if (mounted) {
                              setState(() {
                                _pending = null;
                                _progress = null;
                              });
                            }
                          }),
                ),
                TechButton(
                  t('td.flow.discardUpload'),
                  small: true,
                  style: CustomButtonStyle.outline,
                  onPressed: flowBusy
                      ? null
                      : () => setState(() {
                            _pending = null;
                            _progress = null;
                          }),
                ),
              ],
            ),
          ] else if (_desktop)
            TechButton(t('dk.photo.pickFile'), icon: Icons.add_rounded, expand: true, small: true, onPressed: canAdd ? _pickFile : null)
          else
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                TechButton(t('dk.photo.camera'), icon: Icons.photo_camera_outlined, small: true, onPressed: canAdd ? () => _pickImage(ImageSource.camera) : null),
                TechButton(t('dk.photo.gallery'), small: true, style: CustomButtonStyle.outline, onPressed: canAdd ? () => _pickImage(ImageSource.gallery) : null),
              ],
            ),
        ],
      ),
    );

    bool hasKind(PhotoKind k) => photos.any((p) => p.kind == k);
    final failing = photos.where((p) => p.qcResult != QcResult.pass).length;
    Widget check(String label, String value, Color color) => Container(
          padding: const EdgeInsets.symmetric(vertical: 10),
          decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: AppColors.divider))),
          child: Row(
            children: [
              Expanded(child: Text(label, style: const TextStyle(fontSize: 14))),
              Text(value, style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: color)),
            ],
          ),
        );
    final submit = TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('td.flow.submitPhotos')),
          Text(t('td.flow.photoGate'), style: const TextStyle(fontSize: 13, color: AppColors.warning, height: 1.4)),
          const SizedBox(height: 8),
          check(t('td.flow.photo.OVERALL'), hasKind(PhotoKind.overall) ? '✓' : '–', hasKind(PhotoKind.overall) ? AppColors.success : AppColors.warning),
          check(t('td.flow.photo.CLOSE_UP'), hasKind(PhotoKind.closeUp) ? '✓' : '–', hasKind(PhotoKind.closeUp) ? AppColors.success : AppColors.warning),
          check(t('td.api.passed'), '${photos.length - failing}/${photos.length}', failing == 0 && photos.isNotEmpty ? AppColors.success : AppColors.warning),
          const SizedBox(height: 16),
          TechButton(
            t('td.flow.submitPhotos'),
            expand: true,
            onPressed: blocked || _pending != null || !photosReady(photos)
                ? null
                : () => run(() => api.submitPhotos(id), confirm: t('td.flow.confirmSubmitPhotos')),
          ),
          const SizedBox(height: 20),
          CardHead(t('td.flow.qcFail')),
          Text(t('td.flow.qcFailHelp'), style: const TextStyle(fontSize: 13, color: AppColors.textSecondary, height: 1.4)),
          const SizedBox(height: 12),
          CustomTextField(label: t('td.flow.reason'), controller: _failNote, maxLines: 2, maxLength: 500, enabled: !blocked, onChanged: (_) => setState(() {})),
          const SizedBox(height: 8),
          TechButton(
            t('td.flow.qcFail'),
            small: true,
            style: CustomButtonStyle.outline,
            onPressed: blocked || _failNote.text.trim().length < 3
                ? null
                : () => run(() => api.failQc(id, _failNote.text), confirm: t('td.flow.confirmQcFail')),
          ),
        ],
      ),
    );

    final main = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        JobFeedback(loading: !photosQ.hasValue && photosQ.isLoading, error: photosQ.hasError ? photosQ.error : null, retry: () => ref.invalidate(jobPhotosProvider(id))),
        FlowMessages(busy: flowBusy, error: flowError, notice: flowNotice),
        if (photos.isNotEmpty) grid,
        if (photosQ.hasValue && !photosQ.hasError && photos.isEmpty)
          EmptyCard(title: t('td.flow.photos'), body: t('td.flow.noPhotos')),
        if (j?.status == JobStatus.photoUploaded) ...[
          const SizedBox(height: 12),
          Text(t('td.flow.photosSubmitted'), style: const TextStyle(fontSize: 14, color: AppColors.success)),
        ],
      ],
    );
    final side = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [upload, const SizedBox(height: 16), submit],
    );

    return TechPage(
      title: d == null ? t('td.flow.photos') : '${t('td.flow.photos')} · ${j!.orderCode.isEmpty ? j.orderId : j.orderCode}',
      subtitle: t('td.flow.photoHelp'),
      actions: [
        TechButton(t('td.api.back'), small: true, style: CustomButtonStyle.outline, icon: Icons.arrow_back_rounded, onPressed: () => context.go('/tech/qc')),
        TechButton(t('td.api.reload'), small: true, style: CustomButtonStyle.outline, onPressed: () => reloadTechData(ref)),
      ],
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          JobFeedback(loading: !q.hasValue && q.isLoading, error: q.hasError ? q.error : null, retry: () => reloadTechData(ref)),
          if (d != null)
            LayoutBuilder(builder: (context, c) {
              if (!editable) return main;
              if (c.maxWidth < 900) {
                return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [main, const SizedBox(height: 16), side]);
              }
              return Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [Expanded(child: main), const SizedBox(width: 16), SizedBox(width: 400, child: side)],
              );
            }),
        ],
      ),
    );
  }
}

class _PhotoCard extends ConsumerWidget {
  final ProductPhoto photo;
  final bool editable;
  final bool disabled;
  final VoidCallback onPass;
  final VoidCallback onFail;
  final VoidCallback onRemove;
  final VoidCallback onReload;
  const _PhotoCard({
    required this.photo,
    required this.editable,
    required this.disabled,
    required this.onPass,
    required this.onFail,
    required this.onRemove,
    required this.onReload,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    final p = photo;
    final name = t('td.flow.photo.${p.kind.code}');
    // Scrolls inside the frame on a narrow photo card, where the sentence wraps a lot.
    final expired = SingleChildScrollView(
      child: Column(
        children: [
          Text(t('td.flow.photoLinkExpired'), textAlign: TextAlign.center, style: const TextStyle(fontSize: 13, color: AppColors.secondaryLight)),
          const SizedBox(height: 8),
          TechButton(t('td.api.reload'), small: true, style: CustomButtonStyle.outline, onPressed: onReload),
        ],
      ),
    );
    final (label, color) = switch (p.qcResult) {
      QcResult.pass => (t('td.api.passed'), AppColors.success),
      QcResult.fail => (t('td.api.notPassed'), AppColors.error),
      null => (t('td.api.notRecorded'), AppColors.warning),
    };
    return TechCard(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            height: 200,
            clipBehavior: Clip.antiAlias,
            padding: p.url == null ? const EdgeInsets.all(12) : EdgeInsets.zero,
            decoration: BoxDecoration(color: AppColors.surfaceVariant, borderRadius: BorderRadius.circular(TechRadius.inner)),
            child: p.url == null
                ? expired
                : Image.network(
                    p.url!,
                    fit: BoxFit.cover,
                    semanticLabel: name,
                    errorBuilder: (_, _, _) => Padding(padding: const EdgeInsets.all(12), child: expired),
                  ),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(child: Text(name, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600))),
              Flexible(child: Align(alignment: Alignment.centerRight, child: StatusPill(label, color))),
            ],
          ),
          if (p.qcNote != null && p.qcNote!.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(p.qcNote!, style: const TextStyle(fontSize: 13, height: 1.4, color: AppColors.textSecondary)),
          ],
          if (editable) ...[
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: TechButton(
                    t('td.api.passed'),
                    small: true,
                    expand: true,
                    style: p.qcResult == QcResult.pass ? CustomButtonStyle.primary : CustomButtonStyle.outline,
                    onPressed: disabled ? null : onPass,
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: TechButton(
                    t('td.api.notPassed'),
                    small: true,
                    expand: true,
                    style: p.qcResult == QcResult.fail ? CustomButtonStyle.primary : CustomButtonStyle.outline,
                    onPressed: disabled ? null : onFail,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 4),
            TechButton(t('td.flow.remove'), small: true, style: CustomButtonStyle.text, onPressed: disabled ? null : onRemove),
          ],
        ],
      ),
    );
  }
}

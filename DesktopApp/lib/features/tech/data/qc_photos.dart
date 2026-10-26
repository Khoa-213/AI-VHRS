import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/painting.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';

/// Photo handling for QC (FE `phase.ts` shrinkImage / samplePhoto).
/// Photos are downscaled and written to the app support folder; orders keep
/// only the file path, so the saved order list stays small.

class QcPhotoError implements Exception {
  /// Translation key, e.g. `qc.err.process`.
  final String key;
  const QcPhotoError(this.key);
}

Future<Directory> _dir() async {
  final base = await getApplicationSupportDirectory();
  final d = Directory('${base.path}${Platform.pathSeparator}qc');
  if (!d.existsSync()) d.createSync(recursive: true);
  return d;
}

Future<String> _save(Uint8List png, String name) async {
  final d = await _dir();
  final f = File('${d.path}${Platform.pathSeparator}$name-${DateTime.now().millisecondsSinceEpoch}.png');
  await f.writeAsBytes(png, flush: true);
  return f.path;
}

/// Opens the file picker (Windows has no camera source) and returns the saved path, or null if cancelled.
Future<String?> pickQcPhoto(String name, {int max = 1100}) async {
  final file = await ImagePicker().pickImage(source: ImageSource.gallery);
  if (file == null) return null;
  final bytes = await file.readAsBytes();
  try {
    final buffer = await ui.ImmutableBuffer.fromUint8List(bytes);
    final desc = await ui.ImageDescriptor.encoded(buffer);
    final k = math.min(1.0, max / math.max(desc.width, desc.height));
    final codec = await desc.instantiateCodec(
      targetWidth: math.max(1, (desc.width * k).round()),
      targetHeight: math.max(1, (desc.height * k).round()),
    );
    final frame = await codec.getNextFrame();
    final data = await frame.image.toByteData(format: ui.ImageByteFormat.png);
    frame.image.dispose();
    codec.dispose();
    desc.dispose();
    buffer.dispose();
    if (data == null) throw const QcPhotoError('qc.err.process');
    return await _save(data.buffer.asUint8List(), name);
  } on QcPhotoError {
    rethrow;
  } catch (_) {
    throw const QcPhotoError('qc.err.format');
  }
}

/// Prototype only: a drawn stand-in for a camera shot, so QC can be completed without a camera.
Future<String> samplePhoto(String name, String label, int paper, int ink) async {
  const w = 640.0, h = 480.0;
  final rec = ui.PictureRecorder();
  final c = Canvas(rec);
  c.drawRect(const Rect.fromLTWH(0, 0, w, h), Paint()..color = const Color(0xFF2A2A2E));
  c.drawRect(const Rect.fromLTWH(70, 50, 500, 380), Paint()..color = Color(paper));
  void text(String s, TextStyle style, double y) {
    final tp = TextPainter(text: TextSpan(text: s, style: style), textDirection: TextDirection.ltr)..layout(maxWidth: 480);
    tp.paint(c, Offset((w - tp.width) / 2, y - tp.height / 2));
    tp.dispose();
  }

  text('Sample photo', TextStyle(fontFamily: 'DancingScript', fontSize: 44, color: Color(ink)), 225);
  text(label, TextStyle(fontFamily: 'BeVietnamPro', fontSize: 18, fontWeight: FontWeight.w500, color: Color(ink)), 285);
  final img = await rec.endRecording().toImage(w.toInt(), h.toInt());
  final data = await img.toByteData(format: ui.ImageByteFormat.png);
  img.dispose();
  return _save(data!.buffer.asUint8List(), name);
}

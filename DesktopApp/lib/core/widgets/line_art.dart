import 'dart:math' as math;

import 'package:flutter/material.dart';
import '../constants/app_colors.dart';

/// Hand-built line illustrations in solid ink — the visual motif of the app
/// (quill, nib, paper). Drawn with CustomPainter so they stay crisp at any
/// size and need no image assets.

/// A quill resting against an open sheet of paper, with a single ink stroke
/// trailing across the page.
class QuillPaperArt extends StatelessWidget {
  final double size;
  final Color color;

  const QuillPaperArt({super.key, this.size = 140, this.color = AppColors.ink});

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'Illustration of a quill writing on paper',
      child: CustomPaint(
        size: Size(size * 1.25, size),
        painter: _QuillPaperPainter(color),
      ),
    );
  }
}

class _QuillPaperPainter extends CustomPainter {
  final Color color;
  _QuillPaperPainter(this.color);

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final h = size.height;
    final line = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = w * 0.014
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    final fill = Paint()..color = color;

    // Paper sheet — slightly rotated, outline only.
    canvas.save();
    canvas.translate(w * 0.56, h * 0.58);
    canvas.rotate(-0.06);
    final sheet = RRect.fromRectAndRadius(
      Rect.fromCenter(center: Offset.zero, width: w * 0.62, height: h * 0.66),
      Radius.circular(w * 0.02),
    );
    canvas.drawRRect(sheet, Paint()..color = Colors.white);
    canvas.drawRRect(sheet, line);

    // The written line on the page.
    final ink = Path()..moveTo(-w * 0.22, h * 0.06);
    const waves = 5;
    for (var i = 0; i < waves; i++) {
      final x0 = -w * 0.22 + i * w * 0.07;
      ink.cubicTo(
        x0 + w * 0.02, h * (i.isEven ? -0.04 : 0.1),
        x0 + w * 0.05, h * (i.isEven ? 0.12 : -0.02),
        x0 + w * 0.07, h * 0.05,
      );
    }
    canvas.drawPath(ink, line..strokeWidth = w * 0.011);
    // Ruled guides.
    final guide = Paint()
      ..color = color.withValues(alpha: 0.18)
      ..strokeWidth = w * 0.006;
    for (final dy in [-0.14, -0.04, 0.16]) {
      canvas.drawLine(
        Offset(-w * 0.24, h * dy),
        Offset(w * 0.24, h * dy),
        guide,
      );
    }
    canvas.restore();

    // Quill — solid vane with a white shaft cut through it.
    canvas.save();
    canvas.translate(w * 0.28, h * 0.46);
    canvas.rotate(-0.5);
    final vane = Path()
      ..moveTo(0, h * 0.42)
      ..cubicTo(-w * 0.13, h * 0.2, -w * 0.12, -h * 0.2, 0, -h * 0.42)
      ..cubicTo(w * 0.1, -h * 0.18, w * 0.1, h * 0.18, 0, h * 0.42)
      ..close();
    canvas.drawPath(vane, fill);
    // Barbs: short white notches along the vane edge.
    final notch = Paint()
      ..color = Colors.white
      ..strokeWidth = w * 0.012
      ..strokeCap = StrokeCap.round;
    canvas.drawLine(Offset(-w * 0.075, -h * 0.06), Offset(-w * 0.03, -h * 0.03), notch);
    canvas.drawLine(Offset(w * 0.06, h * 0.08), Offset(w * 0.02, h * 0.1), notch);
    // Shaft.
    canvas.drawLine(
      Offset(0, -h * 0.36),
      Offset(0, h * 0.52),
      Paint()
        ..color = Colors.white
        ..strokeWidth = w * 0.01
        ..strokeCap = StrokeCap.round,
    );
    canvas.drawLine(Offset(0, h * 0.42), Offset(0, h * 0.54), line..strokeWidth = w * 0.014);
    canvas.restore();

    // Two small ink dots — a flourish, echoing stoic's stars.
    canvas.drawCircle(Offset(w * 0.9, h * 0.12), w * 0.012, fill);
    canvas.drawCircle(Offset(w * 0.96, h * 0.22), w * 0.008, fill);
  }

  @override
  bool shouldRepaint(covariant _QuillPaperPainter old) => old.color != color;
}

/// Small glyphs for the three input modes.
enum ModeGlyphKind { photo, text, canvas }

class ModeGlyph extends StatelessWidget {
  final ModeGlyphKind kind;
  final double size;
  final Color color;

  const ModeGlyph({
    super.key,
    required this.kind,
    this.size = 40,
    this.color = AppColors.ink,
  });

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      size: Size.square(size),
      painter: _ModeGlyphPainter(kind, color),
    );
  }
}

class _ModeGlyphPainter extends CustomPainter {
  final ModeGlyphKind kind;
  final Color color;
  _ModeGlyphPainter(this.kind, this.color);

  @override
  void paint(Canvas canvas, Size size) {
    final s = size.width;
    final stroke = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = s * 0.055
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    final fill = Paint()..color = color;

    switch (kind) {
      case ModeGlyphKind.photo:
        // A sheet with a handwritten squiggle, caught in viewfinder corners.
        final c = s * 0.16;
        for (final corner in [
          [Offset(s * 0.08, s * 0.08), 1.0, 1.0],
          [Offset(s * 0.92, s * 0.08), -1.0, 1.0],
          [Offset(s * 0.08, s * 0.92), 1.0, -1.0],
          [Offset(s * 0.92, s * 0.92), -1.0, -1.0],
        ]) {
          final o = corner[0] as Offset;
          final dx = corner[1] as double;
          final dy = corner[2] as double;
          canvas.drawPath(
            Path()
              ..moveTo(o.dx, o.dy + c * dy)
              ..lineTo(o.dx, o.dy)
              ..lineTo(o.dx + c * dx, o.dy),
            stroke,
          );
        }
        final squiggle = Path()..moveTo(s * 0.26, s * 0.56);
        squiggle.cubicTo(s * 0.34, s * 0.3, s * 0.42, s * 0.72, s * 0.5, s * 0.48);
        squiggle.cubicTo(s * 0.58, s * 0.26, s * 0.66, s * 0.7, s * 0.74, s * 0.44);
        canvas.drawPath(squiggle, stroke);
        canvas.drawCircle(Offset(s * 0.62, s * 0.3), s * 0.035, fill);
      case ModeGlyphKind.text:
        // "Aa" built from strokes, with a single-line baseline.
        final a = Path()
          ..moveTo(s * 0.1, s * 0.74)
          ..lineTo(s * 0.3, s * 0.2)
          ..lineTo(s * 0.5, s * 0.74)
          ..moveTo(s * 0.18, s * 0.54)
          ..lineTo(s * 0.42, s * 0.54);
        canvas.drawPath(a, stroke);
        canvas.drawCircle(Offset(s * 0.7, s * 0.6), s * 0.13, stroke);
        canvas.drawLine(Offset(s * 0.83, s * 0.44), Offset(s * 0.83, s * 0.74), stroke);
        canvas.drawLine(
          Offset(s * 0.08, s * 0.88),
          Offset(s * 0.92, s * 0.88),
          stroke..strokeWidth = s * 0.03,
        );
      case ModeGlyphKind.canvas:
        // A fountain-pen nib: solid body, white slit and breather hole.
        canvas.save();
        canvas.translate(s * 0.5, s * 0.5);
        canvas.rotate(math.pi / 4);
        final nib = Path()
          ..moveTo(0, s * 0.46)
          ..cubicTo(-s * 0.2, s * 0.12, -s * 0.2, -s * 0.12, -s * 0.16, -s * 0.3)
          ..lineTo(s * 0.16, -s * 0.3)
          ..cubicTo(s * 0.2, -s * 0.12, s * 0.2, s * 0.12, 0, s * 0.46)
          ..close();
        canvas.drawPath(nib, fill);
        canvas.drawRect(
          Rect.fromLTRB(-s * 0.19, -s * 0.46, s * 0.19, -s * 0.36),
          fill,
        );
        final cut = Paint()
          ..color = Colors.white
          ..strokeWidth = s * 0.045
          ..strokeCap = StrokeCap.round;
        canvas.drawLine(Offset(0, -s * 0.02), Offset(0, s * 0.4), cut);
        canvas.drawCircle(Offset(0, -s * 0.06), s * 0.06, Paint()..color = Colors.white);
        canvas.restore();
    }
  }

  @override
  bool shouldRepaint(covariant _ModeGlyphPainter old) =>
      old.kind != kind || old.color != color;
}

/// A faint cursive stroke used as texture inside dark hero cards.
class InkFlourish extends StatelessWidget {
  final Color color;
  const InkFlourish({super.key, required this.color});

  @override
  Widget build(BuildContext context) {
    return CustomPaint(painter: _FlourishPainter(color), size: Size.infinite);
  }
}

class _FlourishPainter extends CustomPainter {
  final Color color;
  _FlourishPainter(this.color);

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final h = size.height;
    final p = Path()..moveTo(-w * 0.05, h * 0.82);
    p.cubicTo(w * 0.12, h * 0.52, w * 0.22, h * 1.02, w * 0.36, h * 0.74);
    p.cubicTo(w * 0.46, h * 0.52, w * 0.4, h * 0.44, w * 0.34, h * 0.56);
    p.cubicTo(w * 0.28, h * 0.7, w * 0.52, h * 0.96, w * 0.66, h * 0.7);
    p.cubicTo(w * 0.76, h * 0.52, w * 0.9, h * 0.86, w * 1.08, h * 0.6);
    canvas.drawPath(
      p,
      Paint()
        ..color = color
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.2
        ..strokeCap = StrokeCap.round,
    );
  }

  @override
  bool shouldRepaint(covariant _FlourishPainter old) => old.color != color;
}

import 'dart:ui' as ui;

import 'package:flutter/material.dart';

/// Represents a single point in a handwriting stroke with timestamp.
class StrokePoint {
  final Offset position;
  final DateTime timestamp;

  const StrokePoint({required this.position, required this.timestamp});

  Map<String, dynamic> toJson() => {
        'x': position.dx,
        'y': position.dy,
        'timestamp': timestamp.millisecondsSinceEpoch,
      };
}

/// Represents a complete stroke (pen-down to pen-up).
class Stroke {
  final List<StrokePoint> points;
  final Color color;
  final double strokeWidth;
  final int order; // stroke sequence number

  const Stroke({
    required this.points,
    required this.color,
    required this.strokeWidth,
    required this.order,
  });

  Map<String, dynamic> toJson() => {
        'order': order,
        'color': color.value,
        'stroke_width': strokeWidth,
        'points': points.map((p) => p.toJson()).toList(),
      };
}

/// CustomPainter that renders handwriting strokes on a canvas.
/// Records touch coordinates and stroke sequence for trajectory reconstruction.
class HandwritingCanvasPainter extends CustomPainter {
  final List<Stroke> completedStrokes;
  final List<StrokePoint>? currentStrokePoints;
  final Color currentColor;
  final double currentStrokeWidth;

  HandwritingCanvasPainter({
    required this.completedStrokes,
    this.currentStrokePoints,
    required this.currentColor,
    required this.currentStrokeWidth,
  });

  @override
  void paint(Canvas canvas, Size size) {
    // Draw paper background
    canvas.drawRect(
      Rect.fromLTWH(0, 0, size.width, size.height),
      Paint()..color = Colors.white,
    );

    // Draw grid lines for writing guidance
    _drawGuideLines(canvas, size);

    // Draw completed strokes
    for (final stroke in completedStrokes) {
      _drawStroke(canvas, stroke.points, stroke.color, stroke.strokeWidth);
    }

    // Draw the current active stroke
    if (currentStrokePoints != null && currentStrokePoints!.isNotEmpty) {
      _drawStroke(canvas, currentStrokePoints!, currentColor, currentStrokeWidth);
    }
  }

  void _drawGuideLines(Canvas canvas, Size size) {
    final linePaint = Paint()
      ..color = const Color(0xFFE8ECF0)
      ..strokeWidth = 0.5;

    // Horizontal guide lines every 40px
    for (double y = 40; y < size.height; y += 40) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), linePaint);
    }

    // Light vertical margin line
    final marginPaint = Paint()
      ..color = const Color(0xFFFFCDD2)
      ..strokeWidth = 0.8;
    canvas.drawLine(
      const Offset(40, 0),
      Offset(40, size.height),
      marginPaint,
    );
  }

  void _drawStroke(Canvas canvas, List<StrokePoint> points, Color color, double width) {
    if (points.isEmpty) return;

    final paint = Paint()
      ..color = color
      ..strokeWidth = width
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..style = PaintingStyle.stroke;

    if (points.length == 1) {
      // Single point — draw a dot
      canvas.drawCircle(points.first.position, width / 2, paint..style = PaintingStyle.fill);
      return;
    }

    // Draw smooth path through points using quadratic bezier curves
    final path = Path();
    path.moveTo(points.first.position.dx, points.first.position.dy);

    for (int i = 1; i < points.length - 1; i++) {
      final p0 = points[i].position;
      final p1 = points[i + 1].position;
      final midPoint = Offset((p0.dx + p1.dx) / 2, (p0.dy + p1.dy) / 2);
      path.quadraticBezierTo(p0.dx, p0.dy, midPoint.dx, midPoint.dy);
    }

    // Draw the last segment
    if (points.length > 1) {
      final lastPoint = points.last.position;
      path.lineTo(lastPoint.dx, lastPoint.dy);
    }

    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant HandwritingCanvasPainter oldDelegate) {
    return oldDelegate.completedStrokes != completedStrokes ||
        oldDelegate.currentStrokePoints != currentStrokePoints ||
        oldDelegate.currentColor != currentColor ||
        oldDelegate.currentStrokeWidth != currentStrokeWidth;
  }
}

import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import '../domain/tech_models.dart';
import 'sim.dart';

/// Ink-on-black palette for the viewport: the monochrome theme turned down,
/// so the paper and the ink are the only colour on screen.
class _V {
  static const floor = Color(0xFF0E0E10);
  static const grid = Color(0x09FFFFFF);
  static const bench = Color(0xFF18181B);
  static const benchEdge = Color(0x12FFFFFF);
  static const link = Color(0xFFD4D4D8);
  static const linkHi = Color(0xFFF4F4F5);
  static const joint = Color(0xFF1B1B1E);
  static const ring = Color(0xFFA1A1AA);
  static const live = Color(0xFF6FBF8B);
  static const label = Color(0xFFC9C9CF);
  static const muted = Color(0xFF8B8B93);
  static const path = Color(0x8CFFFFFF);
}

/// Prebuilt text for the ink layer: one fill and one stroke painter per line.
class InkLayer {
  final List<(TextPainter fill, TextPainter stroke, PlanLine line)> lines;
  InkLayer._(this.lines);

  factory InkLayer.build(TechOrder o, Plan plan, Tuning tuning) {
    final sp = o.spec;
    final strokeW = math.max(0.3, sp.penW * 0.35 * (tuning.force / 1.2));
    final out = <(TextPainter, TextPainter, PlanLine)>[];
    for (final l in plan.lines) {
      final fill = TextPainter(
        text: TextSpan(text: l.text, style: inkStyle(sp, plan.fontPx)),
        textDirection: TextDirection.ltr,
      )..layout();
      final stroke = TextPainter(
        text: TextSpan(
          text: l.text,
          style: inkStyle(sp, plan.fontPx).copyWith(
            color: null,
            foreground: Paint()
              ..style = PaintingStyle.stroke
              ..strokeWidth = strokeW
              ..strokeJoin = StrokeJoin.round
              ..color = Color(sp.inkColor),
          ),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      out.add((fill, stroke, l));
    }
    return InkLayer._(out);
  }

  void paintLine(Canvas c, int i) {
    final (fill, stroke, l) = lines[i];
    final at = Offset(l.x0, l.y - fill.height / 2);
    fill.paint(c, at);
    stroke.paint(c, at);
  }

  void dispose() {
    for (final (f, s, _) in lines) {
      f.dispose();
      s.dispose();
    }
  }
}

/// Smoothed pen height for the side view, kept between frames.
class ZState {
  double z = 0;
}

/// Draws the bench, paper, ink so far, the FR3 arm and the side view
/// (FE `SimCanvas.tsx`). Logical size is [simW] × [simH], scaled to fit.
class SimPainter extends CustomPainter {
  final TechOrder order;
  final Plan plan;
  final SimViewport vp;
  final PenState pen;
  final Arm arm;
  final Tuning tuning;
  final ViewFlags flags;
  final InkLayer ink;
  final ZState z;
  final bool live;
  final String sideViewLabel;

  SimPainter({
    required this.order,
    required this.plan,
    required this.vp,
    required this.pen,
    required this.arm,
    required this.tuning,
    required this.flags,
    required this.ink,
    required this.z,
    required this.live,
    required this.sideViewLabel,
  });

  static TextStyle _mono(double size, Color color, {FontWeight w = FontWeight.w600}) =>
      TextStyle(fontFamily: 'BeVietnamPro', fontSize: size, fontWeight: w, color: color, fontFeatures: const [ui.FontFeature.tabularFigures()]);

  void _text(Canvas c, String s, Offset at, TextStyle style) {
    final tp = TextPainter(text: TextSpan(text: s, style: style), textDirection: TextDirection.ltr)..layout();
    tp.paint(c, Offset(at.dx, at.dy - tp.height * 0.8));
    tp.dispose();
  }

  @override
  void paint(Canvas canvas, Size size) {
    final k = math.min(size.width / simW, size.height / simH);
    canvas.save();
    canvas.translate((size.width - simW * k) / 2, (size.height - simH * k) / 2);
    canvas.scale(k);
    canvas.clipRect(const Rect.fromLTWH(0, 0, simW, simH));

    // Floor and bench
    canvas.drawRect(const Rect.fromLTWH(0, 0, simW, simH), Paint()..color = _V.floor);
    final grid = Paint()
      ..color = _V.grid
      ..strokeWidth = 1;
    for (double x = 0; x <= simW; x += 40) {
      canvas.drawLine(Offset(x, 0), Offset(x, simH), grid);
    }
    for (double y = 0; y <= simH; y += 40) {
      canvas.drawLine(Offset(0, y), Offset(simW, y), grid);
    }
    final bench = RRect.fromRectAndRadius(const Rect.fromLTWH(30, 50, simW - 60, simH - 100), const Radius.circular(10));
    canvas.drawRRect(bench, Paint()..color = _V.bench);
    canvas.drawRRect(
        bench,
        Paint()
          ..color = _V.benchEdge
          ..style = PaintingStyle.stroke);

    // Reach envelope
    if (flags.reach) {
      final p = Paint()
        ..color = _V.ring.withValues(alpha: 0.45)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.2;
      final r = 400 * px;
      const dash = 6.0, gap = 8.0;
      final step = (dash + gap) / r;
      for (double a = -1.2; a < 1.2; a += step) {
        canvas.drawArc(Rect.fromCircle(center: vp.base, radius: r), a, math.min(dash / r, 1.2 - a), false, p);
      }
    }

    // Paper
    final paper = vp.paper;
    final paperColor = Color(order.spec.paperColor);
    canvas.drawRect(
      paper.shift(const Offset(0, 10)),
      Paint()
        ..color = Colors.black.withValues(alpha: 0.55)
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 12),
    );
    canvas.drawRect(paper, Paint()..color = paperColor);

    // Planned path, dotted, for the lines not written yet
    if (flags.trajectory) {
      final p = Paint()
        ..color = _V.path
        ..strokeWidth = 1.5;
      for (var i = 0; i < plan.lines.length; i++) {
        if (i < pen.line) continue;
        final l = plan.lines[i];
        final from = i == pen.line ? pen.x : l.x0;
        for (double x = from; x < l.x1; x += 8) {
          canvas.drawLine(Offset(x, l.y), Offset(math.min(x + 2, l.x1), l.y), p);
        }
      }
    }

    // Ink written so far
    if (pen.char > 0) {
      if (order.layout.frame) {
        final m = paper.width * 0.05;
        final framePaint = Paint()
          ..color = Color(order.spec.inkColor)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.4;
        canvas.drawRect(paper.deflate(m), framePaint);
        canvas.drawRect(paper.deflate(m + 5), framePaint);
      }
      for (var i = 0; i < plan.lines.length; i++) {
        if (i > pen.line) break;
        final l = plan.lines[i];
        final right = i < pen.line ? l.x1 + 6 : pen.x;
        canvas.save();
        canvas.clipRect(Rect.fromLTWH(l.x0 - 6, l.y - plan.lineH / 2, math.max(0, right - l.x0 + 6), plan.lineH));
        ink.paintLine(canvas, i);
        canvas.restore();
      }
    }

    // Arm
    void link(Offset from, Offset to, double w) {
      canvas.drawLine(
        from + const Offset(6, 10),
        to + const Offset(6, 10),
        Paint()
          ..color = Colors.black.withValues(alpha: 0.35)
          ..strokeWidth = w + 6
          ..strokeCap = StrokeCap.round,
      );
      canvas.drawLine(
          from,
          to,
          Paint()
            ..color = _V.link
            ..strokeWidth = w
            ..strokeCap = StrokeCap.round);
      canvas.drawLine(
        from - Offset(0, w * 0.15),
        to - Offset(0, w * 0.15),
        Paint()
          ..color = _V.linkHi
          ..strokeWidth = w * 0.35
          ..strokeCap = StrokeCap.round,
      );
    }

    canvas.drawRRect(
      RRect.fromRectAndRadius(Rect.fromCenter(center: arm.base, width: 68, height: 68), const Radius.circular(10)),
      Paint()..color = const Color(0xFF232326),
    );
    link(arm.base, arm.elbow, 30);
    link(arm.elbow, arm.tip, 20);
    void joint(Offset pt, double r) {
      canvas.drawCircle(pt, r, Paint()..color = _V.joint);
      canvas.drawCircle(
          pt,
          r - 4,
          Paint()
            ..color = live ? _V.live : _V.ring
            ..style = PaintingStyle.stroke
            ..strokeWidth = 2.5);
    }

    joint(arm.base, 22);
    joint(arm.elbow, 17);
    joint(arm.tip, 11);
    // Pen holder and pen
    canvas.drawLine(
        arm.tip,
        arm.tip + const Offset(22, -14),
        Paint()
          ..color = const Color(0xFF2E2E33)
          ..strokeWidth = 6);
    canvas.drawCircle(arm.tip, pen.down ? 4 : 3, Paint()..color = pen.down ? Color(order.spec.inkColor) : const Color(0xFF9A9AA2));
    canvas.drawCircle(
        arm.tip,
        pen.down ? 4 : 3,
        Paint()
          ..color = Colors.white
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.5);
    if (flags.joints) {
      final s = _mono(12, _V.label);
      _text(canvas, 'J1 ${arm.q[0].toStringAsFixed(0)}°', arm.base + const Offset(-30, 52), s);
      _text(canvas, 'J4 ${arm.q[3].toStringAsFixed(0)}°', arm.elbow + const Offset(14, -12), s);
      _text(
        canvas,
        '${((arm.tip.dx - paper.left) / px).toStringAsFixed(0)}, ${((arm.tip.dy - paper.top) / px).toStringAsFixed(0)} mm',
        arm.tip + const Offset(18, 26),
        s,
      );
    }

    // Side view inset: pen height over the paper
    const bx = simW - 270;
    const by = simH - 150;
    canvas.drawRRect(
      RRect.fromRectAndRadius(const Rect.fromLTWH(bx, by, 230, 90), const Radius.circular(8)),
      Paint()..color = const Color(0xD10A0A0C),
    );
    _text(canvas, sideViewLabel, const Offset(bx + 12, by + 20), _mono(11, _V.muted, w: FontWeight.w700));
    final target = pen.down ? 0.0 : tuning.lift;
    z.z += (target - z.z) * 0.4;
    canvas.drawRect(const Rect.fromLTWH(bx + 12, by + 70, 206, 4), Paint()..color = paperColor);
    final penTop = by + 70 - 12 - z.z * 2.6;
    canvas.drawLine(
        Offset(bx + 115, penTop - 26),
        Offset(bx + 115, penTop),
        Paint()
          ..color = _V.link
          ..strokeWidth = 7
          ..strokeCap = StrokeCap.round);
    canvas.drawCircle(Offset(bx + 115, penTop + 3), 3, Paint()..color = Color(order.spec.inkColor));
    _text(canvas, 'Z +${z.z.toStringAsFixed(1)} mm', const Offset(bx + 140, by + 20), _mono(11, _V.label, w: FontWeight.w700));

    canvas.restore();
  }

  @override
  bool shouldRepaint(SimPainter old) =>
      old.pen.x != pen.x ||
      old.pen.y != pen.y ||
      old.pen.char != pen.char ||
      old.pen.down != pen.down ||
      old.flags != flags ||
      old.ink != ink ||
      old.live != live ||
      old.tuning != tuning ||
      old.sideViewLabel != sideViewLabel;
}

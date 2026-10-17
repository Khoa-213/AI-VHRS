import 'dart:math' as math;

import 'package:flutter/painting.dart';

import '../domain/tech_models.dart';

/// Stand-in for the Isaac Sim viewport, ported from FE `pages/tech/sim.ts`.
/// Nothing here talks to a simulator: the pen path is derived from the order
/// text and a 2-link arm follows it with inverse kinematics, so every order
/// option has a visible effect.

class Tuning {
  /// Pen speed on paper, mm/s.
  final double speed;

  /// Contact force, N. Wider and darker lines at higher force.
  final double force;

  /// How far the pen rises between words, mm.
  final double lift;

  const Tuning({this.speed = 60, this.force = 1.2, this.lift = 8});

  Tuning copyWith({double? speed, double? force, double? lift}) =>
      Tuning(speed: speed ?? this.speed, force: force ?? this.force, lift: lift ?? this.lift);
}

class ViewFlags {
  final bool trajectory;
  final bool reach;
  final bool joints;
  const ViewFlags({this.trajectory = true, this.reach = false, this.joints = true});

  ViewFlags copyWith({bool? trajectory, bool? reach, bool? joints}) => ViewFlags(
        trajectory: trajectory ?? this.trajectory,
        reach: reach ?? this.reach,
        joints: joints ?? this.joints,
      );
}

/// Logical size of the viewport. The painter scales it to fit.
const double simW = 1200;
const double simH = 720;

/// Pixels per millimetre in the viewport.
const double px = 2.6;
const _origin = Offset(660, 380);
const double _l1 = 200;
const double _l2 = 200;

class PlanLine {
  final String text;
  final double y, x0, x1;
  final int startChar;
  const PlanLine(this.text, this.y, this.x0, this.x1, this.startChar);
}

class Plan {
  final String text;
  final List<PlanLine> lines;
  final double fontPx;
  final double lineH;
  final int chars;
  const Plan(this.text, this.lines, this.fontPx, this.lineH, this.chars);
}

class SimViewport {
  final Rect paper;
  final Offset base;
  const SimViewport(this.paper, this.base);
}

String planText(TechOrder o) {
  final t = o.recognizedText.trim();
  return t.isEmpty ? 'Xin chào' : t;
}

/// Font size (in % of paper width) by text length, FE `fontScale`.
double _fontScale(int len) => len < 22 ? 11 : len < 60 ? 7.5 : len < 140 ? 5.2 : 4;

/// Paper footprint in mm. Aspect already includes orientation.
({double w, double h}) paperMm(String aspect) {
  final parts = aspect.split('/').map((s) => double.tryParse(s) ?? 0).toList();
  final ratio = parts.length == 2 && parts[0] > 0 && parts[1] > 0 ? parts[0] / parts[1] : 0.72;
  final w = ratio >= 1 ? 220.0 : 148.0;
  return (w: w, h: w / ratio);
}

SimViewport viewportFor(String aspect) {
  final mm = paperMm(aspect);
  final pw = mm.w * px;
  final ph = mm.h * px;
  return SimViewport(
    Rect.fromLTWH(_origin.dx - pw / 2, _origin.dy - ph / 2, pw, ph),
    Offset(_origin.dx - pw / 2 - 95 * px, _origin.dy),
  );
}

/// Caveat has no glyphs for ư, ơ and their tones, so script text falls back
/// to Dancing Script (full Vietnamese), then the UI font.
const scriptFallback = ['DancingScript', 'BeVietnamPro'];

/// Text style the robot writes with, at a given size.
TextStyle inkStyle(OrderSpec sp, double fontPx, {Color? color}) => TextStyle(
      fontFamily: sp.font,
      fontFamilyFallback: scriptFallback,
      fontSize: fontPx,
      fontWeight: FontWeight.w600,
      fontVariations: const [FontVariation('wght', 600)],
      color: color ?? Color(sp.inkColor),
      height: 1,
    );

/// Measures text width with a reusable painter.
class TextMeasurer {
  final TextPainter _tp = TextPainter(textDirection: TextDirection.ltr, maxLines: 1);

  double width(String text, TextStyle style) {
    if (text.isEmpty) return 0;
    _tp.text = TextSpan(text: text, style: style);
    _tp.layout();
    return _tp.width;
  }

  void dispose() => _tp.dispose();
}

/// Lays the text out inside the paper the way the order layout asks, in viewport pixels.
Plan buildPlan(TextMeasurer m, TechOrder o, SimViewport vp) {
  final sp = o.spec;
  final layout = o.layout;
  final text = planText(o);
  final w = vp.paper.width;
  final h = vp.paper.height;
  final padX = (layout == LayoutKind.letter ? 0.1 : layout.frame ? 0.14 : 0.1) * w;
  final padY = (layout == LayoutKind.letter ? 0.12 : layout.frame ? 0.14 : 0.1) * w;
  final inner = w - padX * 2;
  var fontPx = (_fontScale(text.length) / 100) * w * 0.82;

  List<String> wrap(double size) {
    final style = inkStyle(sp, size);
    final out = <String>[];
    for (final para in text.split('\n')) {
      var cur = '';
      for (final word in para.split(RegExp(r'\s+')).where((s) => s.isNotEmpty)) {
        final next = cur.isEmpty ? word : '$cur $word';
        if (cur.isNotEmpty && m.width(next, style) > inner) {
          out.add(cur);
          cur = word;
        } else {
          cur = next;
        }
      }
      out.add(cur);
    }
    return out;
  }

  var lines = wrap(fontPx);
  while (lines.length * fontPx * 1.25 > h - padY * 2 && fontPx > 10) {
    fontPx *= 0.92;
    lines = wrap(fontPx);
  }
  final style = inkStyle(sp, fontPx);
  final lineH = fontPx * 1.25;
  final total = lines.length * lineH;
  final top = layout.top ? vp.paper.top + padY : vp.paper.top + (h - total) / 2;
  var startChar = 0;
  final out = <PlanLine>[];
  for (var i = 0; i < lines.length; i++) {
    final t = lines[i];
    final lw = m.width(t, style);
    final x0 = layout.left ? vp.paper.left + padX : vp.paper.left + (w - lw) / 2;
    out.add(PlanLine(t, top + i * lineH + lineH / 2, x0, x0 + lw, startChar));
    startChar += t.length + 1;
  }
  return Plan(text, out, fontPx, lineH, math.max(1, startChar - 1));
}

class PenState {
  final double x, y;
  final bool down;
  final int line;
  final int char;

  /// Strokes completed so far (words, as pen lifts).
  final int words;
  const PenState(this.x, this.y, this.down, this.line, this.char, this.words);
}

PenState penAt(TextMeasurer m, Plan plan, TechOrder o, double p) {
  final target = math.min(plan.chars.toDouble(), math.max(0.0, p * plan.chars));
  var li = -1;
  for (var i = 0; i < plan.lines.length; i++) {
    final l = plan.lines[i];
    if (target <= l.startChar + l.text.length + (i < plan.lines.length - 1 ? 0 : 1)) {
      li = i;
      break;
    }
  }
  if (li < 0) li = plan.lines.length - 1;
  final line = plan.lines[li];
  final c = math.min(line.text.length.toDouble(), math.max(0.0, target - line.startChar));
  final style = inkStyle(o.spec, plan.fontPx);
  final before = m.width(line.text.substring(0, c.floor()), style);
  final next = m.width(line.text.substring(0, c.ceil()), style);
  final x = line.x0 + before + (next - before) * (c - c.floor());
  final idx = math.min(line.text.length - 1, c.floor());
  final ch = idx >= 0 && line.text.isNotEmpty ? line.text[idx] : ' ';
  final wob = math.sin(x * 0.17) * plan.lineH * 0.16 + math.sin(x * 0.05 + li) * plan.lineH * 0.08;
  final written = plan.text.substring(0, math.min(plan.text.length, target.floor()));
  return PenState(
    x,
    line.y + wob,
    ch != ' ' && p < 1 && p > 0,
    li,
    target.floor(),
    written.split(RegExp(r'\s+')).where((s) => s.isNotEmpty).length,
  );
}

class Arm {
  final Offset base, elbow, tip;

  /// Angles in degrees: shoulder yaw, elbow, then wrist terms (7 joints like the FR3 view).
  final List<double> q;
  final bool reachable;
  const Arm(this.base, this.elbow, this.tip, this.q, this.reachable);
}

/// Two-link planar IK with the elbow kept up, in viewport pixels.
Arm solveArm(SimViewport vp, Offset tip, double wobble) {
  const l1 = _l1 * px;
  const l2 = _l2 * px;
  final dx = tip.dx - vp.base.dx;
  final dy = tip.dy - vp.base.dy;
  final raw = math.sqrt(dx * dx + dy * dy);
  final d = math.min(l1 + l2 - 0.5, math.max((l1 - l2).abs() + 8, raw));
  final a = math.atan2(dy, dx);
  final sh = a - math.acos(((d * d + l1 * l1 - l2 * l2) / (2 * d * l1)).clamp(-1.0, 1.0));
  final elbow = Offset(vp.base.dx + l1 * math.cos(sh), vp.base.dy + l1 * math.sin(sh));
  final el = math.acos(((l1 * l1 + l2 * l2 - d * d) / (2 * l1 * l2)).clamp(-1.0, 1.0));
  double deg(double r) => r * 180 / math.pi;
  return Arm(
    vp.base,
    elbow,
    Offset(vp.base.dx + d * math.cos(a), vp.base.dy + d * math.sin(a)),
    [
      deg(a),
      deg(sh) + 60,
      -deg(sh) * 0.4,
      deg(math.pi - el) - 90,
      math.sin(wobble) * 3,
      90 - deg(a) * 0.3,
      math.cos(wobble * 0.7) * 2,
    ],
    raw <= l1 + l2,
  );
}

double mmOf(double pixels) => pixels / px;

/// Real seconds one piece takes at the tuned speed (arc length of the text over pen speed, plus lifts).
double pieceSeconds(Plan plan, Tuning t) {
  final inkPx = plan.lines.fold<double>(0, (a, l) => a + (l.x1 - l.x0)) * 3.1;
  final mm = inkPx / px;
  final lifts = plan.text.split(RegExp(r'\s+')).where((s) => s.isNotEmpty).length;
  return math.max(10, mm / t.speed + lifts * (0.6 + t.lift / 40) + 4 * plan.lines.length);
}

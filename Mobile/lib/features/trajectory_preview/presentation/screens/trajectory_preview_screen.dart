import 'dart:ui' show PathMetric;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/utils/formatters.dart';
import '../../../../core/widgets/widgets.dart';

/// Trajectory preview: replays the robot's pen path on paper — strokes,
/// pen lifts and timing — with a scrubbable timeline and the price estimate.
class TrajectoryPreviewScreen extends ConsumerStatefulWidget {
  final String projectId;

  const TrajectoryPreviewScreen({super.key, required this.projectId});

  @override
  ConsumerState<TrajectoryPreviewScreen> createState() =>
      _TrajectoryPreviewScreenState();
}

class _TrajectoryPreviewScreenState extends ConsumerState<TrajectoryPreviewScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _animationController;

  // Simulated trajectory data
  final double _estimatedPrice = 25000;
  final int _totalStrokes = 42;
  final double _totalLength = 3456.7;
  final Duration _estimatedWriteTime = const Duration(minutes: 5, seconds: 30);

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 8),
    )..addStatusListener((_) => setState(() {}));
    // Start the replay once the page transition has settled.
    Future.delayed(const Duration(milliseconds: 450), () {
      if (mounted && _animationController.value == 0) _togglePlayback();
    });
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  bool get _isPlaying => _animationController.isAnimating;

  void _togglePlayback() {
    if (_isPlaying) {
      _animationController.stop();
    } else {
      if (_animationController.isCompleted) _animationController.reset();
      _animationController.forward();
    }
    setState(() {});
  }

  String _clock(double fraction) {
    final seconds = (_estimatedWriteTime.inSeconds * fraction).round();
    return '${seconds ~/ 60}:${(seconds % 60).toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      body: SafeArea(
        child: Stack(
          children: [
            Column(
              children: [
                _TopBar(
                  onBack: () => context.pop(),
                  onClose: () => context.go('/projects'),
                ),
                Expanded(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.fromLTRB(24, 8, 24, 120),
                    child: Column(
                      children: [
                        const QuillPaperArt(size: 104),
                        const SizedBox(height: 24),
                        Text(
                          'preview robot trajectory.',
                          style: theme.textTheme.displaySmall,
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 10),
                        ConstrainedBox(
                          constraints: const BoxConstraints(maxWidth: 320),
                          child: Text(
                            'Every pen movement, lift and pause, simulated on paper before the robot arm touches ink.',
                            style: theme.textTheme.bodyMedium?.copyWith(
                              color: AppColors.textSecondary,
                            ),
                            textAlign: TextAlign.center,
                          ),
                        ),
                        const SizedBox(height: 28),

                        // Paper
                        AspectRatio(
                          aspectRatio: 1.45,
                          child: Container(
                            decoration: BoxDecoration(
                              color: AppColors.surface,
                              borderRadius: BorderRadius.circular(24),
                              boxShadow: const [
                                BoxShadow(
                                  color: AppColors.shadow,
                                  blurRadius: 24,
                                  offset: Offset(0, 8),
                                ),
                              ],
                            ),
                            child: ClipRRect(
                              borderRadius: BorderRadius.circular(24),
                              child: AnimatedBuilder(
                                animation: _animationController,
                                builder: (context, _) => CustomPaint(
                                  painter: _TrajectoryAnimationPainter(
                                    progress: _animationController.value,
                                  ),
                                  size: Size.infinite,
                                ),
                              ),
                            ),
                          ),
                        ),
                        const SizedBox(height: 28),

                        // Timeline
                        AnimatedBuilder(
                          animation: _animationController,
                          builder: (context, _) {
                            final v = _animationController.value;
                            return Column(
                              children: [
                                Row(
                                  children: [
                                    Text(
                                      'Stroke ${(v * _totalStrokes).ceil()} of $_totalStrokes',
                                      style: theme.textTheme.titleLarge?.copyWith(
                                        fontFeatures: const [FontFeature.tabularFigures()],
                                      ),
                                    ),
                                    const Spacer(),
                                    _PlayButton(
                                      playing: _isPlaying,
                                      onTap: _togglePlayback,
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 14),
                                InkSlider(
                                  value: v,
                                  semanticLabel: 'Playback position',
                                  onChangeStart: () {
                                    _animationController.stop();
                                    setState(() {});
                                  },
                                  onChanged: (next) => _animationController.value = next,
                                  startLabel: _clock(v),
                                  endLabel: _clock(1),
                                ),
                              ],
                            );
                          },
                        ),
                        const SizedBox(height: 28),

                        // Estimate
                        Container(
                          padding: const EdgeInsets.fromLTRB(20, 18, 20, 20),
                          decoration: BoxDecoration(
                            color: AppColors.surface,
                            borderRadius: BorderRadius.circular(24),
                          ),
                          child: Column(
                            children: [
                              _EstimateRow(
                                label: 'Path length',
                                value: '${_totalLength.toStringAsFixed(1)} mm',
                              ),
                              _EstimateRow(
                                label: 'Write time',
                                value: '${_estimatedWriteTime.inMinutes}m ${_estimatedWriteTime.inSeconds % 60}s',
                              ),
                              const Padding(
                                padding: EdgeInsets.symmetric(vertical: 12),
                                child: Divider(),
                              ),
                              Row(
                                crossAxisAlignment: CrossAxisAlignment.end,
                                children: [
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text('Estimated price', style: theme.textTheme.bodySmall),
                                        const SizedBox(height: 2),
                                        Text(
                                          Formatters.formatVND(_estimatedPrice),
                                          style: theme.textTheme.displaySmall?.copyWith(
                                            fontFeatures: const [FontFeature.tabularFigures()],
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                  Text(
                                    'Ready for VNPay',
                                    style: theme.textTheme.bodySmall?.copyWith(
                                      color: AppColors.success,
                                      fontWeight: FontWeight.w500,
                                    ),
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
            Positioned(
              right: 24,
              bottom: 20,
              child: InkCircleButton(
                semanticLabel: 'Continue to checkout',
                onPressed: () => context.push('/projects/${widget.projectId}/checkout'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TopBar extends StatelessWidget {
  final VoidCallback onBack;
  final VoidCallback onClose;

  const _TopBar({required this.onBack, required this.onClose});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 4, 8, 0),
      child: Row(
        children: [
          IconButton(
            onPressed: onBack,
            tooltip: 'Back',
            icon: const Icon(Icons.chevron_left_rounded, size: 28),
          ),
          const Expanded(child: Center(child: StepDashes(total: 4, current: 2))),
          IconButton(
            onPressed: onClose,
            tooltip: 'Close',
            icon: const Icon(Icons.close_rounded, size: 22),
          ),
        ],
      ),
    );
  }
}

class _PlayButton extends StatelessWidget {
  final bool playing;
  final VoidCallback onTap;

  const _PlayButton({required this.playing, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Pressable(
      onTap: onTap,
      semanticLabel: playing ? 'Pause' : 'Play',
      child: Container(
        padding: const EdgeInsets.fromLTRB(12, 7, 14, 7),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(999),
          border: Border.all(color: AppColors.border, width: 1.2),
          color: AppColors.surface,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(playing ? Icons.pause_rounded : Icons.play_arrow_rounded, size: 18),
            const SizedBox(width: 4),
            Text(
              playing ? 'Pause' : 'Play',
              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
            ),
          ],
        ),
      ),
    );
  }
}

class _EstimateRow extends StatelessWidget {
  final String label;
  final String value;

  const _EstimateRow({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(
        children: [
          Expanded(
            child: Text(
              label,
              style: const TextStyle(fontSize: 14, color: AppColors.textSecondary),
            ),
          ),
          Text(
            value,
            style: const TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w600,
              color: AppColors.textPrimary,
              fontFeatures: [FontFeature.tabularFigures()],
            ),
          ),
        ],
      ),
    );
  }
}

/// Replays a sample cursive trajectory. Pen-down strokes draw in ink; the
/// pen-up travel between them shows as a faint dotted line once reached.
class _TrajectoryAnimationPainter extends CustomPainter {
  final double progress;

  _TrajectoryAnimationPainter({required this.progress});

  /// Sample strokes in normalized coordinates: a looping word, a second word,
  /// and a Vietnamese diacritic hook above it.
  static List<Path> _strokes(Size s) {
    Offset p(double x, double y) => Offset(s.width * x, s.height * y);

    final word1 = Path()..moveTo(p(0.1, 0.6).dx, p(0.1, 0.6).dy);
    void curve(Path path, Offset a, Offset b, Offset c) =>
        path.cubicTo(a.dx, a.dy, b.dx, b.dy, c.dx, c.dy);
    curve(word1, p(0.14, 0.34), p(0.2, 0.34), p(0.2, 0.52));
    curve(word1, p(0.2, 0.7), p(0.14, 0.7), p(0.17, 0.56));
    curve(word1, p(0.22, 0.4), p(0.28, 0.48), p(0.28, 0.62));
    curve(word1, p(0.3, 0.44), p(0.36, 0.42), p(0.37, 0.6));
    curve(word1, p(0.4, 0.46), p(0.45, 0.44), p(0.46, 0.62));

    final word2 = Path()..moveTo(p(0.54, 0.46).dx, p(0.54, 0.46).dy);
    curve(word2, p(0.5, 0.4), p(0.5, 0.66), p(0.58, 0.62));
    curve(word2, p(0.62, 0.3), p(0.66, 0.28), p(0.64, 0.62));
    curve(word2, p(0.68, 0.44), p(0.74, 0.46), p(0.72, 0.62));
    curve(word2, p(0.76, 0.46), p(0.84, 0.42), p(0.82, 0.58));
    curve(word2, p(0.8, 0.7), p(0.9, 0.66), p(0.9, 0.56));

    final hook = Path()..moveTo(p(0.76, 0.3).dx, p(0.76, 0.3).dy);
    curve(hook, p(0.8, 0.22), p(0.84, 0.28), p(0.8, 0.34));

    return [word1, word2, hook];
  }

  @override
  void paint(Canvas canvas, Size size) {
    // Ruled guides.
    final guide = Paint()
      ..color = AppColors.divider
      ..strokeWidth = 1;
    for (final y in [0.38, 0.62, 0.86]) {
      canvas.drawLine(Offset(24, size.height * y), Offset(size.width - 24, size.height * y), guide);
    }

    final metrics = <PathMetric>[
      for (final path in _strokes(size)) path.computeMetrics().first,
    ];
    final total = metrics.fold<double>(0, (sum, m) => sum + m.length);
    var remaining = total * progress;

    final ink = Paint()
      ..color = AppColors.ink
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.4
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    final travel = Paint()..color = AppColors.textTertiary;

    Offset? tip;
    for (var i = 0; i < metrics.length; i++) {
      final m = metrics[i];
      if (remaining <= 0) break;

      final drawn = remaining.clamp(0.0, m.length);
      canvas.drawPath(m.extractPath(0, drawn), ink);
      remaining -= m.length;

      if (remaining < 0) {
        tip = m.getTangentForOffset(drawn)?.position;
      } else if (i + 1 < metrics.length) {
        // Pen lift: dotted travel to the next stroke's start.
        final from = m.getTangentForOffset(m.length)!.position;
        final to = metrics[i + 1].getTangentForOffset(0)!.position;
        const dots = 14;
        for (var d = 1; d < dots; d++) {
          canvas.drawCircle(Offset.lerp(from, to, d / dots)!, 1.1, travel);
        }
      }
    }

    if (tip != null) {
      canvas.drawCircle(tip, 7, Paint()..color = AppColors.ink.withValues(alpha: 0.08));
      canvas.drawCircle(tip, 3.5, Paint()..color = AppColors.ink);
    }
  }

  @override
  bool shouldRepaint(covariant _TrajectoryAnimationPainter oldDelegate) {
    return oldDelegate.progress != progress;
  }
}

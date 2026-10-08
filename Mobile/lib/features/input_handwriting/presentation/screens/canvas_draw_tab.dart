import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_constants.dart';
import '../../../../core/widgets/widgets.dart';
import '../widgets/handwriting_canvas_painter.dart';

/// Canvas drawing tab: interactive drawing area using CustomPainter.
/// Captures stroke coordinates, order, and timing for robot trajectory.
class CanvasDrawTab extends StatefulWidget {
  final String projectId;

  const CanvasDrawTab({super.key, required this.projectId});

  @override
  State<CanvasDrawTab> createState() => _CanvasDrawTabState();
}

class _CanvasDrawTabState extends State<CanvasDrawTab>
    with AutomaticKeepAliveClientMixin {
  final List<Stroke> _completedStrokes = [];
  List<StrokePoint> _currentPoints = [];
  Color _penColor = AppColors.textPrimary;
  double _strokeWidth = AppConstants.defaultStrokeWidth;
  int _strokeCounter = 0;
  bool _isSubmitting = false;

  @override
  bool get wantKeepAlive => true;

  void _onPanStart(DragStartDetails details) {
    setState(() {
      _currentPoints = [
        StrokePoint(
          position: details.localPosition,
          timestamp: DateTime.now(),
        ),
      ];
    });
  }

  void _onPanUpdate(DragUpdateDetails details) {
    setState(() {
      _currentPoints = [
        ..._currentPoints,
        StrokePoint(
          position: details.localPosition,
          timestamp: DateTime.now(),
        ),
      ];
    });
  }

  void _onPanEnd(DragEndDetails details) {
    if (_currentPoints.isEmpty) return;

    setState(() {
      _strokeCounter++;
      _completedStrokes.add(Stroke(
        points: List.from(_currentPoints),
        color: _penColor,
        strokeWidth: _strokeWidth,
        order: _strokeCounter,
      ));
      _currentPoints = [];
    });
  }

  void _undoLastStroke() {
    if (_completedStrokes.isEmpty) return;
    setState(() {
      _completedStrokes.removeLast();
      _strokeCounter = _completedStrokes.length;
    });
  }

  void _clearCanvas() {
    setState(() {
      _completedStrokes.clear();
      _currentPoints.clear();
      _strokeCounter = 0;
    });
  }

  List<Map<String, dynamic>> _exportStrokesJson() {
    return _completedStrokes.map((s) => s.toJson()).toList();
  }

  Future<void> _handleSubmit() async {
    if (_completedStrokes.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Please draw something on the canvas.'),
          backgroundColor: AppColors.warning,
        ),
      );
      return;
    }

    setState(() => _isSubmitting = true);

    final _ = _exportStrokesJson();
    // Simulate submitting stroke data to API
    await Future.delayed(const Duration(seconds: 2));

    setState(() => _isSubmitting = false);

    if (mounted) {
      context.push('/projects/${widget.projectId}/trajectory');
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final theme = Theme.of(context);

    return Column(
      children: [
        // Canvas Area
        Expanded(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Container(
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: AppColors.border, width: 1.5),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withOpacity(0.06),
                    blurRadius: 12,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(14),
                child: GestureDetector(
                  onPanStart: _onPanStart,
                  onPanUpdate: _onPanUpdate,
                  onPanEnd: _onPanEnd,
                  child: CustomPaint(
                    painter: HandwritingCanvasPainter(
                      completedStrokes: _completedStrokes,
                      currentStrokePoints: _currentPoints,
                      currentColor: _penColor,
                      currentStrokeWidth: _strokeWidth,
                    ),
                    size: Size.infinite,
                  ),
                ),
              ),
            ),
          ),
        ),

        // Controls Bar
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppColors.surface,
            border: Border(top: BorderSide(color: AppColors.border)),
          ),
          child: Column(
            children: [
              // Stroke Width Slider
              Row(
                children: [
                  const Icon(Icons.line_weight, size: 18, color: AppColors.textTertiary),
                  Expanded(
                    child: Slider(
                      value: _strokeWidth,
                      min: AppConstants.minStrokeWidth,
                      max: AppConstants.maxStrokeWidth,
                      activeColor: AppColors.primary,
                      inactiveColor: AppColors.border,
                      onChanged: (value) => setState(() => _strokeWidth = value),
                    ),
                  ),
                  Text(
                    _strokeWidth.toStringAsFixed(1),
                    style: theme.textTheme.labelMedium?.copyWith(
                      color: AppColors.textSecondary,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),

              // Color & Action Buttons
              Row(
                children: [
                  // Color Picker
                  ...[AppColors.ink, const Color(0xFF1F3A5F), AppColors.error, AppColors.textSecondary]
                      .map((color) => Padding(
                            padding: const EdgeInsets.only(right: 8),
                            child: GestureDetector(
                              onTap: () => setState(() => _penColor = color),
                              child: Container(
                                width: 32,
                                height: 32,
                                decoration: BoxDecoration(
                                  color: color,
                                  shape: BoxShape.circle,
                                  border: Border.all(
                                    color: _penColor == color
                                        ? AppColors.primary
                                        : AppColors.border,
                                    width: _penColor == color ? 3 : 1,
                                  ),
                                ),
                              ),
                            ),
                          )),
                  const Spacer(),
                  // Stroke count badge
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: AppColors.surfaceVariant,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      '${_completedStrokes.length} strokes',
                      style: theme.textTheme.labelSmall?.copyWith(
                        color: AppColors.textTertiary,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  // Undo
                  IconButton(
                    onPressed: _completedStrokes.isNotEmpty ? _undoLastStroke : null,
                    icon: const Icon(Icons.undo_rounded),
                    color: AppColors.textSecondary,
                    disabledColor: AppColors.textTertiary.withOpacity(0.3),
                    tooltip: 'Undo',
                  ),
                  // Clear
                  IconButton(
                    onPressed: _completedStrokes.isNotEmpty ? _clearCanvas : null,
                    icon: const Icon(Icons.delete_outline_rounded),
                    color: AppColors.error,
                    disabledColor: AppColors.textTertiary.withOpacity(0.3),
                    tooltip: 'Clear All',
                  ),
                ],
              ),
              const SizedBox(height: 12),

              // Submit Button
              CustomButton(
                label: 'Submit drawing',
                onPressed: _handleSubmit,
                isLoading: _isSubmitting,
                icon: Icons.send_rounded,
              ),
            ],
          ),
        ),
      ],
    );
  }
}

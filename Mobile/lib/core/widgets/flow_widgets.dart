import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../constants/app_colors.dart';

/// A thick pill slider: ink fill with a white knob riding inside it.
/// Drag or tap anywhere on the track to set the value (0–1).
class InkSlider extends StatelessWidget {
  final double value;
  final ValueChanged<double> onChanged;
  final VoidCallback? onChangeStart;
  final String? startLabel;
  final String? endLabel;
  final String semanticLabel;

  const InkSlider({
    super.key,
    required this.value,
    required this.onChanged,
    this.onChangeStart,
    this.startLabel,
    this.endLabel,
    this.semanticLabel = 'Slider',
  });

  static const double _height = 36;

  @override
  Widget build(BuildContext context) {
    final v = value.clamp(0.0, 1.0);

    return Semantics(
      label: semanticLabel,
      value: '${(v * 100).round()}%',
      slider: true,
      child: Column(
        children: [
          LayoutBuilder(
            builder: (context, constraints) {
              final width = constraints.maxWidth;
              // Fill never shrinks below the knob so the knob stays inside it.
              final fillWidth = _height + (width - _height) * v;

              void update(double dx) {
                final next = ((dx - _height / 2) / (width - _height)).clamp(0.0, 1.0);
                onChanged(next);
              }

              return GestureDetector(
                behavior: HitTestBehavior.opaque,
                onHorizontalDragStart: (d) {
                  onChangeStart?.call();
                  HapticFeedback.selectionClick();
                  update(d.localPosition.dx);
                },
                onHorizontalDragUpdate: (d) => update(d.localPosition.dx),
                onTapDown: (d) {
                  onChangeStart?.call();
                  update(d.localPosition.dx);
                },
                child: Container(
                  height: _height,
                  decoration: BoxDecoration(
                    color: AppColors.surface,
                    borderRadius: BorderRadius.circular(_height),
                    border: Border.all(color: AppColors.border),
                  ),
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: Container(
                      width: fillWidth,
                      height: _height,
                      alignment: Alignment.centerRight,
                      padding: const EdgeInsets.all(4),
                      decoration: BoxDecoration(
                        color: AppColors.ink,
                        borderRadius: BorderRadius.circular(_height),
                      ),
                      child: Container(
                        width: _height - 8,
                        height: _height - 8,
                        decoration: const BoxDecoration(
                          color: AppColors.onInk,
                          shape: BoxShape.circle,
                        ),
                      ),
                    ),
                  ),
                ),
              );
            },
          ),
          if (startLabel != null || endLabel != null) ...[
            const SizedBox(height: 8),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(startLabel ?? '', style: _labelStyle),
                Text(endLabel ?? '', style: _labelStyle),
              ],
            ),
          ],
        ],
      ),
    );
  }

  static const _labelStyle = TextStyle(
    fontSize: 12,
    color: AppColors.textSecondary,
    fontFeatures: [FontFeature.tabularFigures()],
  );
}

/// Thin dashes showing progress through a multi-step flow.
class StepDashes extends StatelessWidget {
  final int total;
  final int current; // zero-based index of the active step

  const StepDashes({super.key, required this.total, required this.current});

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'Step ${current + 1} of $total',
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: List.generate(total, (i) {
          return AnimatedContainer(
            duration: const Duration(milliseconds: 250),
            margin: const EdgeInsets.symmetric(horizontal: 2),
            width: 18,
            height: 2,
            decoration: BoxDecoration(
              color: i <= current ? AppColors.ink : AppColors.border,
              borderRadius: BorderRadius.circular(2),
            ),
          );
        }),
      ),
    );
  }
}

/// A 56px ink circle with a single icon — the "next" affordance.
class InkCircleButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback? onPressed;
  final String semanticLabel;

  const InkCircleButton({
    super.key,
    this.icon = Icons.chevron_right_rounded,
    required this.onPressed,
    required this.semanticLabel,
  });

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: semanticLabel,
      child: GestureDetector(
        onTap: onPressed,
        child: TweenAnimationBuilder<double>(
          tween: Tween(begin: 0.85, end: 1),
          duration: const Duration(milliseconds: 380),
          curve: Curves.easeOutBack,
          builder: (context, scale, child) => Transform.scale(scale: scale, child: child),
          child: Container(
            width: 56,
            height: 56,
            decoration: const BoxDecoration(
              color: AppColors.ink,
              shape: BoxShape.circle,
              boxShadow: [
                BoxShadow(color: Color(0x1F121212), blurRadius: 16, offset: Offset(0, 6)),
              ],
            ),
            child: Icon(icon, color: AppColors.onInk, size: 28),
          ),
        ),
      ),
    );
  }
}

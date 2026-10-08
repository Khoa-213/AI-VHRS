import 'package:flutter/material.dart';
import '../constants/app_colors.dart';
import 'pressable.dart';

/// Pill button in five styles: ink (primary), charcoal (secondary),
/// hairline outline, bare text, and inverted (white on ink cards).
/// Handles loading state with a spinner and prevents double-taps during loading.
enum CustomButtonStyle { primary, secondary, outline, text, inverted }

class CustomButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final CustomButtonStyle style;
  final bool isLoading;
  final bool isExpanded;
  final IconData? icon;
  final double? height;
  final double? fontSize;
  final EdgeInsetsGeometry? padding;
  final BorderRadius? borderRadius;

  const CustomButton({
    super.key,
    required this.label,
    this.onPressed,
    this.style = CustomButtonStyle.primary,
    this.isLoading = false,
    this.isExpanded = true,
    this.icon,
    this.height,
    this.fontSize,
    this.padding,
    this.borderRadius,
  });

  ({Color background, Color foreground, Color? border}) _colors() {
    switch (style) {
      case CustomButtonStyle.primary:
        return (background: AppColors.ink, foreground: AppColors.onInk, border: null);
      case CustomButtonStyle.secondary:
        return (background: AppColors.secondary, foreground: AppColors.onInk, border: null);
      case CustomButtonStyle.outline:
        return (background: AppColors.surface, foreground: AppColors.textPrimary, border: AppColors.border);
      case CustomButtonStyle.text:
        return (background: Colors.transparent, foreground: AppColors.textPrimary, border: null);
      case CustomButtonStyle.inverted:
        return (background: AppColors.onInk, foreground: AppColors.ink, border: null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = _colors();
    final effectiveOnPressed = isLoading ? null : onPressed;
    final radius = borderRadius ?? BorderRadius.circular(999);

    final content = Row(
      mainAxisSize: isExpanded ? MainAxisSize.max : MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        if (isLoading) ...[
          SizedBox(
            width: 18,
            height: 18,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              valueColor: AlwaysStoppedAnimation<Color>(colors.foreground),
            ),
          ),
          const SizedBox(width: 12),
        ],
        Text(
          isLoading ? 'Please wait' : label,
          style: TextStyle(
            fontSize: fontSize ?? 15,
            fontWeight: FontWeight.w600,
            letterSpacing: -0.1,
            color: colors.foreground,
          ),
        ),
        if (!isLoading && icon != null) ...[
          const SizedBox(width: 8),
          Icon(icon, size: 18, color: colors.foreground),
        ],
      ],
    );

    return Pressable(
      onTap: effectiveOnPressed,
      semanticLabel: label,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        width: isExpanded ? double.infinity : null,
        height: height ?? 54,
        padding: padding ?? const EdgeInsets.symmetric(horizontal: 28),
        decoration: BoxDecoration(
          color: colors.background,
          borderRadius: radius,
          border: colors.border != null
              ? Border.all(color: colors.border!, width: 1.2)
              : null,
        ),
        child: content,
      ),
    );
  }
}
